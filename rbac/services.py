from django.db.models import Q

from entity.models import Entity, RolePrivilege, UserRole

from .models import Menu, MenuPermission, Permission, Role, RolePermission, UserRoleAssignment


class MenuTreeService:
    @staticmethod
    def root_queryset():
        return Menu.objects.filter(parent__isnull=True, isactive=True).order_by("sort_order", "name")


class LegacyRBACCodes:
    @staticmethod
    def role_code(legacy_role_id):
        return f"legacy_role_{legacy_role_id}"

    @staticmethod
    def main_menu_code(legacy_main_menu_id):
        return f"legacy.mainmenu.{legacy_main_menu_id}"

    @staticmethod
    def sub_menu_code(legacy_submenu_id):
        return f"legacy.submenu.{legacy_submenu_id}"

    @staticmethod
    def main_menu_permission_code(legacy_main_menu_id):
        return f"legacy.mainmenu.{legacy_main_menu_id}.access"

    @staticmethod
    def sub_menu_permission_code(legacy_submenu_id):
        return f"legacy.submenu.{legacy_submenu_id}.access"


class EffectivePermissionService:
    @staticmethod
    def role_summaries_for_user(user, entity_id):
        assignments = list(
            UserRoleAssignment.objects.filter(
                user=user,
                entity_id=entity_id,
                isactive=True,
                role__isactive=True,
            )
            .select_related("role")
            .order_by("-is_primary", "role__priority", "role__name")
        )
        if assignments:
            return [
                {
                    "id": assignment.role_id,
                    "name": assignment.role.name,
                    "code": assignment.role.code,
                    "description": assignment.role.description,
                    "source": "rbac",
                    "is_primary": assignment.is_primary,
                }
                for assignment in assignments
            ]

        legacy_role = (
            UserRole.objects.filter(user=user, entity_id=entity_id)
            .select_related("role")
            .order_by("id")
            .first()
        )
        if not legacy_role or not legacy_role.role_id:
            return []
        return [
            {
                "id": legacy_role.role_id,
                "name": legacy_role.role.rolename,
                "code": LegacyRBACCodes.role_code(legacy_role.role_id),
                "description": legacy_role.role.roledesc or "",
                "source": "legacy",
                "is_primary": True,
            }
        ]

    @staticmethod
    def permission_codes_for_user(user, entity_id, role_id=None):
        assignments = UserRoleAssignment.objects.filter(
            user=user,
            entity_id=entity_id,
            isactive=True,
            role__isactive=True,
        ).select_related("role")
        if role_id is not None:
            assignments = assignments.filter(role__code=LegacyRBACCodes.role_code(role_id))

        role_ids = list(assignments.values_list("role_id", flat=True))
        if not role_ids:
            return set()

        allowed = set(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                isactive=True,
                effect=RolePermission.EFFECT_ALLOW,
                permission__isactive=True,
            ).values_list("permission__code", flat=True)
        )
        denied = set(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                isactive=True,
                effect=RolePermission.EFFECT_DENY,
                permission__isactive=True,
            ).values_list("permission__code", flat=True)
        )
        return allowed - denied

    @staticmethod
    def entity_for_user(user, entity_id):
        return (
            Entity.objects.filter(id=entity_id)
            .filter(Q(userrole__user=user) | Q(user_role_assignments__user=user))
            .distinct()
            .first()
        )


class EffectiveMenuService:
    @staticmethod
    def _collect_visible_menu_ids(permission_codes):
        return LegacyMenuCompatibilityService._collect_visible_menu_ids(permission_codes)

    @staticmethod
    def _build_recursive_tree(menu_queryset):
        menu_list = list(menu_queryset)
        children_map = {}
        for menu in menu_list:
            children_map.setdefault(menu.parent_id, []).append(menu)

        def serialize_node(node):
            return {
                "id": node.id,
                "name": node.name,
                "code": node.route_name or node.code,
                "menu_code": node.code,
                "menu_type": node.menu_type,
                "route_path": node.route_path,
                "route_name": node.route_name,
                "icon": node.icon,
                "sort_order": node.sort_order,
                "depth": node.depth,
                "children": [
                    serialize_node(child)
                    for child in children_map.get(node.id, [])
                ],
            }

        return [serialize_node(root) for root in children_map.get(None, [])]

    @staticmethod
    def menu_tree_for_user(user, entity_id, role_id=None):
        permission_codes = EffectivePermissionService.permission_codes_for_user(user, entity_id, role_id=role_id)
        visible_menu_ids = EffectiveMenuService._collect_visible_menu_ids(permission_codes)
        if not visible_menu_ids:
            return []
        queryset = (
            Menu.objects.filter(id__in=visible_menu_ids, isactive=True)
            .only("id", "parent_id", "name", "code", "menu_type", "route_path", "route_name", "icon", "sort_order", "depth")
            .order_by("parent_id", "sort_order", "name")
        )
        return EffectiveMenuService._build_recursive_tree(queryset)


class LegacyMenuCompatibilityService:
    @staticmethod
    def _collect_visible_menu_ids(permission_codes):
        visible_ids = set(
            MenuPermission.objects.filter(
                permission__code__in=permission_codes,
                isactive=True,
                menu__isactive=True,
            ).values_list("menu_id", flat=True)
        )
        if not visible_ids:
            return visible_ids

        menu_map = {
            menu.id: menu.parent_id
            for menu in Menu.objects.filter(id__in=visible_ids).only("id", "parent_id")
        }
        pending_parent_ids = {parent_id for parent_id in menu_map.values() if parent_id}

        while pending_parent_ids:
            parents = Menu.objects.filter(id__in=pending_parent_ids, isactive=True).only("id", "parent_id")
            next_pending = set()
            for parent in parents:
                if parent.id not in visible_ids:
                    visible_ids.add(parent.id)
                if parent.parent_id and parent.parent_id not in visible_ids:
                    next_pending.add(parent.parent_id)
            pending_parent_ids = next_pending

        return visible_ids

    @staticmethod
    def _rbac_response(user, entity_id, role_id=None):
        permission_codes = EffectivePermissionService.permission_codes_for_user(user, entity_id, role_id=role_id)
        visible_menu_ids = LegacyMenuCompatibilityService._collect_visible_menu_ids(permission_codes)
        if not visible_menu_ids:
            return []

        menus = list(
            Menu.objects.filter(id__in=visible_menu_ids, isactive=True)
            .only("id", "parent_id", "name", "code", "route_path", "route_name", "sort_order")
            .order_by("sort_order", "name")
        )
        menu_by_parent = {}
        for menu in menus:
            menu_by_parent.setdefault(menu.parent_id, []).append(menu)

        final_rows = []
        for root in menu_by_parent.get(None, []):
            submenus = [
                {
                    "submenu": child.name,
                    "subMenuurl": child.route_path,
                    "submenucode": child.route_name or child.code,
                }
                for child in menu_by_parent.get(root.id, [])
            ]
            final_rows.append(
                {
                    "mainmenu": root.name,
                    "menuurl": root.route_path,
                    "menucode": root.route_name or root.code,
                    "submenu": submenus,
                }
            )
        return final_rows

    @staticmethod
    def _legacy_response(entity_id, role_id):
        rows = RolePrivilege.objects.filter(entity_id=entity_id, role_id=role_id).values(
            "submenu__mainmenu__id",
            "submenu__mainmenu__mainmenu",
            "submenu__mainmenu__menuurl",
            "submenu__mainmenu__menucode",
            "submenu__mainmenu__order",
            "submenu__id",
            "submenu__submenu",
            "submenu__subMenuurl",
            "submenu__submenucode",
            "submenu__order",
        ).order_by("submenu__mainmenu__order", "submenu__order", "submenu__id")

        grouped = {}
        for row in rows:
            key = row["submenu__mainmenu__id"]
            if key not in grouped:
                grouped[key] = {
                    "mainmenu": row["submenu__mainmenu__mainmenu"],
                    "menuurl": row["submenu__mainmenu__menuurl"],
                    "menucode": row["submenu__mainmenu__menucode"],
                    "submenu": [],
                }
            grouped[key]["submenu"].append(
                {
                    "submenu": row["submenu__submenu"],
                    "subMenuurl": row["submenu__subMenuurl"],
                    "submenucode": row["submenu__submenucode"],
                }
            )
        return list(grouped.values())

    @staticmethod
    def legacy_shape_for_user(user, entity_id, role_id=None):
        rbac_rows = LegacyMenuCompatibilityService._rbac_response(user, entity_id, role_id=role_id)
        if rbac_rows:
            return rbac_rows

        if role_id is None:
            user_role = UserRole.objects.filter(user=user, entity_id=entity_id).values_list("role_id", flat=True).first()
            role_id = user_role
        if role_id is None:
            return []
        return LegacyMenuCompatibilityService._legacy_response(entity_id, role_id)
