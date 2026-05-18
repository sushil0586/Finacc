from __future__ import annotations

from django.test import TestCase

from payroll.serializers.payroll_setup_serializers import SalaryStructureSerializer
from payroll.services.payroll_setup_service import PayrollSetupService
from payroll.tests.factories import PayrollFactory


class PayrollSetupContractTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.accounting = PayrollFactory.accounting_setup(entity=self.scope["entity"], user=self.scope["user"])
        self.payment_account = PayrollFactory.gl_account(
            entity=self.scope["entity"],
            user=self.scope["user"],
            accounthead=self.accounting["accounthead"],
            partytype="Employee",
        )
        self.component = PayrollFactory.component(entity=self.scope["entity"], code="BASIC")
        self.structure = PayrollFactory.salary_structure(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )
        self.version = PayrollFactory.salary_structure_version(
            salary_structure=self.structure,
            version_no=3,
        )
        self.version.calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "ctc",
        }
        self.version.save(update_fields=["calculation_policy_json"])
        PayrollFactory.salary_structure_line(
            salary_structure=self.structure,
            salary_structure_version=self.version,
            component=self.component,
            rule_mode="STANDARD",
            fixed_amount="50000.00",
            recurrence_frequency="MONTHLY",
            compensation_bucket="FIXED_PAY",
            ctc_treatment="INCLUDED",
            gross_treatment="INCLUDED",
        )
    def test_salary_structure_serializer_exposes_scope_and_current_version_metadata(self):
        prior_version = PayrollFactory.salary_structure_version(
            salary_structure=self.structure,
            version_no=2,
        )
        prior_version.status = "RETIRED"
        prior_version.calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
        }
        prior_version.save(update_fields=["status", "calculation_policy_json"])
        self.structure.current_version = self.version
        self.structure.save(update_fields=["current_version"])
        payload = SalaryStructureSerializer(self.structure).data

        self.assertEqual(payload["entity_name"], self.scope["entity"].entityname)
        self.assertEqual(payload["entityfin_name"], self.scope["entityfinid"].desc)
        self.assertEqual(payload["subentity_name"], self.scope["subentity"].subentityname)
        self.assertEqual(payload["current_version"]["version_no"], 3)
        self.assertEqual(payload["current_version"]["status"], "APPROVED")
        self.assertEqual(payload["current_version"]["calculation_policy_json"]["salary_mode"], "ctc")
        self.assertEqual(payload["current_version"]["lines"][0]["rule_mode"], "STANDARD")
        self.assertEqual(payload["current_version"]["lines"][0]["recurrence_frequency"], "MONTHLY")
        self.assertEqual(payload["current_version"]["lines"][0]["compensation_bucket"], "FIXED_PAY")
        self.assertEqual(payload["current_version"]["lines"][0]["ctc_treatment"], "INCLUDED")
        self.assertEqual(payload["current_version"]["lines"][0]["gross_treatment"], "INCLUDED")
        self.assertEqual(len(payload["available_versions"]), 2)
        self.assertEqual(payload["available_versions"][0]["version_no"], 3)
        self.assertEqual(payload["available_versions"][1]["status"], "RETIRED")

    def test_structure_version_service_persists_calculation_policy_json(self):
        newer_component = PayrollFactory.component(entity=self.scope["entity"], code="HRA")
        version = PayrollSetupService.create_structure_version(
            structure=self.structure,
            lines=[{
                "component": newer_component,
                "sequence": 2,
                "rule_mode": "CUSTOM_FORMULA",
                "calculation_basis": "FIXED",
                "fixed_amount": "15000.00",
                "recurrence_frequency": "QUARTERLY",
                "compensation_bucket": "VARIABLE_PAY",
                "ctc_treatment": "TARGET_ONLY",
                "gross_treatment": "EXCLUDED",
                "rule_json": {"type": "case", "default": {"value": 0}},
            }],
            approved_by=self.scope["user"],
            calculation_policy_json={
                "country_code": "IN",
                "salary_mode": "gross",
                "proration_basis": "payable_days",
                "rounding_policy": "round_up",
                "tds_standard_deduction_old_regime": "50000.00",
                "tds_standard_deduction_new_regime": "50000.00",
                "tds_allow_80c_old_regime": True,
                "tds_allow_80d_old_regime": False,
                "tds_allow_hra_exemption_old_regime": True,
                "tds_require_verified_tax_declarations_for_approval": True,
                "tds_80c_cap": "150000.00",
                "tds_80d_cap": "25000.00",
            },
        )

        self.assertEqual(version.version_no, 4)
        self.assertEqual(version.calculation_policy_json["salary_mode"], "gross")
        self.assertEqual(version.calculation_policy_json["proration_basis"], "payable_days")
        self.assertTrue(version.calculation_policy_json["tds_allow_80c_old_regime"])
        self.assertFalse(version.calculation_policy_json["tds_allow_80d_old_regime"])
        self.assertTrue(version.calculation_policy_json["tds_require_verified_tax_declarations_for_approval"])
        self.assertEqual(version.calculation_policy_json["tds_80c_cap"], "150000.00")
        self.assertEqual(version.lines.first().rule_mode, "CUSTOM_FORMULA")
        self.assertEqual(version.lines.first().recurrence_frequency, "QUARTERLY")
        self.assertEqual(version.lines.first().compensation_bucket, "VARIABLE_PAY")
        self.assertEqual(version.lines.first().ctc_treatment, "TARGET_ONLY")
        self.assertEqual(version.lines.first().gross_treatment, "EXCLUDED")
        self.assertEqual(version.lines.first().rule_json["type"], "case")
