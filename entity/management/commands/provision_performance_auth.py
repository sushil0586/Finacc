from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, SubEntity
from purchase.models.purchase_ap import VendorBillOpenItem
from purchase.models.purchase_core import PurchaseInvoiceHeader
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from sales.models import CustomerBillOpenItem, SalesInvoiceHeader
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService


@dataclass(frozen=True)
class PerfTenantTarget:
    label: str
    email: str
    username: str


class Command(BaseCommand):
    help = (
        "Provision local-only performance API users for the deterministic Phase 2B.3B "
        "fixture tenants after strict performance-environment safety checks pass."
    )

    ROLE_CODE = "perf_read_report_baseline"
    PASSWORD_ENV = "FINACC_PERF_AUTH_PASSWORD"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-db-name", action="append", default=[])
        parser.add_argument("--allow-db-host", action="append", default=[])
        parser.add_argument(
            "--password-env",
            default=self.PASSWORD_ENV,
            help="Environment variable containing the local-only password. The value is never printed.",
        )
        parser.add_argument(
            "--email-domain",
            default="local.invalid",
            help="Local-only email domain for generated performance users.",
        )

    def handle(self, *args, **options):
        started = time.perf_counter()
        self._assert_safety(options)

        password_env = options["password_env"]
        password = os.environ.get(password_env)
        if not password and not options["dry_run"]:
            raise CommandError(
                f"Missing {password_env}. Supply the local-only password through an environment variable."
            )

        targets = self._targets(options["email_domain"])
        before = self._financial_snapshot()
        permission_ids = list(self._read_report_permissions().values_list("id", flat=True))
        if not permission_ids:
            raise CommandError("No active read/report permissions were found for the performance role.")

        results = []
        for target in targets:
            entity = self._resolve_entity(target.label)
            if options["dry_run"]:
                results.append(self._dry_run_result(target, entity, permission_ids))
                continue
            with transaction.atomic():
                results.append(
                    self._provision_target(
                        target=target,
                        entity=entity,
                        password=password,
                        permission_ids=permission_ids,
                    )
                )

        after = self._financial_snapshot()
        payload = {
            "dry_run": bool(options["dry_run"]),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "password_source": password_env,
            "password_logged": False,
            "financial_snapshot_before": before,
            "financial_snapshot_after": after,
            "financial_counts_unchanged": before == after,
            "targets": results,
        }
        self._write(payload, options)

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
            raise CommandError(f"Performance auth provisioning blocked by safety audit: {exc}") from exc
        payload = json.loads(out.getvalue())
        if not payload.get("ready"):
            raise CommandError("Performance auth provisioning blocked because safety audit is not ready.")

    def _targets(self, email_domain: str) -> list[PerfTenantTarget]:
        domain = (email_domain or "local.invalid").strip().lower()
        if domain in {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com"}:
            raise CommandError("Refusing to create performance users on a public email domain.")
        return [
            PerfTenantTarget(
                label="Phase2B3B small Small Tenant",
                email=f"perf-api-small@{domain}",
                username="perf-api-small",
            ),
            PerfTenantTarget(
                label="Phase2B3B small Medium Tenant",
                email=f"perf-api-medium@{domain}",
                username="perf-api-medium",
            ),
            PerfTenantTarget(
                label="Phase2B3B small Large Tenant",
                email=f"perf-api-large@{domain}",
                username="perf-api-large",
            ),
        ]

    def _resolve_entity(self, label: str) -> Entity:
        matches = list(
            Entity.objects.filter(entityname=label, isactive=True)
            .select_related("customer_account")
            .order_by("id")
        )
        if len(matches) != 1:
            raise CommandError(f"Expected exactly one active fixture entity named {label!r}; found {len(matches)}.")
        return matches[0]

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

    def _dry_run_result(self, target: PerfTenantTarget, entity: Entity, permission_ids: list[int]) -> dict:
        fy = self._entity_financial_year(entity)
        subentity = self._subentity(entity)
        return {
            "email": target.email,
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "customer_account_id": entity.customer_account_id,
            "entityfinid": getattr(fy, "id", None),
            "subentity_id": getattr(subentity, "id", None),
            "permission_count": len(permission_ids),
            "action": "would_provision",
        }

    def _provision_target(
        self,
        *,
        target: PerfTenantTarget,
        entity: Entity,
        password: str,
        permission_ids: list[int],
    ) -> dict:
        user, user_created = User.objects.get_or_create(
            email=target.email,
            defaults={
                "username": target.username,
                "first_name": "Performance",
                "last_name": target.username.rsplit("-", 1)[-1].title(),
                "is_active": True,
                "email_verified": True,
            },
        )
        changed_fields = []
        for attr, value in {
            "username": target.username,
            "is_active": True,
            "email_verified": True,
            "is_staff": False,
            "is_superuser": False,
        }.items():
            if getattr(user, attr) != value:
                setattr(user, attr, value)
                changed_fields.append(attr)
        user.set_password(password)
        if hasattr(user, "last_password_changed_at"):
            user.last_password_changed_at = timezone.now()
            changed_fields.append("last_password_changed_at")
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
            role=UserEntityAccess.Role.VIEWER,
            granted_by=user,
        )
        SubscriptionService.ensure_active_subscription(customer_account=account)

        if entity.customer_account_id is None:
            entity.customer_account = account
            entity.save(update_fields=["customer_account", "updated_at"])
        elif entity.customer_account_id != account.id:
            raise CommandError(
                f"Fixture entity {entity.id} already belongs to a different customer account."
            )

        role, role_created = Role.objects.get_or_create(
            entity=entity,
            code=self.ROLE_CODE,
            defaults={
                "name": "Performance Read and Report Baseline",
                "description": "Local-only read/report permissions for performance baseline API certification.",
                "role_level": Role.LEVEL_ENTITY,
                "is_system_role": False,
                "is_assignable": False,
                "priority": 900,
                "createdby": user,
                "metadata": {"local_performance_fixture": True},
            },
        )
        if not role.isactive:
            role.isactive = True
            role.save(update_fields=["isactive", "updated_at"])

        existing_permission_ids = set(
            RolePermission.objects.filter(role=role, isactive=True).values_list("permission_id", flat=True)
        )
        missing_permissions = [
            RolePermission(
                role=role,
                permission_id=permission_id,
                effect=RolePermission.EFFECT_ALLOW,
                metadata={"local_performance_fixture": True},
            )
            for permission_id in permission_ids
            if permission_id not in existing_permission_ids
        ]
        if missing_permissions:
            RolePermission.objects.bulk_create(missing_permissions, ignore_conflicts=True)

        assignment, assignment_created = UserRoleAssignment.objects.get_or_create(
            user=user,
            entity=entity,
            role=role,
            subentity=None,
            defaults={
                "assigned_by": user,
                "effective_from": timezone.now(),
                "is_primary": True,
                "scope_data": {"local_performance_fixture": True},
            },
        )
        if not assignment.isactive or not assignment.is_primary:
            assignment.isactive = True
            assignment.is_primary = True
            assignment.save(update_fields=["isactive", "is_primary", "updated_at"])

        fy = self._entity_financial_year(entity)
        subentity = self._subentity(entity)
        return {
            "email": user.email,
            "user_id": user.id,
            "user_created": user_created,
            "password_set_from_env": True,
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "customer_account_id": account.id,
            "membership_id": membership.id,
            "membership_role": membership.role,
            "role_id": role.id,
            "role_created": role_created,
            "assignment_id": assignment.id,
            "assignment_created": assignment_created,
            "permission_count": len(permission_ids),
            "entityfinid": getattr(fy, "id", None),
            "subentity_id": getattr(subentity, "id", None),
            "changed_user_fields": sorted(set(changed_fields)),
        }

    def _entity_financial_year(self, entity: Entity):
        return EntityFinancialYear.objects.filter(entity=entity, isactive=True).order_by("-id").first()

    def _subentity(self, entity: Entity):
        return SubEntity.objects.filter(entity=entity, isactive=True).order_by("id").first()

    def _financial_snapshot(self) -> dict:
        rows = []
        for entity in Entity.objects.filter(entityname__startswith="Phase2B3B small", isactive=True).order_by("id"):
            rows.append(
                {
                    "entity_id": entity.id,
                    "entity_name": entity.entityname,
                    "sales_invoices": SalesInvoiceHeader.objects.filter(entity=entity, is_active=True).count(),
                    "purchase_invoices": PurchaseInvoiceHeader.objects.filter(entity=entity).count(),
                    "ar_open": str(
                        CustomerBillOpenItem.objects.filter(entity=entity).aggregate(
                            total=Sum("outstanding_amount")
                        )["total"]
                        or "0.00"
                    ),
                    "ap_open": str(
                        VendorBillOpenItem.objects.filter(entity=entity).aggregate(
                            total=Sum("outstanding_amount")
                        )["total"]
                        or "0.00"
                    ),
                }
            )
        return {"tenant_count": len(rows), "tenants": rows}

    def _write(self, payload: dict, options):
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
            return
        self.stdout.write(
            "performance_auth_ready="
            f"{not options['dry_run']} targets={len(payload['targets'])} "
            f"financial_counts_unchanged={payload['financial_counts_unchanged']}"
        )
