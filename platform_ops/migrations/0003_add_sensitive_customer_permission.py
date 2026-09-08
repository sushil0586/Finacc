from django.db import migrations


def add_permission(apps, schema_editor):
    Permission = apps.get_model("platform_ops", "PlatformPermission")
    Role = apps.get_model("platform_ops", "PlatformRole")
    permission, _ = Permission.objects.update_or_create(
        code="platform.customer.sensitive.view",
        defaults={"name": "View sensitive customer data", "is_active": True},
    )
    role = Role.objects.filter(code="platform-security-admin").first()
    if role:
        role.permissions.add(permission)


def remove_permission(apps, schema_editor):
    Permission = apps.get_model("platform_ops", "PlatformPermission")
    Permission.objects.filter(code="platform.customer.sensitive.view").delete()


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0002_seed_platform_access_catalog")]
    operations = [migrations.RunPython(add_permission, remove_permission)]
