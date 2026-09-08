from django.db import migrations


def assign_repair_permissions(apps, schema_editor):
    Permission = apps.get_model("platform_ops", "PlatformPermission")
    Role = apps.get_model("platform_ops", "PlatformRole")
    preview = Permission.objects.get(code="platform.repair.preview")
    execute = Permission.objects.get(code="platform.repair.execute")
    for code in ("onboarding-operator", "platform-security-admin"):
        role = Role.objects.filter(code=code).first()
        if role:
            role.permissions.add(preview, execute)


def remove_repair_permissions(apps, schema_editor):
    Permission = apps.get_model("platform_ops", "PlatformPermission")
    Role = apps.get_model("platform_ops", "PlatformRole")
    permissions = Permission.objects.filter(code__in=("platform.repair.preview", "platform.repair.execute"))
    for role in Role.objects.filter(code__in=("onboarding-operator", "platform-security-admin")):
        role.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0014_platformoperationrequest_cancellation_reason_and_more")]
    operations = [migrations.RunPython(assign_repair_permissions, remove_repair_permissions)]
