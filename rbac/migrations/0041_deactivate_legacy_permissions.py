import importlib

from django.db import migrations


def _canonical_permission_codes():
    route_catalog = importlib.import_module("rbac.migrations.0038_seed_route_based_rbac_catalog")
    codes = set()
    for spec in route_catalog.ROUTE_SPECS:
        codes.add(spec["view_permission"])
        codes.update(spec["actions"])
    return codes


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    canonical_codes = _canonical_permission_codes()
    legacy_permission_ids = list(
        Permission.objects.filter(isactive=True).exclude(code__in=canonical_codes).values_list("id", flat=True)
    )
    if not legacy_permission_ids:
        return

    RolePermission.objects.filter(permission_id__in=legacy_permission_ids, isactive=True).update(isactive=False)
    MenuPermission.objects.filter(permission_id__in=legacy_permission_ids, isactive=True).update(isactive=False)
    Permission.objects.filter(id__in=legacy_permission_ids, isactive=True).update(isactive=False)


def backwards(apps, schema_editor):
    # Legacy permissions were intentionally retired to keep the route-based
    # catalog as the single source of truth. Reactivation should be deliberate.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0040_delete_legacy_menu_rows"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
