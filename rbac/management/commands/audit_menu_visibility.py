from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from rbac.models import Menu, MenuPermission, Permission


class Command(BaseCommand):
    help = "Audit active RBAC screen menus that are missing visibility permission mappings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-missing",
            action="store_true",
            help="Exit with a non-zero status when missing mappings are found.",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Auto-create visibility mappings when a single best-match permission is found.",
        )

    def _unmapped_screen_menus(self):
        return (
            Menu.objects.filter(isactive=True, menu_type=Menu.TYPE_SCREEN)
            .annotate(
                visibility_count=Count(
                    "menu_permissions",
                    filter=Q(
                        menu_permissions__isactive=True,
                        menu_permissions__relation_type=MenuPermission.RELATION_VISIBILITY,
                    ),
                    distinct=True,
                )
            )
            .filter(visibility_count=0)
            .order_by("code")
        )

    def _find_candidates(self, menu):
        route_name = (menu.route_name or "").strip()
        route_path = (menu.route_path or "").strip().replace("/", ".")

        checks = [
            Q(metadata__menu_code=menu.code),
            Q(code=f"{menu.code}.view"),
            Q(code=f"{menu.code}.access"),
        ]
        if route_name:
            checks.extend([
                Q(code=f"{route_name}.view"),
                Q(code=f"{route_name}.access"),
            ])
        if route_path:
            checks.extend([
                Q(code=f"{route_path}.view"),
                Q(code=f"{route_path}.access"),
            ])

        query = checks[0]
        for item in checks[1:]:
            query |= item

        candidates = list(Permission.objects.filter(isactive=True).filter(query).order_by("code"))

        # Stable prioritization: menu_code metadata > exact menu.code prefixes > route-derived.
        def rank(permission):
            code = permission.code or ""
            if permission.metadata.get("menu_code") == menu.code:
                return 0
            if code in {f"{menu.code}.view", f"{menu.code}.access"}:
                return 1
            if route_name and code in {f"{route_name}.view", f"{route_name}.access"}:
                return 2
            if route_path and code in {f"{route_path}.view", f"{route_path}.access"}:
                return 3
            return 9

        return sorted(candidates, key=lambda permission: (rank(permission), permission.code))

    def _try_auto_map(self, menu):
        candidates = self._find_candidates(menu)
        if len(candidates) != 1:
            return False, candidates

        permission = candidates[0]
        MenuPermission.objects.update_or_create(
            menu=menu,
            permission=permission,
            relation_type=MenuPermission.RELATION_VISIBILITY,
            defaults={"isactive": True},
        )
        return True, candidates

    def handle(self, *args, **options):
        unmapped = list(self._unmapped_screen_menus())
        count = len(unmapped)
        if count == 0:
            self.stdout.write(self.style.SUCCESS("RBAC audit passed: all active screen menus have visibility mappings."))
            return

        fix_enabled = bool(options.get("fix"))
        self.stdout.write(
            self.style.WARNING(
                f"RBAC audit found {count} active screen menu(s) without visibility mappings:"
            )
        )

        fixed = 0
        unresolved = 0
        for menu in unmapped:
            mapped = False
            candidates = []
            if fix_enabled:
                mapped, candidates = self._try_auto_map(menu)
                if mapped:
                    fixed += 1
            if not mapped:
                unresolved += 1
                if not candidates:
                    candidates = self._find_candidates(menu)

            candidate_codes = ", ".join(permission.code for permission in candidates[:5]) or "none"
            suffix = " [fixed]" if mapped else ""
            self.stdout.write(
                f"- id={menu.id} code={menu.code} route={menu.route_path or '-'} parent_id={menu.parent_id or '-'} candidates={candidate_codes}{suffix}"
            )

        if fix_enabled:
            self.stdout.write(
                self.style.SUCCESS(f"Auto-fix summary: fixed={fixed}, unresolved={unresolved}.")
            )

        if unresolved > 0:
            self.stdout.write(
                "Tip: map unresolved menus via Admin -> RBAC Management -> Menus -> Access Rules."
            )

        if options.get("fail_on_missing") and unresolved > 0:
            raise SystemExit(1)
