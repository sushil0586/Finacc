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
        {"name": "HRMS User", "code": "hrms_user", "priority": 90, "template": "hrms_user"},
        {"name": "Compliance User", "code": "compliance_user", "priority": 100, "template": "compliance_user"},
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
        ("payroll.contract_profile.view", "View Contract Payroll Profiles", "payroll", "contract_profile", "view"),
        ("payroll.contract_profile.manage", "Manage Contract Payroll Profiles", "payroll", "contract_profile", "manage"),
        ("payroll.contract_profile.create", "Create Contract Payroll Profiles", "payroll", "contract_profile", "create"),
        ("payroll.contract_profile.edit", "Edit Contract Payroll Profiles", "payroll", "contract_profile", "edit"),
        ("payroll.contract_salary_assignment.view", "View Contract Salary Assignments", "payroll", "contract_salary_assignment", "view"),
        ("payroll.contract_salary_assignment.manage", "Manage Contract Salary Assignments", "payroll", "contract_salary_assignment", "manage"),
        ("payroll.contract_salary_assignment.create", "Create Contract Salary Assignments", "payroll", "contract_salary_assignment", "create"),
        ("payroll.contract_salary_assignment.edit", "Edit Contract Salary Assignments", "payroll", "contract_salary_assignment", "edit"),
        ("payroll.attendance_summaries.view", "View Attendance Summaries", "payroll", "attendance_summaries", "view"),
        ("payroll.attendance_summaries.create", "Create Attendance Summaries", "payroll", "attendance_summaries", "create"),
        ("payroll.attendance_summaries.update", "Update Attendance Summaries", "payroll", "attendance_summaries", "update"),
        ("payroll.attendance_summaries.delete", "Delete Attendance Summaries", "payroll", "attendance_summaries", "delete"),
        ("payroll.attendance_adjustments.view", "View Attendance Adjustments", "payroll", "attendance_adjustments", "view"),
        ("payroll.attendance_adjustments.create", "Create Attendance Adjustments", "payroll", "attendance_adjustments", "create"),
        ("payroll.attendance_adjustments.update", "Update Attendance Adjustments", "payroll", "attendance_adjustments", "update"),
        ("payroll.attendance_adjustments.delete", "Delete Attendance Adjustments", "payroll", "attendance_adjustments", "delete"),
        ("payroll.policies.view", "View Payroll Policies", "payroll", "policies", "view"),
        ("payroll.policies.create", "Create Payroll Policies", "payroll", "policies", "create"),
        ("payroll.policies.update", "Update Payroll Policies", "payroll", "policies", "update"),
        ("payroll.policies.delete", "Delete Payroll Policies", "payroll", "policies", "delete"),
        ("payroll.recurring_pay_items.view", "View Recurring Pay Items", "payroll", "recurring_pay_items", "view"),
        ("payroll.recurring_pay_items.create", "Create Recurring Pay Items", "payroll", "recurring_pay_items", "create"),
        ("payroll.recurring_pay_items.update", "Update Recurring Pay Items", "payroll", "recurring_pay_items", "update"),
        ("payroll.recurring_pay_items.delete", "Delete Recurring Pay Items", "payroll", "recurring_pay_items", "delete"),
        ("payroll.one_time_pay_items.view", "View One-Time Pay Items", "payroll", "one_time_pay_items", "view"),
        ("payroll.one_time_pay_items.create", "Create One-Time Pay Items", "payroll", "one_time_pay_items", "create"),
        ("payroll.one_time_pay_items.update", "Update One-Time Pay Items", "payroll", "one_time_pay_items", "update"),
        ("payroll.one_time_pay_items.delete", "Delete One-Time Pay Items", "payroll", "one_time_pay_items", "delete"),
        ("payroll.statutory_schemes.view", "View Statutory Schemes", "payroll", "statutory_schemes", "view"),
        ("payroll.statutory_schemes.create", "Create Statutory Schemes", "payroll", "statutory_schemes", "create"),
        ("payroll.statutory_schemes.update", "Update Statutory Schemes", "payroll", "statutory_schemes", "update"),
        ("payroll.statutory_schemes.delete", "Delete Statutory Schemes", "payroll", "statutory_schemes", "delete"),
        ("payroll.statutory_rules.view", "View Statutory Rules", "payroll", "statutory_rules", "view"),
        ("payroll.statutory_rules.create", "Create Statutory Rules", "payroll", "statutory_rules", "create"),
        ("payroll.statutory_rules.update", "Update Statutory Rules", "payroll", "statutory_rules", "update"),
        ("payroll.statutory_rules.delete", "Delete Statutory Rules", "payroll", "statutory_rules", "delete"),
        ("payroll.statutory_registrations.view", "View Statutory Registrations", "payroll", "statutory_registrations", "view"),
        ("payroll.statutory_registrations.create", "Create Statutory Registrations", "payroll", "statutory_registrations", "create"),
        ("payroll.statutory_registrations.update", "Update Statutory Registrations", "payroll", "statutory_registrations", "update"),
        ("payroll.statutory_registrations.delete", "Delete Statutory Registrations", "payroll", "statutory_registrations", "delete"),
        ("payroll.contract_statutory_profiles.view", "View Contract Statutory Profiles", "payroll", "contract_statutory_profiles", "view"),
        ("payroll.contract_statutory_profiles.create", "Create Contract Statutory Profiles", "payroll", "contract_statutory_profiles", "create"),
        ("payroll.contract_statutory_profiles.update", "Update Contract Statutory Profiles", "payroll", "contract_statutory_profiles", "update"),
        ("payroll.contract_statutory_profiles.delete", "Delete Contract Statutory Profiles", "payroll", "contract_statutory_profiles", "delete"),
        ("payroll.runtime_readiness.view", "View Payroll Runtime Readiness", "payroll", "runtime_readiness", "view"),
        ("payroll.period.view", "View Payroll Periods", "payroll", "period", "view"),
        ("payroll.period.manage", "Manage Payroll Periods", "payroll", "period", "manage"),
        ("payroll.period.create", "Create Payroll Periods", "payroll", "period", "create"),
        ("payroll.period.edit", "Edit Payroll Periods", "payroll", "period", "edit"),
        ("payroll.global_component_group.view", "View Global Payroll Component Groups", "payroll", "global_component_group", "view"),
        ("payroll.global_component_group.manage", "Manage Global Payroll Component Groups", "payroll", "global_component_group", "manage"),
        ("payroll.global_component_group.create", "Create Global Payroll Component Groups", "payroll", "global_component_group", "create"),
        ("payroll.global_component_group.edit", "Edit Global Payroll Component Groups", "payroll", "global_component_group", "edit"),
        ("payroll.global_component.view", "View Global Payroll Components", "payroll", "global_component", "view"),
        ("payroll.global_component.manage", "Manage Global Payroll Components", "payroll", "global_component", "manage"),
        ("payroll.global_component.create", "Create Global Payroll Components", "payroll", "global_component", "create"),
        ("payroll.global_component.edit", "Edit Global Payroll Components", "payroll", "global_component", "edit"),
        ("payroll.global_salary_template.view", "View Global Salary Templates", "payroll", "global_salary_template", "view"),
        ("payroll.global_salary_template.manage", "Manage Global Salary Templates", "payroll", "global_salary_template", "manage"),
        ("payroll.global_salary_template.create", "Create Global Salary Templates", "payroll", "global_salary_template", "create"),
        ("payroll.global_salary_template.edit", "Edit Global Salary Templates", "payroll", "global_salary_template", "edit"),
        ("payroll.global_salary_template.adopt", "Adopt Global Salary Templates", "payroll", "global_salary_template", "adopt"),
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
            "code": "payroll.attendance-summaries",
            "name": "Attendance Summaries",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/attendance-summaries",
            "route_name": "payroll-attendance-summaries",
            "sort_order": 4,
            "icon": "calendar-check-2",
            "parent_code": "payroll",
            "permission_code": "payroll.attendance_summaries.view",
        },
        {
            "code": "payroll.attendance-adjustments",
            "name": "Attendance Adjustments",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/attendance-adjustments",
            "route_name": "payroll-attendance-adjustments",
            "sort_order": 5,
            "icon": "file-pen-line",
            "parent_code": "payroll",
            "permission_code": "payroll.attendance_adjustments.view",
        },
        {
            "code": "payroll.policies",
            "name": "Payroll Policies",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/policies",
            "route_name": "payroll-policies",
            "sort_order": 6,
            "icon": "sliders-vertical",
            "parent_code": "payroll",
            "permission_code": "payroll.policies.view",
        },
        {
            "code": "payroll.recurring-pay-items",
            "name": "Recurring Pay Items",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/recurring-pay-items",
            "route_name": "payroll-recurring-pay-items",
            "sort_order": 9,
            "icon": "refresh-ccw",
            "parent_code": "payroll",
            "permission_code": "payroll.recurring_pay_items.view",
        },
        {
            "code": "payroll.one-time-pay-items",
            "name": "One-Time Pay Items",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/one-time-pay-items",
            "route_name": "payroll-one-time-pay-items",
            "sort_order": 10,
            "icon": "circle-dollar-sign",
            "parent_code": "payroll",
            "permission_code": "payroll.one_time_pay_items.view",
        },
        {
            "code": "payroll.statutory-schemes",
            "name": "Statutory Schemes",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/statutory/schemes",
            "route_name": "payroll-statutory-schemes",
            "sort_order": 5,
            "icon": "shield-ellipsis",
            "parent_code": "payroll",
            "permission_code": "payroll.statutory_schemes.view",
        },
        {
            "code": "payroll.statutory-rules",
            "name": "Statutory Rules",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/statutory/rules",
            "route_name": "payroll-statutory-rules",
            "sort_order": 6,
            "icon": "scale",
            "parent_code": "payroll",
            "permission_code": "payroll.statutory_rules.view",
        },
        {
            "code": "payroll.statutory-registrations",
            "name": "Statutory Registrations",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/statutory/registrations",
            "route_name": "payroll-statutory-registrations",
            "sort_order": 7,
            "icon": "file-check-2",
            "parent_code": "payroll",
            "permission_code": "payroll.statutory_registrations.view",
        },
        {
            "code": "payroll.contract-statutory-profiles",
            "name": "Contract Statutory Profiles",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/statutory/contract-profiles",
            "route_name": "payroll-contract-statutory-profiles",
            "sort_order": 8,
            "icon": "shield-check",
            "parent_code": "payroll",
            "permission_code": "payroll.contract_statutory_profiles.view",
        },
        {
            "code": "payroll.salary-structures",
            "name": "Salary Structures",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/salary-structures",
            "route_name": "payroll-salary-structures",
            "sort_order": 11,
            "icon": "network",
            "parent_code": "payroll",
            "permission_code": "payroll.structure.view",
        },
        {
            "code": "payroll.contract-profiles",
            "name": "Contract Payroll Profiles",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/contract-profiles",
            "route_name": "payroll-contract-profiles",
            "sort_order": 13,
            "icon": "file-user",
            "parent_code": "payroll",
            "permission_code": "payroll.contract_profile.view",
        },
        {
            "code": "payroll.contract-tax-declarations",
            "name": "Contract Tax Declarations",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/contract-tax-declarations",
            "route_name": "payroll-contract-tax-declarations",
            "sort_order": 14,
            "icon": "receipt-text",
            "parent_code": "payroll",
            "permission_code": "payroll.contract_profile.view",
        },
        {
            "code": "payroll.contract-input-snapshots",
            "name": "Contract Input Snapshots",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/contract-input-snapshots",
            "route_name": "payroll-contract-input-snapshots",
            "sort_order": 15,
            "icon": "database-zap",
            "parent_code": "payroll",
            "permission_code": "payroll.contract_profile.view",
        },
        {
            "code": "payroll.periods",
            "name": "Periods",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/periods",
            "route_name": "payroll-periods",
            "sort_order": 16,
            "icon": "calendar-days",
            "parent_code": "payroll",
            "permission_code": "payroll.period.view",
        },
        {
            "code": "payroll.runtime-readiness",
            "name": "Payroll Readiness",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/runtime/readiness",
            "route_name": "payroll-runtime-readiness",
            "sort_order": 17,
            "icon": "clipboard-check",
            "parent_code": "payroll",
            "permission_code": "payroll.runtime_readiness.view",
        },
        {
            "code": "payroll.approval-policies",
            "name": "Approval Policies",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/approval-policies",
            "route_name": "payroll-approval-policies",
            "sort_order": 18,
            "icon": "badge-check",
            "parent_code": "payroll",
            "permission_code": "payroll.policies.view",
        },
        {
            "code": "payroll.reports",
            "name": "Reports",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/reports",
            "route_name": "payroll-reports",
            "sort_order": 19,
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
            "sort_order": 20,
            "icon": "clipboard-check",
            "parent_code": "payroll",
            "permission_code": "payroll.contract_profile.manage",
        },
        {
            "code": "payroll.global-component-groups",
            "name": "Global Component Groups",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/global/component-groups",
            "route_name": "payroll-global-component-groups",
            "sort_order": 21,
            "icon": "boxes",
            "parent_code": "payroll",
            "permission_code": "payroll.global_component_group.view",
        },
        {
            "code": "payroll.global-components",
            "name": "Global Components",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/global/components",
            "route_name": "payroll-global-components",
            "sort_order": 22,
            "icon": "package-plus",
            "parent_code": "payroll",
            "permission_code": "payroll.global_component.view",
        },
        {
            "code": "payroll.global-salary-templates",
            "name": "Global Salary Templates",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/payroll/global/salary-templates",
            "route_name": "payroll-global-salary-templates",
            "sort_order": 23,
            "icon": "files",
            "parent_code": "payroll",
            "permission_code": "payroll.global_salary_template.view",
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
                "payroll.policies.view",
                "payroll.policies.create",
                "payroll.policies.update",
                "payroll.policies.delete",
                "payroll.statutory_schemes.view",
                "payroll.statutory_schemes.create",
                "payroll.statutory_schemes.update",
                "payroll.statutory_schemes.delete",
                "payroll.statutory_rules.view",
                "payroll.statutory_rules.create",
                "payroll.statutory_rules.update",
                "payroll.statutory_rules.delete",
                "payroll.statutory_registrations.view",
                "payroll.statutory_registrations.create",
                "payroll.statutory_registrations.update",
                "payroll.statutory_registrations.delete",
                "payroll.contract_statutory_profiles.view",
                "payroll.contract_statutory_profiles.create",
                "payroll.contract_statutory_profiles.update",
                "payroll.contract_statutory_profiles.delete",
                "payroll.runtime_readiness.view",
                "payroll.contract_profile.view",
                "payroll.contract_profile.manage",
                "payroll.contract_profile.create",
                "payroll.contract_profile.edit",
                "payroll.contract_salary_assignment.view",
                "payroll.contract_salary_assignment.manage",
                "payroll.contract_salary_assignment.create",
                "payroll.contract_salary_assignment.edit",
                "payroll.period.manage",
                "payroll.period.create",
                "payroll.period.edit",
                "payroll.global_component_group.view",
                "payroll.global_component_group.manage",
                "payroll.global_component_group.create",
                "payroll.global_component_group.edit",
                "payroll.global_component.view",
                "payroll.global_component.manage",
                "payroll.global_component.create",
                "payroll.global_component.edit",
                "payroll.global_salary_template.view",
                "payroll.global_salary_template.manage",
                "payroll.global_salary_template.create",
                "payroll.global_salary_template.edit",
                "payroll.global_salary_template.adopt",
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
                "payroll.policies.view",
                "payroll.statutory_schemes.view",
                "payroll.statutory_rules.view",
                "payroll.statutory_registrations.view",
                "payroll.contract_statutory_profiles.view",
                "payroll.runtime_readiness.view",
                "payroll.contract_profile.view",
                "payroll.contract_salary_assignment.view",
                "payroll.period.view",
                "payroll.global_component_group.view",
                "payroll.global_component.view",
                "payroll.global_salary_template.view",
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


class HrmsRBACSeedService:
    CATALOG_VERSION = "hrms_rbac_2026_05"
    SEED_TAG = "hrms_rbac_seed"

    PERMISSION_SPECS = (
        ("hrms.organization_unit.view", "View Organization Units", "hrms", "organization_unit", "view"),
        ("hrms.organization_unit.create", "Create Organization Units", "hrms", "organization_unit", "create"),
        ("hrms.organization_unit.update", "Update Organization Units", "hrms", "organization_unit", "update"),
        ("hrms.organization_unit.delete", "Delete Organization Units", "hrms", "organization_unit", "delete"),
        ("hrms.employee.view", "View Employees", "hrms", "employee", "view"),
        ("hrms.employee.create", "Create Employees", "hrms", "employee", "create"),
        ("hrms.employee.update", "Update Employees", "hrms", "employee", "update"),
        ("hrms.employee.delete", "Delete Employees", "hrms", "employee", "delete"),
        ("hrms.employment_contract.view", "View Employment Contracts", "hrms", "employment_contract", "view"),
        ("hrms.employment_contract.create", "Create Employment Contracts", "hrms", "employment_contract", "create"),
        ("hrms.employment_contract.update", "Update Employment Contracts", "hrms", "employment_contract", "update"),
        ("hrms.employment_contract.delete", "Delete Employment Contracts", "hrms", "employment_contract", "delete"),
        ("hrms.shift.view", "View Shifts", "hrms", "shift", "view"),
        ("hrms.shift.create", "Create Shifts", "hrms", "shift", "create"),
        ("hrms.shift.update", "Update Shifts", "hrms", "shift", "update"),
        ("hrms.shift.delete", "Delete Shifts", "hrms", "shift", "delete"),
        ("hrms.holiday_calendar.view", "View Holiday Calendars", "hrms", "holiday_calendar", "view"),
        ("hrms.holiday_calendar.create", "Create Holiday Calendars", "hrms", "holiday_calendar", "create"),
        ("hrms.holiday_calendar.update", "Update Holiday Calendars", "hrms", "holiday_calendar", "update"),
        ("hrms.holiday_calendar.delete", "Delete Holiday Calendars", "hrms", "holiday_calendar", "delete"),
        ("hrms.onboarding.view", "View HRMS Onboarding", "hrms", "onboarding", "view"),
        ("hrms.onboarding.adopt", "Adopt HRMS Templates", "hrms", "onboarding", "adopt"),
        ("hrms.onboarding.update", "Update HRMS Setup", "hrms", "onboarding", "update"),
        ("hrms.attendance_entry.view", "View Daily Attendance", "hrms", "attendance_entry", "view"),
        ("hrms.attendance_entry.create", "Create Daily Attendance", "hrms", "attendance_entry", "create"),
        ("hrms.attendance_entry.update", "Update Daily Attendance", "hrms", "attendance_entry", "update"),
        ("hrms.attendance_import_batch.view", "View Attendance Import Batches", "hrms", "attendance_import_batch", "view"),
        ("hrms.attendance_import_batch.create", "Create Attendance Import Batches", "hrms", "attendance_import_batch", "create"),
        ("hrms.attendance_summary.view", "View Attendance Summaries", "hrms", "attendance_summary", "view"),
        ("hrms.attendance_payroll_period.view", "View Attendance Payroll Periods", "hrms", "attendance_payroll_period", "view"),
        ("hrms.attendance_approval.view", "View Attendance Approvals", "hrms", "attendance_approval", "view"),
        ("hrms.attendance_approval.submit", "Submit Attendance Approvals", "hrms", "attendance_approval", "submit"),
        ("hrms.attendance_approval.approve", "Approve Attendance Approvals", "hrms", "attendance_approval", "approve"),
        ("hrms.attendance_approval.reject", "Reject Attendance Approvals", "hrms", "attendance_approval", "reject"),
        ("hrms.attendance_monthly_close.view", "View Attendance Monthly Closes", "hrms", "attendance_monthly_close", "view"),
        ("hrms.attendance_monthly_close.create", "Create Attendance Monthly Closes", "hrms", "attendance_monthly_close", "create"),
        ("hrms.attendance_monthly_close.submit", "Submit Attendance Monthly Closes", "hrms", "attendance_monthly_close", "submit"),
        ("hrms.attendance_monthly_close.approve", "Approve Attendance Monthly Closes", "hrms", "attendance_monthly_close", "approve"),
        ("hrms.attendance_monthly_close.close", "Close Attendance Months", "hrms", "attendance_monthly_close", "close"),
        ("hrms.leave_policy.view", "View Leave Policies", "hrms", "leave_policy", "view"),
        ("hrms.leave_policy.update", "Update Leave Policies", "hrms", "leave_policy", "update"),
        ("hrms.leave_balance.view", "View Leave Balances", "hrms", "leave_balance", "view"),
        ("hrms.leave_ledger.view", "View Leave Ledger", "hrms", "leave_ledger", "view"),
        ("hrms.leave_application.view", "View Leave Applications", "hrms", "leave_application", "view"),
        ("hrms.leave_application.create", "Create Leave Applications", "hrms", "leave_application", "create"),
        ("hrms.leave_application.approve", "Approve Leave Applications", "hrms", "leave_application", "approve"),
        ("hrms.leave_application.reject", "Reject Leave Applications", "hrms", "leave_application", "reject"),
        ("hrms.leave_application.cancel", "Cancel Leave Applications", "hrms", "leave_application", "cancel"),
    )

    MENU_SPECS = (
        {
            "code": "hrms",
            "name": "HRMS",
            "menu_type": Menu.TYPE_GROUP,
            "route_path": "/hrms",
            "route_name": "hrms",
            "sort_order": 41,
            "icon": "people",
            "parent_code": None,
            "permission_code": "hrms.employee.view",
        },
        {
            "code": "hrms.organization_units",
            "name": "Organization Units",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/organization-units",
            "route_name": "hrms-organization-units",
            "sort_order": 1,
            "icon": "diagram-3",
            "parent_code": "hrms",
            "permission_code": "hrms.organization_unit.view",
        },
        {
            "code": "hrms.employees",
            "name": "Employees",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/employees",
            "route_name": "hrms-employees",
            "sort_order": 2,
            "icon": "person-vcard",
            "parent_code": "hrms",
            "permission_code": "hrms.employee.view",
        },
        {
            "code": "hrms.contracts",
            "name": "Employment Contracts",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/contracts",
            "route_name": "hrms-contracts",
            "sort_order": 3,
            "icon": "file-earmark-text",
            "parent_code": "hrms",
            "permission_code": "hrms.employment_contract.view",
        },
        {
            "code": "hrms.shifts",
            "name": "Shifts",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/shifts",
            "route_name": "hrms-shifts",
            "sort_order": 4,
            "icon": "clock-history",
            "parent_code": "hrms",
            "permission_code": "hrms.shift.view",
        },
        {
            "code": "hrms.holiday_calendars",
            "name": "Holiday Calendars",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/holiday-calendars",
            "route_name": "hrms-holiday-calendars",
            "sort_order": 5,
            "icon": "calendar4-week",
            "parent_code": "hrms",
            "permission_code": "hrms.holiday_calendar.view",
        },
        {
            "code": "hrms.onboarding",
            "name": "Onboarding",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/onboarding",
            "route_name": "hrms-onboarding",
            "sort_order": 6,
            "icon": "clipboard-check",
            "parent_code": "hrms",
            "permission_code": "hrms.onboarding.view",
        },
        {
            "code": "hrms.attendance",
            "name": "Attendance",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/attendance",
            "route_name": "hrms-attendance",
            "sort_order": 7,
            "icon": "calendar-check-2",
            "parent_code": "hrms",
            "permission_code": "hrms.attendance_summary.view",
        },
        {
            "code": "hrms.attendance_monthly_summary",
            "name": "Attendance Summary",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/attendance-monthly-summary",
            "route_name": "hrms-attendance-monthly-summary",
            "sort_order": 8,
            "icon": "calendar3",
            "parent_code": "hrms",
            "permission_code": "hrms.attendance_summary.view",
        },
        {
            "code": "hrms.attendance_import",
            "name": "Attendance Import",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/attendance-import",
            "route_name": "hrms-attendance-import",
            "sort_order": 9,
            "icon": "upload",
            "parent_code": "hrms",
            "permission_code": "hrms.attendance_import_batch.view",
        },
        {
            "code": "hrms.attendance_approval_close",
            "name": "Attendance Approval & Close",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/attendance-approval-close",
            "route_name": "hrms-attendance-approval-close",
            "sort_order": 10,
            "icon": "check2-square",
            "parent_code": "hrms",
            "permission_code": "hrms.attendance_monthly_close.view",
        },
        {
            "code": "hrms.leave",
            "name": "Leave",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/leave",
            "route_name": "hrms-leave",
            "sort_order": 11,
            "icon": "briefcase",
            "parent_code": "hrms",
            "permission_code": "hrms.leave_application.view",
        },
        {
            "code": "hrms.leave_policy_rules",
            "name": "Leave Policy Rules",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/leave-policy-rules",
            "route_name": "hrms-leave-policy-rules",
            "sort_order": 12,
            "icon": "sliders",
            "parent_code": "hrms",
            "permission_code": "hrms.leave_policy.view",
        },
        {
            "code": "hrms.leave_balance_ledger",
            "name": "Leave Balance Ledger",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/leave-balance-ledger",
            "route_name": "hrms-leave-balance-ledger",
            "sort_order": 13,
            "icon": "journal-text",
            "parent_code": "hrms",
            "permission_code": "hrms.leave_balance.view",
        },
        {
            "code": "hrms.ess_leave_application",
            "name": "ESS Leave Application",
            "menu_type": Menu.TYPE_SCREEN,
            "route_path": "/hrms/ess-leave-application",
            "route_name": "hrms-ess-leave-application",
            "sort_order": 14,
            "icon": "person-check",
            "parent_code": "hrms",
            "permission_code": "hrms.leave_application.view",
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
            "name": "HRMS Operator",
            "code": "hrms_operator",
            "priority": 65,
            "permissions": {
                "hrms.organization_unit.view",
                "hrms.organization_unit.create",
                "hrms.organization_unit.update",
                "hrms.organization_unit.delete",
                "hrms.employee.view",
                "hrms.employee.create",
                "hrms.employee.update",
                "hrms.employee.delete",
                "hrms.employment_contract.view",
                "hrms.employment_contract.create",
                "hrms.employment_contract.update",
                "hrms.employment_contract.delete",
                "hrms.shift.view",
                "hrms.shift.create",
                "hrms.shift.update",
                "hrms.shift.delete",
                "hrms.holiday_calendar.view",
                "hrms.holiday_calendar.create",
                "hrms.holiday_calendar.update",
                "hrms.holiday_calendar.delete",
                "hrms.onboarding.view",
                "hrms.onboarding.adopt",
                "hrms.onboarding.update",
                "hrms.attendance_entry.view",
                "hrms.attendance_entry.create",
                "hrms.attendance_entry.update",
                "hrms.attendance_import_batch.view",
                "hrms.attendance_import_batch.create",
                "hrms.attendance_summary.view",
                "hrms.attendance_payroll_period.view",
                "hrms.attendance_approval.view",
                "hrms.attendance_approval.submit",
                "hrms.attendance_monthly_close.view",
                "hrms.attendance_monthly_close.create",
                "hrms.attendance_monthly_close.submit",
                "hrms.leave_policy.view",
                "hrms.leave_policy.update",
                "hrms.leave_balance.view",
                "hrms.leave_ledger.view",
                "hrms.leave_application.view",
                "hrms.leave_application.create",
                "hrms.leave_application.cancel",
            },
        },
        {
            "name": "HRMS Approver",
            "code": "hrms_approver",
            "priority": 70,
            "permissions": {
                "hrms.attendance_approval.view",
                "hrms.attendance_approval.approve",
                "hrms.attendance_approval.reject",
                "hrms.attendance_monthly_close.view",
                "hrms.attendance_monthly_close.approve",
                "hrms.attendance_monthly_close.close",
                "hrms.leave_application.view",
                "hrms.leave_application.approve",
                "hrms.leave_application.reject",
                "hrms.leave_balance.view",
                "hrms.leave_ledger.view",
            },
        },
        {
            "name": "HRMS Read-only Reviewer",
            "code": "hrms_read_only_reviewer",
            "priority": 75,
            "permissions": {
                "hrms.organization_unit.view",
                "hrms.employee.view",
                "hrms.employment_contract.view",
                "hrms.shift.view",
                "hrms.holiday_calendar.view",
                "hrms.onboarding.view",
                "hrms.attendance_entry.view",
                "hrms.attendance_import_batch.view",
                "hrms.attendance_summary.view",
                "hrms.attendance_payroll_period.view",
                "hrms.attendance_approval.view",
                "hrms.attendance_monthly_close.view",
                "hrms.leave_policy.view",
                "hrms.leave_balance.view",
                "hrms.leave_ledger.view",
                "hrms.leave_application.view",
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

        entity_super_admin = Role.objects.filter(entity=entity, code="entity.super_admin").first()
        if entity_super_admin:
            cls._grant_permissions(role=entity_super_admin, permissions=permission_map.values())

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

            target_permissions = permission_map.values() if spec["permissions"] == "__all__" else [permission_map[code] for code in spec["permissions"]]
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
                        metadata={"seed": HrmsRBACSeedService.SEED_TAG, "catalog_version": HrmsRBACSeedService.CATALOG_VERSION},
                        isactive=True,
                    )
                    for permission_id in missing
                ]
            )
        RolePermission.objects.filter(role=role, permission_id__in=permission_ids).update(isactive=True, effect=RolePermission.EFFECT_ALLOW)
        return len(missing)
