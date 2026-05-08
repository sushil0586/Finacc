from django.db import migrations


LEGACY_TO_CANONICAL_PERMISSION_MAP = (
    (("reports.daybook.view",), ("reports.financial_hub.daybook.view",)),
    (("reports.daybook.export",), ("reports.financial_hub.daybook.export",)),
    (("reports.cash_book.view", "reports.cashbook.view"), ("reports.financial_hub.cashbook.view",)),
    (("reports.cash_book.export", "reports.cashbook.export"), ("reports.financial_hub.cashbook.export",)),
    (("reports.balance_sheet.view",), ("reports.financial_hub.balance_sheet.view",)),
    (("reports.balance_sheet.export",), ("reports.financial_hub.balance_sheet.export",)),
    (("reports.income_expenditure.view",), ("reports.financial_hub.profit_loss.view",)),
    (("reports.income_expenditure.export",), ("reports.financial_hub.profit_loss.export",)),
)


CANONICAL_MENU_CONFIG = {
    "reports.financial_hub.daybook": {
        "route_path": "reports/financial/daybook",
        "route_name": "reports-financial-daybook",
        "permission_codes": ("reports.financial_hub.daybook.view",),
        "metadata": {"canonical_route": "reports/financial/daybook"},
    },
    "reports.financial_hub.cashbook": {
        "route_path": "reports/financial/cashbook",
        "route_name": "reports-financial-cashbook",
        "permission_codes": ("reports.financial_hub.cashbook.view",),
        "metadata": {"canonical_route": "reports/financial/cashbook"},
    },
    "reports.financial_hub.balance_sheet": {
        "route_path": "reports/financial/balance-sheet",
        "route_name": "reports-financial-balance-sheet",
        "permission_codes": ("reports.financial_hub.balance_sheet.view",),
        "metadata": {"canonical_route": "reports/financial/balance-sheet"},
    },
    "reports.financial_hub.profit_loss": {
        "route_path": "reports/financial/profit-loss",
        "route_name": "reports-financial-profit-loss",
        "permission_codes": ("reports.financial_hub.profit_loss.view",),
        "metadata": {"canonical_route": "reports/financial/profit-loss"},
    },
}


LEGACY_MENU_REPLACEMENTS = {
    "reports.daybook": "reports.financial_hub.daybook",
    "reports.cashbook": "reports.financial_hub.cashbook",
    "reports.balancesheet": "reports.financial_hub.balance_sheet",
    "reports.incomeexpenditurereport": "reports.financial_hub.profit_loss",
    "reports.financial.balancesheet": "reports.financial_hub.balance_sheet",
    "reports.financial.incomeexpenditurereport": "reports.financial_hub.profit_loss",
}


ADMIN_ROLE_CODES = ("admin", "entity.admin", "entity.super_admin")


def _ensure_permission(permission_model, code):
    module, resource, action = code.split(".", 2)
    permission, _ = permission_model.objects.update_or_create(
        code=code,
        defaults={
            "name": code.replace(".", " ").replace("_", " ").title(),
            "module": module,
            "resource": resource,
            "action": action,
            "scope_type": "entity",
            "is_system_defined": True,
            "isactive": True,
            "metadata": {"seed": "financial_report_route_reconcile"},
        },
    )
    if not permission.isactive:
        permission.isactive = True
        permission.save(update_fields=["isactive", "updated_at"])
    return permission


def _grant_permission(role_permission_model, role, permission):
    role_permission, created = role_permission_model.objects.get_or_create(
        role=role,
        permission=permission,
        defaults={
            "effect": "allow",
            "isactive": True,
            "metadata": {"seed": "financial_report_route_reconcile"},
        },
    )
    if not created:
        update_fields = []
        if role_permission.effect != "allow":
            role_permission.effect = "allow"
            update_fields.append("effect")
        if not role_permission.isactive:
            role_permission.isactive = True
            update_fields.append("isactive")
        if update_fields:
            update_fields.append("updated_at")
            role_permission.save(update_fields=update_fields)


def reconcile_financial_report_routes(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    permission_cache = {}
    target_codes = {
        code
        for _sources, targets in LEGACY_TO_CANONICAL_PERMISSION_MAP
        for code in targets
    }
    for code in target_codes:
        permission_cache[code] = _ensure_permission(Permission, code)

    for source_codes, target_codes_for_source in LEGACY_TO_CANONICAL_PERMISSION_MAP:
        source_permissions = list(Permission.objects.filter(code__in=source_codes))
        if not source_permissions:
            continue
        role_ids = RolePermission.objects.filter(
            permission_id__in=[permission.id for permission in source_permissions],
            effect="allow",
            isactive=True,
        ).values_list("role_id", flat=True)
        for role in Role.objects.filter(id__in=role_ids, isactive=True):
            for target_code in target_codes_for_source:
                _grant_permission(RolePermission, role, permission_cache[target_code])

    for role in Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True):
        for code in target_codes:
            _grant_permission(RolePermission, role, permission_cache[code])

    for menu_code, config in CANONICAL_MENU_CONFIG.items():
        menu = Menu.objects.filter(code=menu_code).first()
        if menu is None:
            continue
        menu.route_path = config["route_path"]
        menu.route_name = config["route_name"]
        menu.isactive = True
        menu.metadata = {**(menu.metadata or {}), **config["metadata"]}
        menu.save(update_fields=["route_path", "route_name", "isactive", "metadata", "updated_at"])

        for permission_code in config["permission_codes"]:
            permission = permission_cache.get(permission_code) or Permission.objects.filter(code=permission_code).first()
            if permission is None:
                continue
            menu_permission, created = MenuPermission.objects.get_or_create(
                menu=menu,
                permission=permission,
                relation_type="visibility",
                defaults={"isactive": True},
            )
            if not created and not menu_permission.isactive:
                menu_permission.isactive = True
                menu_permission.save(update_fields=["isactive", "updated_at"])

    for legacy_code, replacement_code in LEGACY_MENU_REPLACEMENTS.items():
        menu = Menu.objects.filter(code=legacy_code).first()
        if menu is None:
            continue
        menu.isactive = False
        menu.metadata = {
            **(menu.metadata or {}),
            "replaced_by": replacement_code,
            "legacy": True,
        }
        menu.save(update_fields=["isactive", "metadata", "updated_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0098_reconcile_legacy_report_routes"),
    ]

    operations = [
        migrations.RunPython(reconcile_financial_report_routes, noop_reverse),
    ]
