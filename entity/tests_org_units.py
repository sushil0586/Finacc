from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityOrgUnit, SubEntity
from subscriptions.services import SubscriptionService


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class EntityOrgUnitApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="org-owner@example.com",
            username="org-owner@example.com",
            password="secret123",
            email_verified=True,
        )
        self.other_user = User.objects.create_user(
            email="org-other@example.com",
            username="org-other@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Org Scoped Entity", createdby=self.owner)
        SubscriptionService.register_entity_creation(entity=self.entity, owner=self.owner)
        self.shared_branch = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )
        self.city_branch = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Mumbai Branch",
            branch_type=SubEntity.BranchType.BRANCH,
        )
        self.shared_department = EntityOrgUnit.objects.create(
            entity=self.entity,
            unit_type=EntityOrgUnit.UnitType.DEPARTMENT,
            code="OPS",
            name="Operations",
            createdby=self.owner,
        )
        self.branch_department = EntityOrgUnit.objects.create(
            entity=self.entity,
            subentity=self.city_branch,
            unit_type=EntityOrgUnit.UnitType.DEPARTMENT,
            code="OPS-MUM",
            name="Operations Mumbai",
            parent=self.shared_department,
            createdby=self.owner,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_list_org_units_requires_entity_scope(self):
        response = self.client.get("/api/entity/org-units/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["entity"]), "entity is required.")

    def test_resolved_subentity_list_includes_shared_and_specific_units(self):
        response = self.client.get(
            f"/api/entity/org-units/?entity={self.entity.id}&subentity={self.city_branch.id}&unit_type=department&resolution_mode=resolved"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["code"] for row in response.data], ["OPS", "OPS-MUM"])

    def test_create_org_unit_persists_entity_scoped_payload(self):
        response = self.client.post(
            "/api/entity/org-units/",
            {
                "entity": self.entity.id,
                "subentity": self.city_branch.id,
                "unit_type": "work_location",
                "code": "MUM-HQ",
                "name": "Mumbai HQ",
                "status": "active",
                "sort_order": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["code"], "MUM-HQ")
        self.assertEqual(response.data["subentity_name"], "Mumbai Branch")
        self.assertTrue(
            EntityOrgUnit.objects.filter(
                entity=self.entity,
                subentity=self.city_branch,
                unit_type=EntityOrgUnit.UnitType.WORK_LOCATION,
                code="MUM-HQ",
            ).exists()
        )

    def test_non_member_cannot_access_entity_org_units(self):
        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)

        response = other_client.get(f"/api/entity/org-units/?entity={self.entity.id}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "tenant_membership_required")

    def test_create_org_unit_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/entity/org-units/",
            {
                "entity": self.entity.id,
                "subentity": self.city_branch.id,
                "unit_type": "work_location",
                "code": "C" * 41,
                "name": "N" * 151,
                "short_name": "S" * 81,
                "description": "D" * 256,
                "manager_title": "M" * 101,
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)
        self.assertIn("short_name", response.data)
        self.assertIn("description", response.data)
        self.assertIn("manager_title", response.data)
