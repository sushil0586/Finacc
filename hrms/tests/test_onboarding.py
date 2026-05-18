from __future__ import annotations

from datetime import date

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from Authentication.models import User
from entity.models import Entity
from hrms.models import (
    AttendancePolicy,
    GlobalLeavePolicyTemplate,
    GlobalLeaveType,
    GlobalShiftTemplate,
    HRPolicy,
    HrEmployee,
    HrEmploymentContract,
    HrHolidayCalendar,
    HrShift,
    LeavePolicy,
    LeavePolicyRule,
    LeaveType,
)
from hrms.services import HrmsGlobalAdoptionService, HrmsRuntimePolicyService


class HrmsGlobalSeedCommandTests(TestCase):
    def test_seed_global_hrms_catalog_creates_templates(self):
        call_command("seed_global_hrms_catalog")

        self.assertTrue(GlobalLeaveType.objects.filter(code="CL").exists())
        self.assertTrue(GlobalLeaveType.objects.filter(code="EL").exists())
        self.assertTrue(GlobalLeavePolicyTemplate.objects.filter(code="SME_OFFICE_STD").exists())
        self.assertTrue(GlobalShiftTemplate.objects.filter(code="GENERAL_9_6").exists())


class HrmsGlobalAdoptionServiceTests(TestCase):
    def setUp(self):
        call_command("seed_global_hrms_catalog")
        self.user = User.objects.create_user(
            email="hrms-onboarding@example.com",
            username="hrms-onboarding@example.com",
            password="testpass123",
        )
        self.entity = Entity.objects.create(entityname="HRMS Onboarding Entity", createdby=self.user)
        self.employee = HrEmployee.objects.create(
            entity=self.entity,
            employee_number="EMP-HRMS-1",
            legal_first_name="Diya",
            legal_last_name="Nair",
            display_name="Diya Nair",
            work_email="diya@example.com",
            created_by=self.user,
            updated_by=self.user,
        )
        self.contract = HrEmploymentContract.objects.create(
            entity=self.entity,
            employee=self.employee,
            contract_code="CTR-HRMS-1",
            start_date=date(2026, 4, 1),
            payroll_effective_from=date(2026, 4, 1),
            created_by=self.user,
            updated_by=self.user,
        )

    def test_adoption_preview_returns_recommended_templates(self):
        preview = HrmsGlobalAdoptionService.preview_adoption(
            entity=self.entity,
            industry_type="services",
            employee_category="services",
            year=2026,
        )

        self.assertGreaterEqual(len(preview["templates"]["leave_policy_templates"]), 1)
        self.assertGreaterEqual(len(preview["templates"]["shift_templates"]), 1)
        self.assertGreaterEqual(len(preview["templates"]["attendance_policy_templates"]), 1)

    def test_adoption_clones_global_templates_into_entity_setup(self):
        result = HrmsGlobalAdoptionService.adopt_recommended_templates(
            entity=self.entity,
            industry_type="services",
            employee_category="services",
            year=2026,
        )

        self.assertGreaterEqual(LeaveType.objects.filter(entity=self.entity).count(), 1)
        self.assertGreaterEqual(LeavePolicy.objects.filter(entity=self.entity).count(), 1)
        self.assertGreaterEqual(LeavePolicyRule.objects.filter(entity=self.entity).count(), 1)
        self.assertGreaterEqual(HrShift.objects.filter(entity=self.entity).count(), 1)
        self.assertGreaterEqual(HrHolidayCalendar.objects.filter(entity=self.entity).count(), 1)
        self.assertGreaterEqual(AttendancePolicy.objects.filter(entity=self.entity).count(), 1)
        self.assertGreaterEqual(HRPolicy.objects.filter(entity=self.entity).count(), 1)
        self.assertIn("summary", result)

    def test_entity_edits_do_not_modify_global_templates(self):
        HrmsGlobalAdoptionService.adopt_recommended_templates(
            entity=self.entity,
            industry_type="services",
            employee_category="services",
            year=2026,
        )
        leave_type = LeaveType.objects.filter(entity=self.entity).first()
        global_name = leave_type.source_global_leave_type.name

        leave_type.name = "Entity Casual Leave"
        leave_type.save()

        leave_type.source_global_leave_type.refresh_from_db()
        self.assertEqual(leave_type.source_global_leave_type.name, global_name)

    def test_runtime_uses_entity_adopted_setup_only(self):
        HrmsGlobalAdoptionService.adopt_recommended_templates(
            entity=self.entity,
            industry_type="services",
            employee_category="services",
            year=2026,
        )

        runtime = HrmsRuntimePolicyService.resolve_runtime_setup(contract=self.contract)

        self.assertIsNotNone(runtime["leave_policy_id"])
        self.assertIsNotNone(runtime["attendance_policy_id"])
        self.assertIsNotNone(runtime["shift_id"])
        self.assertIsNotNone(runtime["holiday_calendar_id"])


class HrmsOnboardingApiTests(APITestCase):
    def setUp(self):
        call_command("seed_global_hrms_catalog")
        self.user = User.objects.create_user(
            email="hrms-onboarding-api@example.com",
            username="hrms-onboarding-api@example.com",
            password="testpass123",
        )
        self.entity = Entity.objects.create(entityname="HRMS Onboarding API Entity", createdby=self.user)
        self.client.force_authenticate(self.user)

    def test_adoption_preview_api_works(self):
        response = self.client.get(
            "/api/hrms/onboarding/adoption-preview/",
            {"entity": self.entity.id, "industry_type": "services", "employee_category": "services", "year": 2026},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("templates", response.data)
        self.assertGreaterEqual(len(response.data["templates"]["leave_policy_templates"]), 1)

    def test_adopt_templates_api_clones_setup(self):
        response = self.client.post(
            "/api/hrms/onboarding/adopt/",
            {
                "entity": self.entity.id,
                "mode": "recommended",
                "industry_type": "services",
                "employee_category": "services",
                "year": 2026,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(LeavePolicy.objects.filter(entity=self.entity).count(), 1)
