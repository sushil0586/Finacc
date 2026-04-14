from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "financial_hub_reports_2026_04_14"


MENU_GROUP = {
    "code": "reports.financial_hub",
    "name": "Financial Hub",
    "parent_code": "reports",
    "sort_order": 0,
    "icon": "chart-column",
}

MENU_SPECS = [
    {
        "code": "reports.financial_hub.index",
        "name": "Hub Overview",
        "route_path": "/reports/financial",
        "route_name": "financialhub",
        "icon": "chart-column",
        "sort_order": 1,
        "permission_code": "reports.financial_hub.view",
    },
    {
        "code": "reports.financial_hub.trial_balance",
        "name": "Trial Balance",
        "route_path": "/reports/financial/trial-balance",
        "route_name": "financial-trial-balance",
        "icon": "scale-3d",
        "sort_order": 2,
        "permission_code": "reports.financial_hub.trial_balance.view",
        "export_permission_code": "reports.financial_hub.trial_balance.export",
    },
    {
        "code": "reports.financial_hub.ledger_book",
        "name": "Ledger Book",
        "route_path": "/reports/financial/ledger-book",
        "route_name": "financial-ledger-book",
        "icon": "book",
        "sort_order": 3,
        "permission_code": "reports.financial_hub.ledger_book.view",
        "export_permission_code": "reports.financial_hub.ledger_book.export",
    },
    {
        "code": "reports.financial_hub.profit_loss",
        "name": "Profit & Loss",
        "route_path": "/reports/financial/profit-loss",
        "route_name": "financial-profit-loss",
        "icon": "chart-pie-4",
        "sort_order": 4,
        "permission_code": "reports.financial_hub.profit_loss.view",
        "export_permission_code": "reports.financial_hub.profit_loss.export",
    },
    {
        "code": "reports.financial_hub.balance_sheet",
        "name": "Balance Sheet",
        "route_path": "/reports/financial/balance-sheet",
        "route_name": "financial-balance-sheet",
        "icon": "scale-3d",
        "sort_order": 5,
        "permission_code": "reports.financial_hub.balance_sheet.view",
        "export_permission_code": "reports.financial_hub.balance_sheet.export",
    },
    {
        "code": "reports.financial_hub.trading_account",
        "name": "Trading Account",
        "route_path": "/reports/financial/trading-account",
        "route_name": "financial-trading-account",
        "icon": "receipt",
        "sort_order": 6,
        "permission_code": "reports.financial_hub.trading_account.view",
        "export_permission_code": "reports.financial_hub.trading_account.export",
    },
    {
        "code": "reports.financial_hub.daybook",
        "name": "Daybook",
        "route_path": "/reports/financial/daybook",
        "route_name": "financial-daybook",
        "icon": "calendar-clock",
        "sort_order": 7,
        "permission_code": "reports.financial_hub.daybook.view",
        "export_permission_code": "reports.financial_hub.daybook.export",
    },
    {
        "code": "reports.financial_hub.cashbook",
        "name": "Cashbook",
        "route_path": "/reports/financial/cashbook",
        "route_name": "financial-cashbook",
        "icon": "wallet",
        "sort_order": 8,
        "permission_code": "reports.financial_hub.cashbook.view",
        "export_permission_code": "reports.financial_hub.cashbook.export",
    },
]


def _permission_parts(code: str) -> tuple[str, str, str]:
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = ".".join(parts[1:-1]) or module
    return module, resource.replace(".", "_"), action


def _permission_name(code: str) -> str:
    action_labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "print": "Print",
        "post": "Post",
        "unpost": "Unpost",
        "export": "Export",
        "file": "File",
        "change": "Change",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1])
    resource = resource.title() if resource else parts[0].title()
    return f"{action_labels.get(action, action.title())} {resource}".strip()


def _upsert_permission(Permission, permission_code: str, *, seed: str, menu_code: str) -> int:
    module, resource, action = _permission_parts(permission_code)
    permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": _permission_name(permission_code),
            "module": module,
            "resource": resource,
            "action": action,
            "description": _permission_name(permission_code),
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": seed,
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

    reports_parent = Menu.objects.filter(code="reports", isactive=True).first()
    if reports_parent is None:
        reports_parent = Menu.objects.filter(code="reports.reports", isactive=True).first()
    if reports_parent is None:
        return

    group_menu, _ = Menu.objects.update_or_create(
        code=MENU_GROUP["code"],
        defaults={
            "parent_id": reports_parent.id,
            "name": MENU_GROUP["name"],
            "menu_type": "group",
            "route_path": "",
            "route_name": "reports-financial-hub",
            "icon": MENU_GROUP["icon"],
            "sort_order": MENU_GROUP["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "financial_hub_reports",
                "catalog_version": CATALOG_VERSION,
                "group": MENU_GROUP["code"],
            },
            "isactive": True,
        },
    )

    permission_ids: list[int] = []
    for spec in MENU_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": group_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "financial_hub_reports",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                    "route_path": spec["route_path"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        permission_ids.append(_upsert_permission(Permission, spec["permission_code"], seed="financial_hub_reports", menu_code=spec["code"]))
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission_ids[-1],
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        export_code = spec.get("export_permission_code")
        if export_code:
            export_permission_id = _upsert_permission(Permission, export_code, seed="financial_hub_reports", menu_code=spec["code"])
            permission_ids.append(export_permission_id)

    source_permission_codes = [
        "reports.trial_balance.view",
        "reports.trial_balance.export",
        "reports.ledger_book.view",
        "reports.ledger_book.export",
    ]
    source_role_ids = set()
    for code in source_permission_codes:
        source_role_ids.update(
            RolePermission.objects.filter(
                permission__code=code,
                role__isactive=True,
            ).values_list("role_id", flat=True)
        )

    if not source_role_ids:
        source_role_ids.update(
            Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True)
        )

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=source_role_ids,
            permission_id__in=permission_ids,
        ).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in source_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "financial_hub_reports", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0056_add_financial_hub_menu")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
