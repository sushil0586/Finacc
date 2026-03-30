from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
PERMISSION_SCOPE_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"
SEED_NAME = "service_invoice_menu"
CATALOG_VERSION = "service_invoice_menu_2026_03_29"

MENU_DEFS = [
    {
        "code": "sales.saleserviceinvoice",
        "name": "Service Invoice",
        "route_path": "saleserviceinvoice",
        "route_name": "saleserviceinvoice",
        "icon": "briefcase",
        "sort_order": 2,
        "parent_candidates": ["sales.transactions", "sales"],
        "permission_code": "sales.invoice.view",
        "permission_fallback": {
            "name": "View Sales Invoice",
            "module": "sales",
            "resource": "invoice",
            "action": "view",
            "description": "Access sales invoice screens",
        },
    },
    {
        "code": "purchase.purchaseserviceinvoice",
        "name": "Service Purchase",
        "route_path": "purchaseserviceinvoice",
        "route_name": "purchaseserviceinvoice",
        "icon": "wrench",
        "sort_order": 2,
        "parent_candidates": ["purchase.transactions", "purchase"],
        "permission_code": "purchase.invoice.view",
        "permission_fallback": {
            "name": "View Purchase Invoice",
            "module": "purchase",
            "resource": "invoice",
            "action": "view",
            "description": "Access purchase invoice screens",
        },
    },
]


def _resolve_parent(Menu, candidates):
    for code in candidates:
        parent = Menu.objects.filter(code=code).first()
        if parent:
            return parent
    return None


def _ensure_permission(Permission, permission_code, fallback):
    permission = Permission.objects.filter(code=permission_code).first()
    if permission:
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=["isactive"])
        return permission

    permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": fallback["name"],
            "module": fallback["module"],
            "resource": fallback["resource"],
            "action": fallback["action"],
            "description": fallback["description"],
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "fallback_permission": True,
            },
            "isactive": True,
        },
    )
    return permission


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    mapped_permission_ids = set()

    for menu_def in MENU_DEFS:
        parent = _resolve_parent(Menu, menu_def["parent_candidates"])
        menu, _ = Menu.objects.update_or_create(
            code=menu_def["code"],
            defaults={
                "parent_id": parent.id if parent else None,
                "name": menu_def["name"],
                "menu_type": "screen",
                "route_path": menu_def["route_path"],
                "route_name": menu_def["route_name"],
                "icon": menu_def["icon"],
                "sort_order": menu_def["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_NAME,
                    "catalog_version": CATALOG_VERSION,
                    "permission_code": menu_def["permission_code"],
                },
                "isactive": True,
            },
        )

        permission = _ensure_permission(
            Permission,
            menu_def["permission_code"],
            menu_def["permission_fallback"],
        )
        mapped_permission_ids.add(permission.id)

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True)
    )
    if not role_ids or not mapped_permission_ids:
        return

    existing = set(
        RolePermission.objects.filter(
            role_id__in=role_ids, permission_id__in=mapped_permission_ids
        ).values_list("role_id", "permission_id")
    )

    inserts = []
    for role_id in role_ids:
        for permission_id in mapped_permission_ids:
            if (role_id, permission_id) in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_NAME, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_codes = [item["code"] for item in MENU_DEFS]
    menu_ids = list(Menu.objects.filter(code__in=menu_codes).values_list("id", flat=True))
    if not menu_ids:
        return

    permission_ids = list(
        MenuPermission.objects.filter(menu_id__in=menu_ids).values_list("permission_id", flat=True)
    )
    RolePermission.objects.filter(
        permission_id__in=permission_ids,
        metadata__seed=SEED_NAME,
    ).delete()
    MenuPermission.objects.filter(menu_id__in=menu_ids).delete()
    Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0036_add_sales_compliance_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
