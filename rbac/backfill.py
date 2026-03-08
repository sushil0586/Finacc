from django.db import transaction

from Authentication.models import MainMenu, Submenu, User
from entity.models import Entity, Role as LegacyRole, RolePrivilege, UserRole

from .models import Menu, MenuPermission, Permission, Role, RolePermission, UserRoleAssignment
from .services import LegacyRBACCodes


def _safe_sort_order(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


class LegacyRBACBackfillService:
    @classmethod
    @transaction.atomic
    def run(cls):
        cls._backfill_menus_and_permissions()
        cls._backfill_roles()
        cls._backfill_role_permissions()
        cls._backfill_user_assignments()

    @classmethod
    def _backfill_menus_and_permissions(cls):
        for main_menu in MainMenu.objects.all().order_by("order", "id"):
            root_menu, _ = Menu.objects.update_or_create(
                code=LegacyRBACCodes.main_menu_code(main_menu.id),
                defaults={
                    "name": main_menu.mainmenu,
                    "route_path": main_menu.menuurl or "",
                    "route_name": main_menu.menucode or "",
                    "sort_order": _safe_sort_order(main_menu.order),
                    "menu_type": Menu.TYPE_GROUP,
                    "is_system_menu": True,
                    "metadata": {"legacy_mainmenu_id": main_menu.id},
                },
            )
            root_permission, _ = Permission.objects.update_or_create(
                code=LegacyRBACCodes.main_menu_permission_code(main_menu.id),
                defaults={
                    "name": f"{main_menu.mainmenu} Menu Access",
                    "module": main_menu.menucode or "legacy",
                    "resource": "menu",
                    "action": "access",
                    "description": f"Access to {main_menu.mainmenu} menu",
                    "scope_type": Permission.SCOPE_ENTITY,
                    "is_system_defined": True,
                    "metadata": {"legacy_mainmenu_id": main_menu.id},
                },
            )
            MenuPermission.objects.get_or_create(
                menu=root_menu,
                permission=root_permission,
                relation_type=MenuPermission.RELATION_VISIBILITY,
            )

        for submenu in Submenu.objects.select_related("mainmenu").all().order_by("mainmenu__order", "order", "id"):
            parent_menu = Menu.objects.get(code=LegacyRBACCodes.main_menu_code(submenu.mainmenu_id))
            child_menu, _ = Menu.objects.update_or_create(
                code=LegacyRBACCodes.sub_menu_code(submenu.id),
                defaults={
                    "parent": parent_menu,
                    "name": submenu.submenu,
                    "route_path": submenu.subMenuurl or "",
                    "route_name": submenu.submenucode or "",
                    "sort_order": _safe_sort_order(submenu.order),
                    "menu_type": Menu.TYPE_SCREEN,
                    "is_system_menu": True,
                    "metadata": {
                        "legacy_submenu_id": submenu.id,
                        "legacy_mainmenu_id": submenu.mainmenu_id,
                    },
                },
            )
            permission, _ = Permission.objects.update_or_create(
                code=LegacyRBACCodes.sub_menu_permission_code(submenu.id),
                defaults={
                    "name": f"{submenu.submenu} Access",
                    "module": submenu.mainmenu.menucode or "legacy",
                    "resource": submenu.submenucode or "submenu",
                    "action": "access",
                    "description": f"Access to {submenu.submenu}",
                    "scope_type": Permission.SCOPE_ENTITY,
                    "is_system_defined": True,
                    "metadata": {
                        "legacy_submenu_id": submenu.id,
                        "legacy_mainmenu_id": submenu.mainmenu_id,
                    },
                },
            )
            MenuPermission.objects.get_or_create(
                menu=child_menu,
                permission=permission,
                relation_type=MenuPermission.RELATION_VISIBILITY,
            )

    @classmethod
    def _backfill_roles(cls):
        for legacy_role in LegacyRole.objects.select_related("entity").all():
            Role.objects.update_or_create(
                entity=legacy_role.entity,
                code=LegacyRBACCodes.role_code(legacy_role.id),
                defaults={
                    "name": legacy_role.rolename,
                    "description": legacy_role.roledesc or "",
                    "role_level": Role.LEVEL_ENTITY,
                    "is_system_role": False,
                    "is_assignable": True,
                    "priority": legacy_role.rolelevel or 100,
                    "metadata": {
                        "legacy_role_id": legacy_role.id,
                        "legacy_entity_id": legacy_role.entity_id,
                    },
                },
            )

    @classmethod
    def _backfill_role_permissions(cls):
        for privilege in RolePrivilege.objects.select_related("role", "submenu", "entity").all():
            if privilege.role_id is None or privilege.submenu_id is None:
                continue
            role = Role.objects.filter(
                entity_id=privilege.entity_id,
                code=LegacyRBACCodes.role_code(privilege.role_id),
            ).first()
            permission = Permission.objects.filter(
                code=LegacyRBACCodes.sub_menu_permission_code(privilege.submenu_id)
            ).first()
            if role and permission:
                RolePermission.objects.get_or_create(
                    role=role,
                    permission=permission,
                    defaults={"effect": RolePermission.EFFECT_ALLOW},
                )

    @classmethod
    def _backfill_user_assignments(cls):
        for user_role in UserRole.objects.select_related("user", "entity", "role").all():
            if user_role.user_id is None or user_role.entity_id is None or user_role.role_id is None:
                continue
            role = Role.objects.filter(
                entity_id=user_role.entity_id,
                code=LegacyRBACCodes.role_code(user_role.role_id),
            ).first()
            if not role:
                continue
            UserRoleAssignment.objects.get_or_create(
                user_id=user_role.user_id,
                entity_id=user_role.entity_id,
                role=role,
                subentity=None,
                defaults={
                    "assigned_by_id": user_role.user_id if User.objects.filter(id=user_role.user_id).exists() else None,
                    "is_primary": True,
                    "scope_data": {"legacy_user_role_id": user_role.id},
                },
            )
