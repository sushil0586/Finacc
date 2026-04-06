from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from entity.models import Entity

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

    def test_admin_user_search_returns_global_user_matches(self):
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
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], outsider.id)
        self.assertEqual(response.data[0]["entity_assignment_count"], 0)

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
        self.assertTrue(assignment.is_primary)
        self.assertEqual(assignment.scope_data["region"], "north")
        self.assertIsNotNone(assignment.effective_from)
        self.assertIsNotNone(assignment.effective_to)

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
        self.assertIsNotNone(assignment.effective_from)
        self.assertIsNotNone(assignment.effective_to)
