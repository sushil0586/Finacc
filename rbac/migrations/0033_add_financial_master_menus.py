from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "financial_master_menu_2026_03_21"

PARENT_MENU_CODE = "admin"
GROUP_MENU_CODE = "admin.financial-master"

MENU_DEFS = [
    {
        "code": "admin.financial-master.account-types",
        "name": "Account Types",
        "route_path": "financial-master/account-types",
        "route_name": "financial-master-account-types",
        "icon": "layers",
        "sort_order": 1,
        "permission_code": "financial.account_types.view",
    },
    {
        "code": "admin.financial-master.account-heads",
        "name": "Account Heads",
        "route_path": "financial-master/account-heads",
        "route_name": "financial-master-account-heads",
        "icon": "layers",
        "sort_order": 2,
        "permission_code": "financial.account_heads.view",
    },
    {
        "code": "admin.financial-master.ledgers",
        "name": "Ledgers",
        "route_path": "financial-master/ledgers",
        "route_name": "financial-master-ledgers",
        "icon": "wallet",
        "sort_order": 3,
        "permission_code": "financial.ledgers.view",
    },
    {
        "code": "admin.financial-master.accounts",
        "name": "Accounts",
        "route_path": "financial-master/accounts",
        "route_name": "financial-master-accounts",
        "icon": "users",
        "sort_order": 4,
        "permission_code": "financial.accounts.view",
    },
]

PERMISSIONS = [
    ("financial.master.menu.access", "View Financial Master Menu", "financial", "financial_master", "menu_access"),
    ("financial.account_types.view", "View Account Types", "financial", "account_types", "view"),
    ("financial.account_types.create", "Create Account Types", "financial", "account_types", "create"),
    ("financial.account_types.edit", "Edit Account Types", "financial", "account_types", "edit"),
    ("financial.account_types.update", "Update Account Types", "financial", "account_types", "update"),
    ("financial.account_types.delete", "Delete Account Types", "financial", "account_types", "delete"),
    ("financial.account_heads.view", "View Account Heads", "financial", "account_heads", "view"),
    ("financial.account_heads.create", "Create Account Heads", "financial", "account_heads", "create"),
    ("financial.account_heads.edit", "Edit Account Heads", "financial", "account_heads", "edit"),
    ("financial.account_heads.update", "Update Account Heads", "financial", "account_heads", "update"),
    ("financial.account_heads.delete", "Delete Account Heads", "financial", "account_heads", "delete"),
    ("financial.ledgers.view", "View Ledgers", "financial", "ledgers", "view"),
    ("financial.ledgers.create", "Create Ledgers", "financial", "ledgers", "create"),
    ("financial.ledgers.edit", "Edit Ledgers", "financial", "ledgers", "edit"),
    ("financial.ledgers.update", "Update Ledgers", "financial", "ledgers", "update"),
    ("financial.ledgers.delete", "Delete Ledgers", "financial", "ledgers", "delete"),
    ("financial.accounts.view", "View Accounts", "financial", "accounts", "view"),
    ("financial.accounts.create", "Create Accounts", "financial", "accounts", "create"),
    ("financial.accounts.edit", "Edit Accounts", "financial", "accounts", "edit"),
    ("financial.accounts.update", "Update Accounts", "financial", "accounts", "update"),
    ("financial.accounts.delete", "Delete Accounts", "financial", "accounts", "delete"),
]


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = Menu.objects.filter(code=PARENT_MENU_CODE).first()

    group_menu, _ = Menu.objects.update_or_create(
        code=GROUP_MENU_CODE,
        defaults={
            "parent_id": parent.id if parent else None,
            "name": "Financial Master",
            "menu_type": "group",
            "route_path": "financial-master",
            "route_name": "financial-master",
            "icon": "database",
            "sort_order": 20,
            "is_system_menu": True,
            "metadata": {
                "seed": "financial_master_menu",
                "catalog_version": CATALOG_VERSION,
                "module": "financial",
            },
            "isactive": True,
        },
    )

    permission_by_code = {}
    permission_ids = []
    for code, name, module, resource, action in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "financial_master_menu",
                    "catalog_version": CATALOG_VERSION,
                },
                "isactive": True,
            },
        )
        permission_by_code[code] = permission
        permission_ids.append(permission.id)

    MenuPermission.objects.update_or_create(
        menu_id=group_menu.id,
        permission_id=permission_by_code["financial.master.menu.access"].id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    for menu_def in MENU_DEFS:
        menu, _ = Menu.objects.update_or_create(
            code=menu_def["code"],
            defaults={
                "parent_id": group_menu.id,
                "name": menu_def["name"],
                "menu_type": "screen",
                "route_path": menu_def["route_path"],
                "route_name": menu_def["route_name"],
                "icon": menu_def["icon"],
                "sort_order": menu_def["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "financial_master_menu",
                    "catalog_version": CATALOG_VERSION,
                    "module": "financial",
                },
                "isactive": True,
            },
        )
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission_by_code[menu_def["permission_code"]].id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True)
    )
    if not role_ids:
        return

    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={
                        "seed": "financial_master_menu",
                        "catalog_version": CATALOG_VERSION,
                    },
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [code for code, *_ in PERMISSIONS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_codes = [GROUP_MENU_CODE] + [m["code"] for m in MENU_DEFS]
    menu_ids = list(Menu.objects.filter(code__in=menu_codes).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(
            permission_id__in=permission_ids,
            metadata__seed="financial_master_menu",
        ).delete()
        MenuPermission.objects.filter(menu_id__in=menu_ids, permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0032_add_static_account_settings_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
