from django.db import migrations


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    menu = Menu.objects.filter(code="accounts.capital_distribution_setup", isactive=True).first()
    permission = Permission.objects.filter(code="capital_distribution.run.view", isactive=True).first()
    if menu and permission:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type="visibility",
            defaults={"isactive": True},
        )


def backwards(apps, schema_editor):
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    MenuPermission.objects.filter(
        menu__code="accounts.capital_distribution_setup",
        permission__code="capital_distribution.run.view",
        relation_type="visibility",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0146_add_capital_distribution_run_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
