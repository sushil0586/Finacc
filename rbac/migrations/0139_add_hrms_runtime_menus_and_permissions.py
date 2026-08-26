from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "hrms_runtime_menus_permissions"
CATALOG_VERSION = "hrms_runtime_menus_permissions_2026_08_25"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


ROOT_MENU = {
    "code": "hrms",
    "name": "HRMS",
    "route_path": "/hrms",
    "route_name": "hrms",
    "icon": "people",
    "sort_order": 41,
}


SCREEN_SPECS = (
    {
        "menu_code": "hrms.onboarding",
        "name": "Onboarding",
        "route_path": "/hrms/onboarding",
        "route_name": "hrms-onboarding",
        "icon": "magic",
        "sort_order": 0,
        "permissions": (
            ("hrms.onboarding.view", "View HRMS Onboarding", "onboarding", "view"),
            ("hrms.onboarding.adopt", "Adopt HRMS Onboarding Templates", "onboarding", "adopt"),
            ("hrms.onboarding.update", "Update HRMS Onboarding Setup", "onboarding", "update"),
        ),
    },
    {
        "menu_code": "hrms.attendance_daily_grid",
        "name": "Daily Attendance Grid",
        "route_path": "/hrms/attendance-daily-grid",
        "route_name": "hrms-attendance-daily-grid",
        "icon": "calendar-check",
        "sort_order": 10,
        "permissions": (
            ("hrms.attendance_entry.view", "View HRMS Attendance Entries", "attendance_entry", "view"),
            ("hrms.attendance_entry.create", "Create HRMS Attendance Entries", "attendance_entry", "create"),
            ("hrms.attendance_entry.update", "Update HRMS Attendance Entries", "attendance_entry", "update"),
            ("hrms.attendance_payroll_period.view", "View HRMS Attendance Payroll Periods", "attendance_payroll_period", "view"),
        ),
    },
    {
        "menu_code": "hrms.attendance_monthly_summary",
        "name": "Monthly Attendance Summary",
        "route_path": "/hrms/attendance-monthly-summary",
        "route_name": "hrms-attendance-monthly-summary",
        "icon": "calendar2-range",
        "sort_order": 11,
        "permissions": (
            ("hrms.attendance_summary.view", "View HRMS Attendance Summary", "attendance_summary", "view"),
            ("hrms.attendance_payroll_period.view", "View HRMS Attendance Payroll Periods", "attendance_payroll_period", "view"),
        ),
    },
    {
        "menu_code": "hrms.attendance_import",
        "name": "Attendance Import",
        "route_path": "/hrms/attendance-import",
        "route_name": "hrms-attendance-import",
        "icon": "upload",
        "sort_order": 12,
        "permissions": (
            ("hrms.attendance_import_batch.view", "View HRMS Attendance Imports", "attendance_import_batch", "view"),
            ("hrms.attendance_import_batch.create", "Create HRMS Attendance Imports", "attendance_import_batch", "create"),
            ("hrms.attendance_payroll_period.view", "View HRMS Attendance Payroll Periods", "attendance_payroll_period", "view"),
        ),
    },
    {
        "menu_code": "hrms.attendance_approval_close",
        "name": "Attendance Approval and Close",
        "route_path": "/hrms/attendance-approval-close",
        "route_name": "hrms-attendance-approval-close",
        "icon": "clipboard-check",
        "sort_order": 13,
        "permissions": (
            ("hrms.attendance_approval.view", "View HRMS Attendance Approvals", "attendance_approval", "view"),
            ("hrms.attendance_approval.submit", "Submit HRMS Attendance Approvals", "attendance_approval", "submit"),
            ("hrms.attendance_approval.approve", "Approve HRMS Attendance", "attendance_approval", "approve"),
            ("hrms.attendance_approval.reject", "Reject HRMS Attendance", "attendance_approval", "reject"),
            ("hrms.attendance_monthly_close.view", "View HRMS Attendance Monthly Close", "attendance_monthly_close", "view"),
            ("hrms.attendance_monthly_close.create", "Create HRMS Attendance Monthly Close", "attendance_monthly_close", "create"),
            ("hrms.attendance_monthly_close.submit", "Submit HRMS Attendance Monthly Close", "attendance_monthly_close", "submit"),
            ("hrms.attendance_monthly_close.approve", "Approve HRMS Attendance Monthly Close", "attendance_monthly_close", "approve"),
            ("hrms.attendance_monthly_close.close", "Close HRMS Attendance Month", "attendance_monthly_close", "close"),
            ("hrms.attendance_summary.view", "View HRMS Attendance Summary", "attendance_summary", "view"),
            ("hrms.attendance_payroll_period.view", "View HRMS Attendance Payroll Periods", "attendance_payroll_period", "view"),
        ),
    },
    {
        "menu_code": "hrms.employee_attendance_view",
        "name": "My Attendance",
        "route_path": "/hrms/employee-attendance-view",
        "route_name": "hrms-employee-attendance-view",
        "icon": "person-check",
        "sort_order": 14,
        "permissions": (
            ("hrms.attendance_entry.view", "View HRMS Attendance Entries", "attendance_entry", "view"),
            ("hrms.attendance_summary.view", "View HRMS Attendance Summary", "attendance_summary", "view"),
            ("hrms.attendance_payroll_period.view", "View HRMS Attendance Payroll Periods", "attendance_payroll_period", "view"),
        ),
    },
    {
        "menu_code": "hrms.leave_policy_rules",
        "name": "Leave Policy Rules",
        "route_path": "/hrms/leave-policy-rules",
        "route_name": "hrms-leave-policy-rules",
        "icon": "sliders",
        "sort_order": 20,
        "permissions": (
            ("hrms.leave_policy.view", "View HRMS Leave Policies", "leave_policy", "view"),
            ("hrms.leave_policy.update", "Update HRMS Leave Policies", "leave_policy", "update"),
        ),
    },
    {
        "menu_code": "hrms.ess_leave_application",
        "name": "My Leave",
        "route_path": "/hrms/ess-leave-application",
        "route_name": "hrms-ess-leave-application",
        "icon": "calendar-plus",
        "sort_order": 21,
        "permissions": (
            ("hrms.leave_application.view", "View HRMS Leave Applications", "leave_application", "view"),
            ("hrms.leave_application.create", "Create HRMS Leave Applications", "leave_application", "create"),
            ("hrms.leave_application.cancel", "Cancel HRMS Leave Applications", "leave_application", "cancel"),
            ("hrms.leave_balance.view", "View HRMS Leave Balances", "leave_balance", "view"),
        ),
    },
    {
        "menu_code": "hrms.manager_leave_approval",
        "name": "Leave Approval",
        "route_path": "/hrms/manager-leave-approval",
        "route_name": "hrms-manager-leave-approval",
        "icon": "person-check-fill",
        "sort_order": 22,
        "permissions": (
            ("hrms.leave_application.view", "View HRMS Leave Applications", "leave_application", "view"),
            ("hrms.leave_application.approve", "Approve HRMS Leave Applications", "leave_application", "approve"),
            ("hrms.leave_application.reject", "Reject HRMS Leave Applications", "leave_application", "reject"),
        ),
    },
    {
        "menu_code": "hrms.leave_balance_ledger",
        "name": "Leave Ledger",
        "route_path": "/hrms/leave-balance-ledger",
        "route_name": "hrms-leave-balance-ledger",
        "icon": "journal-text",
        "sort_order": 23,
        "permissions": (
            ("hrms.leave_balance.view", "View HRMS Leave Balances", "leave_balance", "view"),
            ("hrms.leave_ledger.view", "View HRMS Leave Ledger", "leave_ledger", "view"),
            ("hrms.leave_policy.update", "Update HRMS Leave Policies", "leave_policy", "update"),
        ),
    },
)


def _upsert_permission(Permission, *, code, name, resource, action, menu_code):
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "module": "hrms",
            "resource": resource,
            "action": action,
            "description": name,
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": menu_code,
            },
            "isactive": True,
        },
    )
    return permission.id


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    root_menu, _ = Menu.objects.update_or_create(
        code=ROOT_MENU["code"],
        defaults={
            "name": ROOT_MENU["name"],
            "menu_type": "group",
            "route_path": ROOT_MENU["route_path"],
            "route_name": ROOT_MENU["route_name"],
            "icon": ROOT_MENU["icon"],
            "sort_order": ROOT_MENU["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "feature": "feature_payroll",
                "access_mode": "setup",
                "menu_group": "hrms",
            },
            "isactive": True,
        },
    )

    admin_role_ids = set(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    all_permission_ids = set()

    for spec in SCREEN_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["menu_code"],
            defaults={
                "parent_id": root_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                    "route_path": spec["route_path"],
                    "feature": "feature_payroll",
                    "access_mode": "setup",
                    "menu_group": "hrms",
                },
                "isactive": True,
            },
        )

        permission_ids = []
        for code, name, resource, action in spec["permissions"]:
            permission_id = _upsert_permission(
                Permission,
                code=code,
                name=name,
                resource=resource,
                action=action,
                menu_code=spec["menu_code"],
            )
            permission_ids.append(permission_id)
            all_permission_ids.add(permission_id)

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission_ids[0],
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=admin_role_ids,
            permission_id__in=all_permission_ids,
        ).values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in admin_role_ids:
        for permission_id in all_permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={
                        "seed": SEED_TAG,
                        "catalog_version": CATALOG_VERSION,
                    },
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()
    MenuPermission.objects.filter(menu__metadata__seed=SEED_TAG).delete()
    Menu.objects.filter(metadata__seed=SEED_TAG).exclude(code=ROOT_MENU["code"]).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0138_regrant_static_account_settings_admin_access")]

    operations = [migrations.RunPython(forwards, backwards)]
