from django.db import transaction

from rbac.backfill import LegacyRBACBackfillService
from rbac.models import Menu, Permission, Role, RolePermission, UserRoleAssignment


class RBACSeedService:
    """
    Seeds entity access in a compatibility-safe way.

    New onboarding uses RBAC as the real access model, but this service also
    creates a legacy Admin/UserRole mapping so current entity-selection flows
    keep working until the rest of the application fully moves away from them.
    """

    DEFAULT_ROLE_SHELLS = (
        {"name": "Manager", "code": "manager", "priority": 20},
        {"name": "Accountant", "code": "accountant", "priority": 30},
        {"name": "Sales User", "code": "sales_user", "priority": 40},
        {"name": "Purchase User", "code": "purchase_user", "priority": 50},
        {"name": "Report Viewer", "code": "report_viewer", "priority": 60},
    )

    @classmethod
    @transaction.atomic
    def seed_entity(cls, *, entity, actor, seed_default_roles=True):
        cls._ensure_global_catalog()

        admin_role, _ = Role.objects.get_or_create(
            entity=entity,
            code="entity.super_admin",
            defaults={
                "name": "Entity Super Admin",
                "description": "Entity Administrator",
                "role_level": Role.LEVEL_ENTITY,
                "is_system_role": True,
                "is_assignable": True,
                "priority": 1,
                "createdby": actor,
                "isactive": True,
                "metadata": {"seed": "entity_onboarding"},
            },
        )
        admin_role.name = "Entity Super Admin"
        admin_role.description = "Entity Administrator"
        admin_role.is_system_role = True
        admin_role.is_assignable = True
        admin_role.priority = 1
        admin_role.isactive = True
        admin_role.save()

        all_permission_ids = list(Permission.objects.filter(isactive=True).values_list("id", flat=True))
        existing_permission_ids = set(
            RolePermission.objects.filter(role=admin_role, permission_id__in=all_permission_ids)
            .values_list("permission_id", flat=True)
        )
        missing_permission_ids = set(all_permission_ids) - existing_permission_ids
        RolePermission.objects.bulk_create(
            [
                RolePermission(role=admin_role, permission_id=permission_id, effect=RolePermission.EFFECT_ALLOW)
                for permission_id in missing_permission_ids
            ]
        )

        assignment, _ = UserRoleAssignment.objects.get_or_create(
            user=actor,
            entity=entity,
            role=admin_role,
            subentity=None,
            defaults={
                "assigned_by": actor,
                "is_primary": True,
                "scope_data": {"seed": "entity_onboarding"},
                "isactive": True,
            },
        )
        if not assignment.isactive or not assignment.is_primary:
            assignment.isactive = True
            assignment.is_primary = True
            assignment.assigned_by = actor
            assignment.save(update_fields=["isactive", "is_primary", "assigned_by", "updated_at"])

        shell_role_ids = []
        if seed_default_roles:
            for row in cls.DEFAULT_ROLE_SHELLS:
                role, _ = Role.objects.get_or_create(
                    entity=entity,
                    code=row["code"],
                    defaults={
                        "name": row["name"],
                        "description": row["name"],
                        "role_level": Role.LEVEL_ENTITY,
                        "is_system_role": False,
                        "is_assignable": True,
                        "priority": row["priority"],
                        "createdby": actor,
                        "isactive": True,
                        "metadata": {"seed": "entity_onboarding"},
                    },
                )
                shell_role_ids.append(role.id)

        return {
            "rbac_admin_role_id": admin_role.id,
            "rbac_admin_assignment_id": assignment.id,
            "permission_count": len(all_permission_ids),
            "shell_role_ids": shell_role_ids,
            "catalog_seeded": bool(all_permission_ids) and Menu.objects.filter(isactive=True).exists(),
        }

    @staticmethod
    def _ensure_global_catalog():
        if Permission.objects.exists() and Menu.objects.exists():
            RBACSeedService._normalize_menu_catalog()
            return
        LegacyRBACBackfillService.run()
        RBACSeedService._normalize_menu_catalog()

    @staticmethod
    def _normalize_menu_catalog():
        """
        Older experiments created a route-based legacy menu tree using codes like
        `legacy.admin` and `legacy.admin.user`. The current catalog uses
        `legacy.mainmenu.*` and `legacy.submenu.*`.

        For new onboarding, keep only the current catalog active so menu trees
        do not show duplicate top-level groups.
        """
        legacy_route_qs = Menu.objects.filter(code__startswith="legacy.").exclude(code__startswith="legacy.mainmenu.").exclude(code__startswith="legacy.submenu.")
        legacy_route_qs.update(isactive=False)
