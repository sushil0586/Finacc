"""Services for applying the canonical RBAC catalog to database state."""

from __future__ import annotations

from django.db import transaction

from rbac import access_catalog
from rbac.models import Menu, MenuPermission, Permission


SEED_TAG = "canonical_launch_access_catalog_2026_09_21"
CATALOG_VERSION = "canonical_launch_access_catalog_2026_09_21"


class CanonicalRBACCatalogSeedService:
    """Apply the launch access catalog without relying on legacy menu shape."""

    @classmethod
    @transaction.atomic
    def seed_global_catalog(cls):
        permissions = cls._ensure_permissions()
        menus = cls._ensure_menus()
        cls._ensure_menu_permissions(menus=menus, permissions=permissions)
        cls._deactivate_legacy_menus()
        return {
            "permission_count": len(permissions),
            "menu_count": len(menus),
            "catalog_version": CATALOG_VERSION,
        }

    @staticmethod
    def _permission_defaults(permission_code):
        parts = permission_code.split(".")
        module = parts[0] if parts else "rbac"
        action = parts[-1] if len(parts) > 1 else "view"
        resource = "_".join(parts[1:-1]) if len(parts) > 2 else module
        name = " ".join(part.replace("_", " ").title() for part in parts)
        return {
            "name": name[:150],
            "module": module[:100],
            "resource": resource[:100],
            "action": action[:100],
            "description": f"Canonical launch permission for {permission_code}.",
            "scope_type": Permission.SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "feature_source": "rbac.access_catalog",
            },
            "isactive": True,
        }

    @classmethod
    def _ensure_permissions(cls):
        permission_codes = sorted(access_catalog.permission_codes_for_features(access_catalog.ALL_FEATURE_CODES))
        permissions = {}
        for code in permission_codes:
            defaults = cls._permission_defaults(code)
            permission, _ = Permission.objects.update_or_create(
                code=code,
                defaults=defaults,
            )
            permissions[code] = permission
        return permissions

    @staticmethod
    def _route_name_for(spec):
        if not spec.route_path:
            return f"{spec.code.replace('.', '-')}-section"
        return spec.route_path.strip("/").replace("/", "-") or spec.code.replace(".", "-")

    @classmethod
    def _menu_defaults(cls, spec, parent):
        return {
            "parent": parent,
            "name": spec.name,
            "menu_type": spec.menu_type,
            "route_path": spec.route_path,
            "route_name": cls._route_name_for(spec),
            "icon": spec.icon,
            "sort_order": spec.sort_order,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "feature_code": spec.feature_code,
                "permission_code": spec.permission_code,
                "access_mode": spec.access_mode,
                "is_canonical": spec.canonical,
                "default_role_codes": list(spec.default_role_codes),
            },
            "isactive": True,
        }

    @classmethod
    def _ensure_menus(cls):
        menus = {}
        pending = list(access_catalog.MENU_SPECS)

        while pending:
            next_pending = []
            progress = False
            for spec in pending:
                parent = None
                if spec.parent_code:
                    parent = menus.get(spec.parent_code) or Menu.objects.filter(code=spec.parent_code).first()
                    if parent is None:
                        next_pending.append(spec)
                        continue

                menu, _ = Menu.objects.update_or_create(
                    code=spec.code,
                    defaults=cls._menu_defaults(spec, parent),
                )
                menus[spec.code] = menu
                progress = True

            if not progress and next_pending:
                missing = ", ".join(spec.code for spec in next_pending)
                raise ValueError(f"Unable to seed menu catalog; missing parents for: {missing}")
            pending = next_pending

        return menus

    @staticmethod
    def _ensure_menu_permissions(*, menus, permissions):
        for spec in access_catalog.MENU_SPECS:
            menu = menus[spec.code]
            permission = permissions[spec.permission_code]
            MenuPermission.objects.update_or_create(
                menu=menu,
                permission=permission,
                relation_type=MenuPermission.RELATION_VISIBILITY,
                defaults={"isactive": True},
            )

    @staticmethod
    def _normalise_route(route_path):
        return (route_path or "").strip().strip("/").lower()

    @classmethod
    def _deactivate_menu_queryset(cls, queryset, *, metadata):
        menu_ids = list(queryset.values_list("id", flat=True))
        if not menu_ids:
            return
        Menu.objects.filter(id__in=menu_ids).update(
            isactive=False,
            metadata=metadata,
        )
        MenuPermission.objects.filter(menu_id__in=menu_ids).update(isactive=False)

    @classmethod
    def _deactivate_legacy_menus(cls):
        for code in access_catalog.LEGACY_MENU_CODES_TO_DISABLE:
            cls._deactivate_menu_queryset(
                Menu.objects.filter(code=code),
                metadata={
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "deactivated_as_legacy": True,
                },
            )
            cls._deactivate_menu_queryset(
                Menu.objects.filter(code__startswith=f"{code}."),
                metadata={
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "deactivated_as_legacy": True,
                },
            )

        cls._deactivate_menu_queryset(
            Menu.objects.filter(code__in=access_catalog.LEGACY_DUPLICATE_MENU_CODES_TO_DISABLE),
            metadata={
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "deactivated_as_duplicate_legacy_menu": True,
            },
        )

        canonical_codes = {spec.code for spec in access_catalog.MENU_SPECS}
        canonical_routes = {
            cls._normalise_route(spec.route_path): spec.code
            for spec in access_catalog.MENU_SPECS
            if spec.route_path
        }
        duplicate_legacy_ids = []

        for menu in Menu.objects.filter(isactive=True).only("id", "code", "route_path"):
            route_key = cls._normalise_route(menu.route_path)
            canonical_code = canonical_routes.get(route_key)
            if not canonical_code or menu.code in canonical_codes:
                continue
            duplicate_legacy_ids.append((menu.id, canonical_code, route_key))

        for menu_id, canonical_code, route_key in duplicate_legacy_ids:
            cls._deactivate_menu_queryset(
                Menu.objects.filter(id=menu_id),
                metadata={
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "deactivated_as_duplicate_canonical_route": True,
                    "canonical_code": canonical_code,
                    "canonical_route": route_key,
                },
            )

        empty_legacy_group_ids = []
        for menu in Menu.objects.filter(isactive=True, route_path="").exclude(code__in=canonical_codes):
            if not menu.children.filter(isactive=True).exists():
                empty_legacy_group_ids.append(menu.id)

        if empty_legacy_group_ids:
            cls._deactivate_menu_queryset(
                Menu.objects.filter(id__in=empty_legacy_group_ids),
                metadata={
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "deactivated_as_empty_legacy_group": True,
                },
            )
