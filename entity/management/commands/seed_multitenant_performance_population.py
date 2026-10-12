from __future__ import annotations

import json
import os
import random
import hashlib
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from Authentication.models import User
from entity.management.commands.seed_performance_fixtures import Command as FixtureSeedCommand
from entity.management.commands.seed_performance_fixtures import TenantTarget
from entity.models import (
    Entity,
    EntityFinancialYear,
    EntityGstRegistration,
    PerformanceFixtureCheckpoint,
    PerformanceFixtureRun,
    SubEntity,
)
from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement
from purchase.models.purchase_core import PurchaseInvoiceHeader
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from sales.models import CustomerBillOpenItem, CustomerSettlement, SalesInvoiceHeader
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService


ZERO = Decimal("0.00")
PROTECTED_ENTITY_IDS = {5, 6, 7, 8, 9, 10, 11, 12}


@dataclass(frozen=True)
class PopulationTenant:
    code: str
    label: str
    size: str
    sales: int
    purchase: int
    payment_ratio: Decimal
    users: int


class Command(FixtureSeedCommand):
    help = (
        "Seed deterministic namespace-scoped multi-tenant performance populations. "
        "Dry-run is the default; writes require --execute after the strict safety audit passes."
    )

    ROLE_CODE = "perf_population_read_report"
    PASSWORD_ENV = "FINACC_PERF_AUTH_PASSWORD"
    GENERATOR_VERSION = "phase2c2c2-v1"

    def add_arguments(self, parser):
        parser.add_argument("--namespace", required=True, help="Explicit fixture namespace, e.g. P2C2B-PILOT5.")
        parser.add_argument(
            "--profile",
            choices=["local3", "pilot5", "pilot10", "dry100", "p100"],
            default="pilot5",
            help="Bounded local pilot profile. dry100 is planning-only. p100 requires explicit review flags.",
        )
        parser.add_argument("--seed", type=int, default=20261011)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--execute", action="store_true", help="Required for writes. Omit for dry-run.")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--allow-db-name", action="append", default=[])
        parser.add_argument("--allow-db-host", action="append", default=[])
        parser.add_argument("--provision-auth", action="store_true", help="Provision scoped read/report users after tenant seed.")
        parser.add_argument("--password-env", default=self.PASSWORD_ENV)
        parser.add_argument("--email-domain", default="local.invalid")
        parser.add_argument("--cleanup", action="store_true", help="Preview or execute namespace cleanup.")
        parser.add_argument("--confirm-cleanup-namespace", default="")
        parser.add_argument(
            "--allow-execution-namespace",
            action="append",
            default=[],
            help="Namespace allowlist required for writes. Repeatable.",
        )
        parser.add_argument(
            "--confirm-execute-namespace",
            default="",
            help="Must exactly match --namespace for writes.",
        )
        parser.add_argument(
            "--max-tenants",
            type=int,
            default=10,
            help="Execution guard. p100 requires --max-tenants 100 or higher.",
        )
        parser.add_argument(
            "--tenant-start-sequence",
            type=int,
            default=1,
            help="1-based tenant sequence to start from. Used for bounded execution windows.",
        )
        parser.add_argument(
            "--tenant-limit",
            type=int,
            default=0,
            help="Maximum tenants to process in this invocation. 0 means all remaining tenants.",
        )

    def handle(self, *args, **options):
        started = time.perf_counter()
        namespace = self._normalize_namespace(options["namespace"])
        self._assert_population_safety(options)
        source_system = self._source_system(namespace)
        tenants = self._population_tenants(namespace, options["profile"])
        selected_tenants = self._selected_tenant_window(
            tenants,
            start_sequence=int(options["tenant_start_sequence"]),
            limit=int(options["tenant_limit"]),
        )
        before = self._database_snapshot()
        protected_before = self._protected_snapshot()
        if options["profile"] == "dry100" and options["execute"]:
            raise CommandError("The dry100 profile is planning-only and cannot be executed by this command.")
        if options["execute"]:
            self._assert_execution_authorized(namespace=namespace, tenants=tenants, options=options)

        if options["cleanup"]:
            cleanup = self._cleanup_namespace(
                namespace=namespace,
                source_system=source_system,
                execute=bool(options["execute"]),
                confirm_namespace=options["confirm_cleanup_namespace"],
            )
            payload = {
                "mode": "cleanup",
                "dry_run": not options["execute"],
                "namespace": namespace,
                "profile": options["profile"],
                "database_before": before,
                "cleanup": cleanup,
                "protected_snapshot_unchanged": protected_before == self._protected_snapshot(),
            }
            self._write(payload, options)
            return

        dry_run = not bool(options["execute"])
        if dry_run:
            payload = {
                "mode": "seed",
                "dry_run": True,
                "namespace": namespace,
                "source_system": source_system,
                "profile": options["profile"],
                "targets": [asdict(tenant) for tenant in tenants],
                "selected_window": self._selected_window_payload(selected_tenants),
                "estimated_records": self._estimate_records(tenants),
                "selected_estimated_records": self._estimate_records([tenant for _, tenant in selected_tenants]),
                "database": before,
                "protected_snapshot": protected_before,
                "message": "Safety audit passed. No rows were written because --execute was not supplied.",
            }
            self._write(payload, options)
            return

        fingerprint = self._config_fingerprint(namespace, options["profile"], int(options["seed"]), tenants)
        run = self._prepare_run(
            namespace=namespace,
            profile=options["profile"],
            source_system=source_system,
            fingerprint=fingerprint,
            tenants=tenants,
            database_snapshot=before,
        )
        rng = random.Random(int(options["seed"]))
        results = []
        try:
            for sequence, tenant_target in selected_tenants:
                tenant_started = time.perf_counter()
                checkpoint = self._checkpoint_for(run, tenant_target, sequence)
                if checkpoint.status == PerformanceFixtureCheckpoint.Status.COMPLETED:
                    validation = checkpoint.reconciliation
                    auth = None
                    if options["provision_auth"] and checkpoint.entity_id:
                        auth = self._provision_auth(
                            entity=checkpoint.entity,
                            namespace=namespace,
                            tenant=tenant_target,
                            password_env=options["password_env"],
                            email_domain=options["email_domain"],
                        )
                    results.append(
                        {
                            "tenant": tenant_target.code,
                            "entity_id": checkpoint.entity_id,
                            "sales_inserted": 0,
                            "purchase_inserted": 0,
                            "sales_batches": [],
                            "purchase_batches": [],
                            "size": tenant_target.size,
                            "source_system": source_system,
                            "validation": validation,
                            "auth": auth,
                            "checkpoint_reused": True,
                            "elapsed_seconds": round(time.perf_counter() - tenant_started, 3),
                        }
                    )
                    continue
                self._mark_checkpoint_running(checkpoint)
                try:
                    with transaction.atomic():
                        tenant = self._ensure_tenant(
                            TenantTarget(
                                code=tenant_target.code,
                                label=tenant_target.label,
                                sales=tenant_target.sales,
                                purchase=tenant_target.purchase,
                            )
                        )
                        tenant["source_system"] = source_system
                        result = self._seed_tenant(
                            tenant=tenant,
                            target=TenantTarget(
                                code=tenant_target.code,
                                label=tenant_target.label,
                                sales=tenant_target.sales,
                                purchase=tenant_target.purchase,
                            ),
                            batch_size=int(options["batch_size"]),
                            rng=rng,
                            payment_ratio=tenant_target.payment_ratio,
                        )
                        validation = self._validate_tenant(tenant)
                        if not validation["balanced"] or validation["duplicate_sales_doc_numbers"] or validation["duplicate_purchase_doc_numbers"]:
                            raise CommandError(f"Financial validation failed for {tenant_target.code}: {validation}")
                        reconciliation_hash = self._reconciliation_hash(validation)
                        checkpoint.entity = tenant["entity"]
                        checkpoint.committed_sales = int(validation["sales_count"])
                        checkpoint.committed_purchase = int(validation["purchase_count"])
                        checkpoint.reconciliation = validation
                        checkpoint.reconciliation_hash = reconciliation_hash
                        checkpoint.status = PerformanceFixtureCheckpoint.Status.COMPLETED
                        checkpoint.completed_at = timezone.now()
                        checkpoint.last_error = ""
                        checkpoint.save(
                            update_fields=[
                                "entity",
                                "committed_sales",
                                "committed_purchase",
                                "reconciliation",
                                "reconciliation_hash",
                                "status",
                                "completed_at",
                                "last_error",
                                "updated_at",
                            ]
                        )
                    auth = None
                    if options["provision_auth"]:
                        auth = self._provision_auth(
                            entity=tenant["entity"],
                            namespace=namespace,
                            tenant=tenant_target,
                            password_env=options["password_env"],
                            email_domain=options["email_domain"],
                        )
                    results.append(
                        {
                            **result,
                            "size": tenant_target.size,
                            "source_system": source_system,
                            "validation": validation,
                            "auth": auth,
                            "checkpoint_id": checkpoint.id,
                            "checkpoint_reconciliation_hash": checkpoint.reconciliation_hash,
                            "elapsed_seconds": round(time.perf_counter() - tenant_started, 3),
                        }
                    )
                except Exception as exc:
                    self._mark_checkpoint_failed(checkpoint, exc)
                    raise
        except Exception as exc:
            run.status = PerformanceFixtureRun.Status.FAILED
            run.last_error = str(exc)
            run.save(update_fields=["status", "last_error", "updated_at"])
            raise

        after = self._database_snapshot()
        protected_after = self._protected_snapshot()
        completed_count = run.checkpoints.filter(status=PerformanceFixtureCheckpoint.Status.COMPLETED).count()
        if completed_count >= len(tenants):
            run.status = PerformanceFixtureRun.Status.COMPLETED
            run.completed_at = timezone.now()
        else:
            run.status = PerformanceFixtureRun.Status.RUNNING
        run.last_error = ""
        run.save(update_fields=["status", "completed_at", "last_error", "updated_at"])
        payload = {
            "mode": "seed",
            "dry_run": False,
            "namespace": namespace,
            "source_system": source_system,
            "profile": options["profile"],
            "selected_window": self._selected_window_payload(selected_tenants),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "database_before": before,
            "database_after": after,
            "protected_snapshot_unchanged": protected_before == protected_after,
            "protected_snapshot_before": protected_before,
            "protected_snapshot_after": protected_after,
            "targets": [asdict(tenant) for tenant in tenants],
            "results": results,
            "aggregate_validation": self._validate_namespace(namespace, source_system),
            "fixture_run": self._run_payload(run),
            "completed_checkpoints": completed_count,
            "remaining_checkpoints": max(len(tenants) - completed_count, 0),
            "runtime_snapshot": self._runtime_snapshot(),
        }
        self._write(payload, options)

    def _assert_population_safety(self, options):
        out = StringIO()
        args = ["--json", "--strict"]
        for name in options["allow_db_name"]:
            args.extend(["--allow-db-name", name])
        for host in options["allow_db_host"]:
            args.extend(["--allow-db-host", host])
        try:
            call_command("audit_performance_staging", *args, stdout=out)
        except CommandError as exc:
            raise CommandError(f"Population fixture seeding blocked by safety audit: {exc}") from exc
        payload = json.loads(out.getvalue())
        if not payload.get("ready"):
            raise CommandError("Population fixture seeding blocked because staging audit is not ready.")

    @staticmethod
    def _normalize_namespace(namespace: str) -> str:
        value = (namespace or "").strip().upper()
        if not (value.startswith("P2C2B-") or value.startswith("P2C2C-")):
            raise CommandError("Namespace must start with P2C2B- or P2C2C- so cleanup cannot target certified fixtures.")
        if len(value) > 48:
            raise CommandError("Namespace is too long; keep it at 48 characters or fewer.")
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        if any(ch not in allowed for ch in value):
            raise CommandError("Namespace may contain only letters, numbers, hyphen, and underscore.")
        return value

    @staticmethod
    def _source_system(namespace: str) -> str:
        value = f"phase2c2b:{namespace.lower()}"
        if len(value) > 100:
            raise CommandError("Derived legacy source system exceeds 100 characters.")
        return value

    def _population_tenants(self, namespace: str, profile: str) -> list[PopulationTenant]:
        plans = {
            "local3": [("micro", 20, 10, "0.10", 3), ("small", 200, 100, "0.20", 6), ("medium", 1000, 500, "0.25", 10)],
            "pilot5": [
                ("micro", 20, 10, "0.10", 3),
                ("micro", 30, 15, "0.15", 3),
                ("small", 200, 100, "0.20", 6),
                ("small", 300, 150, "0.25", 6),
                ("medium", 1000, 500, "0.25", 10),
            ],
            "pilot10": [
                ("micro", 20, 10, "0.10", 3),
                ("micro", 25, 12, "0.15", 3),
                ("micro", 30, 15, "0.15", 3),
                ("micro", 40, 20, "0.20", 3),
                ("small", 200, 100, "0.20", 6),
                ("small", 250, 125, "0.20", 6),
                ("small", 300, 150, "0.25", 6),
                ("medium", 750, 375, "0.25", 10),
                ("medium", 1000, 500, "0.25", 10),
                ("large-capped", 1500, 750, "0.30", 12),
            ],
        }
        if profile in {"dry100", "p100"}:
            plans[profile] = (
                [("micro", 120, 60, "0.10", 3)] * 50
                + [("small", 1000, 500, "0.20", 6)] * 35
                + [("medium", 5000, 2500, "0.25", 10)] * 12
                + [("large", 10000, 5000, "0.30", 20)] * 3
            )
        tenants = []
        for index, (size, sales, purchase, ratio, users) in enumerate(plans[profile], start=1):
            code = f"{namespace}-{size.upper().replace('-', '')}-{index:03d}"
            label = f"{namespace} {size.title()} Tenant {index:03d}"
            tenants.append(
                PopulationTenant(
                    code=code,
                    label=label,
                    size=size,
                    sales=sales,
                    purchase=purchase,
                    payment_ratio=Decimal(ratio),
                    users=users,
                )
            )
        return tenants

    def _assert_execution_authorized(self, *, namespace: str, tenants: list[PopulationTenant], options):
        allowed = {item.strip().upper() for item in options["allow_execution_namespace"] if item.strip()}
        if namespace not in allowed:
            raise CommandError("--allow-execution-namespace must include the exact namespace for writes.")
        if options["confirm_execute_namespace"] != namespace:
            raise CommandError("--confirm-execute-namespace must exactly match --namespace for writes.")
        if len(tenants) > int(options["max_tenants"]):
            raise CommandError(f"Execution target has {len(tenants)} tenants but --max-tenants is {options['max_tenants']}.")

    @staticmethod
    def _selected_tenant_window(tenants: list[PopulationTenant], *, start_sequence: int, limit: int) -> list[tuple[int, PopulationTenant]]:
        if start_sequence < 1:
            raise CommandError("--tenant-start-sequence must be 1 or greater.")
        if start_sequence > len(tenants):
            raise CommandError("--tenant-start-sequence is greater than the profile tenant count.")
        if limit < 0:
            raise CommandError("--tenant-limit must be 0 or greater.")
        indexed = list(enumerate(tenants, start=1))
        selected = [(sequence, tenant) for sequence, tenant in indexed if sequence >= start_sequence]
        if limit:
            selected = selected[:limit]
        if not selected:
            raise CommandError("Selected tenant execution window is empty.")
        return selected

    @staticmethod
    def _selected_window_payload(selected_tenants: list[tuple[int, PopulationTenant]]) -> dict:
        sequences = [sequence for sequence, _tenant in selected_tenants]
        return {
            "start_sequence": sequences[0],
            "end_sequence": sequences[-1],
            "tenant_count": len(sequences),
            "tenant_codes": [tenant.code for _sequence, tenant in selected_tenants],
        }

    def _config_fingerprint(self, namespace: str, profile: str, seed: int, tenants: list[PopulationTenant]) -> str:
        payload = {
            "namespace": namespace,
            "profile": profile,
            "seed": seed,
            "generator_version": self.GENERATOR_VERSION,
            "tenants": [asdict(tenant) for tenant in tenants],
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _prepare_run(self, *, namespace: str, profile: str, source_system: str, fingerprint: str, tenants: list[PopulationTenant], database_snapshot: dict) -> PerformanceFixtureRun:
        targets = self._estimate_records(tenants)
        db_host = str(settings.DATABASES["default"].get("HOST") or "")
        with transaction.atomic():
            run, created = PerformanceFixtureRun.objects.select_for_update().get_or_create(
                namespace=namespace,
                defaults={
                    "profile": profile,
                    "source_system": source_system,
                    "generator_version": self.GENERATOR_VERSION,
                    "config_fingerprint": fingerprint,
                    "database_name": database_snapshot["database"],
                    "database_host": db_host,
                    "target_tenants": targets["tenants"],
                    "target_sales": targets["sales_invoices"],
                    "target_purchase": targets["purchase_invoices"],
                    "target_invoices": targets["total_invoices"],
                    "status": PerformanceFixtureRun.Status.PLANNED,
                    "metadata": {"targets": targets},
                },
            )
            if not created:
                mismatches = []
                for field, expected in {
                    "profile": profile,
                    "source_system": source_system,
                    "generator_version": self.GENERATOR_VERSION,
                    "config_fingerprint": fingerprint,
                    "database_name": database_snapshot["database"],
                    "database_host": db_host,
                }.items():
                    if getattr(run, field) != expected:
                        mismatches.append(field)
                if mismatches:
                    raise CommandError(f"Refusing resume for {namespace}; run metadata mismatch: {', '.join(mismatches)}")
            if run.status == PerformanceFixtureRun.Status.COMPLETED:
                return run
            run.status = PerformanceFixtureRun.Status.RUNNING
            if run.started_at is None:
                run.started_at = timezone.now()
            run.last_error = ""
            run.save(update_fields=["status", "started_at", "last_error", "updated_at"])
        return run

    def _checkpoint_for(self, run: PerformanceFixtureRun, tenant: PopulationTenant, sequence: int) -> PerformanceFixtureCheckpoint:
        checkpoint, created = PerformanceFixtureCheckpoint.objects.get_or_create(
            run=run,
            tenant_code=tenant.code,
            defaults={
                "tenant_label": tenant.label,
                "tenant_size": tenant.size,
                "sequence": sequence,
                "target_sales": tenant.sales,
                "target_purchase": tenant.purchase,
            },
        )
        if not created:
            mismatches = []
            for field, expected in {
                "tenant_label": tenant.label,
                "tenant_size": tenant.size,
                "sequence": sequence,
                "target_sales": tenant.sales,
                "target_purchase": tenant.purchase,
            }.items():
                if getattr(checkpoint, field) != expected:
                    mismatches.append(field)
            if mismatches:
                raise CommandError(f"Refusing resume for {tenant.code}; checkpoint mismatch: {', '.join(mismatches)}")
        return checkpoint

    def _mark_checkpoint_running(self, checkpoint: PerformanceFixtureCheckpoint):
        checkpoint.status = PerformanceFixtureCheckpoint.Status.RUNNING
        checkpoint.started_at = checkpoint.started_at or timezone.now()
        checkpoint.last_error = ""
        checkpoint.save(update_fields=["status", "started_at", "last_error", "updated_at"])

    def _mark_checkpoint_failed(self, checkpoint: PerformanceFixtureCheckpoint, exc: Exception):
        checkpoint.status = PerformanceFixtureCheckpoint.Status.FAILED
        checkpoint.last_error = str(exc)
        checkpoint.save(update_fields=["status", "last_error", "updated_at"])

    @staticmethod
    def _reconciliation_hash(validation: dict) -> str:
        return hashlib.sha256(json.dumps(validation, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _run_payload(self, run: PerformanceFixtureRun) -> dict:
        return {
            "id": run.id,
            "namespace": run.namespace,
            "profile": run.profile,
            "status": run.status,
            "generator_version": run.generator_version,
            "config_fingerprint": run.config_fingerprint,
            "target_tenants": run.target_tenants,
            "target_sales": run.target_sales,
            "target_purchase": run.target_purchase,
            "target_invoices": run.target_invoices,
            "completed_checkpoints": run.checkpoints.filter(status=PerformanceFixtureCheckpoint.Status.COMPLETED).count(),
            "failed_checkpoints": run.checkpoints.filter(status=PerformanceFixtureCheckpoint.Status.FAILED).count(),
        }

    def _gstin_for_target(self, target: TenantTarget) -> str:
        existing_entity = Entity.objects.filter(entityname=target.label).order_by("id").first()
        if existing_entity:
            existing_registration = (
                EntityGstRegistration.objects.filter(entity=existing_entity, isactive=True)
                .order_by("id")
                .first()
            )
            if existing_registration:
                return existing_registration.gstin

        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(target.code))
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        letter = letters[seed % len(letters)]
        check = letters[(seed // len(letters)) % len(letters)]
        for offset in range(10000):
            number = (seed + offset) % 10000
            pan = f"PF{letter}CB{number:04d}{check}"
            gstin = f"27{pan}1Z5"
            if not EntityGstRegistration.objects.filter(gstin=gstin, isactive=True).exists():
                return gstin
        raise CommandError(f"Could not allocate a unique local GSTIN for {target.code}.")

    @staticmethod
    def _estimate_records(tenants: list[PopulationTenant]) -> dict:
        sales = sum(tenant.sales for tenant in tenants)
        purchase = sum(tenant.purchase for tenant in tenants)
        invoices = sales + purchase
        return {
            "tenants": len(tenants),
            "sales_invoices": sales,
            "purchase_invoices": purchase,
            "total_invoices": invoices,
            "minimum_invoice_lines": invoices,
            "minimum_tax_summaries": invoices,
            "minimum_open_items": invoices,
            "minimum_journal_lines": sales * 3 + purchase * 3,
        }

    def _provision_auth(self, *, entity: Entity, namespace: str, tenant: PopulationTenant, password_env: str, email_domain: str) -> dict:
        password = os.environ.get(password_env)
        if not password:
            raise CommandError(f"Missing {password_env}; password values must come from environment variables only.")
        domain = (email_domain or "local.invalid").strip().lower()
        if domain in {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com"}:
            raise CommandError("Refusing to create performance users on a public email domain.")
        permissions = list(self._read_report_permissions().values_list("id", flat=True))
        if not permissions:
            raise CommandError("No active read/report permissions were found.")

        email = f"perf-{namespace.lower()}-{tenant.size.replace('-', '')}-{tenant.code[-3:]}@{domain}"
        username = email.split("@", 1)[0]
        with transaction.atomic():
            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": username,
                    "first_name": "Performance",
                    "last_name": "Population",
                    "is_active": True,
                    "email_verified": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.username = username
            user.is_active = True
            user.email_verified = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(password)
            if hasattr(user, "last_password_changed_at"):
                user.last_password_changed_at = timezone.now()
            user.save()

            account = SubscriptionService.ensure_customer_account(user=user, intent=SubscriptionService.INTENT_TRIAL)
            if account.status != account.Status.ACTIVE:
                account.status = account.Status.ACTIVE
                account.save(update_fields=["status", "updated_at"])
            membership = SubscriptionService.ensure_account_membership(
                customer_account=account,
                user=user,
                role=UserEntityAccess.Role.VIEWER,
                granted_by=user,
            )
            SubscriptionService.ensure_active_subscription(customer_account=account)
            if entity.customer_account_id is None:
                entity.customer_account = account
                entity.save(update_fields=["customer_account", "updated_at"])
            elif entity.customer_account_id != account.id:
                raise CommandError(f"Fixture entity {entity.id} already belongs to a different customer account.")

            role, _ = Role.objects.get_or_create(
                entity=entity,
                code=self.ROLE_CODE,
                defaults={
                    "name": "Performance Population Read and Report",
                    "description": "Local-only read/report permissions for Phase 2C population pilot.",
                    "role_level": Role.LEVEL_ENTITY,
                    "is_system_role": False,
                    "is_assignable": False,
                    "priority": 910,
                    "createdby": user,
                    "metadata": {"performance_namespace": namespace},
                },
            )
            existing = set(RolePermission.objects.filter(role=role, isactive=True).values_list("permission_id", flat=True))
            RolePermission.objects.bulk_create(
                [
                    RolePermission(
                        role=role,
                        permission_id=permission_id,
                        effect=RolePermission.EFFECT_ALLOW,
                        metadata={"performance_namespace": namespace},
                    )
                    for permission_id in permissions
                    if permission_id not in existing
                ],
                ignore_conflicts=True,
            )
            assignment, assignment_created = UserRoleAssignment.objects.get_or_create(
                user=user,
                entity=entity,
                role=role,
                subentity=None,
                defaults={
                    "assigned_by": user,
                    "effective_from": timezone.now(),
                    "is_primary": True,
                    "scope_data": {"performance_namespace": namespace},
                },
            )
            if not assignment.isactive or not assignment.is_primary:
                assignment.isactive = True
                assignment.is_primary = True
                assignment.save(update_fields=["isactive", "is_primary", "updated_at"])
        return {
            "email": email,
            "user_created": user_created,
            "user_id": user.id,
            "customer_account_id": account.id,
            "membership_id": membership.id,
            "role_id": role.id,
            "assignment_id": assignment.id,
            "assignment_created": assignment_created,
            "permission_count": len(permissions),
            "password_source": password_env,
            "password_logged": False,
        }

    def _read_report_permissions(self):
        read_actions = {"access", "export", "list", "read", "view"}
        denied_tokens = (
            "approve",
            "cancel",
            "confirm",
            "create",
            "delete",
            "edit",
            "file",
            "import",
            "manage",
            "offset",
            "post",
            "reconcile",
            "reverse",
            "save",
            "submit",
            "update",
            "upload",
        )
        queryset = Permission.objects.filter(isactive=True, action__in=read_actions)
        for token in denied_tokens:
            queryset = queryset.exclude(Q(code__icontains=token) | Q(action__icontains=token))
        return queryset.order_by("code")

    def _validate_namespace(self, namespace: str, source_system: str) -> dict:
        entities = Entity.objects.filter(entityname__startswith=f"{namespace} ", isactive=True).order_by("id")
        rows = []
        aggregate_debit = ZERO
        aggregate_credit = ZERO
        for entity in entities:
            sales = SalesInvoiceHeader.objects.filter(entity=entity, legacy_source_system=source_system)
            purchase = PurchaseInvoiceHeader.objects.filter(entity=entity, legacy_source_system=source_system)
            validation = self._validate_tenant({"entity": entity, "source_system": source_system})
            aggregate_debit += Decimal(validation["journal_debit"])
            aggregate_credit += Decimal(validation["journal_credit"])
            rows.append(
                {
                    "entity_id": entity.id,
                    "entity_name": entity.entityname,
                    "sales_count": sales.count(),
                    "purchase_count": purchase.count(),
                    "ar_open_total": validation["ar_open_total"],
                    "ap_open_total": validation["ap_open_total"],
                    "journal_debit": validation["journal_debit"],
                    "journal_credit": validation["journal_credit"],
                    "balanced": validation["balanced"],
                    "duplicate_sales_doc_numbers": validation["duplicate_sales_doc_numbers"],
                    "duplicate_purchase_doc_numbers": validation["duplicate_purchase_doc_numbers"],
                }
            )
        return {
            "namespace": namespace,
            "source_system": source_system,
            "tenant_count": len(rows),
            "sales_count": sum(row["sales_count"] for row in rows),
            "purchase_count": sum(row["purchase_count"] for row in rows),
            "journal_debit": str(aggregate_debit),
            "journal_credit": str(aggregate_credit),
            "balanced": aggregate_debit == aggregate_credit,
            "tenants": rows,
        }

    def _cleanup_namespace(self, *, namespace: str, source_system: str, execute: bool, confirm_namespace: str) -> dict:
        if execute and confirm_namespace != namespace:
            raise CommandError("--confirm-cleanup-namespace must exactly match --namespace for cleanup execution.")
        entities = Entity.objects.filter(entityname__startswith=f"{namespace} ").order_by("id")
        entity_ids = set(entities.values_list("id", flat=True))
        protected = sorted(entity_ids & PROTECTED_ENTITY_IDS)
        if protected:
            raise CommandError(f"Cleanup scope includes protected certified entity IDs: {protected}")
        sales = SalesInvoiceHeader.objects.filter(entity_id__in=entity_ids, legacy_source_system=source_system)
        purchase = PurchaseInvoiceHeader.objects.filter(entity_id__in=entity_ids, legacy_source_system=source_system)
        preview = {
            "namespace": namespace,
            "source_system": source_system,
            "entity_ids": sorted(entity_ids),
            "entities": len(entity_ids),
            "sales_headers": sales.count(),
            "purchase_headers": purchase.count(),
            "customer_settlements": CustomerSettlement.objects.filter(entity_id__in=entity_ids).count(),
            "vendor_settlements": VendorSettlement.objects.filter(entity_id__in=entity_ids).count(),
        }
        if not execute:
            return {**preview, "executed": False}
        with transaction.atomic():
            from posting.models import Entry, PostingBatch

            Entry.objects.filter(entity_id__in=entity_ids).delete()
            PostingBatch.objects.filter(entity_id__in=entity_ids).delete()
            purchase.delete()
            sales.delete()
            Entity.objects.filter(id__in=entity_ids, entityname__startswith=f"{namespace} ").delete()
        return {**preview, "executed": True}

    def _protected_snapshot(self) -> dict:
        rows = []
        for entity in Entity.objects.filter(id__in=PROTECTED_ENTITY_IDS).order_by("id"):
            rows.append(
                {
                    "entity_id": entity.id,
                    "entity_name": entity.entityname,
                    "sales": SalesInvoiceHeader.objects.filter(entity=entity, is_active=True).count(),
                    "purchase": PurchaseInvoiceHeader.objects.filter(entity=entity).count(),
                    "ar_open": str(CustomerBillOpenItem.objects.filter(entity=entity).aggregate(v=Sum("outstanding_amount"))["v"] or ZERO),
                    "ap_open": str(VendorBillOpenItem.objects.filter(entity=entity).aggregate(v=Sum("outstanding_amount"))["v"] or ZERO),
                }
            )
        return {"protected_entity_ids": sorted(PROTECTED_ENTITY_IDS), "tenants": rows}

    def _runtime_snapshot(self) -> dict:
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from pg_stat_activity where datname = current_database()")
            connections = cursor.fetchone()[0]
            cursor.execute(
                """
                select count(*)
                from pg_locks l
                join pg_database d on d.oid = l.database
                where d.datname = current_database()
                """
            )
            locks = cursor.fetchone()[0]
        return {"postgres_connections": connections, "postgres_locks": locks}
