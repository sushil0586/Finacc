from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
SEED_TAG = "cfo_phase_8_evidence_center"
CATALOG_VERSION = "cfo_phase_8_evidence_center_2026_09_24"


PERMISSION_SPECS = (
    ("cfo.evidence_center.view", "View CFO Evidence Center", "evidence_center", "view"),
    ("cfo.evidence_center.manage", "Manage CFO Evidence Items", "evidence_center", "manage"),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    root_menu, _ = Menu.objects.update_or_create(
        code="cfo",
        defaults={
            "parent": None,
            "name": "CFO",
            "menu_type": "screen",
            "route_path": "/cfo",
            "route_name": "cfo",
            "icon": "speedometer2",
            "sort_order": 18,
            "is_system_menu": True,
            "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION, "phase": "cfo_phase_8"},
            "isactive": True,
        },
    )

    menu, _ = Menu.objects.update_or_create(
        code="cfo.evidence_center",
        defaults={
            "parent": root_menu,
            "name": "Evidence Center",
            "menu_type": "screen",
            "route_path": "/cfo/evidence-center",
            "route_name": "cfo-evidence-center",
            "icon": "journal-check",
            "sort_order": 80,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "permission_code": "cfo.evidence_center.view",
            },
            "isactive": True,
        },
    )

    permission_ids = []
    permissions = {}
    for code, name, resource, action in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "cfo",
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION, "phase": "cfo_phase_8"},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)
        permissions[code] = permission

    MenuPermission.objects.update_or_create(
        menu=menu,
        permission=permissions["cfo.evidence_center.view"],
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code__in=[spec[0] for spec in PERMISSION_SPECS]).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids, menu__metadata__seed=SEED_TAG).delete()
        Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    Menu.objects.filter(code="cfo.evidence_center", metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0187_add_cfo_management_pack_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
