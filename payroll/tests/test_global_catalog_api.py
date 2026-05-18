from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import GlobalPayrollComponentGroup, GlobalSalaryStructureTemplate, SalaryStructure
from payroll.services.payroll_global_seed_service import PayrollGlobalSeedService
from payroll.tests.factories import PayrollFactory


class GlobalPayrollCatalogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)

    def test_component_group_create_and_list(self):
        create_response = self.client.post(
            "/api/payroll/global/component-groups/",
            {
                "code": "EARNINGS",
                "name": "Earnings",
                "group_type": "EARNINGS",
                "sort_order": 100,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)

        list_response = self.client.get("/api/payroll/global/component-groups/")
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        results = payload if isinstance(payload, list) else payload.get("results", payload)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["code"], "EARNINGS")

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    def test_adoption_preview_enforces_scope_and_returns_preview(self, _assert_entity_access):
        scope = PayrollFactory.entity_scope(user=self.user)
        PayrollGlobalSeedService.seed_default_catalog()
        template = GlobalSalaryStructureTemplate.objects.get(code="INDIA_SME_MONTHLY_STAFF")

        response = self.client.post(
            f"/api/payroll/global/salary-templates/{template.id}/adoption-preview/",
            {"entity": scope["entity"].id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("components_to_create", response.json())

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    def test_adopt_executes_and_returns_summary(self, _assert_entity_access):
        scope = PayrollFactory.entity_scope(user=self.user)
        PayrollGlobalSeedService.seed_default_catalog()
        template = GlobalSalaryStructureTemplate.objects.get(code="INDIA_SME_MONTHLY_STAFF")

        response = self.client.post(
            f"/api/payroll/global/salary-templates/{template.id}/adopt/",
            {
                "entity": scope["entity"].id,
                "entityfinid": scope["entityfinid"].id,
                "subentity": scope["subentity"].id,
                "effective_from": "2026-04-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertTrue(payload["adopted"])
        self.assertTrue(SalaryStructure.objects.filter(entity=scope["entity"], code=template.code).exists())

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    def test_adopt_returns_conflict_for_duplicate_structure_code(self, _assert_entity_access):
        scope = PayrollFactory.entity_scope(user=self.user)
        PayrollGlobalSeedService.seed_default_catalog()
        template = GlobalSalaryStructureTemplate.objects.get(code="INDIA_SME_MONTHLY_STAFF")
        SalaryStructure.objects.create(entity=scope["entity"], code=template.code, name="Existing")

        response = self.client.post(
            f"/api/payroll/global/salary-templates/{template.id}/adopt/",
            {
                "entity": scope["entity"].id,
                "effective_from": "2026-04-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(response.json()["conflicts"])

    def test_template_lines_create_and_patch(self):
        group = GlobalPayrollComponentGroup.objects.create(
            code="EARNINGS",
            name="Earnings",
            group_type="EARNINGS",
        )
        component_response = self.client.post(
            "/api/payroll/global/components/",
            {
                "group": str(group.id),
                "code": "BASIC",
                "name": "Basic Salary",
                "component_type": "EARNING",
                "calculation_type": "PERCENTAGE",
                "effective_from": str(date(2026, 4, 1)),
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(component_response.status_code, 201, component_response.content)

        template_response = self.client.post(
            "/api/payroll/global/salary-templates/",
            {
                "code": "IN_TEST",
                "name": "India Test",
                "template_type": "MONTHLY_STAFF",
                "country_code": "IN",
                "pay_frequency": "MONTHLY",
                "effective_from": str(date(2026, 4, 1)),
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(template_response.status_code, 201, template_response.content)

        template_id = template_response.json()["id"]
        component_id = component_response.json()["id"]
        line_response = self.client.post(
            f"/api/payroll/global/salary-templates/{template_id}/lines/",
            {
                "component": component_id,
                "sequence": 100,
                "calculation_type": "PERCENTAGE",
                "percentage_default": "40.0000",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(line_response.status_code, 201, line_response.content)

        line_id = line_response.json()["id"]
        patch_response = self.client.patch(
            f"/api/payroll/global/salary-template-lines/{line_id}/",
            {"formula": "40% of CTC"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(patch_response.json()["formula"], "40% of CTC")
