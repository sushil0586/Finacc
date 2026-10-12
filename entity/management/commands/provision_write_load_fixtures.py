from __future__ import annotations

import json
import os
import random
import time
from dataclasses import asdict, dataclass
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from Authentication.models import User
from entity.management.commands.seed_performance_fixtures import Command as SeedCommand
from entity.management.commands.seed_performance_fixtures import TenantTarget
from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import Ledger
from financial.seeding import FinancialSeedService
from posting.models import EntityStaticAccountMap, StaticAccount
from posting.services.static_accounts import StaticAccountService
from purchase.services.purchase_settings_service import PurchaseSettingsService
from payments.models import PaymentVoucherHeader
from purchase.models.purchase_ap import VendorBillOpenItem
from purchase.models.purchase_core import PurchaseInvoiceHeader
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from sales.models import CustomerBillOpenItem, SalesInvoiceHeader
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService


@dataclass(frozen=True)
class WriteTenantTarget:
    code: str
    label: str
    email: str
    username: str
    sales: int
    purchase: int


class Command(BaseCommand):
    help = (
        "Provision local-only Phase 2B.3D write-load tenants and users after strict "
        "performance-environment safety checks pass."
    )

    PASSWORD_ENV = "FINACC_PERF_WRITE_PASSWORD"
    ROLE_CODE = "perf_write_load_financial_workflows"
    NAMESPACE = "Phase2B3D Write"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--reset-fixture", action="store_true")
        parser.add_argument("--confirm-reset", action="store_true")
        parser.add_argument("--sales", type=int, default=8)
        parser.add_argument("--purchase", type=int, default=8)
        parser.add_argument("--seed", type=int, default=20261011)
        parser.add_argument("--password-env", default=self.PASSWORD_ENV)
        parser.add_argument("--email-domain", default="local.invalid")
        parser.add_argument("--allow-db-name", action="append", default=[])
        parser.add_argument("--allow-db-host", action="append", default=[])

    def handle(self, *args, **options):
        started = time.perf_counter()
        self._assert_safety(options)
        targets = self._targets(options)
        before = self._snapshot()

        if options["reset_fixture"]:
            reset = self._reset_fixture(dry_run=options["dry_run"], confirm=options["confirm_reset"])
            self._write(
                {
                    "dry_run": bool(options["dry_run"]),
                    "reset_requested": True,
                    "reset": reset,
                    "protected_read_fixture_before": before["protected_read_fixture"],
                    "protected_read_fixture_after": self._snapshot()["protected_read_fixture"],
                },
                options,
            )
            return

        password_env = options["password_env"]
        password = os.environ.get(password_env)
        if not password and not options["dry_run"]:
            raise CommandError(f"Missing {password_env}. Supply a local-only password through the environment.")

        permission_ids = list(self._write_permissions().values_list("id", flat=True))
        if not permission_ids:
            raise CommandError("No active workflow permissions found for write-load provisioning.")

        if options["dry_run"]:
            self._write(
                {
                    "dry_run": True,
                    "targets": [asdict(target) for target in targets],
                    "permission_count": len(permission_ids),
                    "snapshot_before": before,
                    "message": "Safety audit passed. No write-load rows were written.",
                },
                options,
            )
            return

        seed_command = SeedCommand()
        rng = random.Random(int(options["seed"]))
        results = []
        for target in targets:
            seed_target = TenantTarget(code=target.code, label=target.label, sales=target.sales, purchase=target.purchase)
            with transaction.atomic():
                tenant = seed_command._ensure_tenant(seed_target)
                self._ensure_posting_and_numbering(tenant)
            seed_result = seed_command._seed_tenant(
                tenant=tenant,
                target=seed_target,
                batch_size=max(target.sales, target.purchase, 1),
                rng=rng,
                payment_ratio=0,
            )
            validation = seed_command._validate_tenant(tenant)
            user_result = self._provision_user(
                target=target,
                entity=tenant["entity"],
                password=password,
                permission_ids=permission_ids,
            )
            results.append(
                {
                    "target": asdict(target),
                    "entity_id": tenant["entity"].id,
                    "entityfinid": tenant["entityfin"].id,
                    "subentity_id": tenant["subentity"].id,
                    "seed": seed_result,
                    "validation": validation,
                    "auth": user_result,
                }
            )

        after = self._snapshot()
        self._write(
            {
                "dry_run": False,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "password_source": password_env,
                "password_logged": False,
                "targets": results,
                "snapshot_before": before,
                "snapshot_after": after,
                "protected_read_fixture_unchanged": before["protected_read_fixture"] == after["protected_read_fixture"],
                "write_fixture_validation": self._write_fixture_validation(),
            },
            options,
        )

    def _assert_safety(self, options):
        out = StringIO()
        args = ["--json", "--strict"]
        for name in options["allow_db_name"]:
            args.extend(["--allow-db-name", name])
        for host in options["allow_db_host"]:
            args.extend(["--allow-db-host", host])
        try:
            call_command("audit_performance_staging", *args, stdout=out)
        except CommandError as exc:
            raise CommandError(f"Write-load fixture provisioning blocked by safety audit: {exc}") from exc
        payload = json.loads(out.getvalue())
        if not payload.get("ready"):
            raise CommandError("Write-load fixture provisioning blocked because safety audit is not ready.")

    def _targets(self, options) -> list[WriteTenantTarget]:
        domain = (options["email_domain"] or "local.invalid").strip().lower()
        if domain in {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com"}:
            raise CommandError("Refusing to create write-load users on a public email domain.")
        sales = int(options["sales"])
        purchase = int(options["purchase"])
        if sales < 1 or purchase < 1:
            raise CommandError("Write-load sales and purchase counts must be at least 1.")
        return [
            WriteTenantTarget("P2B3D-A", f"{self.NAMESPACE} Tenant A", f"perf-write-a@{domain}", "perf-write-a", sales, purchase),
            WriteTenantTarget("P2B3D-B", f"{self.NAMESPACE} Tenant B", f"perf-write-b@{domain}", "perf-write-b", sales, purchase),
        ]

    def _write_permissions(self):
        workflow_tokens = (
            "sales.invoice",
            "purchase.invoice",
            "payment",
            "voucher.journal",
            "voucher.cash",
            "voucher.bank",
            "reports.",
            "dashboard.",
        )
        allowed_actions = {
            "access",
            "approve",
            "confirm",
            "create",
            "edit",
            "list",
            "post",
            "read",
            "submit",
            "update",
            "view",
        }
        queryset = Permission.objects.filter(isactive=True, action__in=allowed_actions)
        token_filter = Q()
        for token in workflow_tokens:
            token_filter |= Q(code__icontains=token)
        return queryset.filter(token_filter).exclude(code__icontains="delete").order_by("code")

    def _provision_user(self, *, target: WriteTenantTarget, entity: Entity, password: str, permission_ids: list[int]) -> dict:
        user, user_created = User.objects.get_or_create(
            email=target.email,
            defaults={
                "username": target.username,
                "first_name": "Performance",
                "last_name": "Writer",
                "is_active": True,
                "email_verified": True,
            },
        )
        user.username = target.username
        user.is_active = True
        user.email_verified = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        if hasattr(user, "last_password_changed_at"):
            user.last_password_changed_at = timezone.now()
        user.save()

        account = SubscriptionService.ensure_customer_account(
            user=user,
            intent=SubscriptionService.INTENT_TRIAL,
        )
        if account.status != account.Status.ACTIVE:
            account.status = account.Status.ACTIVE
            account.save(update_fields=["status", "updated_at"])
        membership = SubscriptionService.ensure_account_membership(
            customer_account=account,
            user=user,
            role=UserEntityAccess.Role.OWNER,
            granted_by=user,
        )
        SubscriptionService.ensure_active_subscription(customer_account=account)

        if entity.customer_account_id is None:
            entity.customer_account = account
            entity.save(update_fields=["customer_account", "updated_at"])
        elif entity.customer_account_id != account.id:
            raise CommandError(f"Write-load entity {entity.id} already belongs to a different customer account.")

        role, role_created = Role.objects.get_or_create(
            entity=entity,
            code=self.ROLE_CODE,
            defaults={
                "name": "Performance Write-Load Financial Workflows",
                "description": "Local-only scoped permissions for Phase 2B.3D write-load certification.",
                "role_level": Role.LEVEL_ENTITY,
                "is_system_role": False,
                "is_assignable": False,
                "priority": 850,
                "createdby": user,
                "metadata": {"local_performance_fixture": True, "phase": "2B.3D.1"},
            },
        )
        if not role.isactive:
            role.isactive = True
            role.save(update_fields=["isactive", "updated_at"])

        existing = set(RolePermission.objects.filter(role=role, isactive=True).values_list("permission_id", flat=True))
        missing = [
            RolePermission(
                role=role,
                permission_id=permission_id,
                effect=RolePermission.EFFECT_ALLOW,
                metadata={"local_performance_fixture": True, "phase": "2B.3D.1"},
            )
            for permission_id in permission_ids
            if permission_id not in existing
        ]
        if missing:
            RolePermission.objects.bulk_create(missing, ignore_conflicts=True)

        assignment, assignment_created = UserRoleAssignment.objects.get_or_create(
            user=user,
            entity=entity,
            role=role,
            subentity=None,
            defaults={
                "assigned_by": user,
                "effective_from": timezone.now(),
                "is_primary": True,
                "scope_data": {"local_performance_fixture": True, "phase": "2B.3D.1"},
            },
        )
        if not assignment.isactive or not assignment.is_primary:
            assignment.isactive = True
            assignment.is_primary = True
            assignment.save(update_fields=["isactive", "is_primary", "updated_at"])

        fy = EntityFinancialYear.objects.filter(entity=entity, isactive=True).order_by("id").first()
        subentity = SubEntity.objects.filter(entity=entity, isactive=True).order_by("id").first()
        return {
            "email": user.email,
            "user_id": user.id,
            "user_created": user_created,
            "superuser": user.is_superuser,
            "staff": user.is_staff,
            "membership_id": membership.id,
            "membership_role": membership.role,
            "role_id": role.id,
            "role_created": role_created,
            "assignment_id": assignment.id,
            "assignment_created": assignment_created,
            "permission_count": len(permission_ids),
            "entityfinid": getattr(fy, "id", None),
            "subentity_id": getattr(subentity, "id", None),
        }

    def _ensure_posting_and_numbering(self, tenant: dict) -> None:
        entity = tenant["entity"]
        entityfin = tenant["entityfin"]
        subentity = tenant["subentity"]
        actor = tenant["actor"]
        FinancialSeedService.seed_entity(entity=entity, actor=actor, template_code="indian_accounting_final")
        StaticAccountService.seed_static_account_master()
        StaticAccountService.seed_required_entity_mappings(entity=entity, actor=actor)
        static_ledger_codes = {
            "PURCHASE_DEFAULT": 1001,
            "PURCHASE_MISC_EXPENSE": 8351,
            "ROUND_OFF_INCOME": 7081,
            "ROUND_OFF_EXPENSE": 8403,
            "INPUT_CGST": 6501,
            "INPUT_SGST": 6502,
            "INPUT_IGST": 6503,
            "INPUT_CESS": 6504,
            "OUTPUT_CGST": 6601,
            "OUTPUT_SGST": 6602,
            "OUTPUT_IGST": 6603,
            "OUTPUT_CESS": 6604,
            "SALES_DEFAULT": 3001,
            "SALES_REVENUE": 3002,
        }
        for static_code, ledger_code in static_ledger_codes.items():
            static_account = StaticAccount.objects.filter(code=static_code).first()
            ledger = Ledger.objects.filter(entity=entity, ledger_code=ledger_code).first()
            account_profile = getattr(ledger, "account_profile", None) if ledger else None
            if not static_account or not ledger or not account_profile:
                continue
            EntityStaticAccountMap.objects.update_or_create(
                entity=entity,
                sub_entity=None,
                static_account=static_account,
                defaults={"account": account_profile, "ledger": ledger, "createdby": actor},
            )
        StaticAccountService.invalidate(entity.id)
        call_command(
            "seed_payment_numbering",
            "--entity",
            str(entity.id),
            "--entityfinid",
            str(entityfin.id),
            "--subentity",
            str(subentity.id),
            "--doc-code",
            "PPV",
            "--prefix",
            f"{entity.id}PV",
            verbosity=0,
        )
        call_command(
            "seed_voucher_numbering",
            "--entity",
            str(entity.id),
            "--entityfinid",
            str(entityfin.id),
            "--subentity",
            str(subentity.id),
            "--voucher-type",
            "JOURNAL",
            verbosity=0,
        )
        PurchaseSettingsService.upsert_settings(
            entity_id=entity.id,
            subentity_id=subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )

    def _reset_fixture(self, *, dry_run: bool, confirm: bool) -> dict:
        entities = Entity.objects.filter(entityname__startswith=self.NAMESPACE)
        preview = self._write_fixture_validation()
        preview["entity_ids"] = list(entities.order_by("id").values_list("id", flat=True))
        if dry_run:
            preview["action"] = "dry_run_only"
            return preview
        if not confirm:
            raise CommandError("--confirm-reset is required for non-dry-run write-load fixture cleanup.")
        with transaction.atomic():
            entities.delete()
            User.objects.filter(email__in=["perf-write-a@local.invalid", "perf-write-b@local.invalid"]).delete()
        preview["action"] = "deleted_write_load_namespace"
        return preview

    def _snapshot(self) -> dict:
        return {
            "protected_read_fixture": self._fixture_rows("Phase2B3B small"),
            "write_fixture": self._fixture_rows(self.NAMESPACE),
        }

    def _fixture_rows(self, prefix: str) -> list[dict]:
        rows = []
        for entity in Entity.objects.filter(entityname__startswith=prefix, isactive=True).order_by("id"):
            rows.append(
                {
                    "entity_id": entity.id,
                    "entity_name": entity.entityname,
                    "sales_invoices": SalesInvoiceHeader.objects.filter(entity=entity, is_active=True).count(),
                    "purchase_invoices": PurchaseInvoiceHeader.objects.filter(entity=entity).count(),
                    "payment_vouchers": PaymentVoucherHeader.objects.filter(entity=entity).count(),
                    "ar_open": str(
                        CustomerBillOpenItem.objects.filter(entity=entity).aggregate(total=Sum("outstanding_amount"))["total"]
                        or "0.00"
                    ),
                    "ap_open": str(
                        VendorBillOpenItem.objects.filter(entity=entity).aggregate(total=Sum("outstanding_amount"))["total"]
                        or "0.00"
                    ),
                }
            )
        return rows

    def _write_fixture_validation(self) -> dict:
        rows = self._fixture_rows(self.NAMESPACE)
        users = list(
            User.objects.filter(email__in=["perf-write-a@local.invalid", "perf-write-b@local.invalid"])
            .order_by("email")
            .values("email", "is_active", "is_staff", "is_superuser")
        )
        duplicate_sales = 0
        duplicate_purchase = 0
        for entity in Entity.objects.filter(entityname__startswith=self.NAMESPACE, isactive=True):
            duplicate_sales += (
                SalesInvoiceHeader.objects.filter(entity=entity)
                .values("doc_code", "doc_no")
                .annotate(c=Count("id"))
                .filter(c__gt=1)
                .count()
            )
            duplicate_purchase += (
                PurchaseInvoiceHeader.objects.filter(entity=entity)
                .values("doc_code", "doc_no")
                .annotate(c=Count("id"))
                .filter(c__gt=1)
                .count()
            )
        return {
            "tenant_count": len(rows),
            "tenants": rows,
            "users": users,
            "duplicate_sales_doc_number_groups": duplicate_sales,
            "duplicate_purchase_doc_number_groups": duplicate_purchase,
        }

    def _write(self, payload: dict, options):
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
