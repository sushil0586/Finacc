import os
import re
from pathlib import Path

from django.test import SimpleTestCase

from rbac import access_catalog


PERMISSION_LITERAL_RE = re.compile(
    r"'([a-zA-Z0-9_.]+\.(?:view|manage|create|update|delete|post|unpost|cancel|confirm|print|export|handoff|approve|operate|ensure|edit|validate|file|change))'"
)


def _normalize_route(path: str | None) -> str:
    value = (path or "").strip().strip("\"'")
    value = value.split("?", 1)[0].split("#", 1)[0]
    value = value.replace("/#/", "/")
    return value.strip().strip("/").lower()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _route_matches_template(route: str, template: str) -> bool:
    route_parts = [part for part in route.split("/") if part]
    template_parts = [part for part in template.split("/") if part]
    if len(route_parts) != len(template_parts):
        return False
    return all(template_part.startswith(":") or route_part == template_part for route_part, template_part in zip(route_parts, template_parts))


class FrontendBackendRouteSyncTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.frontend_root = cls._resolve_frontend_root()
        if cls.frontend_root is None:
            return

        cls.frontend_routes, cls.frontend_permissions = cls._collect_frontend_contract(cls.frontend_root)
        cls.frontend_route_templates = {route for route in cls.frontend_routes if ":" in route}

    @classmethod
    def _resolve_frontend_root(cls) -> Path | None:
        configured = os.environ.get("FINACC_FRONTEND_DIR")
        candidates = []
        if configured:
            candidates.append(Path(configured))

        repo_root = Path(__file__).resolve().parents[4]
        candidates.extend(
            [
                repo_root / "accountproject",
                repo_root / "finacc-angular" / "accountproject",
            ]
        )

        for candidate in candidates:
            if (candidate / "src/app/app-routing.module.ts").exists():
                return candidate
        return None

    @classmethod
    def _collect_frontend_contract(cls, frontend_root: Path) -> tuple[set[str], set[str]]:
        routes: set[str] = set()
        permissions: set[str] = set()

        app_routing = frontend_root / "src/app/app-routing.module.ts"
        app_ts = _read(app_routing)

        for match in re.finditer(r"(?:lazyProtected(?:Dirty|Module)?Route|redirectRoute)\(\s*'([^']+)'", app_ts):
            route = _normalize_route(match.group(1))
            if route and route != "**":
                routes.add(route)

        for match in re.finditer(r"path:\s*'([^']+)'", app_ts):
            route = _normalize_route(match.group(1))
            if route and route != "**":
                routes.add(route)

        permissions.update(PERMISSION_LITERAL_RE.findall(app_ts))

        child_route_files = (
            ("payroll", frontend_root / "src/app/payroll/payroll-routing.module.ts", ("protectedPayrollRoute", "essPayrollRoute")),
            ("hrms", frontend_root / "src/app/hrms/hrms-routing.module.ts", ("protectedHrmsRoute",)),
            ("bank-reco", frontend_root / "src/app/bank-reco/bank-reco-routing.module.ts", ("protectedBankRecoRoute",)),
        )
        for prefix, route_file, helper_names in child_route_files:
            if not route_file.exists():
                continue

            routes.add(prefix)
            ts = _read(route_file)
            helper_pattern = "|".join(re.escape(helper_name) for helper_name in helper_names)
            for match in re.finditer(rf"(?:{helper_pattern})\(\s*'([^']+)'", ts):
                route = _normalize_route(f"{prefix}/{match.group(1)}")
                if route:
                    routes.add(route)
            permissions.update(PERMISSION_LITERAL_RE.findall(ts))

        auth_guard = frontend_root / "src/app/guard/auth.guard.ts"
        if auth_guard.exists():
            permissions.update(PERMISSION_LITERAL_RE.findall(_read(auth_guard)))

        return routes, permissions

    def _assert_frontend_available(self):
        if self.frontend_root is None:
            self.skipTest("Angular frontend checkout not found. Set FINACC_FRONTEND_DIR to enable RBAC route sync checks.")

    def _frontend_route_exists(self, route: str) -> bool:
        if route in self.frontend_routes:
            return True
        return any(_route_matches_template(route, template) for template in self.frontend_route_templates)

    def test_backend_catalog_menu_routes_exist_in_frontend(self):
        self._assert_frontend_available()

        missing_routes = []
        for spec in access_catalog.MENU_SPECS:
            route = _normalize_route(spec.route_path)
            if route and not self._frontend_route_exists(route):
                missing_routes.append(f"{spec.code} -> /{route}")

        self.assertEqual(missing_routes, [])

    def test_frontend_guard_permissions_exist_in_backend_catalog(self):
        self._assert_frontend_available()

        backend_permissions = access_catalog.permission_codes_for_features(access_catalog.ALL_FEATURE_CODES)
        missing_permissions = sorted(self.frontend_permissions - backend_permissions)

        self.assertEqual(missing_permissions, [])
