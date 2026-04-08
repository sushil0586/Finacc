from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from entity.models import Entity
from entity.models import SubEntity
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService

from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


User = get_user_model()


class RbacUserAccessAdminTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="Admin@123",
            first_name="Admin",
        )
        self.entity = Entity.objects.create(entityname="Acme", createdby=self.admin_user)
        SubscriptionService.register_entity_creation(entity=self.entity, owner=self.admin_user)
        self.entity.refresh_from_db()
        self.subentity = SubEntity.objects.create(subentityname="Head Office", entity=self.entity)
        self.admin_role = Role.objects.create(
            entity=self.entity,
            name="Entity Admin",
            code="entity.admin",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        for code in ("admin.user.view", "admin.user.create", "admin.user.update", "admin.role.view"):
            permission, _ = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": code,
                    "module": "admin",
                    "resource": "user",
                    "action": code.rsplit(".", 1)[-1],
                },
            )
            RolePermission.objects.get_or_create(role=self.admin_role, permission=permission)
        UserRoleAssignment.objects.create(
            user=self.admin_user,
            entity=self.entity,
            role=self.admin_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        self.client.force_authenticate(self.admin_user)

    def test_admin_user_search_is_limited_to_tenant_members(self):
        outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="Pass@123",
            first_name="Out",
            last_name="Sider",
        )

        response = self.client.get(
            reverse("rbac_api:admin-users"),
            {"entity": self.entity.id, "q": "outsider"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_create_and_assign_creates_user_and_assignment(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Operator",
            code="entity.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        effective_from = timezone.now()
        effective_to = effective_from + timedelta(days=7)

        response = self.client.post(
            reverse("rbac_api:admin-users-create-and-assign"),
            {
                "entity": self.entity.id,
                "first_name": "New",
                "last_name": "User",
                "email": "new.user@example.com",
                "username": "new.user",
                "password": "Secure@12345",
                "role": target_role.id,
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat(),
                "is_primary": True,
                "isactive": True,
                "scope_data": {"region": "north"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="new.user@example.com")
        assignment = UserRoleAssignment.objects.get(user=created_user, entity=self.entity, role=target_role)
        self.entity.refresh_from_db()
        self.assertTrue(assignment.is_primary)
        self.assertEqual(assignment.scope_data["region"], "north")
        self.assertIsNotNone(assignment.effective_from)
        self.assertIsNotNone(assignment.effective_to)
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=self.entity.customer_account,
                user=created_user,
                is_active=True,
            ).exists()
        )

    def test_bulk_assign_persists_effective_dates(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Reviewer",
            code="entity.reviewer",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        target_user = User.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="Review@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=target_user,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.admin_user,
        )
        effective_from = timezone.now()
        effective_to = effective_from + timedelta(days=10)

        response = self.client.post(
            reverse("rbac_api:admin-assignments-bulk"),
            {
                "entity": self.entity.id,
                "user_ids": [target_user.id],
                "role": target_role.id,
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat(),
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment = UserRoleAssignment.objects.get(user=target_user, entity=self.entity, role=target_role)
        self.entity.refresh_from_db()
        self.assertIsNotNone(assignment.effective_from)
        self.assertIsNotNone(assignment.effective_to)
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=self.entity.customer_account,
                user=target_user,
                is_active=True,
            ).exists()
        )

    def test_bulk_assign_rejects_user_without_tenant_membership(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Reviewer",
            code="entity.reviewer.2",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        outsider = User.objects.create_user(
            username="reviewer-out",
            email="reviewer-out@example.com",
            password="Review@123",
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments-bulk"),
            {
                "entity": self.entity.id,
                "user_ids": [outsider.id],
                "role": target_role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_ids", response.data)

    def test_new_primary_assignment_demotes_existing_primary(self):
        existing_role = Role.objects.create(
            entity=self.entity,
            name="Existing",
            code="entity.existing",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        existing_assignment = UserRoleAssignment.objects.create(
            user=self.admin_user,
            entity=self.entity,
            role=existing_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        target_role = Role.objects.create(
            entity=self.entity,
            name="Operator",
            code="entity.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": self.admin_user.id,
                "role": target_role.id,
                "is_primary": True,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        existing_assignment.refresh_from_db()
        new_assignment = UserRoleAssignment.objects.get(user=self.admin_user, entity=self.entity, role=target_role)
        self.assertFalse(existing_assignment.is_primary)
        self.assertTrue(new_assignment.is_primary)

    def test_subentity_scoped_assignment_cannot_be_primary(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Branch Operator",
            code="entity.branch.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": self.admin_user.id,
                "role": target_role.id,
                "subentity": self.subentity.id,
                "is_primary": True,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subentity", response.data)

    def test_single_assignment_rejects_user_without_tenant_membership(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Member Operator",
            code="entity.member.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        outsider = User.objects.create_user(
            username="outsider-role",
            email="outsider-role@example.com",
            password="Out@12345",
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": outsider.id,
                "role": target_role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user", response.data)

    def test_non_assignable_role_cannot_be_assigned(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="System Role",
            code="entity.system.role",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
            is_assignable=False,
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": self.admin_user.id,
                "role": target_role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)
