from django.db import migrations


MENU_FAMILIES = {
    "purchase.purchaseinvoice": "purchase.invoice",
    "purchase.purchaseserviceinvoice": "purchase.invoice",
    "purchase.purchasecreditnoteinvoice": "purchase.credit_note",
    "purchase.purchaseservicecreditnoteinvoice": "purchase.credit_note",
    "purchase.purchasedebitnoteinvoice": "purchase.debit_note",
    "purchase.purchaseservicedebitnoteinvoice": "purchase.debit_note",
}

WORKFLOW_ACTIONS = (
    "create",
    "update",
    "edit",
    "delete",
    "print",
    "confirm",
    "post",
    "unpost",
    "cancel",
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    menus = {menu.code: menu for menu in Menu.objects.filter(code__in=MENU_FAMILIES)}
    permission_codes = {
        f"{family}.{action}"
        for family in set(MENU_FAMILIES.values())
        for action in WORKFLOW_ACTIONS
    }
    permissions = {
        permission.code: permission
        for permission in Permission.objects.filter(code__in=permission_codes, isactive=True)
    }

    for menu_code, family in MENU_FAMILIES.items():
        menu = menus.get(menu_code)
        if menu is None:
            continue
        for action in WORKFLOW_ACTIONS:
            permission = permissions.get(f"{family}.{action}")
            if permission is None:
                continue
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=permission.id,
                relation_type="action",
                defaults={"isactive": True},
            )


def backwards(apps, schema_editor):
    # Keep live action mappings intact if a deployment is rolled back.
    return


class Migration(migrations.Migration):
    dependencies = [("rbac", "0152_add_capital_distribution_migration_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
