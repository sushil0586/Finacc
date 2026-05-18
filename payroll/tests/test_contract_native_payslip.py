from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from payroll.models import ContractAttendanceSummary, ContractPayrollInputSnapshot, ContractPayrollProfile, ContractTaxDeclaration
from payroll.services import (
    ContractAttendanceSummaryService,
    ContractPayrollInputSnapshotService,
    ContractPayrollProfileService,
    ContractSalaryAssignmentService,
    ContractTaxDeclarationService,
    EntityPayrollPolicyService,
    OneTimePayItemService,
    PayslipService,
    PayrollRunService,
    RecurringPayItemService,
)
from payroll.tests.factories import PayrollFactory


@override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
class ContractNativePayslipServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["profile"].employee_user = self.setup["user"]
        self.setup["profile"].save(update_fields=["employee_user"])

    def _create_contract_profile(self, **overrides):
        contract = self.setup["hrms_contract"]
        contract.start_date = date(2025, 4, 1)
        contract.payroll_effective_from = date(2025, 4, 1)
        contract.save(update_fields=["start_date", "payroll_effective_from", "updated_at"])
        payload = {
            "entity": self.setup["entity"],
            "hrms_contract": contract,
            "pay_frequency": "MONTHLY",
            "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
            "payroll_start_date": contract.payroll_effective_from,
            "tax_regime": "NEW",
            "payment_mode": "BANK_TRANSFER",
            "pf_applicable": False,
            "esi_applicable": False,
            "pt_applicable": False,
            "tds_applicable": True,
            "lwf_applicable": False,
            "attendance_required": True,
            "is_active": True,
        }
        payload.update(overrides)
        return ContractPayrollProfileService.create_or_update_profile(payload, instance=self.setup["contract_profile"])

    def _create_policy(self):
        return EntityPayrollPolicyService.create_or_update_policy(
            {
                "entity": self.setup["entity"],
                "code": "MONTHLY_DEFAULT",
                "name": "Monthly Default",
                "pay_frequency": "MONTHLY",
                "effective_from": date(2025, 4, 1),
                "is_default": True,
                "is_active": True,
            }
        )

    def _ensure_component_posting(self, component):
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

    def _create_tax_inputs(self, contract_profile):
        declaration = ContractTaxDeclarationService.create_or_update_declaration(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": contract_profile,
                "financial_year": self.setup["entityfinid"],
                "tax_regime": "NEW",
                "declaration_status": ContractTaxDeclaration.DeclarationStatus.APPROVED,
                "declared_annual_income": "650000.00",
                "previous_employer_income": "45000.00",
                "previous_employer_tds": "2500.00",
                "standard_deduction_amount": "50000.00",
                "professional_tax_declared": "2400.00",
                "is_active": True,
            }
        )
        ContractTaxDeclarationService.create_or_update_line(
            {
                "declaration": declaration,
                "section_code": "80C",
                "description": "ELSS",
                "declared_amount": "150000.00",
                "approved_amount": "120000.00",
                "evidence_required": True,
                "evidence_status": "VERIFIED",
                "metadata": {"review_note": "Matched receipts"},
                "is_active": True,
            }
        )
        ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": contract_profile,
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                "input_json": {"monthly_tds": "900.00", "other_income": "15000.00"},
                "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )

    def _create_attendance_summary(self, contract_profile):
        return ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": contract_profile,
                "payroll_period": self.setup["period"],
                "attendance_days": "27.00",
                "payable_days": "26.00",
                "lop_days": "1.00",
                "weekly_off_days": "4.00",
                "holiday_days": "1.00",
                "overtime_hours": "3.50",
                "late_count": 2,
                "half_days": "0.50",
                "source": ContractAttendanceSummary.Source.MANUAL,
                "approval_status": ContractAttendanceSummary.ApprovalStatus.APPROVED,
                "is_active": True,
            },
            instance=self.setup["attendance_summary"],
        )

    def _create_runtime_row_with_contract_native_inputs(self):
        contract_profile = self._create_contract_profile()
        ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": contract_profile,
                "salary_structure": self.setup["structure"],
                "salary_structure_version": self.setup["version"],
                "effective_from": date(2025, 4, 1),
                "assignment_status": "ACTIVE",
                "ctc_amount": "120000.00",
                "gross_amount": "10000.00",
                "is_active": True,
            },
            instance=self.setup["salary_assignment"],
        )
        self._create_policy()
        self._create_attendance_summary(contract_profile)
        self._create_tax_inputs(contract_profile)

        recurring_component = PayrollFactory.component(entity=self.setup["entity"], code="PHONE_ALLOW")
        one_time_component = PayrollFactory.component(entity=self.setup["entity"], code="JOIN_BONUS")
        self._ensure_component_posting(recurring_component)
        self._ensure_component_posting(one_time_component)

        RecurringPayItemService.create_or_update_item(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": contract_profile,
                "payroll_component": recurring_component,
                "item_type": "EARNING",
                "amount": "2500.00",
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )
        OneTimePayItemService.create_or_update_item(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": contract_profile,
                "payroll_component": one_time_component,
                "item_type": "EARNING",
                "payroll_period": self.setup["period"],
                "requested_date": self.setup["period"].period_start,
                "effective_date": self.setup["period"].period_end,
                "amount": "750.00",
                "quantity": "1.00",
                "approval_status": "APPROVED",
                "source_type": "INCENTIVE",
                "is_active": True,
            }
        )
        run = PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type="REGULAR",
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run
        PayrollRunService.calculate_run(run)
        row = run.employee_runs.select_related(
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "salary_structure",
            "salary_structure_version",
        ).prefetch_related("components").get()
        return run, row, recurring_component, one_time_component

    def test_payslip_generation_uses_contract_native_row_identity_and_payload(self):
        run, row, recurring_component, one_time_component = self._create_runtime_row_with_contract_native_inputs()

        payslip = PayslipService.build_for_run_employee(row)

        self.assertEqual(payslip.payroll_run_employee_id, row.id)
        self.assertEqual(payslip.payload["employee_code"], row.contract_payroll_profile.employee_code)
        self.assertEqual(payslip.payload["employee_name"], row.contract_payroll_profile.employee_name)
        self.assertEqual(payslip.payload["contract_payroll_profile_id"], str(row.contract_payroll_profile_id))
        self.assertEqual(payslip.payload["contract_code"], row.contract_payroll_profile.hrms_contract.contract_code)
        self.assertEqual(payslip.payload["payroll_period_code"], run.payroll_period.code)
        self.assertEqual(payslip.payload["attendance"]["attendance_days"], "27.00")
        self.assertEqual(payslip.payload["attendance"]["payable_days"], "26.00")
        self.assertEqual(payslip.payload["attendance"]["overtime_hours"], "3.50")
        self.assertEqual(payslip.payload["attendance"]["source"], "contract_native")
        self.assertEqual(payslip.payload["tax_projection_snapshot"]["monthly_tds"], "900.00")
        self.assertEqual(payslip.payload["tax_projection_snapshot"]["deduction_80c"], "120000.00")
        self.assertTrue(payslip.payload["policy_snapshot"])
        self.assertEqual(len(payslip.payload["recurring_pay_items"]), 1)
        self.assertEqual(len(payslip.payload["one_time_pay_items"]), 1)

        component_codes = {item["code"] for item in payslip.payload["components"]}
        self.assertIn(self.setup["component"].code, component_codes)
        self.assertIn(recurring_component.code, component_codes)
        self.assertIn(one_time_component.code, component_codes)

        recurring_row = next(item for item in payslip.payload["components"] if item["code"] == recurring_component.code)
        one_time_row = next(item for item in payslip.payload["components"] if item["code"] == one_time_component.code)
        self.assertEqual(recurring_row["amount"], "2500.00")
        self.assertEqual(recurring_row["source"], "recurring_pay_item")
        self.assertEqual(one_time_row["amount"], "750.00")
        self.assertEqual(one_time_row["source"], "one_time_pay_item")
        self.assertEqual(
            payslip.payload["section_totals"]["earnings"],
            str(
                (
                    row.gross_amount.quantize(Decimal("0.01"))
                )
            ),
        )

    def test_payslip_generation_keeps_historical_payload_immutable_after_approval(self):
        run, row, _, _ = self._create_runtime_row_with_contract_native_inputs()
        payslip = PayslipService.build_for_run_employee(row)
        original_payload = payslip.payload
        original_generated_at = payslip.generated_at

        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submit")
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approve")

        row.refresh_from_db()
        regenerated = PayslipService.build_for_run_employee(row)

        self.assertEqual(regenerated.id, payslip.id)
        self.assertEqual(regenerated.payload, original_payload)
        self.assertEqual(regenerated.generated_at, original_generated_at)
