from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from payroll.models import (
    ContractPayrollInputSnapshot,
    FnFSettlement,
    OneTimePayItem,
    PayrollComponent,
    PayrollRun,
)
from payroll.services import (
    ContractPayrollInputSnapshotService,
    EntityPayrollPolicyService,
    PayrollFnFEngine,
    PayrollPolicyRuleService,
    PayrollRunService,
)
from payroll.tests.factories import PayrollFactory


class PayrollFnFEngineTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def _ensure_payroll_policy(self):
        policy = EntityPayrollPolicyService.resolve_active_policy(
            entity_id=self.setup["entity"].id,
            payroll_date=self.setup["period"].period_end,
            pay_frequency=self.setup["contract_profile"].pay_frequency,
        )
        if policy is not None:
            return policy
        return EntityPayrollPolicyService.create_or_update_policy(
            {
                "entity": self.setup["entity"],
                "code": f"FNF_POLICY_{self.setup['entity'].id}",
                "name": "FnF Policy",
                "pay_frequency": self.setup["contract_profile"].pay_frequency,
                "effective_from": self.setup["period"].period_start,
                "is_default": True,
                "is_active": True,
            }
        )

    def _set_fixed_salary(self, amount: str):
        existing = ContractPayrollInputSnapshot.objects.filter(
            contract_payroll_profile=self.setup["contract_profile"],
            payroll_period=self.setup["period"],
            input_type=ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
        ).first()
        ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.setup["contract_profile"],
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
                "input_json": {"fixed_salary": amount},
                "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            },
            instance=existing,
        )

    def test_calculate_fnf_earned_salary_till_last_working_day(self):
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 15),
            inputs={"payable_days": "15.00"},
        )
        salary_component = settlement.components.get(source_type="SALARY_LINE", component=self.setup["component"])
        self.assertEqual(settlement.status, FnFSettlement.Status.CALCULATED)
        self.assertEqual(salary_component.amount, Decimal("500.00"))
        self.assertEqual(settlement.net_payable_amount, Decimal("500.00"))

    def test_calculate_fnf_notice_recovery(self):
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._set_fixed_salary("3000.00")
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={"notice_shortfall_days": "10.00"},
        )
        notice_row = settlement.components.get(source_type="NOTICE_PAY_RECOVERY")
        self.assertEqual(notice_row.amount, Decimal("1000.00"))
        self.assertEqual(settlement.net_recoverable_amount, Decimal("0.00"))
        self.assertGreater(settlement.recovery_amount, Decimal("0.00"))

    def test_calculate_fnf_leave_encashment(self):
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._set_fixed_salary("3000.00")
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={"leave_encashment_days": "2.00"},
        )
        leave_row = settlement.components.get(source_type="LEAVE_ENCASHMENT")
        self.assertEqual(leave_row.amount, Decimal("200.00"))
        self.assertEqual(settlement.earned_amount, Decimal("1200.00"))

    def test_calculate_fnf_asset_recovery(self):
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={"asset_recovery_amount": "450.00"},
        )
        asset_row = settlement.components.get(source_type="ASSET_RECOVERY")
        self.assertEqual(asset_row.amount, Decimal("450.00"))
        self.assertEqual(settlement.recovery_amount, Decimal("450.00"))

    def test_calculate_fnf_loan_recovery_from_contract_native_item(self):
        recovery_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="LOAN_RECOVERY",
            component_type=PayrollComponent.ComponentType.RECOVERY,
            posting_behavior=PayrollComponent.PostingBehavior.RECOVERY,
        )
        OneTimePayItem.objects.create(
            entity=self.setup["entity"],
            contract_payroll_profile=self.setup["contract_profile"],
            payroll_component=recovery_component,
            item_type=OneTimePayItem.ItemType.RECOVERY,
            payroll_period=self.setup["period"],
            effective_date=self.setup["period"].period_end,
            amount=Decimal("275.00"),
            quantity=Decimal("1.00"),
            approval_status=OneTimePayItem.ApprovalStatus.APPROVED,
            source_type=OneTimePayItem.SourceType.RECOVERY,
            is_active=True,
        )
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={},
        )
        loan_row = settlement.components.get(source_type="LOAN_RECOVERY")
        self.assertEqual(loan_row.amount, Decimal("275.00"))
        self.assertEqual(settlement.recovery_amount, Decimal("275.00"))

    def test_calculate_fnf_net_payable(self):
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={
                "bonus_amount": "500.00",
                "reimbursement_amount": "200.00",
                "loan_recovery_amount": "100.00",
            },
        )
        self.assertEqual(settlement.net_payable_amount, Decimal("1600.00"))
        self.assertEqual(settlement.net_recoverable_amount, Decimal("0.00"))

    def test_calculate_fnf_net_recoverable(self):
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 15),
            inputs={
                "payable_days": "15.00",
                "asset_recovery_amount": "900.00",
            },
        )
        self.assertEqual(settlement.net_payable_amount, Decimal("0.00"))
        self.assertEqual(settlement.net_recoverable_amount, Decimal("400.00"))

    def test_duplicate_active_settlement_blocked(self):
        PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={},
        )
        with self.assertRaises(Exception) as error:
            PayrollFnFEngine.calculate_fnf(
                self.setup["hrms_contract"].id,
                separation_date=date(2025, 4, 30),
                inputs={},
            )
        self.assertIn("Duplicate active FnF settlement", str(error.exception))

    def test_approved_settlement_cannot_recalculate_without_unlock(self):
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={},
        )
        PayrollFnFEngine.approve_fnf(settlement.id)
        with self.assertRaises(Exception) as error:
            PayrollFnFEngine.recalculate_fnf(settlement.id, {"bonus_amount": "100.00"})
        self.assertIn("cannot be recalculated", str(error.exception))

    def test_normal_payroll_excludes_fnf_contract_where_policy_configured(self):
        policy = self._ensure_payroll_policy()
        PayrollPolicyRuleService.create_or_update_rule(
            {
                "policy": policy,
                "rule_type": "PAYROLL",
                "rule_key": "exclude_fnf_contracts_from_regular_payroll",
                "rule_value_json": {"value": True},
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )
        settlement = PayrollFnFEngine.calculate_fnf(
            self.setup["hrms_contract"].id,
            separation_date=date(2025, 4, 30),
            inputs={},
        )
        PayrollFnFEngine.approve_fnf(settlement.id)
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
        self.assertEqual(run.employee_runs.count(), 0)
