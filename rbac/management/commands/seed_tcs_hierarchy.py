from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rbac.models import Menu, MenuPermission, Permission, Role, RolePermission


TCS_PERMISSIONS = [
    ("tcs.menu.access", "TCS Menu Access", "tcs", "menu", "access"),
    ("tcs.config.view", "View TCS Configuration", "tcs", "config", "view"),
    ("tcs.sections.view", "View TCS Sections", "tcs", "sections", "view"),
    ("tcs.rules.view", "View TCS Rules", "tcs", "rules", "view"),
    ("tcs.party_profiles.view", "View TCS Party Profiles", "tcs", "party_profiles", "view"),
    ("tcs.ledger_report.view", "View TCS Ledger Report", "tcs", "ledger_report", "view"),
    ("tcs.return_27eq.view", "View TCS Return 27EQ", "tcs", "return_27eq", "view"),
    ("tcs.filing_pack.view", "View TCS Filing Pack", "tcs", "filing_pack", "view"),
]

TCS_MENUS = [
    {
        "code": "statutory",
        "name": "Statutory",
        "menu_type": Menu.TYPE_GROUP,
        "route_path": "",
        "route_name": "statutory",
        "sort_order": 20,
        "parent_code": None,
    },
    {
        "code": "statutory.tcs",
        "name": "TCS",
        "menu_type": Menu.TYPE_GROUP,
        "route_path": "",
        "route_name": "tcs",
        "sort_order": 1,
        "parent_code": "statutory",
    },
    {
        "code": "statutory.tcs.config",
        "name": "Configuration",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcsconfig",
        "route_name": "tcsconfig",
        "sort_order": 1,
        "parent_code": "statutory.tcs",
    },
    {
        "code": "statutory.tcs.sections",
        "name": "Sections",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcssections",
        "route_name": "tcssections",
        "sort_order": 2,
        "parent_code": "statutory.tcs",
    },
    {
        "code": "statutory.tcs.rules",
        "name": "Rules",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcsrules",
        "route_name": "tcsrules",
        "sort_order": 3,
        "parent_code": "statutory.tcs",
    },
    {
        "code": "statutory.tcs.party_profiles",
        "name": "Party Profiles",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcspartyprofiles",
        "route_name": "tcspartyprofiles",
        "sort_order": 4,
        "parent_code": "statutory.tcs",
    },
    {
        "code": "statutory.tcs.ledger_report",
        "name": "Ledger Report",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcsledgerreport",
        "route_name": "tcsledgerreport",
        "sort_order": 5,
        "parent_code": "statutory.tcs",
    },
    {
        "code": "statutory.tcs.return_27eq",
        "name": "Return 27EQ",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcsreturn27eq",
        "route_name": "tcsreturn27eq",
        "sort_order": 6,
        "parent_code": "statutory.tcs",
    },
    {
        "code": "statutory.tcs.filing_pack",
        "name": "Filing Pack",
        "menu_type": Menu.TYPE_SCREEN,
        "route_path": "tcsfilingpack",
        "route_name": "tcsfilingpack",
        "sort_order": 7,
        "parent_code": "statutory.tcs",
    },
]

MENU_PERMISSION_MAP = [
    ("statutory.tcs", "tcs.menu.access"),
    ("statutory.tcs.config", "tcs.config.view"),
    ("statutory.tcs.sections", "tcs.sections.view"),
    ("statutory.tcs.rules", "tcs.rules.view"),
    ("statutory.tcs.party_profiles", "tcs.party_profiles.view"),
    ("statutory.tcs.ledger_report", "tcs.ledger_report.view"),
    ("statutory.tcs.return_27eq", "tcs.return_27eq.view"),
    ("statutory.tcs.filing_pack", "tcs.filing_pack.view"),
]


class Command(BaseCommand):
    help = "Seed hierarchical TCS menus, permissions, and role-permission mappings."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--role-code", type=str, default="legacy_role_2")
        parser.add_argument("--replace-role-permissions", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        role_code = options["role_code"]
        replace_role_permissions = options["replace_role_permissions"]

        role = Role.objects.filter(entity_id=entity_id, code=role_code, isactive=True).first()
        if not role:
            raise CommandError(f"Role not found for entity_id={entity_id}, role_code={role_code}")

        permission_map = {}
        for code, name, module, resource, action in TCS_PERMISSIONS:
            permission, _ = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "module": module,
                    "resource": resource,
                    "action": action,
                    "description": name,
                    "scope_type": Permission.SCOPE_ENTITY,
                    "is_system_defined": False,
                    "metadata": {"seed": "tcs_hierarchy"},
                    "isactive": True,
                },
            )
            permission_map[code] = permission

        menu_map = {}
        for item in TCS_MENUS:
            menu, _ = Menu.objects.get_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "menu_type": item["menu_type"],
                    "route_path": item["route_path"],
                    "route_name": item["route_name"],
                    "sort_order": item["sort_order"],
                    "icon": "",
                    "is_system_menu": False,
                    "metadata": {"seed": "tcs_hierarchy"},
                    "isactive": True,
                },
            )
            menu_map[item["code"]] = menu

        for item in TCS_MENUS:
            menu = menu_map[item["code"]]
            parent = menu_map.get(item["parent_code"])
            updated = False

            if menu.parent_id != (parent.id if parent else None):
                menu.parent = parent
                updated = True
            if menu.name != item["name"]:
                menu.name = item["name"]
                updated = True
            if menu.menu_type != item["menu_type"]:
                menu.menu_type = item["menu_type"]
                updated = True
            if menu.route_path != item["route_path"]:
                menu.route_path = item["route_path"]
                updated = True
            if menu.route_name != item["route_name"]:
                menu.route_name = item["route_name"]
                updated = True
            if menu.sort_order != item["sort_order"]:
                menu.sort_order = item["sort_order"]
                updated = True
            if not menu.isactive:
                menu.isactive = True
                updated = True

            if updated:
                menu.save()

        for menu_code, permission_code in MENU_PERMISSION_MAP:
            MenuPermission.objects.get_or_create(
                menu=menu_map[menu_code],
                permission=permission_map[permission_code],
                relation_type=MenuPermission.RELATION_VISIBILITY,
                defaults={"isactive": True},
            )

        if replace_role_permissions:
            RolePermission.objects.filter(
                role=role,
                permission__code__startswith="tcs.",
            ).delete()

        for _, permission in permission_map.items():
            RolePermission.objects.get_or_create(
                role=role,
                permission=permission,
                defaults={
                    "effect": RolePermission.EFFECT_ALLOW,
                    "metadata": {"seed": "tcs_hierarchy"},
                    "isactive": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("TCS hierarchy seeded successfully."))
        self.stdout.write(f"Entity ID: {entity_id}")
        self.stdout.write(f"Role Code: {role_code}")
