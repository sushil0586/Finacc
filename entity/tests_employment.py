from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityEmploymentProfile, EntityOrgUnit, SubEntity
from subscriptions.services import SubscriptionService


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class EntityEmploymentApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="employment-owner@example.com",
            username="employment-owner@example.com",
            password="secret123",
            email_verified=True,
            first_name="Owner",
            last_name="User",
        )
        self.employee = User.objects.create_user(
            email="employee@example.com",
            username="employee@example.com",
            password="secret123",
            email_verified=True,
            first_name="Asha",
            last_name="Patel",
        )
        self.manager = User.objects.create_user(
            email="manager@example.com",
            username="manager@example.com",
            password="secret123",
            email_verified=True,
            first_name="Rahul",
            last_name="Sharma",
        )
        self.other_user = User.objects.create_user(
            email="employment-other@example.com",
            username="employment-other@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Employment Entity", createdby=self.owner)
        SubscriptionService.register_entity_creation(entity=self.entity, owner=self.owner)
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Bengaluru Branch",
            branch_type=SubEntity.BranchType.BRANCH,
        )
        self.department = EntityOrgUnit.objects.create(
            entity=self.entity,
            unit_type=EntityOrgUnit.UnitType.DEPARTMENT,
            code="ENG",
            name="Engineering",
            createdby=self.owner,
        )
        self.designation = EntityOrgUnit.objects.create(
            entity=self.entity,
            unit_type=EntityOrgUnit.UnitType.DESIGNATION,
            code="SSE",
            name="Senior Software Engineer",
            createdby=self.owner,
        )
        self.location = EntityOrgUnit.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            unit_type=EntityOrgUnit.UnitType.WORK_LOCATION,
            code="BLR",
            name="Bengaluru Office",
            createdby=self.owner,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_create_employment_profile_with_scoped_org_units(self):
        response = self.client.post(
            "/api/entity/employment/",
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "employee_user": self.employee.id,
                "employee_code": "EMP-1001",
                "full_name": "Asha Patel",
                "work_email": "asha@example.com",
                "department": self.department.id,
                "designation": self.designation.id,
                "work_location": self.location.id,
                "manager_user": self.manager.id,
                "employment_type": "full_time",
                "work_type": "hybrid",
                "status": "active",
                "effective_from": "2025-04-01",
                "date_of_joining": "2025-04-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["department_name"], "Engineering")
        self.assertEqual(response.data["designation_name"], "Senior Software Engineer")
        self.assertEqual(response.data["manager_name"], "Rahul Sharma")
        self.assertTrue(
            EntityEmploymentProfile.objects.filter(
                entity=self.entity,
                employee_user=self.employee,
                employee_code="EMP-1001",
            ).exists()
        )

    def test_employment_profile_rejects_wrong_org_unit_type(self):
        response = self.client.post(
            "/api/entity/employment/",
            {
                "entity": self.entity.id,
                "employee_user": self.employee.id,
                "employee_code": "EMP-1002",
                "full_name": "Asha Patel",
                "department": self.designation.id,
                "effective_from": "2025-04-01",
                "date_of_joining": "2025-04-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["department"][0], "Org unit must be of type 'department'.")

    def test_list_current_only_filters_open_employment_rows(self):
        EntityEmploymentProfile.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee_user=self.employee,
            employee_code="EMP-OPEN",
            full_name="Asha Patel",
            work_email="asha@example.com",
            department=self.department,
            designation=self.designation,
            work_location=self.location,
            effective_from=date(2025, 4, 1),
            date_of_joining=date(2025, 4, 1),
        )
        EntityEmploymentProfile.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee_user=self.employee,
            employee_code="EMP-OLD",
            full_name="Asha Patel",
            work_email="asha@example.com",
            department=self.department,
            designation=self.designation,
            work_location=self.location,
            status=EntityEmploymentProfile.EmploymentStatus.EXITED,
            effective_from=date(2024, 4, 1),
            effective_to=date(2025, 3, 31),
            date_of_joining=date(2024, 4, 1),
        )

        response = self.client.get(f"/api/entity/employment/?entity={self.entity.id}&current_only=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["employee_code"] for row in response.data], ["EMP-OPEN"])

    def test_manager_list_returns_current_non_exited_profiles(self):
        EntityEmploymentProfile.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee_user=self.manager,
            employee_code="MGR-1",
            full_name="Rahul Sharma",
            work_email="manager@example.com",
            department=self.department,
            designation=self.designation,
            work_location=self.location,
            effective_from=date(2025, 4, 1),
            date_of_joining=date(2025, 4, 1),
        )
        EntityEmploymentProfile.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee_user=self.employee,
            employee_code="EMP-REP",
            full_name="Asha Patel",
            work_email="asha@example.com",
            department=self.department,
            designation=self.designation,
            work_location=self.location,
            manager_user=self.manager,
            effective_from=date(2025, 4, 1),
            date_of_joining=date(2025, 4, 1),
        )

        manager_response = self.client.get(f"/api/entity/employment/managers/?entity={self.entity.id}")
        report_response = self.client.get(
            f"/api/entity/employment/?entity={self.entity.id}&manager_user={self.manager.id}"
        )
        hierarchy_response = self.client.get(
            f"/api/entity/employment/hierarchy/?entity={self.entity.id}&employee_user={self.employee.id}"
        )

        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual({row["employee_code"] for row in manager_response.data}, {"MGR-1", "EMP-REP"})
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual([row["employee_code"] for row in report_response.data], ["EMP-REP"])
        self.assertEqual(hierarchy_response.status_code, 200)
        self.assertEqual(hierarchy_response.data["employee_code"], "EMP-REP")
        self.assertEqual(hierarchy_response.data["depth"], 1)
        self.assertEqual(hierarchy_response.data["chain"][0]["employee_code"], "MGR-1")

    def test_non_member_cannot_access_employment_profiles(self):
        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)

        response = other_client.get(f"/api/entity/employment/?entity={self.entity.id}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "tenant_membership_required")
