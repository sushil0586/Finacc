from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity
from rbac.models import Role, UserRoleAssignment


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class EntityContextAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="context-user@example.com",
            username="context-user@example.com",
            password="secret123",
            email_verified=True,
        )
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Scoped Entity", createdby=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_entities_list_ignores_future_assignments(self):
        role = Role.objects.create(entity=self.entity, name="Viewer", code="VIEWER")
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=role,
            effective_from=timezone.now() + timezone.timedelta(days=1),
            is_primary=True,
        )

        response = self.client.get("/api/entity/me/entities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_entity_scoped_endpoint_denies_future_assignment(self):
        role = Role.objects.create(entity=self.entity, name="Viewer", code="VIEWER_FY")
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=role,
            effective_from=timezone.now() + timezone.timedelta(days=1),
            is_primary=True,
        )

        response = self.client.get(f"/api/entity/me/entities/{self.entity.id}/financial-years")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "Entity not found or access denied.")
