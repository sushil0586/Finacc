from django.db import transaction

from rbac.backfill import LegacyRBACBackfillService
from rbac.models import Menu, MenuPermission, Permission, Role, RolePermission, UserRoleAssignment
from rbac.services import RoleTemplateService


class RBACSeedService:
    """
    Seeds entity access with a modern RBAC-first catalog.

    New entities get a usable set of onboarding roles with suggested permissions so
    customers can start assigning users immediately after creation.
    """

    DEFAULT_ROLE_SHELLS = (
        {"name": "Admin", "code": "admin", "priority": 20, "template": "admin"},
        {"name": "Sales User", "code": "sales_user", "priority": 30, "template": "sales_user"},
        {"name": "Purchase User", "code": "purchase_user", "priority": 40, "template": "purchase_user"},
        {"name": "Accounts User", "code": "accounts_user", "priority": 50, "template": "accounts_user"},
        {"name": "Report Viewer", "code": "report_viewer", "priority": 60, "template": "report_viewer"},
        {"name": "Payables User", "code": "payables_user", "priority": 70, "template": "payables_user"},
        {"name": "Payroll User", "code": "payroll_user", "priority": 80, "template": "payroll_user"},
        {"name": "Compliance User", "code": "compliance_user", "priority": 90, "template": "compliance_user"},
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
            RolePermission.objects.filter(role=admin_role, permission_id__in=all_permission_ids).values_list("permission_id", flat=True)
        )
        missing_permission_ids = set(all_permission_ids) - existing_permission_ids
        if missing_permission_ids:
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
                        "metadata": {"seed": "entity_onboarding", "template": row["template"]},
                    },
                )
                role.name = row["name"]
                role.description = row["name"]
                role.priority = row["priority"]
                role.is_assignable = True
                role.isactive = True
                role.metadata = {**(role.metadata or {}), "seed": "entity_onboarding", "template": row["template"]}
                role.save()
                RoleTemplateService.apply_template(role, row["template"], [], actor=actor)
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
        legacy_route_qs = Menu.objects.filter(code__startswith="legacy.").exclude(code__startswith="legacy.mainmenu.").exclude(code__startswith="legacy.submenu.")
        legacy_route_qs.update(isactive=False)


class PayrollRBACSeedService:
    CATALOG_VERSION = "payroll_rbac_2026_03"
    SEED_TAG = "payroll_rbac_seed"

    PERMISSION_SPECS = (
        ("payroll.run.view", "View Payroll Runs", "payroll", "run", "view"),
        ("payroll.run.manage", "Manage Payroll Runs", "payroll", "run", "manage"),
        ("payroll.run.calculate", "Calculate Payroll Runs", "payroll", "run", "calculate"),
        ("payroll.run.submit", "Submit Payroll Runs", "payroll", "run", "submit"),
        ("payroll.run.approve", "Approve Payroll Runs", "payroll", "run", "approve"),
        ("payroll.run.post", "Post Payroll Runs", "payroll", "run", "post"),
        ("payroll.run.reverse", "Reverse Payroll Runs", "payroll", "run", "reverse"),
        ("payroll.run.payment_handoff", "Handoff Payroll Payments", "payroll", "run", "payment_handoff"),
        ("payroll.run.payment_reconcile", "Reconcile Payroll Payments", "payroll", "run", "payment_reconcile"),
        ("payroll.component.view", "View Payroll Components", "payroll", "component", "view"),
        ("payroll.component.manage", "Manage Payroll Components", "payroll", "component", "manage"),
        ("payroll.component.create", "Create Payroll Components", "payroll", "component", "create"),
        ("payroll.component.edit", "Edit Payroll Components", "payroll", "component", "edit"),
        ("payroll.structure.view", "View Salary Structures", "payroll", "structure", "view"),
        ("payroll.structure.manage", "Manage Salary Structures", "payroll", "structure", "manage"),
        ("payroll.structure.create", "Create Salary Structures", "payroll", "structure", "create"),
        ("payroll.structure.edit", "Edit Salary Structures", "payroll", "structure", "edit"),
        ("payroll.profile.view", "View Payroll Profiles", "payroll", "profile", "view"),
        ("payroll.profile.manage", "Manage Payroll Profiles", "payroll", "profile", "manage"),
        ("payroll.profile.create", "Create Payroll Profiles", "payroll", "profile", "create"),
        ("payroll.profile.edit", "Edit Payroll Profiles", "payroll", "profile", "edit"),
        ("payroll.period.view", "View Payroll Periods", "payroll", "period", "view"),
        ("payroll.period.manage", "Manage Payroll Periods", "payroll", "period", "manage"),
        ("payroll.period.create", "Create Payroll Periods", "payroll", "period", "create"),
        ("payroll.period.edit", "Edit Payroll Periods", "payroll", "period", "edit"),
        ("payroll.adjustment.view", "View Payroll Adjustments", "payroll", "adjustment", "view"),
        ("payroll.adjustment.manage", "Manage Payroll Adjustments", "payroll", "adjustment", "manage"),
        ("payroll.adjustment.create", "Create Payroll Adjustments", "payroll", "adjustment", "create"),
        ("payroll.adjustment.edit", "Edit Payroll Adjustments", "payroll", "adjustment", "edit"),
        ("reports.payroll.view", "View Payroll Reports", "reports", "payroll", "view"),
        ("reports.payroll.export", "Export Payroll Reports", "reports", "payroll", "export"),
        ("payments.payroll.handoff", "Handoff Payroll Payments", "payments", "payroll", "handoff"),
        ("payments.payroll.reconcile", "Reconcile Payroll Payments", "payments", "payroll", "reconcile"),
    )

    MENU_SPECS = (
        {
            "code": "payroll",
            "name": "Payroll",
            "menu_type": Menu.TYPE_GROUP,
            "route_path": "",
            "route_name": "payroll",
            "sort_order": 55,
            "icon": "badge-indian-rupee",
            "parent_code": None,
            "permission_code": "payroll.run.view",
        },
        {
            "code": "payroll.dashboard",
            "name": "Dashboard",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/dashboard",
            "route_name": "payroll-dashboard",
            "sort_order": 1,
            "icon": "layout-dashboard",
            "parent_code": "payroll",
            "permission_code": "payroll.run.view",
        },
        {
            "code": "payroll.runs",
            "name": "Runs",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/runs",
            "route_name": "payroll-runs",
            "sort_order": 2,
            "icon": "list-checks",
            "parent_code": "payroll",
            "permission_code": "payroll.run.view",
        },
        {
            "code": "payroll.components",
            "name": "Components",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/components",
            "route_name": "payroll-components",
            "sort_order": 3,
            "icon": "component",
            "parent_code": "payroll",
            "permission_code": "payroll.component.view",
        },
        {
            "code": "payroll.salary-structures",
            "name": "Salary Structures",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/salary-structures",
            "route_name": "payroll-salary-structures",
            "sort_order": 4,
            "icon": "network",
            "parent_code": "payroll",
            "permission_code": "payroll.structure.view",
        },
        {
            "code": "payroll.employee-profiles",
            "name": "Employee Profiles",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/employee-profiles",
            "route_name": "payroll-employee-profiles",
            "sort_order": 5,
            "icon": "users-round",
            "parent_code": "payroll",
            "permission_code": "payroll.profile.view",
        },
        {
            "code": "payroll.periods",
            "name": "Periods",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/periods",
            "route_name": "payroll-periods",
            "sort_order": 6,
            "icon": "calendar-days",
            "parent_code": "payroll",
            "permission_code": "payroll.period.view",
        },
        {
            "code": "payroll.adjustments",
            "name": "Adjustments",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/adjustments",
            "route_name": "payroll-adjustments",
            "sort_order": 7,
            "icon": "sliders-horizontal",
            "parent_code": "payroll",
            "permission_code": "payroll.adjustment.view",
        },
        {
            "code": "payroll.reports",
            "name": "Reports",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/reports",
            "route_name": "payroll-reports",
            "sort_order": 8,
            "icon": "bar-chart-3",
            "parent_code": "payroll",
            "permission_code": "reports.payroll.view",
        },
        {
            "code": "payroll.onboarding",
            "name": "Onboarding",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/onboarding",
            "route_name": "payroll-onboarding",
            "sort_order": 9,
            "icon": "clipboard-check",
            "parent_code": "payroll",
            "permission_code": "payroll.profile.manage",
        },
    )

    ROLE_SPECS = (
        {
            "name": "Admin",
            "code": "admin",
            "priority": 20,
            "permissions": "__all__",
        },
        {
            "name": "Payroll Operator",
            "code": "payroll_operator",
            "priority": 70,
            "permissions": {
                "payroll.run.view",
                "payroll.run.manage",
                "payroll.run.calculate",
                "payroll.run.submit",
                "payroll.profile.manage",
                "payroll.profile.create",
                "payroll.profile.edit",
                "payroll.period.manage",
                "payroll.period.create",
                "payroll.period.edit",
                "payroll.adjustment.manage",
                "payroll.adjustment.create",
                "payroll.adjustment.edit",
                "reports.payroll.view",
            },
        },
        {
            "name": "Approver",
            "code": "payroll_approver",
            "priority": 75,
            "permissions": {
                "payroll.run.view",
                "payroll.run.approve",
                "reports.payroll.view",
            },
        },
        {
            "name": "Finance Manager",
            "code": "payroll_finance_manager",
            "priority": 80,
            "permissions": {
                "payroll.run.view",
                "payroll.run.post",
                "payroll.run.payment_handoff",
                "payroll.run.payment_reconcile",
                "reports.payroll.view",
                "reports.payroll.export",
                "payments.payroll.handoff",
                "payments.payroll.reconcile",
            },
        },
        {
            "name": "Read-only Reviewer",
            "code": "payroll_read_only_reviewer",
            "priority": 90,
            "permissions": {
                "payroll.run.view",
                "payroll.component.view",
                "payroll.structure.view",
                "payroll.profile.view",
                "payroll.period.view",
                "payroll.adjustment.view",
                "reports.payroll.view",
            },
        },
    )

    @classmethod
    @transaction.atomic
    def seed_global_catalog(cls):
        permission_map = {}
        for code, name, module, resource, action in cls.PERMISSION_SPECS:
            permission, _ = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "module": module,
                    "resource": resource,
                    "action": action,
                    "description": name,
                    "scope_type": Permission.SCOPE_ENTITY,
                    "is_system_defined": True,
                    "metadata": {
                        "seed": cls.SEED_TAG,
                        "catalog_version": cls.CATALOG_VERSION,
                    },
                    "isactive": True,
                },
            )
            permission_map[code] = permission

        menu_map = {}
        for spec in cls.MENU_SPECS:
            menu, _ = Menu.objects.get_or_create(
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "menu_type": spec["menu_type"],
                    "route_path": spec["route_path"],
                    "route_name": spec["route_name"],
                    "sort_order": spec["sort_order"],
                    "icon": spec["icon"],
                    "is_system_menu": True,
                    "metadata": {
                        "seed": cls.SEED_TAG,
                        "catalog_version": cls.CATALOG_VERSION,
                        "permission_code": spec["permission_code"],
                    },
                    "isactive": True,
                },
            )
            menu_map[spec["code"]] = menu

        for spec in cls.MENU_SPECS:
            menu = menu_map[spec["code"]]
            parent = menu_map.get(spec["parent_code"])
            menu.parent = parent
            menu.name = spec["name"]
            menu.menu_type = spec["menu_type"]
            menu.route_path = spec["route_path"]
            menu.route_name = spec["route_name"]
            menu.sort_order = spec["sort_order"]
            menu.icon = spec["icon"]
            menu.is_system_menu = True
            menu.isactive = True
            menu.metadata = {
                **(menu.metadata or {}),
                "seed": cls.SEED_TAG,
                "catalog_version": cls.CATALOG_VERSION,
                "permission_code": spec["permission_code"],
            }
            menu.save()

            MenuPermission.objects.update_or_create(
                menu=menu,
                permission=permission_map[spec["permission_code"]],
                relation_type=MenuPermission.RELATION_VISIBILITY,
                defaults={"isactive": True},
            )

        return {
            "permissions": permission_map,
            "menus": menu_map,
        }

    @classmethod
    @transaction.atomic
    def seed_entity_roles(cls, *, entity, actor=None):
        catalog = cls.seed_global_catalog()
        permission_map = catalog["permissions"]
        summary_roles = []

        # Keep entity super admin aligned with all new payroll permissions as well.
        entity_super_admin = Role.objects.filter(entity=entity, code="entity.super_admin").first()
        if entity_super_admin:
            cls._grant_permissions(
                role=entity_super_admin,
                permissions=permission_map.values(),
            )

        for spec in cls.ROLE_SPECS:
            role, _ = Role.objects.get_or_create(
                entity=entity,
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "description": spec["name"],
                    "role_level": Role.LEVEL_ENTITY,
                    "is_system_role": True,
                    "is_assignable": True,
                    "priority": spec["priority"],
                    "createdby": actor,
                    "metadata": {"seed": cls.SEED_TAG, "catalog_version": cls.CATALOG_VERSION},
                    "isactive": True,
                },
            )
            role.name = spec["name"]
            role.description = spec["name"]
            role.role_level = Role.LEVEL_ENTITY
            role.is_system_role = True
            role.is_assignable = True
            role.priority = spec["priority"]
            role.isactive = True
            if actor and not role.createdby_id:
                role.createdby = actor
            role.metadata = {
                **(role.metadata or {}),
                "seed": cls.SEED_TAG,
                "catalog_version": cls.CATALOG_VERSION,
            }
            role.save()

            if spec["permissions"] == "__all__":
                target_permissions = permission_map.values()
            else:
                target_permissions = [permission_map[code] for code in spec["permissions"]]

            added_count = cls._grant_permissions(role=role, permissions=target_permissions)
            summary_roles.append(
                {
                    "role_id": role.id,
                    "role_code": role.code,
                    "role_name": role.name,
                    "permission_count": len(list(target_permissions)),
                    "added_permissions": added_count,
                }
            )

        return {
            "entity_id": entity.id,
            "permission_count": len(permission_map),
            "menu_count": len(catalog["menus"]),
            "roles": summary_roles,
        }

    @staticmethod
    def _grant_permissions(*, role, permissions):
        permission_ids = set(permission.id for permission in permissions)
        existing = set(
            RolePermission.objects.filter(role=role, permission_id__in=permission_ids).values_list("permission_id", flat=True)
        )
        missing = permission_ids - existing
        if missing:
            RolePermission.objects.bulk_create(
                [
                    RolePermission(
                        role=role,
                        permission_id=permission_id,
                        effect=RolePermission.EFFECT_ALLOW,
                        metadata={"seed": PayrollRBACSeedService.SEED_TAG, "catalog_version": PayrollRBACSeedService.CATALOG_VERSION},
                        isactive=True,
                    )
                    for permission_id in missing
                ]
            )
        RolePermission.objects.filter(role=role, permission_id__in=permission_ids).update(isactive=True, effect=RolePermission.EFFECT_ALLOW)
        return len(missing)
