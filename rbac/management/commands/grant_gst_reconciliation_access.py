from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from Authentication.models import User
from entity.models import Entity, SubEntity
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService


GST_RECON_PERMISSION_CODES = [
    "gst.reconciliation.view",
    "gst.reconciliation.review",
    "gst.reconciliation.manage",
]

PILOT_ROLE_CODE = "gst.reconciliation.pilot"
PILOT_ROLE_NAME = "GST Reconciliation Pilot"


class Command(BaseCommand):
    help = "Grant GST Reconciliation pilot access to a user for an entity without giving broad admin access."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, required=True, help="User id to grant access to.")
        parser.add_argument("--entity", type=int, required=True, help="Entity id.")
        parser.add_argument("--subentity", type=int, help="Optional subentity id.")
        parser.add_argument("--assigned-by", type=int, help="Optional assigner user id.")
        parser.add_argument(
            "--tenant-role",
            default=UserEntityAccess.Role.ADMIN,
            choices=[choice[0] for choice in UserEntityAccess.Role.choices],
            help="Tenant membership role to ensure on the entity customer account.",
        )
        parser.add_argument(
            "--primary",
            action="store_true",
            help="Mark the assignment as primary. Leave off for a narrow pilot assignment.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        user = self._get_user(options["user"], label="target user")
        entity = self._get_entity(options["entity"])
        subentity = self._get_subentity(options.get("subentity"), entity=entity)
        assigned_by = self._get_user(options.get("assigned_by"), label="assigned-by user", required=False) or user
        if options["primary"] and subentity is not None:
            raise CommandError("Primary GST reconciliation assignment cannot be limited to a subentity.")

        permissions = list(Permission.objects.filter(code__in=GST_RECON_PERMISSION_CODES, isactive=True))
        if len(permissions) != len(GST_RECON_PERMISSION_CODES):
            found = {permission.code for permission in permissions}
            missing = [code for code in GST_RECON_PERMISSION_CODES if code not in found]
            raise CommandError(
                "Missing GST reconciliation permissions. Run migrations first. Missing: " + ", ".join(missing)
            )

        customer_account = entity.customer_account
        customer_account_id = getattr(customer_account, "id", None)
        if customer_account_id:
            membership = SubscriptionService.ensure_account_membership(
                customer_account=customer_account,
                user=user,
                role=options["tenant_role"],
                granted_by=assigned_by,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured tenant membership for user {user.id} on customer account {customer_account_id} as {membership.role}."
                )
            )
        else:
            raise CommandError("Entity does not have a customer account; tenant membership cannot be ensured.")

        role, role_created = Role.objects.update_or_create(
            entity=entity,
            code=PILOT_ROLE_CODE,
            defaults={
                "name": PILOT_ROLE_NAME,
                "description": "Pilot-only role for GST reconciliation workspace access.",
                "role_level": Role.LEVEL_ENTITY,
                "is_system_role": False,
                "is_assignable": True,
                "priority": 75,
                "metadata": {"seed": "grant_gst_reconciliation_access"},
                "createdby": assigned_by,
                "isactive": True,
            },
        )
        if role_created:
            self.stdout.write(self.style.SUCCESS(f"Created entity role {role.code} for entity {entity.id}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Using existing entity role {role.code} for entity {entity.id}."))

        existing_permission_ids = set(
            RolePermission.objects.filter(
                role=role,
                permission_id__in=[permission.id for permission in permissions],
                isactive=True,
                effect=RolePermission.EFFECT_ALLOW,
            ).values_list("permission_id", flat=True)
        )
        rows = [
            RolePermission(
                role=role,
                permission=permission,
                effect=RolePermission.EFFECT_ALLOW,
                metadata={"seed": "grant_gst_reconciliation_access"},
                isactive=True,
            )
            for permission in permissions
            if permission.id not in existing_permission_ids
        ]
        if rows:
            RolePermission.objects.bulk_create(rows)
            self.stdout.write(self.style.SUCCESS(f"Granted {len(rows)} GST reconciliation permissions to role {role.code}."))

        assignment_defaults = {
            "assigned_by": assigned_by,
            "is_primary": bool(options["primary"]),
            "scope_data": {"screen_testing": True, "feature": "gst_reconciliation"},
            "isactive": True,
        }
        assignment, created = UserRoleAssignment.objects.update_or_create(
            user=user,
            entity=entity,
            role=role,
            subentity=subentity,
            defaults=assignment_defaults,
        )
        status_label = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{status_label} user-role assignment for user {user.id}, entity {entity.id}, role {role.code}"
                + (f", subentity {subentity.id}" if subentity else "")
                + "."
            )
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("GST Reconciliation pilot access is ready."))
        self.stdout.write(f"User: {user.id} ({user.username})")
        self.stdout.write(f"Entity: {entity.id} ({entity.entityname})")
        self.stdout.write(f"Role: {role.code}")
        self.stdout.write("Permissions: " + ", ".join(sorted(permission.code for permission in permissions)))
        self.stdout.write("Route to test: /gst-reconciliation")

    @staticmethod
    def _get_user(user_id: int | None, *, label: str, required: bool = True):
        if not user_id:
            if required:
                raise CommandError(f"Missing {label} id.")
            return None
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist as exc:
            raise CommandError(f"{label.capitalize()} {user_id} not found.") from exc

    @staticmethod
    def _get_entity(entity_id: int):
        try:
            return Entity.objects.select_related("customer_account").get(pk=entity_id)
        except Entity.DoesNotExist as exc:
            raise CommandError(f"Entity {entity_id} not found.") from exc

    @staticmethod
    def _get_subentity(subentity_id: int | None, *, entity: Entity):
        if not subentity_id:
            return None
        try:
            subentity = SubEntity.objects.get(pk=subentity_id)
        except SubEntity.DoesNotExist as exc:
            raise CommandError(f"Subentity {subentity_id} not found.") from exc
        if subentity.entity_id != entity.id:
            raise CommandError("Subentity does not belong to the selected entity.")
        return subentity
