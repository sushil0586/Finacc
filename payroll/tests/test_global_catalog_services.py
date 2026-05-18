from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from payroll.models import (
    GlobalPayrollComponent,
    GlobalPayrollComponentGroup,
    GlobalSalaryStructureTemplate,
    GlobalSalaryStructureTemplateLine,
    PayrollComponent,
    SalaryStructureLine,
    SalaryStructure,
    SalaryStructureVersion,
)
from payroll.services.entity_adoption_preview_service import EntityAdoptionPreviewService
from payroll.services.entity_salary_template_adoption_service import EntitySalaryTemplateAdoptionService
from payroll.services.payroll_global_catalog_service import GlobalPayrollCatalogService
from payroll.services.payroll_global_seed_service import PayrollGlobalSeedService
from payroll.services.payroll_global_template_service import GlobalSalaryTemplateService
from payroll.tests.factories import PayrollFactory


class GlobalPayrollCatalogServiceTests(TestCase):
    def setUp(self):
        self.group = GlobalPayrollCatalogService.create_or_update_component_group(
            {
                "code": "EARNINGS",
                "name": "Earnings",
                "group_type": "EARNINGS",
                "sort_order": 100,
                "is_active": True,
            }
        )

    def test_create_and_update_component_group_and_component(self):
        component = GlobalPayrollCatalogService.create_or_update_component(
            {
                "group": self.group,
                "code": "BASIC",
                "name": "Basic Salary",
                "component_type": "EARNING",
                "calculation_type": "PERCENTAGE",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        self.assertEqual(component.code, "BASIC")

        updated = GlobalPayrollCatalogService.create_or_update_component(
            {
                "name": "Basic Pay",
                "effective_from": date(2026, 4, 1),
            },
            instance=component,
        )
        self.assertEqual(updated.name, "Basic Pay")

    def test_template_line_sequence_validation(self):
        component = GlobalPayrollCatalogService.create_or_update_component(
            {
                "group": self.group,
                "code": "HRA",
                "name": "HRA",
                "component_type": "EARNING",
                "calculation_type": "PERCENTAGE",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        template = GlobalSalaryTemplateService.create_or_update_template(
            {
                "code": "IN_TEMPLATE",
                "name": "India Template",
                "template_type": "MONTHLY_STAFF",
                "pay_frequency": "MONTHLY",
                "effective_from": date(2026, 4, 1),
            }
        )
        GlobalSalaryTemplateService.create_or_update_line(
            template,
            {
                "component": component,
                "sequence": 100,
                "calculation_type": "PERCENTAGE",
            },
        )
        with self.assertRaisesMessage(ValueError, "sequence"):
            GlobalSalaryTemplateService.create_or_update_line(
                template,
                {
                    "component": GlobalPayrollCatalogService.create_or_update_component(
                        {
                            "group": self.group,
                            "code": "SPECIAL",
                            "name": "Special Allowance",
                            "component_type": "EARNING",
                            "calculation_type": "MANUAL",
                            "effective_from": date(2026, 4, 1),
                            "is_active": True,
                        }
                    ),
                    "sequence": 100,
                    "calculation_type": "MANUAL",
                },
            )


class GlobalPayrollAdoptionPreviewTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        seed_result = PayrollGlobalSeedService.seed_default_catalog()
        self.assertGreater(seed_result["components"]["created"], 0)
        self.template = GlobalSalaryStructureTemplate.objects.get(code="INDIA_SME_MONTHLY_STAFF")

    def test_preview_detects_existing_component_and_structure_conflicts(self):
        basic = GlobalPayrollComponent.objects.get(code="BASIC")
        PayrollComponent.objects.create(
            entity=self.scope["entity"],
            code="BASIC",
            name="Basic Existing",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
        )
        SalaryStructure.objects.create(
            entity=self.scope["entity"],
            code=self.template.code,
            name=self.template.name,
        )

        preview = EntityAdoptionPreviewService.preview_template(
            template=self.template,
            entity_id=self.scope["entity"].id,
        )

        self.assertTrue(any(item["code"] == basic.code for item in preview["components_existing"]))
        self.assertTrue(any("different component type" in item for item in preview["conflicts"]))
        self.assertTrue(any(self.template.code in item for item in preview["conflicts"]))


class EntitySalaryTemplateAdoptionServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        PayrollGlobalSeedService.seed_default_catalog()
        self.template = GlobalSalaryStructureTemplate.objects.get(code="INDIA_SME_MONTHLY_STAFF")

    def test_adoption_creates_missing_components_structure_version_and_lines(self):
        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.scope["entity"].id,
            global_template_id=self.template.id,
            effective_from=date(2026, 4, 1),
            entity_financial_year_id=self.scope["entityfinid"].id,
            subentity_id=self.scope["subentity"].id,
        )

        self.assertTrue(result["adopted"])
        self.assertGreater(len(result["created_components"]), 0)
        structure = SalaryStructure.objects.get(entity=self.scope["entity"], code=self.template.code)
        version = SalaryStructureVersion.objects.get(salary_structure=structure, version_no=1)
        lines = SalaryStructureLine.objects.filter(salary_structure=structure, salary_structure_version=version)
        self.assertEqual(lines.count(), self.template.lines.count())
        basic_line = lines.get(component__code="BASIC")
        self.assertEqual(basic_line.calculation_basis, SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC)
        hra_line = lines.get(component__code="HRA")
        self.assertEqual(hra_line.calculation_basis, SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT)

    def test_adoption_reuses_existing_components(self):
        PayrollComponent.objects.create(
            entity=self.scope["entity"],
            code="BASIC",
            name="Basic Existing",
            component_type=PayrollComponent.ComponentType.EARNING,
            posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
        )

        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.scope["entity"].id,
            global_template_id=self.template.id,
            effective_from=date(2026, 4, 1),
        )

        self.assertTrue(result["adopted"])
        self.assertTrue(any(item["code"] == "BASIC" for item in result["reused_components"]))

    def test_duplicate_structure_code_is_blocked(self):
        SalaryStructure.objects.create(
            entity=self.scope["entity"],
            code="INDIA_SME_MONTHLY_STAFF",
            name="Existing",
        )

        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.scope["entity"].id,
            global_template_id=self.template.id,
            effective_from=date(2026, 4, 1),
        )

        self.assertFalse(result["adopted"])
        self.assertTrue(any("already exists" in item for item in result["conflicts"]))

    def test_inactive_template_is_blocked(self):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])

        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.scope["entity"].id,
            global_template_id=self.template.id,
            effective_from=date(2026, 4, 1),
        )

        self.assertFalse(result["adopted"])
        self.assertTrue(any("Inactive global template" in item for item in result["conflicts"]))

    def test_inactive_component_blocks_adoption(self):
        component = GlobalPayrollComponent.objects.get(code="BASIC")
        component.is_active = False
        component.save(update_fields=["is_active"])

        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.scope["entity"].id,
            global_template_id=self.template.id,
            effective_from=date(2026, 4, 1),
        )

        self.assertFalse(result["adopted"])
        self.assertTrue(any("inactive" in item.lower() for item in result["conflicts"]))

    def test_dry_run_makes_no_writes(self):
        result = EntitySalaryTemplateAdoptionService.adopt(
            entity_id=self.scope["entity"].id,
            global_template_id=self.template.id,
            effective_from=date(2026, 4, 1),
            dry_run=True,
        )

        self.assertFalse(result["adopted"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(SalaryStructure.objects.filter(entity=self.scope["entity"], code=self.template.code).exists())
        self.assertFalse(PayrollComponent.objects.filter(entity=self.scope["entity"], code="BASIC").exists())

    def test_transaction_rolls_back_on_failure(self):
        with patch("payroll.services.entity_salary_template_adoption_service.SalaryStructureVersion.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                EntitySalaryTemplateAdoptionService.adopt(
                    entity_id=self.scope["entity"].id,
                    global_template_id=self.template.id,
                    effective_from=date(2026, 4, 1),
                )

        self.assertFalse(SalaryStructure.objects.filter(entity=self.scope["entity"], code=self.template.code).exists())
        self.assertFalse(PayrollComponent.objects.filter(entity=self.scope["entity"], code="BASIC").exists())


class GlobalPayrollSeedServiceTests(TestCase):
    def test_seed_is_idempotent(self):
        first = PayrollGlobalSeedService.seed_default_catalog()
        second = PayrollGlobalSeedService.seed_default_catalog()

        self.assertGreater(first["groups"]["created"], 0)
        self.assertEqual(second["groups"]["created"], 0)
        self.assertEqual(second["groups"]["updated"], 0)
        self.assertGreater(second["groups"]["skipped"], 0)
        self.assertTrue(GlobalSalaryStructureTemplate.objects.filter(code="INDIA_SME_MONTHLY_STAFF").exists())

    def test_seed_dry_run_creates_nothing(self):
        result = PayrollGlobalSeedService.seed_default_catalog(dry_run=True)

        self.assertGreater(result["groups"]["created"], 0)
        self.assertFalse(GlobalPayrollComponentGroup.objects.exists())
        self.assertFalse(GlobalPayrollComponent.objects.exists())
        self.assertFalse(GlobalSalaryStructureTemplate.objects.exists())

    def test_seed_force_updates_existing_system_record(self):
        PayrollGlobalSeedService.seed_default_catalog()
        component = GlobalPayrollComponent.objects.get(code="BASIC")
        component.name = "Old Basic Name"
        component.save(update_fields=["name"])

        result = PayrollGlobalSeedService.seed_default_catalog(force=True)

        component.refresh_from_db()
        self.assertGreater(result["components"]["updated"], 0)
        self.assertEqual(component.name, "Basic Salary")

    def test_seed_without_force_does_not_overwrite_existing_record(self):
        PayrollGlobalSeedService.seed_default_catalog()
        component = GlobalPayrollComponent.objects.get(code="BASIC")
        component.name = "Custom Basic Name"
        component.is_system = False
        component.save(update_fields=["name", "is_system"])

        result = PayrollGlobalSeedService.seed_default_catalog()

        component.refresh_from_db()
        self.assertEqual(component.name, "Custom Basic Name")
        self.assertGreater(result["components"]["skipped"], 0)
        self.assertTrue(any("BASIC" in item for item in result["warnings"]))

    def test_seed_creates_expected_groups_components_templates_and_lines(self):
        PayrollGlobalSeedService.seed_default_catalog()

        self.assertEqual(GlobalPayrollComponentGroup.objects.count(), 6)
        self.assertEqual(
            GlobalPayrollComponent.objects.count(),
            41,
        )
        self.assertEqual(GlobalSalaryStructureTemplate.objects.count(), 7)
        self.assertEqual(GlobalSalaryStructureTemplateLine.objects.count(), 57)
        self.assertTrue(GlobalPayrollComponent.objects.filter(code="DA").exists())
        self.assertTrue(GlobalPayrollComponent.objects.filter(code="OVERTIME_HOURS").exists())
        self.assertTrue(GlobalSalaryStructureTemplate.objects.filter(code="INDIA_FACTORY_WORKER").exists())

    def test_seed_sets_bonus_as_gross_affecting_earning(self):
        PayrollGlobalSeedService.seed_default_catalog()

        bonus = GlobalPayrollComponent.objects.get(code="BONUS")
        self.assertTrue(bonus.affects_gross)
        self.assertEqual(bonus.default_rule_json["scheme_code"], "BONUS")

    def test_executive_template_does_not_bake_reimbursements_into_fixed_structure(self):
        PayrollGlobalSeedService.seed_default_catalog()

        template = GlobalSalaryStructureTemplate.objects.get(code="INDIA_EXECUTIVE")
        line_codes = set(template.lines.values_list("component__code", flat=True))
        self.assertNotIn("FUEL_REIMBURSEMENT", line_codes)
        self.assertNotIn("MOBILE_REIMBURSEMENT", line_codes)

    def test_seed_only_groups_limits_work(self):
        result = PayrollGlobalSeedService.seed_default_catalog(only="groups")

        self.assertGreater(result["groups"]["created"], 0)
        self.assertEqual(result["components"]["created"], 0)
        self.assertEqual(result["templates"]["created"], 0)
        self.assertEqual(result["lines"]["created"], 0)
        self.assertEqual(GlobalPayrollComponentGroup.objects.count(), 6)
        self.assertEqual(GlobalPayrollComponent.objects.count(), 0)

    def test_missing_component_reference_raises_clear_error(self):
        original_templates = PayrollGlobalSeedService.TEMPLATES
        PayrollGlobalSeedService.TEMPLATES = (
            {
                "code": "BROKEN_TEMPLATE",
                "name": "Broken Template",
                "description": "Broken seed template.",
                "template_type": GlobalSalaryStructureTemplate.TemplateType.CUSTOM,
                "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
                "lines": [
                    {
                        "component": "UNKNOWN_COMPONENT",
                        "sequence": 100,
                        "calculation_type": GlobalSalaryStructureTemplateLine.CalculationType.FIXED,
                    }
                ],
            },
        )
        try:
            with self.assertRaisesMessage(ValueError, "UNKNOWN_COMPONENT"):
                PayrollGlobalSeedService.seed_default_catalog(only="templates")
        finally:
            PayrollGlobalSeedService.TEMPLATES = original_templates
