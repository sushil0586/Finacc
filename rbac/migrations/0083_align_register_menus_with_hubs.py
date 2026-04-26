from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "register_hub_alignment_2026_04_24"

SALES_MENU_SPEC = {
    "code": "reports.financial_hub.receivables_hub.sales_register",
    "name": "Sales Register",
    "parent_codes": ["reports.financial_hub.receivables_hub", "reports.financial_hub"],
    "route_path": "/reports/receivables/sales-register",
    "route_name": "sales-register",
    "icon": "journal-text",
    "sort_order": 18,
    "permission_code": "reports.sales_register.view",
}

PURCHASE_MENU_SPEC = {
    "code": "reports.payables.purchase_register",
    "name": "Purchase Register",
    "parent_codes": ["reports.payables", "reports.financial_hub", "reports"],
    "route_path": "/reports/payables/purchase-register",
    "route_name": "purchase-register",
    "icon": "book-copy",
    "sort_order": 4,
    "permission_code": "reports.purchase_register.view",
    "hub_permission_code": "reports.financial_hub.payables_hub.purchase_register.view",
}


def _permission_parts(code: str):
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


def _resolve_parent(Menu, parent_codes):
    for code in parent_codes:
        parent = Menu.objects.filter(code=code, isactive=True).first()
        if parent:
            return parent
    return None


def _upsert_menu(Menu, spec, seed: str):
    parent = _resolve_parent(Menu, spec["parent_codes"])
    if parent is None:
        return None

    menu, _ = Menu.objects.update_or_create(
        code=spec["code"],
        defaults={
            "parent_id": parent.id,
            "name": spec["name"],
            "menu_type": "screen",
            "route_path": spec["route_path"],
            "route_name": spec["route_name"],
            "icon": spec["icon"],
            "sort_order": spec["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": seed,
                "catalog_version": CATALOG_VERSION,
                "menu_code": spec["code"],
                "route_path": spec["route_path"],
                "permission_code": spec["permission_code"],
            },
            "isactive": True,
        },
    )
    return menu


def _sync_visibility(MenuPermission, *, menu_id: int, allowed_permission_ids: list[int]):
    MenuPermission.objects.filter(
        menu_id=menu_id,
        relation_type=MENU_RELATION_VISIBILITY,
    ).exclude(permission_id__in=allowed_permission_ids).update(isactive=False)

    for permission_id in allowed_permission_ids:
        MenuPermission.objects.update_or_create(
            menu_id=menu_id,
            permission_id=permission_id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    # 1) Sales Register under Receivables Hub.
    sales_menu = _upsert_menu(Menu, SALES_MENU_SPEC, seed="register_hub_alignment")
    if sales_menu:
        sales_permission_id = _upsert_permission(
            Permission,
            SALES_MENU_SPEC["permission_code"],
            seed="register_hub_alignment",
            menu_code=SALES_MENU_SPEC["code"],
        )
        _sync_visibility(
            MenuPermission,
            menu_id=sales_menu.id,
            allowed_permission_ids=[sales_permission_id],
        )

    # 2) Purchase Register canonical path + visibility permission alignment.
    purchase_menu = _upsert_menu(Menu, PURCHASE_MENU_SPEC, seed="register_hub_alignment")
    if purchase_menu:
        purchase_view_permission_id = _upsert_permission(
            Permission,
            PURCHASE_MENU_SPEC["permission_code"],
            seed="register_hub_alignment",
            menu_code=PURCHASE_MENU_SPEC["code"],
        )
        purchase_hub_permission_id = _upsert_permission(
            Permission,
            PURCHASE_MENU_SPEC["hub_permission_code"],
            seed="register_hub_alignment",
            menu_code=PURCHASE_MENU_SPEC["code"],
        )
        _sync_visibility(
            MenuPermission,
            menu_id=purchase_menu.id,
            allowed_permission_ids=[purchase_view_permission_id, purchase_hub_permission_id],
        )

        # Preserve legacy aliases but normalize to canonical grouped route.
        legacy_codes = [
            "reports.reports.purchaseregister",
        ]
        Menu.objects.filter(code__in=legacy_codes).update(
            route_path=PURCHASE_MENU_SPEC["route_path"],
            route_name=PURCHASE_MENU_SPEC["route_name"],
            isactive=True,
        )

        # Grant the new hub permission to roles already allowed to view purchase register.
        source_role_ids = set(
            RolePermission.objects.filter(
                permission__code=PURCHASE_MENU_SPEC["permission_code"],
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
                permission_id=purchase_hub_permission_id,
            ).values_list("role_id", "permission_id")
        )

        inserts = []
        for role_id in source_role_ids:
            if (role_id, purchase_hub_permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=purchase_hub_permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={
                        "seed": "register_hub_alignment",
                        "catalog_version": CATALOG_VERSION,
                    },
                    isactive=True,
                )
            )

        if inserts:
            RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    # Keep this forward-only to avoid accidental revocation in live tenants.
    return


class Migration(migrations.Migration):
    dependencies = [("rbac", "0082_add_collections_history_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
