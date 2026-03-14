from django.core.management.base import BaseCommand
from django.db import transaction

from rbac.models import Permission, Role, RolePermission


class Command(BaseCommand):
    help = "Grant all active RBAC permissions to entity.super_admin and admin roles."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, help="Optional entity id to scope the grant")
        parser.add_argument(
            "--role-code",
            action="append",
            dest="role_codes",
            help="Role code to grant. Repeatable. Defaults to entity.super_admin and admin.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        role_codes = options.get("role_codes") or ["entity.super_admin", "admin"]
        roles = Role.objects.filter(code__in=role_codes, isactive=True)
        if options.get("entity"):
            roles = roles.filter(entity_id=options["entity"])

        permissions = list(Permission.objects.filter(isactive=True).values_list("id", flat=True))
        if not permissions:
            self.stdout.write(self.style.WARNING("No active permissions found."))
            return

        granted = 0
        for role in roles:
            existing = set(RolePermission.objects.filter(role=role, permission_id__in=permissions).values_list("permission_id", flat=True))
            rows = [
                RolePermission(role=role, permission_id=permission_id, effect=RolePermission.EFFECT_ALLOW, metadata={"seed": "grant_current_full_access"}, isactive=True)
                for permission_id in permissions
                if permission_id not in existing
            ]
            if rows:
                RolePermission.objects.bulk_create(rows)
                granted += len(rows)
            self.stdout.write(self.style.SUCCESS(f"Granted full access to role {role.code} (entity={role.entity_id})."))

        self.stdout.write(self.style.SUCCESS(f"Done. Added {granted} role-permission rows."))
