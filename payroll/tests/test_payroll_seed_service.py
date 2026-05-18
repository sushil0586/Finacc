from __future__ import annotations

from django.test import TestCase

from payroll.models import PayrollComponent, SalaryStructure, SalaryStructureLine
from payroll.services.payroll_seed_service import PayrollSeedService
from payroll.tests.factories import PayrollFactory


class PayrollSeedServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()

    def test_seeded_template_uses_india_default_component_semantics(self):
        PayrollSeedService.seed_payroll_components(entity_id=self.scope["entity"].id)
        PayrollSeedService.seed_salary_structure_templates(entity_id=self.scope["entity"].id)

        structure = SalaryStructure.objects.get(
            entity=self.scope["entity"],
            code=PayrollSeedService.TEMPLATE_CODE,
        )
        version = structure.current_version

        self.assertEqual(version.calculation_policy_json["country_code"], "IN")
        self.assertEqual(version.calculation_policy_json["salary_mode"], "ctc")
        self.assertEqual(version.calculation_policy_json["proration_basis"], "calendar_days")
        self.assertEqual(version.calculation_policy_json["rounding_policy"], "half_up")
        self.assertEqual(version.calculation_policy_json["pf_wage_cap"], "15000.00")
        self.assertEqual(version.calculation_policy_json["pf_employee_rate"], "12.00")
        self.assertEqual(version.calculation_policy_json["pf_employer_rate"], "12.00")
        self.assertEqual(version.calculation_policy_json["professional_tax_threshold"], "15000.00")
        self.assertEqual(version.calculation_policy_json["professional_tax_amount"], "200.00")
        self.assertEqual(version.calculation_policy_json["esi_wage_threshold"], "21000.00")
        self.assertEqual(version.calculation_policy_json["esi_employee_rate"], "0.75")
        self.assertEqual(version.calculation_policy_json["esi_employer_rate"], "3.25")
        self.assertEqual(version.calculation_policy_json["tds_default_remaining_periods"], "12")
        self.assertEqual(version.calculation_policy_json["tds_projection_rate"], "10.00")
        self.assertEqual(version.calculation_policy_json["tds_projection_rate_old_regime"], "10.00")
        self.assertEqual(version.calculation_policy_json["tds_projection_rate_new_regime"], "12.00")
        self.assertEqual(version.calculation_policy_json["tds_standard_deduction_old_regime"], "50000.00")
        self.assertEqual(version.calculation_policy_json["tds_standard_deduction_new_regime"], "50000.00")
        self.assertEqual(version.calculation_policy_json["tds_old_regime_slabs"][1]["upto"], "500000.00")
        self.assertEqual(version.calculation_policy_json["tds_old_regime_slabs"][1]["rate"], "5.00")
        self.assertEqual(version.calculation_policy_json["tds_new_regime_slabs"][2]["upto"], "1200000.00")
        self.assertEqual(version.calculation_policy_json["tds_new_regime_slabs"][2]["rate"], "10.00")
        self.assertEqual(version.calculation_policy_json["tds_rebate_threshold_old_regime"], "500000.00")
        self.assertEqual(version.calculation_policy_json["tds_rebate_max_old_regime"], "12500.00")
        self.assertEqual(version.calculation_policy_json["tds_rebate_threshold_new_regime"], "1200000.00")
        self.assertEqual(version.calculation_policy_json["tds_rebate_max_new_regime"], "60000.00")
        self.assertEqual(version.calculation_policy_json["tds_old_regime_surcharge_slabs"][1]["rate"], "10.00")
        self.assertEqual(version.calculation_policy_json["tds_new_regime_surcharge_slabs"][-1]["rate"], "25.00")
        self.assertEqual(version.calculation_policy_json["tds_health_education_cess_rate"], "4.00")
        self.assertTrue(version.calculation_policy_json["tds_apply_marginal_relief"])
        self.assertTrue(version.calculation_policy_json["tds_allow_80c_old_regime"])
        self.assertTrue(version.calculation_policy_json["tds_allow_80d_old_regime"])
        self.assertTrue(version.calculation_policy_json["tds_allow_hra_exemption_old_regime"])
        self.assertFalse(version.calculation_policy_json["tds_require_verified_hra_evidence_for_approval"])
        self.assertFalse(version.calculation_policy_json["tds_require_verified_tax_declarations_for_approval"])
        self.assertEqual(version.calculation_policy_json["tds_80c_cap"], "150000.00")
        self.assertEqual(version.calculation_policy_json["tds_80d_cap"], "25000.00")
        self.assertEqual(version.calculation_policy_json["compensation_policy"]["salary_mode"], "ctc")
        self.assertEqual(version.calculation_policy_json["compensation_policy"]["proration_basis"], "calendar_days")
        self.assertEqual(version.calculation_policy_json["statutory_policy"]["pf"]["wage_cap"], "15000.00")
        self.assertEqual(version.calculation_policy_json["statutory_policy"]["professional_tax"]["amount"], "200.00")
        self.assertEqual(version.calculation_policy_json["tax_policy"]["code"], "IN_TDS")
        self.assertEqual(version.calculation_policy_json["tax_policy"]["tds"]["cap_80c"], "150000.00")
        self.assertEqual(version.calculation_policy_json["review_policy"]["require_verified_hra_evidence_for_approval"], False)

        basic_line = version.lines.get(component__code="BASIC")
        hra_line = version.lines.get(component__code="HRA")
        special_line = version.lines.get(component__code="SPECIAL_ALLOWANCE")
        bonus_line = version.lines.get(component__code="BONUS")
        incentive_line = version.lines.get(component__code="INCENTIVE")
        pf_employee_line = version.lines.get(component__code="PF_EMPLOYEE")
        pf_employer_line = version.lines.get(component__code="PF_EMPLOYER")
        esi_employee_line = version.lines.get(component__code="ESI_EMPLOYEE")
        esi_employer_line = version.lines.get(component__code="ESI_EMPLOYER")

        self.assertEqual(basic_line.calculation_basis, SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC)
        self.assertEqual(str(basic_line.rate), "40.0000")
        self.assertEqual(basic_line.compensation_bucket, SalaryStructureLine.CompensationBucket.FIXED_PAY)
        self.assertEqual(hra_line.calculation_basis, SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT)
        self.assertEqual(hra_line.basis_component_id, basic_line.component_id)
        self.assertEqual(str(hra_line.rate), "40.0000")
        self.assertEqual(special_line.calculation_basis, SalaryStructureLine.CalculationBasis.INPUT)
        self.assertEqual(bonus_line.recurrence_frequency, SalaryStructureLine.RecurrenceFrequency.QUARTERLY)
        self.assertEqual(bonus_line.compensation_bucket, SalaryStructureLine.CompensationBucket.VARIABLE_PAY)
        self.assertEqual(bonus_line.ctc_treatment, SalaryStructureLine.CTCTreatment.TARGET_ONLY)
        self.assertEqual(bonus_line.gross_treatment, SalaryStructureLine.GrossTreatment.EXCLUDED)
        self.assertEqual(incentive_line.compensation_bucket, SalaryStructureLine.CompensationBucket.VARIABLE_PAY)
        self.assertEqual(pf_employee_line.calculation_basis, SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT)
        self.assertEqual(pf_employee_line.basis_component_id, basic_line.component_id)
        self.assertEqual(str(pf_employee_line.rate), "12.0000")
        self.assertEqual(pf_employee_line.compensation_bucket, SalaryStructureLine.CompensationBucket.STATUTORY)
        self.assertEqual(pf_employer_line.calculation_basis, SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT)
        self.assertEqual(pf_employer_line.basis_component_id, basic_line.component_id)
        self.assertEqual(str(pf_employer_line.rate), "12.0000")
        self.assertEqual(pf_employer_line.compensation_bucket, SalaryStructureLine.CompensationBucket.EMPLOYER_COST)
        self.assertEqual(esi_employee_line.calculation_basis, SalaryStructureLine.CalculationBasis.INPUT)
        self.assertEqual(esi_employer_line.calculation_basis, SalaryStructureLine.CalculationBasis.INPUT)
        self.assertEqual(basic_line.component.semantic_code, PayrollComponent.SemanticCode.BASIC_PAY)
        self.assertEqual(hra_line.component.semantic_code, PayrollComponent.SemanticCode.HRA)
        self.assertEqual(special_line.component.semantic_code, PayrollComponent.SemanticCode.SPECIAL_ALLOWANCE)
        self.assertEqual(pf_employee_line.component.semantic_code, PayrollComponent.SemanticCode.PF_EMPLOYEE)
        self.assertEqual(pf_employer_line.component.semantic_code, PayrollComponent.SemanticCode.PF_EMPLOYER)
        self.assertEqual(esi_employee_line.component.semantic_code, PayrollComponent.SemanticCode.ESI_EMPLOYEE)
        self.assertEqual(esi_employer_line.component.semantic_code, PayrollComponent.SemanticCode.ESI_EMPLOYER)

    def test_seeded_templates_cover_standard_india_onboarding_scenarios(self):
        PayrollSeedService.seed_payroll_components(entity_id=self.scope["entity"].id)
        PayrollSeedService.seed_salary_structure_templates(entity_id=self.scope["entity"].id)

        templates = set(
            SalaryStructure.objects.filter(entity=self.scope["entity"]).values_list("code", flat=True)
        )

        self.assertTrue({"IND_MONTHLY_CTC_STD", "IND_MONTHLY_GROSS_STD", "IND_CONSULTANT_STD", "IND_ATTENDANCE_WORKER_STD"}.issubset(templates))

        consultant = SalaryStructure.objects.get(entity=self.scope["entity"], code="IND_CONSULTANT_STD")
        consultant_version = consultant.current_version
        self.assertEqual(consultant_version.calculation_policy_json["salary_mode"], "gross")
        self.assertEqual(consultant_version.lines.get(component__code="BONUS").recurrence_frequency, SalaryStructureLine.RecurrenceFrequency.YEARLY)
        self.assertEqual(consultant_version.lines.get(component__code="TDS").compensation_bucket, SalaryStructureLine.CompensationBucket.STATUTORY)

        attendance = SalaryStructure.objects.get(entity=self.scope["entity"], code="IND_ATTENDANCE_WORKER_STD")
        attendance_version = attendance.current_version
        self.assertEqual(attendance_version.calculation_policy_json["proration_basis"], "attendance_days")
        self.assertEqual(attendance_version.lines.get(component__code="OVERTIME").compensation_bucket, SalaryStructureLine.CompensationBucket.VARIABLE_PAY)
