from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from payroll.models import ContractPayrollInputSnapshot, ContractTaxDeclaration, PayrollComponent, PayrollRun, PayrollRunEmployee, SalaryStructureLine
from payroll.services import (
    ContractPayrollInputSnapshotService,
    ContractTaxDeclarationService,
    PayrollCalculationInputResolver,
    PayrollRunService,
    PayslipService,
)
from payroll.tests.factories import PayrollFactory


class PayrollTDSFoundationTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["salary_assignment"].gross_amount = Decimal("50000.00")
        self.setup["salary_assignment"].ctc_amount = Decimal("50000.00")
        self.setup["salary_assignment"].save(update_fields=["gross_amount", "ctc_amount", "updated_at"])
        self.setup["contract_profile"].tax_regime = "OLD"
        self.setup["contract_profile"].save(update_fields=["tax_regime", "updated_at"])

    def _create_declaration(self, **overrides):
        payload = {
            "entity": self.setup["entity"],
            "contract_payroll_profile": self.setup["contract_profile"],
            "financial_year": self.setup["entityfinid"],
            "tax_regime": "OLD",
            "declaration_status": ContractTaxDeclaration.DeclarationStatus.APPROVED,
            "declared_annual_income": "600000.00",
            "annual_other_income": "0.00",
            "previous_employer_income": "0.00",
            "previous_employer_tds": "0.00",
            "standard_deduction_amount": "50000.00",
            "professional_tax_declared": "0.00",
            "is_active": True,
        }
        payload.update(overrides)
        return ContractTaxDeclarationService.create_or_update_declaration(payload)

    def _resolve_input(self):
        return PayrollCalculationInputResolver.resolve(
            contract_payroll_profile=self.setup["contract_profile"],
            salary_assignment=self.setup["salary_assignment"],
            readiness_snapshot={},
            payroll_date=self.setup["period"].period_end,
            payroll_period=self.setup["period"],
        )

    def test_resolver_respects_old_and_new_regime_selection(self):
        self._create_declaration(tax_regime="OLD", declared_annual_income="600000.00")
        resolved_old = self._resolve_input()
        self.assertEqual(resolved_old.tax_projection_snapshot["projected_monthly_tds"], "1950.00")
        self.assertEqual(resolved_old.tax_projection_snapshot["tax_regime"], "OLD")

        declaration = ContractTaxDeclaration.objects.get(contract_payroll_profile=self.setup["contract_profile"])
        self.setup["contract_profile"].tax_regime = "NEW"
        self.setup["contract_profile"].save(update_fields=["tax_regime", "updated_at"])
        updated = ContractTaxDeclarationService.create_or_update_declaration(
            {
                "tax_regime": "NEW",
                "declared_annual_income": "600000.00",
            },
            instance=declaration,
        )
        resolved_new = self._resolve_input()
        self.assertEqual(updated.projected_monthly_tds, Decimal("0.00"))
        self.assertEqual(resolved_new.tax_projection_snapshot["projected_monthly_tds"], "0.00")
        self.assertEqual(resolved_new.tax_projection_snapshot["tax_regime"], "NEW")

    def test_declaration_deductions_reduce_projected_tds(self):
        self.setup["salary_assignment"].gross_amount = Decimal("75000.00")
        self.setup["salary_assignment"].ctc_amount = Decimal("75000.00")
        self.setup["salary_assignment"].save(update_fields=["gross_amount", "ctc_amount", "updated_at"])
        declaration = self._create_declaration(declared_annual_income="900000.00")
        before = self._resolve_input()
        before_amount = Decimal(before.tax_projection_snapshot["projected_monthly_tds"])

        ContractTaxDeclarationService.create_or_update_line(
            {
                "declaration": declaration,
                "section_code": "80C",
                "description": "ELSS",
                "declared_amount": "150000.00",
                "approved_amount": "150000.00",
                "evidence_required": True,
                "evidence_status": "VERIFIED",
                "is_active": True,
                "metadata": {},
            }
        )
        ContractTaxDeclarationService.create_or_update_line(
            {
                "declaration": declaration,
                "section_code": "80D",
                "description": "Health insurance",
                "declared_amount": "25000.00",
                "approved_amount": "25000.00",
                "evidence_required": True,
                "evidence_status": "VERIFIED",
                "is_active": True,
                "metadata": {},
            }
        )

        after = self._resolve_input()
        after_amount = Decimal(after.tax_projection_snapshot["projected_monthly_tds"])
        self.assertLess(after_amount, before_amount)
        self.assertEqual(after.tax_projection_snapshot["annual_deduction_total"], "225000.00")
        self.assertEqual(after.tax_projection_snapshot["projected_taxable_income"], "675000.00")

    def test_monthly_tds_projection_uses_already_deducted_and_remaining_periods(self):
        self._create_declaration(
            declared_annual_income="600000.00",
            previous_employer_tds="2400.00",
        )
        ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.setup["contract_profile"],
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                "input_json": {
                    "tds_deducted_ytd": "6000.00",
                    "remaining_periods": "6",
                },
                "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )
        resolved = self._resolve_input()
        self.assertEqual(resolved.tax_projection_snapshot["projected_annual_tax"], "23400.00")
        self.assertEqual(resolved.tax_projection_snapshot["tax_already_deducted"], "8400.00")
        self.assertEqual(resolved.tax_projection_snapshot["balance_tax"], "15000.00")
        self.assertEqual(resolved.tax_projection_snapshot["projected_monthly_tds"], "2500.00")

    def test_missing_declaration_falls_back_to_contract_and_assignment_projection(self):
        resolved = self._resolve_input()
        self.assertEqual(resolved.tax_projection_snapshot["annual_gross_projection"], "600000.00")
        self.assertEqual(resolved.tax_projection_snapshot["projected_monthly_tds"], "1950.00")
        self.assertEqual(resolved.source_markers["tds_projection_engine"], "payroll_tds_engine")

    def test_payslip_payload_includes_tds_trace(self):
        self.setup["line"].fixed_amount = Decimal("50000.00")
        self.setup["line"].save(update_fields=["fixed_amount"])
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._create_declaration(
            declared_annual_income="600000.00",
            previous_employer_tds="2400.00",
        )
        ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.setup["contract_profile"],
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                "input_json": {
                    "tds_deducted_ytd": "6000.00",
                    "remaining_periods": "6",
                },
                "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            semantic_code=PayrollComponent.SemanticCode.TDS,
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
        )
        tds_line = PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=250,
        )
        tds_line.calculation_basis = SalaryStructureLine.CalculationBasis.INPUT
        tds_line.fixed_amount = Decimal("0.00")
        tds_line.save(update_fields=["calculation_basis", "fixed_amount"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        run = PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run
        PayrollRunService.calculate_run(run)

        row = PayrollRunEmployee.objects.get(payroll_run=run, contract_payroll_profile=self.setup["contract_profile"])
        payslip = PayslipService.build_for_run_employee(row)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("2500.00"))
        self.assertEqual(payslip.payload["tds_projection_trace"]["monthly_tds"], "2500.00")
        self.assertEqual(payslip.payload["tds_projection_trace"]["balance_tax"], "15000.00")
        self.assertEqual(
            tds_row.metadata["calculation_trace"]["tds_projection_trace"]["already_deducted"],
            "8400.00",
        )
