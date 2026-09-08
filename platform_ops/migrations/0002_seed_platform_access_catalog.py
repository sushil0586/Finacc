from django.db import migrations


PERMISSIONS = (
    ("platform.customer.view", "View customers"),
    ("platform.customer.create", "Create customers"),
    ("platform.customer.update", "Update customers"),
    ("platform.entity.view", "View entities"),
    ("platform.entity.onboard", "Onboard entities"),
    ("platform.entity.update", "Update entities"),
    ("platform.entity.suspend", "Suspend entities"),
    ("platform.subscription.view", "View subscriptions"),
    ("platform.subscription.change", "Change subscriptions"),
    ("platform.membership.view", "View memberships"),
    ("platform.membership.manage", "Manage memberships"),
    ("platform.support.request", "Request support access"),
    ("platform.support.activate", "Activate support access"),
    ("platform.operation.view", "View operations"),
    ("platform.operation.approve", "Approve operations"),
    ("platform.operation.execute", "Execute operations"),
    ("platform.repair.preview", "Preview repairs"),
    ("platform.repair.execute", "Execute repairs"),
    ("platform.audit.view", "View platform audit"),
    ("platform.audit.export", "Export platform audit"),
    ("platform.security.manage", "Manage platform security"),
)


ROLES = {
    "platform-viewer": {
        "name": "Platform Viewer",
        "permissions": (
            "platform.customer.view",
            "platform.entity.view",
            "platform.subscription.view",
            "platform.membership.view",
            "platform.operation.view",
            "platform.audit.view",
        ),
    },
    "onboarding-operator": {
        "name": "Onboarding Operator",
        "permissions": (
            "platform.customer.view",
            "platform.customer.create",
            "platform.customer.update",
            "platform.entity.view",
            "platform.entity.onboard",
            "platform.membership.view",
            "platform.membership.manage",
            "platform.operation.view",
            "platform.operation.execute",
            "platform.audit.view",
        ),
    },
    "support-operator": {
        "name": "Support Operator",
        "permissions": (
            "platform.customer.view",
            "platform.entity.view",
            "platform.subscription.view",
            "platform.membership.view",
            "platform.support.request",
            "platform.operation.view",
            "platform.audit.view",
        ),
    },
    "billing-operator": {
        "name": "Billing Operator",
        "permissions": (
            "platform.customer.view",
            "platform.customer.update",
            "platform.entity.view",
            "platform.subscription.view",
            "platform.subscription.change",
            "platform.operation.view",
            "platform.operation.execute",
            "platform.audit.view",
        ),
    },
    "compliance-operator": {
        "name": "Compliance Operator",
        "permissions": (
            "platform.customer.view",
            "platform.entity.view",
            "platform.entity.update",
            "platform.operation.view",
            "platform.repair.preview",
            "platform.audit.view",
        ),
    },
    "platform-approver": {
        "name": "Platform Approver",
        "permissions": (
            "platform.customer.view",
            "platform.entity.view",
            "platform.subscription.view",
            "platform.membership.view",
            "platform.operation.view",
            "platform.operation.approve",
            "platform.audit.view",
            "platform.audit.export",
        ),
    },
    "platform-security-admin": {
        "name": "Platform Security Administrator",
        "permissions": (
            "platform.customer.view",
            "platform.entity.view",
            "platform.operation.view",
            "platform.audit.view",
            "platform.security.manage",
        ),
    },
}


def seed_catalog(apps, schema_editor):
    Permission = apps.get_model("platform_ops", "PlatformPermission")
    Role = apps.get_model("platform_ops", "PlatformRole")
    permission_by_code = {}
    for code, name in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        permission_by_code[code] = permission

    for code, values in ROLES.items():
        role, _ = Role.objects.update_or_create(
            code=code,
            defaults={"name": values["name"], "is_system": True, "is_active": True},
        )
        role.permissions.set(permission_by_code[item] for item in values["permissions"])


def unseed_catalog(apps, schema_editor):
    Role = apps.get_model("platform_ops", "PlatformRole")
    Permission = apps.get_model("platform_ops", "PlatformPermission")
    Role.objects.filter(code__in=ROLES).delete()
    Permission.objects.filter(code__in=[code for code, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0001_initial")]

    operations = [migrations.RunPython(seed_catalog, unseed_catalog)]
