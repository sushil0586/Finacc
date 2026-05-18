from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from decimal import Decimal, ROUND_HALF_UP

from payroll.models import ContractAttendanceSummary, ContractPayrollProfile, PayrollRunActionLog
from payroll.services import (
    ContractAttendanceSummaryService,
    ContractPayrollInputSnapshotService,
    ContractPayrollProfileService,
    ContractSalaryAssignmentService,
    EntityPayrollPolicyService,
    OneTimePayItemService,
    PayrollRunService,
    RecurringPayItemService,
)
from payroll.tests.factories import PayrollFactory


class PayrollRunReadinessIntegrationServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["profile"].employee_user = self.setup["user"]
        self.setup["profile"].save(update_fields=["employee_user"])

    def _get_run_employee(self, run):
        return run.employee_runs.get(contract_payroll_profile=self.setup["contract_profile"])

    def _set_contract_tax_projection(self, payload: dict):
        return ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.setup["contract_profile"],
                "payroll_period": self.setup["period"],
                "input_type": "TAX_PROJECTION",
                "input_json": payload,
                "source": "MANUAL",
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )

    def _set_contract_attendance(self, *, attendance_days, payable_days, period=None, **overrides):
        return ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.setup["contract_profile"],
                "payroll_period": period or self.setup["period"],
                "attendance_days": str(attendance_days),
                "payable_days": str(payable_days),
                "lop_days": str(overrides.pop("lop_days", "0.00")),
                "weekly_off_days": str(overrides.pop("weekly_off_days", "0.00")),
                "holiday_days": str(overrides.pop("holiday_days", "0.00")),
                "overtime_hours": str(overrides.pop("overtime_hours", "0.00")),
                "late_count": overrides.pop("late_count", 0),
                "half_days": str(overrides.pop("half_days", "0.00")),
                "source": overrides.pop("source", ContractAttendanceSummary.Source.MANUAL),
                "approval_status": overrides.pop("approval_status", ContractAttendanceSummary.ApprovalStatus.APPROVED),
                "is_active": overrides.pop("is_active", True),
                **overrides,
            },
            instance=self.setup.get("attendance_summary"),
        )

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
            "pf_applicable": False,
            "esi_applicable": False,
            "pt_applicable": False,
            "tds_applicable": False,
            "lwf_applicable": False,
            "is_active": True,
        }
        payload.update(overrides)
        profile = ContractPayrollProfileService.create_or_update_profile(payload, instance=self.setup["contract_profile"])
        return contract, profile

    def _create_run(self):
        return PayrollRunService.create_run(
            entity_id=self.setup["entity"].id,
            entityfinid_id=self.setup["entityfinid"].id,
            subentity_id=self.setup["subentity"].id,
            payroll_period_id=self.setup["period"].id,
            run_type="REGULAR",
            posting_date=self.setup["period"].period_end,
            payout_date=self.setup["period"].payout_date,
            created_by_id=self.setup["user"].id,
        ).run

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

    def test_flag_off_keeps_old_behavior_and_does_not_invoke_resolver(self):
        run = self._create_run()
        with patch("payroll.services.payroll_run_service.PayrollRunReadinessResolverService.resolve_entity_readiness") as mock_resolver:
            PayrollRunService.calculate_run(run)

        run.refresh_from_db()
        mock_resolver.assert_not_called()
        self.assertEqual(run.employee_runs.count(), 1)
        self.assertNotIn("contract_readiness", run.config_snapshot)

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_flag_on_invokes_resolver_and_stores_snapshot(self):
        run = self._create_run()

        with patch(
            "payroll.services.payroll_run_service.PayrollRunReadinessResolverService.resolve_entity_readiness",
            return_value=[],
        ) as mock_resolver:
            PayrollRunService.calculate_run(run)

        run.refresh_from_db()
        mock_resolver.assert_called_once()
        self.assertIn("contract_readiness", run.config_snapshot)
        self.assertTrue(run.config_snapshot["contract_readiness"]["enabled"])
        self.assertIn("contract_readiness", run.calculation_payload)
        log = run.action_logs.filter(action=PayrollRunActionLog.Action.CALCULATED).latest("id")
        self.assertTrue(log.payload.get("contract_readiness_enabled"))

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_contract_driven_calculation_blocks_when_contract_has_no_salary_assignment(self):
        hrms_employee = PayrollFactory.hrms_employee(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee_number="UNMAPPED-001",
        )
        contract = PayrollFactory.hrms_contract(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee=hrms_employee,
        )
        contract.start_date = date(2025, 4, 1)
        contract.payroll_effective_from = date(2025, 4, 1)
        contract.save(update_fields=["start_date", "payroll_effective_from", "updated_at"])
        ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.setup["entity"],
                "hrms_contract": contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": contract.payroll_effective_from,
                "is_active": True,
            }
        )
        run = self._create_run()

        with self.assertRaises(ValueError) as error:
            PayrollRunService.calculate_run(run)

        payload = error.exception.args[0]
        self.assertIn("preflight", payload)
        self.assertIn(
            "do not resolve to an active salary structure",
            " ".join(payload["preflight"]["blockers"]),
        )

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_blocked_contracts_exclude_mapped_legacy_profiles(self):
        self._create_contract_profile()
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        run.refresh_from_db()

        self.assertEqual(run.employee_runs.count(), 0)
        self.assertEqual(run.calculation_payload["contract_readiness"]["blocked_count"], 1)
        self.assertEqual(len(run.config_snapshot["contract_readiness"]["blocked_contracts"]), 1)

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_contract_driven_source_excludes_legacy_profiles_without_active_contracts(self):
        _, contract_profile = self._create_contract_profile()
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
        second_profile = PayrollFactory.employee_profile(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payment_account=self.setup["payable_account"],
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            employee_code="LEGACY-ONLY",
        )
        second_profile.employee_user = None
        second_profile.save(update_fields=["employee_user"])
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        run.refresh_from_db()

        self.assertEqual(run.employee_runs.count(), 1)
        self.assertEqual(str(run.employee_runs.first().contract_payroll_profile_id), str(contract_profile.id))

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_warnings_are_stored_without_changing_existing_calculation_path(self):
        _, contract_profile = self._create_contract_profile()
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
        RecurringPayItemService.create_or_update_item(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": contract_profile,
                "payroll_component": self.setup["component"],
                "item_type": "EARNING",
                "amount": "2500.00",
                "effective_from": date(2025, 5, 1),
                "is_active": True,
            }
        )
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        run.refresh_from_db()

        self.assertEqual(run.employee_runs.count(), 1)
        self.assertGreaterEqual(run.calculation_payload["contract_readiness"]["warning_count"], 1)
        self.assertTrue(run.calculation_payload["contract_readiness"]["warnings"])

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_flag_on_uses_payroll_calculation_input_resolver(self):
        _, contract_profile = self._create_contract_profile()
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
        run = self._create_run()

        from payroll.services.payroll_calculation_input_resolver import PayrollCalculationInputResolver

        with patch(
            "payroll.services.payroll_run_service.PayrollCalculationInputResolver.resolve",
            wraps=PayrollCalculationInputResolver.resolve,
        ) as mock_resolver:
            PayrollRunService.calculate_run(run)

        self.assertTrue(mock_resolver.called)

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_salary_assignment_values_override_legacy_profile_values(self):
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = "100.0000"
        self.setup["line"].fixed_amount = "0.00"
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        _, contract_profile = self._create_contract_profile(tax_regime="NEW")
        ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": contract_profile,
                "salary_structure": self.setup["structure"],
                "salary_structure_version": self.setup["version"],
                "effective_from": date(2025, 4, 1),
                "assignment_status": "ACTIVE",
                "ctc_amount": "6000.00",
                "gross_amount": "0.00",
                "is_active": True,
            },
            instance=self.setup["salary_assignment"],
        )
        self._create_policy()
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        row = run.employee_runs.get(contract_payroll_profile=contract_profile)
        component_row = row.components.get(component=self.setup["component"])

        self.assertEqual(str(component_row.amount), "6000.00")
        self.assertEqual(
            row.calculation_payload["contract_payroll_profile_snapshot"]["tax_regime"],
            "NEW",
        )

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_contract_native_tax_projection_is_used_for_runtime_fields(self):
        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        self.setup["line"].component = tds_component
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.FIXED
        self.setup["line"].fixed_amount = "0.00"
        self.setup["line"].save(update_fields=["component", "calculation_basis", "fixed_amount"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        _, contract_profile = self._create_contract_profile(tax_regime="OLD")
        ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": contract_profile,
                "salary_structure": self.setup["structure"],
                "salary_structure_version": self.setup["version"],
                "effective_from": date(2025, 4, 1),
                "assignment_status": "ACTIVE",
                "ctc_amount": "120000.00",
                "gross_amount": "0.00",
                "is_active": True,
            },
            instance=self.setup["salary_assignment"],
        )
        self._set_contract_tax_projection({"monthly_tds": "123.00"})
        self._create_policy()
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        row = run.employee_runs.get(contract_payroll_profile=contract_profile)
        component_row = row.components.get(component=tds_component)

        self.assertEqual(str(component_row.amount), "123.00")
        self.assertEqual(
            row.calculation_payload["contract_payroll_profile_snapshot"]["tax_regime"],
            "OLD",
        )
        self.assertEqual(
            row.calculation_payload["tax_projection_snapshot"]["monthly_tds"],
            "123.00",
        )

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_contract_native_attendance_summary_drives_proration(self):
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = "100.0000"
        self.setup["line"].fixed_amount = "0.00"
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        _, contract_profile = self._create_contract_profile()
        ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": contract_profile,
                "salary_structure": self.setup["structure"],
                "salary_structure_version": self.setup["version"],
                "effective_from": date(2025, 4, 1),
                "assignment_status": "ACTIVE",
                "ctc_amount": "30000.00",
                "gross_amount": "0.00",
                "is_active": True,
            },
            instance=self.setup["salary_assignment"],
        )
        self._create_policy()
        summary = self._set_contract_attendance(attendance_days="15.00", payable_days="15.00")
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        row = run.employee_runs.get(contract_payroll_profile=contract_profile)
        component_row = row.components.get(component=self.setup["component"])
        period_days = Decimal((run.payroll_period.period_end - run.payroll_period.period_start).days + 1)
        expected_multiplier = (Decimal("15.00") / period_days).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        expected_amount = (Decimal("30000.00") * expected_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        self.assertEqual(component_row.amount, expected_amount)
        self.assertEqual(row.calculation_payload["source_markers"]["attendance_source"], "contract_native")
        self.assertEqual(row.calculation_payload["attendance_snapshot"]["summary_id"], str(summary.id))
        self.assertEqual(component_row.calculation_basis_snapshot["source_markers"]["attendance_source"], "contract_native")

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    def test_contract_native_pay_items_and_policy_snapshot_are_stored(self):
        _, contract_profile = self._create_contract_profile()
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
        run = self._create_run()

        PayrollRunService.calculate_run(run)
        row = run.employee_runs.get(contract_payroll_profile=contract_profile)
        recurring_row = row.components.get(component=recurring_component)
        one_time_row = row.components.get(component=one_time_component)

        self.assertEqual(recurring_row.amount, Decimal("2500.00"))
        self.assertEqual(recurring_row.calculation_basis_snapshot["contract_native_source"], "recurring_pay_item")
        self.assertEqual(one_time_row.amount, Decimal("750.00"))
        self.assertEqual(one_time_row.calculation_basis_snapshot["contract_native_source"], "one_time_pay_item")
        self.assertIsNotNone(row.calculation_payload["contract_payroll_profile_snapshot"]["payroll_policy"])
        self.assertTrue(row.calculation_payload["contract_payroll_profile_snapshot"]["recurring_items"])
        self.assertTrue(row.calculation_payload["contract_payroll_profile_snapshot"]["one_time_items"])


class PayrollRunReadinessIntegrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["profile"].employee_user = self.setup["user"]
        self.setup["profile"].save(update_fields=["employee_user"])

    @override_settings(PAYROLL_USE_CONTRACT_READINESS=True)
    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_run_views.PayrollPermissionService.assert_action_access", return_value=True)
    def test_calculate_endpoint_returns_readiness_summary(self, _perm, _scope):
        contract = self.setup["hrms_contract"]
        contract.start_date = date(2025, 4, 1)
        contract.payroll_effective_from = date(2025, 4, 1)
        contract.save(update_fields=["start_date", "payroll_effective_from", "updated_at"])
        ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.setup["entity"],
                "hrms_contract": contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": contract.payroll_effective_from,
                "pf_applicable": False,
                "esi_applicable": False,
                "pt_applicable": False,
                "tds_applicable": False,
                "lwf_applicable": False,
                "is_active": True,
            },
            instance=self.setup["contract_profile"],
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

        response = self.client.post(f"/api/payroll/runs/{run.id}/calculate/", {"force": False}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertIn("readiness_summary", payload)
        self.assertEqual(payload["readiness_summary"]["blocked_count"], 1)
