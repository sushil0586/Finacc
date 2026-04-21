from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity
from rbac.models import Menu, MenuPermission, Permission, Role, RolePermission, UserRoleAssignment


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class RBACAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="viewer@example.com",
            username="viewer@example.com",
            password="secret123",
            email_verified=True,
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            username="other@example.com",
            password="secret123",
            email_verified=True,
        )

        self.entity_a = Entity.objects.create(entityname="Entity A", createdby=self.user)
        self.entity_b = Entity.objects.create(entityname="Entity B", createdby=self.other_user)

        self.prefix = f"rbac.test.{self.entity_a.id}.{self.entity_b.id}"
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _grant_basic_access(self, *, entity, user):
        role = Role.objects.create(entity=entity, name="Viewer", code=f"viewer_{entity.id}")
        permission = Permission.objects.create(
            code=f"entity.{entity.id}.dashboard.view",
            name="View Dashboard",
            module="reports",
            resource="dashboard",
            action="view",
        )
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(user=user, entity=entity, role=role, is_primary=True)
        return role, permission

    def _grant_admin_permissions(self, *, entity, user, codes):
        role = Role.objects.create(entity=entity, name="RBAC Admin", code=f"rbac_admin_{entity.id}_{user.id}_{len(codes)}")
        for code in codes:
            permission, _ = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": code,
                    "module": "admin",
                    "resource": code.split(".")[1] if "." in code else "rbac",
                    "action": code.rsplit(".", 1)[-1],
                },
            )
            RolePermission.objects.get_or_create(role=role, permission=permission)
        UserRoleAssignment.objects.create(user=user, entity=entity, role=role, is_primary=True)
        return role

    def test_menu_tree_endpoint_returns_nested_children(self):
        root = Menu.objects.create(name="Sales", code=f"{self.prefix}.sales.root", menu_type=Menu.TYPE_GROUP)
        Menu.objects.create(name="Invoices", code=f"{self.prefix}.sales.invoices", parent=root)

        response = self.client.get("/api/rbac/menus")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(node["code"] == f"{self.prefix}.sales.root" for node in response.data))

    def test_permissions_endpoint_returns_catalog(self):
        Permission.objects.create(
            code=f"{self.prefix}.sales.invoice.view",
            name="View Sales Invoice",
            module="sales",
            resource="invoice",
            action="view",
        )

        response = self.client.get("/api/rbac/permissions")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["code"] == f"{self.prefix}.sales.invoice.view" for row in response.data))

    def test_user_menu_endpoints_return_recursive_tree_for_entity(self):
        root = Menu.objects.create(name="Sales", code=f"{self.prefix}.entity.sales", menu_type=Menu.TYPE_GROUP)
        child = Menu.objects.create(name="Invoices", code=f"{self.prefix}.entity.sales.invoices", parent=root)

        role, _ = self._grant_basic_access(entity=self.entity_a, user=self.user)
        perm_child = Permission.objects.create(
            code=f"{self.prefix}.entity.sales.invoices.view",
            name="View Invoices Menu",
            module="sales",
            resource="invoice",
            action="view",
        )
        menu_perm_root = Permission.objects.get(code=f"entity.{self.entity_a.id}.dashboard.view")
        MenuPermission.objects.create(menu=root, permission=menu_perm_root)
        MenuPermission.objects.create(menu=child, permission=perm_child)
        RolePermission.objects.create(role=role, permission=perm_child)

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity_a.id}&role={role.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["entity_id"], self.entity_a.id)
        self.assertEqual(response.data["menus"][0]["name"], "Sales")
        self.assertEqual(response.data["menus"][0]["code"], root.code)
        self.assertEqual(response.data["menus"][0]["children"][0]["name"], "Invoices")

    def test_user_menu_endpoint_returns_canonical_menu_codes_and_normalized_routes(self):
        root = Menu.objects.create(
            name="Admin",
            code=f"{self.prefix}.admin",
            menu_type=Menu.TYPE_GROUP,
            route_path="admin",
            route_name="admin",
        )
        child = Menu.objects.create(
            name="Users",
            code=f"{self.prefix}.admin.users",
            parent=root,
            route_path="user",
            route_name="user",
        )
        role, root_permission = self._grant_basic_access(entity=self.entity_a, user=self.user)
        child_permission = Permission.objects.create(
            code=f"{self.prefix}.admin.users.view",
            name="View Users Menu",
            module="admin",
            resource="user",
            action="view",
        )
        MenuPermission.objects.create(menu=root, permission=root_permission)
        MenuPermission.objects.create(menu=child, permission=child_permission)
        RolePermission.objects.create(role=role, permission=child_permission)

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity_a.id}&role={role.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["menus"][0]["code"], root.code)
        self.assertEqual(response.data["menus"][0]["route_path"], "/admin")
        self.assertEqual(response.data["menus"][0]["children"][0]["code"], child.code)
        self.assertEqual(response.data["menus"][0]["children"][0]["route_path"], "/user")

    def test_receivables_hub_menu_is_visible_to_receivables_roles(self):
        role = Role.objects.create(entity=self.entity_a, name="Receivables Viewer", code=f"receivables_{self.entity_a.id}")
        menu = Menu.objects.get(code="reports.financial_hub.receivables_hub")
        parent_permission = Permission.objects.get(code="reports.financial_hub.view")
        menu_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.view")
        permission = Permission.objects.get(code="reports.outstanding.view")
        RolePermission.objects.create(role=role, permission=parent_permission)
        RolePermission.objects.create(role=role, permission=menu_permission)
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity_a, role=role, is_primary=True)

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity_a.id}&role={role.id}")

        self.assertEqual(response.status_code, 200)
        def find_node(nodes, menu_code):
            for node in nodes:
                if node["code"] == menu_code:
                    return node
                child = find_node(node.get("children", []), menu_code)
                if child:
                    return child
            return None

        found = find_node(response.data["menus"], menu.code)
        self.assertIsNotNone(found)
        self.assertEqual(found["route_path"], "/reports/receivables")

    def test_customer_ledger_statement_menu_is_visible_to_receivables_roles(self):
        role = Role.objects.create(entity=self.entity_a, name="Receivables Viewer", code=f"receivables_{self.entity_a.id}_cls")
        menu = Menu.objects.get(code="reports.financial_hub.receivables_hub.customer_ledger_statement")
        parent_permission = Permission.objects.get(code="reports.financial_hub.view")
        hub_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.view")
        menu_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.customer_ledger_statement.view")
        permission = Permission.objects.get(code="reports.outstanding.view")
        RolePermission.objects.create(role=role, permission=parent_permission)
        RolePermission.objects.create(role=role, permission=hub_permission)
        RolePermission.objects.create(role=role, permission=menu_permission)
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity_a, role=role, is_primary=True)

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity_a.id}&role={role.id}")

        self.assertEqual(response.status_code, 200)

        def find_node(nodes, menu_code):
            for node in nodes:
                if node["code"] == menu_code:
                    return node
                child = find_node(node.get("children", []), menu_code)
                if child:
                    return child
            return None

        found = find_node(response.data["menus"], menu.code)
        self.assertIsNotNone(found)
        self.assertEqual(found["route_path"], "/reports/receivables/customer-ledger-statement")

    def test_customer_outstanding_menu_is_visible_to_receivables_roles(self):
        role = Role.objects.create(entity=self.entity_a, name="Receivables Viewer", code=f"receivables_{self.entity_a.id}_co")
        menu = Menu.objects.get(code="reports.financial_hub.receivables_hub.customer_outstanding")
        parent_permission = Permission.objects.get(code="reports.financial_hub.view")
        hub_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.view")
        menu_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.customer_outstanding.view")
        permission = Permission.objects.get(code="reports.outstanding.view")
        RolePermission.objects.create(role=role, permission=parent_permission)
        RolePermission.objects.create(role=role, permission=hub_permission)
        RolePermission.objects.create(role=role, permission=menu_permission)
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity_a, role=role, is_primary=True)

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity_a.id}&role={role.id}")

        self.assertEqual(response.status_code, 200)

        def find_node(nodes, menu_code):
            for node in nodes:
                if node["code"] == menu_code:
                    return node
                child = find_node(node.get("children", []), menu_code)
                if child:
                    return child
            return None

        found = find_node(response.data["menus"], menu.code)
        self.assertIsNotNone(found)
        self.assertEqual(found["route_path"], "/reports/receivables/customer-outstanding")

    def test_receivable_aging_menu_is_visible_to_receivables_roles(self):
        role = Role.objects.create(entity=self.entity_a, name="Receivables Viewer", code=f"receivables_{self.entity_a.id}_ra")
        menu = Menu.objects.get(code="reports.financial_hub.receivables_hub.receivable_aging")
        parent_permission = Permission.objects.get(code="reports.financial_hub.view")
        hub_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.view")
        menu_permission = Permission.objects.get(code="reports.financial_hub.receivables_hub.receivable_aging.view")
        permission = Permission.objects.get(code="reports.accounts_receivable_aging.view")
        RolePermission.objects.create(role=role, permission=parent_permission)
        RolePermission.objects.create(role=role, permission=hub_permission)
        RolePermission.objects.create(role=role, permission=menu_permission)
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity_a, role=role, is_primary=True)

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity_a.id}&role={role.id}")

        self.assertEqual(response.status_code, 200)

        def find_node(nodes, menu_code):
            for node in nodes:
                if node["code"] == menu_code:
                    return node
                child = find_node(node.get("children", []), menu_code)
                if child:
                    return child
            return None

        found = find_node(response.data["menus"], menu.code)
        self.assertIsNotNone(found)
        self.assertEqual(found["route_path"], "/reports/receivables/receivable-aging")

    def test_effective_access_preview_denies_when_requester_has_only_future_assignment(self):
        role = Role.objects.create(entity=self.entity_a, name="Reports User", code="REPORTS_USER")
        permission = Permission.objects.create(
            code=f"{self.prefix}.reports.dashboard.view",
            name="View Dashboard",
            module="reports",
            resource="dashboard",
            action="view",
        )
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity_a,
            role=role,
            effective_from=timezone.now() + timezone.timedelta(days=1),
        )

        response = self.client.get(f"/api/rbac/admin/access-preview?entity={self.entity_a.id}&user_id={self.user.id}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "You do not have access to this entity.")

    def test_role_clone_endpoint_clones_permissions(self):
        role = Role.objects.create(entity=self.entity_a, name="Sales User", code="SALES_USER")
        permission = Permission.objects.create(
            code=f"{self.prefix}.sales.invoice.view",
            name="View Sales Invoice",
            module="sales",
            resource="invoice",
            action="view",
        )
        RolePermission.objects.create(role=role, permission=permission)
        self._grant_admin_permissions(entity=self.entity_a, user=self.user, codes=("admin.role.create",))

        response = self.client.post(
            f"/api/rbac/admin/roles/{role.id}/clone?entity={self.entity_a.id}",
            {"name": "Sales User Copy", "code": "SALES_USER_COPY"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        cloned_role = Role.objects.get(code="SALES_USER_COPY", entity=self.entity_a)
        self.assertTrue(RolePermission.objects.filter(role=cloned_role, permission=permission).exists())

    def test_role_delete_is_soft_delete(self):
        role = Role.objects.create(entity=self.entity_a, name="Temp Role", code="TEMP_ROLE")
        self._grant_admin_permissions(entity=self.entity_a, user=self.user, codes=("admin.role.delete",))

        response = self.client.delete(f"/api/rbac/admin/roles/{role.id}?entity={self.entity_a.id}")

        self.assertEqual(response.status_code, 204)
        role.refresh_from_db()
        self.assertFalse(role.isactive)


    def test_future_assignment_cannot_access_admin_bootstrap(self):
        role = Role.objects.create(entity=self.entity_a, name="Future Role", code="FUTURE_ROLE")
        permission, _ = Permission.objects.get_or_create(
            code="admin.role.view",
            defaults={"name": "View Roles", "module": "admin", "resource": "role", "action": "view"},
        )
        RolePermission.objects.get_or_create(role=role, permission=permission)
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity_a,
            role=role,
            effective_from=timezone.now() + timezone.timedelta(days=1),
            is_primary=True,
        )

        response = self.client.get(f"/api/rbac/admin/bootstrap?entity={self.entity_a.id}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "You do not have access to this entity.")

    def test_tenant_boundary_denies_other_entity_access(self):
        self._grant_admin_permissions(entity=self.entity_a, user=self.user, codes=("admin.role.view",))

        response = self.client.get(f"/api/rbac/admin/bootstrap?entity={self.entity_b.id}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "You do not have access to this entity.")

    def test_permissions_regression_deny_overrides_allow(self):
        role_allow = Role.objects.create(entity=self.entity_a, name="Ops Allow", code="OPS_ALLOW")
        role_deny = Role.objects.create(entity=self.entity_a, name="Ops Deny", code="OPS_DENY")
        permission = Permission.objects.create(
            code=f"{self.prefix}.voucher.post",
            name="Post Voucher",
            module="voucher",
            resource="voucher",
            action="post",
        )
        RolePermission.objects.create(role=role_allow, permission=permission, effect=RolePermission.EFFECT_ALLOW)
        RolePermission.objects.create(role=role_deny, permission=permission, effect=RolePermission.EFFECT_DENY)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity_a, role=role_allow, is_primary=True)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity_a, role=role_deny, is_primary=False)

        response = self.client.get(f"/api/rbac/me/permissions?entity={self.entity_a.id}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f"{self.prefix}.voucher.post", response.data["permissions"])

    def test_admin_bootstrap_requires_explicit_role_view_permission(self):
        self._grant_basic_access(entity=self.entity_a, user=self.user)

        response = self.client.get(f"/api/rbac/admin/bootstrap?entity={self.entity_a.id}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "You do not have permission to perform this action for this entity.")

    def test_admin_bootstrap_exposes_capabilities_from_permissions(self):
        self._grant_admin_permissions(
            entity=self.entity_a,
            user=self.user,
            codes=("admin.role.view", "admin.role.update", "admin.user.view"),
        )

        response = self.client.get(f"/api/rbac/admin/bootstrap?entity={self.entity_a.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["capabilities"],
            {
                "can_view_roles": True,
                "can_manage_roles": True,
                "can_view_menus": True,
                "can_manage_menus": True,
                "can_view_role_access": True,
                "can_manage_role_access": True,
                "can_view_user_access": True,
                "can_manage_user_access": False,
                "can_preview_access": True,
                "can_view_audit": True,
            },
        )
