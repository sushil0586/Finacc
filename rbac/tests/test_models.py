from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, SubEntity
from rbac.models import Menu, Permission, Role, RolePermission, UserRoleAssignment
from rbac.seeding import PayrollRBACSeedService
from rbac.services import EffectivePermissionService, RoleTemplateService


class RBACModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="admin@example.com",
            username="admin@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Demo Entity", createdby=self.user)
        self.subentity = SubEntity.objects.create(
            subentityname="Branch 1",
            entity=self.entity,
        )

    def test_role_assignment_supports_multiple_roles_per_entity(self):
        role1 = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        role2 = Role.objects.create(entity=self.entity, name="Reports User", code="REPORT_USER")

        UserRoleAssignment.objects.create(user=self.user, entity=self.entity, role=role1)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity, role=role2)

        self.assertEqual(
            UserRoleAssignment.objects.filter(user=self.user, entity=self.entity).count(),
            2,
        )

    def test_menu_supports_multi_level_hierarchy(self):
        root = Menu.objects.create(name="Sales", code="test.sales", menu_type=Menu.TYPE_GROUP)
        child = Menu.objects.create(name="Invoices", code="test.sales.invoices", parent=root)
        grandchild = Menu.objects.create(name="Credit Notes", code="test.sales.invoices.credit-notes", parent=child)

        self.assertEqual(root.depth, 0)
        self.assertEqual(child.depth, 1)
        self.assertEqual(grandchild.depth, 2)

    def test_menu_cycle_validation(self):
        root = Menu.objects.create(name="Sales", code="test.cycle.sales")
        child = Menu.objects.create(name="Invoices", code="test.cycle.sales.invoices", parent=root)
        root.parent = child

        with self.assertRaises(ValidationError):
            root.save()

    def test_role_permission_unique(self):
        role = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        permission = Permission.objects.create(
            code="test.sales.invoice.view",
            name="View Sales Invoice",
            module="sales",
            resource="invoice",
            action="view",
        )
        RolePermission.objects.create(role=role, permission=permission)

        with self.assertRaises(IntegrityError):
            RolePermission.objects.create(role=role, permission=permission)

    def test_assignment_effective_window_property(self):
        role = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        future_assignment = UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=role,
            effective_from=timezone.now() + timezone.timedelta(days=1),
        )
        self.assertFalse(future_assignment.is_currently_effective)

    def test_assignment_subentity_entity_mismatch_validation(self):
        other_entity = Entity.objects.create(entityname="Other", createdby=self.user)
        role = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        foreign_subentity = SubEntity.objects.create(subentityname="Other Branch", entity=other_entity)
        assignment = UserRoleAssignment(
            user=self.user,
            entity=self.entity,
            role=role,
            subentity=foreign_subentity,
        )

        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_primary_assignment_cannot_be_subentity_scoped(self):
        role = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        assignment = UserRoleAssignment(
            user=self.user,
            entity=self.entity,
            role=role,
            subentity=self.subentity,
            is_primary=True,
        )

        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_primary_assignment_must_be_active(self):
        role = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        assignment = UserRoleAssignment(
            user=self.user,
            entity=self.entity,
            role=role,
            is_primary=True,
            isactive=False,
        )

        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_entity_for_user_requires_tenant_membership(self):
        outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider@example.com",
            password="secret123",
            email_verified=True,
        )
        role = Role.objects.create(entity=self.entity, name="Viewer", code="VIEWER")
        UserRoleAssignment.objects.create(
            user=outsider,
            entity=self.entity,
            role=role,
            is_primary=True,
        )

        resolved = EffectivePermissionService.entity_for_user(outsider, self.entity.id)

        self.assertIsNone(resolved)

    def test_payroll_rbac_seed_service_is_idempotent(self):
        first = PayrollRBACSeedService.seed_entity_roles(entity=self.entity, actor=self.user)
        second = PayrollRBACSeedService.seed_entity_roles(entity=self.entity, actor=self.user)

        self.assertEqual(first["permission_count"], 33)
        self.assertEqual(first["menu_count"], 10)
        self.assertEqual(second["permission_count"], 33)
        self.assertEqual(second["menu_count"], 10)

        self.assertTrue(Permission.objects.filter(code="payroll.run.post", isactive=True).exists())
        self.assertTrue(Menu.objects.filter(code="payroll.runs", route_path="/payroll/runs", isactive=True).exists())

        operator_role = Role.objects.get(entity=self.entity, code="payroll_operator")
        finance_role = Role.objects.get(entity=self.entity, code="payroll_finance_manager")
        readonly_role = Role.objects.get(entity=self.entity, code="payroll_read_only_reviewer")
        admin_role = Role.objects.get(entity=self.entity, code="admin")

        self.assertTrue(RolePermission.objects.filter(role=operator_role, permission__code="payroll.run.calculate", isactive=True).exists())
        self.assertFalse(RolePermission.objects.filter(role=operator_role, permission__code="payroll.run.approve", isactive=True).exists())
        self.assertTrue(RolePermission.objects.filter(role=finance_role, permission__code="payments.payroll.reconcile", isactive=True).exists())
        self.assertTrue(RolePermission.objects.filter(role=readonly_role, permission__code="payroll.component.view", isactive=True).exists())
        self.assertFalse(RolePermission.objects.filter(role=readonly_role, permission__code="reports.payroll.export", isactive=True).exists())
        self.assertEqual(
            RolePermission.objects.filter(role=admin_role, permission__module__in=["payroll", "reports", "payments"], isactive=True).count(),
            33,
        )

    def test_role_template_service_uses_permission_code_prefixes_not_menu_metadata(self):
        sales_permission = Permission.objects.create(
            code="sales.template_test.create",
            name="Create Sales Template Test",
            module="misc",
            resource="misc",
            action="create",
            metadata={},
        )
        unrelated_permission = Permission.objects.create(
            code="inventory.template_test.post",
            name="Post Inventory Adjustment",
            module="sales",
            resource="inventory",
            action="post",
            metadata={"menu_code": "sales.transactions.inventory"},
        )

        template_permissions = set(
            RoleTemplateService._permission_queryset_for_template("sales_user").values_list("id", flat=True)
        )

        self.assertIn(sales_permission.id, template_permissions)
        self.assertNotIn(unrelated_permission.id, template_permissions)
