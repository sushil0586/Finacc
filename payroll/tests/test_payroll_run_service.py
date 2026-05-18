from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from payroll.models import (
    ContractPayrollInputSnapshot,
    ContractSalaryStructureAssignment,
    PayrollComponent,
    PayrollRun,
    SalaryStructureLine,
    StatutoryScheme,
)
from payroll.services import (
    ContractAttendanceAdjustmentService,
    ContractAttendanceSummaryService,
    ContractPayrollInputSnapshotService,
    ContractStatutoryProfileService,
    EntityPayrollPolicyService,
    EntityStatutoryRegistrationService,
    PayrollPolicyRuleService,
    StatutoryRuleService,
    StatutorySchemeService,
    StatutorySlabService,
)
from payroll.services.payroll_run_service import PayrollCalculationError, PayrollRunService
from payroll.services.payroll_statutory_engine import PayrollStatutoryResult
from payroll.tests.factories import PayrollFactory


class PayrollRunServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()

    def _get_run_employee(self, run):
        return run.employee_runs.get(contract_payroll_profile=self.setup["contract_profile"])

    def _sync_contract_native_from_profile(self):
        profile = self.setup["profile"]
        contract_profile = self.setup["contract_profile"]
        extra_data = profile.extra_data or {}

        if contract_profile.tax_regime != (profile.tax_regime or ""):
            contract_profile.tax_regime = profile.tax_regime or ""
            contract_profile.save(update_fields=["tax_regime", "updated_at"])

        if any(key in extra_data for key in ("attendance_days", "payable_days", "lop_days", "overtime_hours", "late_count", "half_days")):
            self.setup["attendance_summary"] = ContractAttendanceSummaryService.create_or_update_summary(
                {
                    "entity": self.setup["entity"],
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": self.setup["period"],
                    "attendance_days": str(extra_data.get("attendance_days", "0")),
                    "payable_days": str(extra_data.get("payable_days", "0")),
                    "lop_days": str(extra_data.get("lop_days", "0")),
                    "weekly_off_days": str(extra_data.get("weekly_off_days", "0")),
                    "holiday_days": str(extra_data.get("holiday_days", "0")),
                    "overtime_hours": str(extra_data.get("overtime_hours", "0")),
                    "late_count": int(extra_data.get("late_count", 0) or 0),
                    "half_days": str(extra_data.get("half_days", "0")),
                    "source": "MANUAL",
                    "approval_status": "APPROVED",
                    "is_active": True,
                },
                instance=self.setup.get("attendance_summary"),
            )

        if "tax_projection_snapshot" in extra_data:
            existing = ContractPayrollInputSnapshot.objects.filter(
                contract_payroll_profile=contract_profile,
                payroll_period=self.setup["period"],
                input_type=ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
            ).first()
            ContractPayrollInputSnapshotService.create_or_update_snapshot(
                {
                    "entity": self.setup["entity"],
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": self.setup["period"],
                    "input_type": ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                    "input_json": extra_data.get("tax_projection_snapshot") or {},
                    "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                    "effective_from": self.setup["period"].period_start,
                    "is_active": True,
                },
                instance=existing,
            )

    def _set_contract_statutory_flags(self, **flags):
        contract_profile = self.setup["contract_profile"]
        updates = []
        for key, value in flags.items():
            if getattr(contract_profile, key) != value:
                setattr(contract_profile, key, value)
                updates.append(key)
        if updates:
            updates.append("updated_at")
            contract_profile.save(update_fields=updates)

    def _active_payroll_policy(self):
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
                "code": f"MONTHLY_DEFAULT_{self.setup['entity'].id}",
                "name": "Monthly Default",
                "pay_frequency": self.setup["contract_profile"].pay_frequency,
                "effective_from": self.setup["period"].period_start,
                "is_default": True,
                "is_active": True,
            }
        )

    def _set_attendance_policy_rule(self, rule_key: str, rule_value_json: dict):
        policy = self._active_payroll_policy()
        self.assertIsNotNone(policy)
        existing = policy.rules.filter(rule_key=rule_key).first()
        return PayrollPolicyRuleService.create_or_update_rule(
            {
                "policy": policy,
                "rule_type": "ATTENDANCE",
                "rule_key": rule_key,
                "rule_value_json": rule_value_json,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            },
            instance=existing,
        )

    def _create_attendance_adjustment(
        self,
        *,
        adjustment_type: str,
        adjustment_value: str,
        metadata: dict | None = None,
        remarks: str = "",
    ):
        return ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.setup["contract_profile"],
                "payroll_period": self.setup["period"],
                "adjustment_type": adjustment_type,
                "adjustment_value": adjustment_value,
                "remarks": remarks,
                "approval_status": "APPROVED",
                "metadata": metadata or {},
                "is_active": True,
            }
        )

    def _create_statutory_runtime_config(
        self,
        *,
        scheme_code: str,
        scheme_type: str,
        rule_type: str = "PERCENTAGE",
        rule_json: dict | None = None,
        slabs: list[dict] | None = None,
        registration_state: str = "",
        is_applicable: bool = True,
    ):
        scheme = StatutorySchemeService.create_or_update_scheme(
            {
                "code": scheme_code,
                "name": f"{scheme_code} Runtime Scheme",
                "scheme_type": scheme_type,
                "country_code": "IN",
                "state_code": registration_state,
                "is_system": True,
                "is_active": True,
            }
        )
        ContractStatutoryProfileService.create_or_update_profile(
            {
                "contract_payroll_profile": self.setup["contract_profile"],
                "scheme": scheme,
                "is_applicable": is_applicable,
                "effective_from": date(2025, 4, 1),
                "is_active": True,
            }
        )
        EntityStatutoryRegistrationService.create_or_update_registration(
            {
                "entity": self.setup["entity"],
                "scheme": scheme,
                "registration_number": f"{scheme_code}-REG-{PayrollFactory.counter}",
                "registration_state": registration_state,
                "effective_from": date(2025, 4, 1),
                "is_active": True,
            }
        )
        rule = None
        if rule_json is not None or slabs is not None:
            rule = StatutoryRuleService.create_or_update_rule(
                {
                    "entity": self.setup["entity"],
                    "scheme": scheme,
                    "rule_code": f"{scheme_code}_RULE",
                    "rule_name": f"{scheme_code} Runtime Rule",
                    "rule_type": rule_type,
                    "effective_from": date(2025, 4, 1),
                    "priority": 10,
                    "is_active": True,
                    "rule_json": rule_json or {},
                }
            )
        for slab in slabs or []:
            StatutorySlabService.create_or_update_slab(
                {
                    "rule": rule,
                    "slab_from": slab.get("slab_from", "0.00"),
                    "slab_to": slab.get("slab_to"),
                    "amount": slab.get("amount", "0.00"),
                    "percentage": slab.get("percentage", "0.00"),
                    "is_active": True,
                }
            )
        return scheme, rule

        if "fixed_salary" in extra_data:
            existing = ContractPayrollInputSnapshot.objects.filter(
                contract_payroll_profile=contract_profile,
                payroll_period=self.setup["period"],
                input_type=ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
            ).first()
            ContractPayrollInputSnapshotService.create_or_update_snapshot(
                {
                    "entity": self.setup["entity"],
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": self.setup["period"],
                    "input_type": ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
                    "input_json": {"fixed_salary": extra_data.get("fixed_salary")},
                    "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                    "effective_from": self.setup["period"].period_start,
                    "is_active": True,
                },
                instance=existing,
            )

    def test_create_calculate_submit_approve_post_run(self):
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
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.CALCULATED)
        self.assertEqual(run.employee_runs.count(), 1)

        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submit")
        PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approve")
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertTrue(run.is_immutable)
        self.assertEqual(run.employee_runs.filter(is_frozen=True).count(), 1)

        with patch("posting.services.posting_service.PostingService._pg_advisory_lock", return_value=None):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.POSTED)
        self.assertIsNotNone(run.posted_entry_id)

    def test_approve_blocks_when_structure_policy_requires_verified_hra_evidence(self):
        self.setup["version"].calculation_policy_json = {
            **(self.setup["version"].calculation_policy_json or {}),
            "tds_require_verified_hra_evidence_for_approval": True,
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "hra_rent_paid_annual": "240000.00",
                "hra_evidence_verified": False,
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submit")

        with self.assertRaises(ValueError) as error:
            PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approve")

        payload = error.exception.args[0]
        self.assertIsInstance(payload, dict)
        self.assertIn("blocking_issues", payload)
        self.assertIn("requires verified HRA evidence before approval", " ".join(payload["blocking_issues"]))

    def test_approve_blocks_when_structure_policy_requires_verified_tax_declarations(self):
        self.setup["version"].calculation_policy_json = {
            **(self.setup["version"].calculation_policy_json or {}),
            "tds_require_verified_tax_declarations_for_approval": True,
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "deduction_80c": "150000.00",
                "deduction_80c_evidence_verified": False,
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        PayrollRunService.submit_run(run, submitted_by_id=self.setup["user"].id, note="submit")

        with self.assertRaises(ValueError) as error:
            PayrollRunService.approve_run(run, approved_by_id=self.setup["user"].id, note="approve")

        payload = error.exception.args[0]
        self.assertIsInstance(payload, dict)
        self.assertIn("blocking_issues", payload)
        self.assertIn("requires verified 80C or 80D declaration evidence before approval", " ".join(payload["blocking_issues"]))

    def test_invalid_post_transition_fails(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        with self.assertRaisesMessage(ValueError, "Only approved payroll runs can be posted."):
            PayrollRunService.post_run(run, posted_by_id=self.setup["user"].id)

    def test_calculate_fails_when_immutable(self):
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
            is_immutable=True,
        )
        with self.assertRaisesMessage(ValueError, "immutable"):
            PayrollRunService.calculate_run(run)

    def test_calculate_blocks_subentity_scope_mismatch(self):
        other_scope = PayrollFactory.entity_scope(user=self.setup["user"], name_prefix="Other")
        other_structure = PayrollFactory.salary_structure(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=other_scope["subentity"],
        )
        other_version = PayrollFactory.salary_structure_version(salary_structure=other_structure)
        PayrollFactory.employee_profile(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=other_scope["subentity"],
            payment_account=self.setup["payable_account"],
            salary_structure=other_structure,
            salary_structure_version=other_version,
            employee_code="EMP-MISMATCH",
        )
        run = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        PayrollRunService.calculate_run(run)
        self.assertEqual(run.employee_runs.count(), 1)
        self.assertTrue(all(row.contract_payroll_profile.hrms_contract.subentity_id == self.setup["subentity"].id for row in run.employee_runs.all()))

    def test_calculate_prorates_fixed_lines_by_attendance_days(self):
        self.setup["profile"].extra_data = {
            "attendance_days": 15,
            "payable_days": 15,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        component_row = row.components.get(component=self.setup["component"])

        self.assertEqual(component_row.amount, Decimal("500.00"))
        self.assertEqual(row.gross_amount, Decimal("500.00"))
        self.assertEqual(component_row.calculation_basis_snapshot["proration_basis"], "attendance_days")
        self.assertEqual(component_row.calculation_basis_snapshot["proration_multiplier"], "0.5000")

    def test_calculate_prorates_percent_of_ctc_lines_by_payable_days(self):
        variable_component = PayrollFactory.component(entity=self.setup["entity"], code="VAR")
        self.setup["line"].component = variable_component
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["component", "calculation_basis", "rate", "fixed_amount"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=variable_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "ctc",
            "proration_basis": "payable_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "attendance_days": 27,
            "payable_days": 21,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        component_row = row.components.get(component=variable_component)

        self.assertEqual(component_row.amount, Decimal("7000.00"))
        self.assertEqual(row.gross_amount, Decimal("7000.00"))
        self.assertEqual(component_row.calculation_basis_snapshot["proration_basis"], "payable_days")
        self.assertEqual(component_row.calculation_basis_snapshot["proration_multiplier"], "0.7000")

    def test_calculate_uses_fixed_salary_basis_for_gross_mode(self):
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "85000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        component_row = row.components.get(component=self.setup["component"])

        self.assertEqual(component_row.amount, Decimal("85000.00"))

    def test_calculate_prorates_by_calendar_days_policy_rule(self):
        self._set_attendance_policy_rule("proration_method", {"method": "CALENDAR_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 20,
            "payable_days": 15,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("500.00"))
        self.assertEqual(component_row.calculation_basis_snapshot["proration_method"], "CALENDAR_DAYS")
        self.assertEqual(component_row.calculation_basis_snapshot["proration_multiplier"], "0.5000")

    def test_calculate_prorates_by_working_days_policy_rule(self):
        self._set_attendance_policy_rule("proration_method", {"method": "WORKING_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 18,
            "payable_days": 18,
            "weekly_off_days": 4,
            "holiday_days": 2,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("750.00"))
        self.assertEqual(component_row.calculation_basis_snapshot["proration_method"], "WORKING_DAYS")
        self.assertEqual(component_row.calculation_basis_snapshot["proration_denominator"], "24.00")

    def test_calculate_prorates_by_fixed_26_days_policy_rule(self):
        self._set_attendance_policy_rule("proration_method", {"method": "FIXED_26_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 26,
            "payable_days": 13,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("500.00"))
        self.assertEqual(component_row.calculation_basis_snapshot["proration_method"], "FIXED_26_DAYS")
        self.assertEqual(component_row.calculation_basis_snapshot["proration_denominator"], "26.00")

    def test_calculate_manual_payable_days_override_adjustment(self):
        self._set_attendance_policy_rule("proration_method", {"method": "MANUAL_PAYABLE_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 30,
            "payable_days": 24,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()
        self._create_attendance_adjustment(
            adjustment_type="PAYABLE_DAY",
            adjustment_value="20.00",
            metadata={"override": True},
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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("666.70"))
        self.assertEqual(
            component_row.metadata["calculation_trace"]["attendance_proration"]["manual_payable_override"],
            "20.00",
        )

    def test_calculate_applies_lop_adjustment_to_proration(self):
        self._set_attendance_policy_rule("proration_method", {"method": "CALENDAR_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 28,
            "payable_days": 28,
            "lop_days": 2,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()
        self._create_attendance_adjustment(adjustment_type="LOP", adjustment_value="2.00")

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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("866.70"))
        self.assertEqual(component_row.calculation_basis_snapshot["attendance_trace"]["lop_days"], "4.00")

    def test_calculate_applies_half_day_impact_to_proration(self):
        self._set_attendance_policy_rule("proration_method", {"method": "CALENDAR_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 30,
            "payable_days": 30,
            "half_days": "0.50",
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()
        self._create_attendance_adjustment(adjustment_type="HALF_DAY", adjustment_value="0.50")

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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("983.30"))
        self.assertEqual(component_row.calculation_basis_snapshot["attendance_trace"]["half_days"], "1.00")

    def test_calculate_exposes_overtime_adjustment_to_formula(self):
        self._set_attendance_policy_rule("proration_method", {"method": "CALENDAR_DAYS"})
        self.setup["line"].rule_mode = SalaryStructureLine.RuleMode.CUSTOM_FORMULA
        self.setup["line"].rule_json = {"formula": "overtime_hours * 100"}
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["rule_mode", "rule_json", "fixed_amount"])
        self.setup["profile"].extra_data = {
            "attendance_days": 30,
            "payable_days": 30,
            "overtime_hours": "2.00",
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()
        self._create_attendance_adjustment(adjustment_type="OVERTIME", adjustment_value="3.00")

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
        component_row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(component_row.amount, Decimal("500.00"))
        self.assertEqual(component_row.metadata["calculation_trace"]["input_variables"]["overtime_hours"], "5.00")

    def test_calculate_missing_attendance_blocks_when_policy_requires_it(self):
        self._set_attendance_policy_rule("missing_attendance_behavior", {"behavior": "BLOCK"})
        self.setup["contract_profile"].attendance_required = True
        self.setup["contract_profile"].save(update_fields=["attendance_required", "updated_at"])
        if self.setup.get("attendance_summary"):
            self.setup["attendance_summary"].delete()

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

        with self.assertRaises(PayrollCalculationError) as error:
            PayrollRunService.calculate_run(run)

        self.assertIn("Missing approved/submitted attendance summary", str(error.exception))

    def test_calculate_invalid_payable_days_fails(self):
        self._set_attendance_policy_rule("proration_method", {"method": "FIXED_26_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 30,
            "payable_days": 29,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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

        with self.assertRaises(PayrollCalculationError) as error:
            PayrollRunService.calculate_run(run)

        self.assertIn("exceeds base days", str(error.exception))

    def test_component_trace_includes_attendance_proration_metadata(self):
        self._set_attendance_policy_rule("proration_method", {"method": "WORKING_DAYS"})
        self.setup["profile"].extra_data = {
            "attendance_days": 22,
            "payable_days": 20,
            "weekly_off_days": 4,
            "holiday_days": 2,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        component_row = row.components.get(component=self.setup["component"])
        trace = component_row.metadata["calculation_trace"]["attendance_proration"]
        self.assertEqual(trace["proration_method"], "WORKING_DAYS")
        self.assertEqual(trace["base_days"], "24.00")
        self.assertEqual(trace["payable_days"], "20.00")
        self.assertEqual(trace["proration_factor"], "0.8333")
        self.assertEqual(row.calculation_assumptions["proration_method"], "WORKING_DAYS")
        self.assertEqual(row.calculation_assumptions["proration_factor"], "0.8333")

    def test_calculate_blocks_gross_mode_without_fixed_salary_basis(self):
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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

        with self.assertRaises(ValueError) as error:
            PayrollRunService.calculate_run(run)

        payload = error.exception.args[0]
        self.assertIn("gross-mode contract payroll profile", " ".join(payload["preflight"]["blockers"]).lower())

    def test_calculate_balances_special_allowance_for_gross_mode_structure(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("40.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        hra_component = PayrollFactory.component(entity=self.setup["entity"], code="HRA")
        special_component = PayrollFactory.component(entity=self.setup["entity"], code="SPECIAL_ALLOWANCE")
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=hra_component,
            fixed_amount="0.00",
            sequence=110,
        )
        hra_line = self.setup["version"].lines.get(component=hra_component)
        hra_line.calculation_basis = hra_line.CalculationBasis.PERCENT_OF_COMPONENT
        hra_line.basis_component = self.setup["component"]
        hra_line.rate = Decimal("40.0000")
        hra_line.save(update_fields=["calculation_basis", "basis_component", "rate"])

        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=special_component,
            fixed_amount="0.00",
            sequence=120,
        )
        special_line = self.setup["version"].lines.get(component=special_component)
        special_line.calculation_basis = special_line.CalculationBasis.INPUT
        special_line.fixed_amount = Decimal("0.00")
        special_line.save(update_fields=["calculation_basis", "fixed_amount"])

        for component in (hra_component, special_component):
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        basic_row = row.components.get(component=self.setup["component"])
        hra_row = row.components.get(component=hra_component)
        special_row = row.components.get(component=special_component)

        self.assertEqual(basic_row.amount, Decimal("20000.00"))
        self.assertEqual(hra_row.amount, Decimal("8000.00"))
        self.assertEqual(special_row.amount, Decimal("22000.00"))
        self.assertEqual(row.gross_amount, Decimal("50000.00"))
        self.assertEqual(special_row.calculation_basis_snapshot["semantic_role"], "SPECIAL_ALLOWANCE")

    def test_calculate_applies_pf_cap_for_employee_and_employer_components(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("40.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        pf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        pf_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYER",
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        for component, sequence in ((pf_employee_component, 300), (pf_employer_component, 400)):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            line = self.setup["version"].lines.get(component=component)
            line.calculation_basis = line.CalculationBasis.PERCENT_OF_COMPONENT
            line.basis_component = self.setup["component"]
            line.rate = Decimal("12.0000")
            line.save(update_fields=["calculation_basis", "basis_component", "rate"])
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "pf_wage_cap": "15000.00",
            "pf_employee_rate": "12.00",
            "pf_employer_rate": "12.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        basic_row = row.components.get(component=self.setup["component"])
        pf_employee_row = row.components.get(component=pf_employee_component)
        pf_employer_row = row.components.get(component=pf_employer_component)

        self.assertEqual(basic_row.amount, Decimal("20000.00"))
        self.assertEqual(pf_employee_row.amount, Decimal("1800.00"))
        self.assertEqual(pf_employer_row.amount, Decimal("1800.00"))
        self.assertEqual(row.deduction_amount, Decimal("1800.00"))
        self.assertEqual(row.employer_contribution_amount, Decimal("1800.00"))
        self.assertEqual(pf_employee_row.calculation_basis_snapshot["semantic_role"], "PF_EMPLOYEE")
        self.assertEqual(pf_employer_row.calculation_basis_snapshot["semantic_role"], "PF_EMPLOYER")

    def test_calculate_applies_professional_tax_when_threshold_is_met(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("40.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=pt_component,
            fixed_amount="0.00",
            sequence=310,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pt_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "professional_tax_threshold": "15000.00",
            "professional_tax_amount": "200.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._set_contract_statutory_flags(pt_applicable=True)
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        pt_row = row.components.get(component=pt_component)

        self.assertEqual(pt_row.amount, Decimal("200.00"))
        self.assertEqual(row.deduction_amount, Decimal("200.00"))
        self.assertEqual(pt_row.calculation_basis_snapshot["semantic_role"], PayrollComponent.SemanticCode.PT)

    def test_calculate_skips_professional_tax_below_threshold(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=pt_component,
            fixed_amount="0.00",
            sequence=310,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pt_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "professional_tax_threshold": "15000.00",
            "professional_tax_amount": "200.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._set_contract_statutory_flags(pt_applicable=True)
        self.setup["profile"].extra_data = {
            "fixed_salary": "12000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        pt_row = row.components.get(component=pt_component)

        self.assertEqual(pt_row.amount, Decimal("0.00"))
        self.assertEqual(row.deduction_amount, Decimal("0.00"))

    def test_calculate_applies_esi_for_eligible_earnings(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        esi_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        esi_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYER",
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        for component, sequence in ((esi_employee_component, 305), (esi_employer_component, 405)):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "esi_wage_threshold": "21000.00",
            "esi_employee_rate": "0.75",
            "esi_employer_rate": "3.25",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._set_contract_statutory_flags(esi_applicable=True)
        self.setup["profile"].extra_data = {
            "fixed_salary": "18000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        esi_employee_row = row.components.get(component=esi_employee_component)
        esi_employer_row = row.components.get(component=esi_employer_component)

        self.assertEqual(esi_employee_row.amount, Decimal("135.00"))
        self.assertEqual(esi_employer_row.amount, Decimal("585.00"))
        self.assertEqual(row.deduction_amount, Decimal("135.00"))
        self.assertEqual(row.employer_contribution_amount, Decimal("585.00"))
        self.assertEqual(esi_employee_row.calculation_basis_snapshot["semantic_role"], "ESI_EMPLOYEE")
        self.assertEqual(esi_employer_row.calculation_basis_snapshot["semantic_role"], "ESI_EMPLOYER")

    def test_calculate_skips_esi_above_threshold(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        esi_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        esi_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYER",
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        for component, sequence in ((esi_employee_component, 305), (esi_employer_component, 405)):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "esi_wage_threshold": "21000.00",
            "esi_employee_rate": "0.75",
            "esi_employer_rate": "3.25",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self._set_contract_statutory_flags(esi_applicable=True)
        self.setup["profile"].extra_data = {
            "fixed_salary": "22000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        esi_employee_row = row.components.get(component=esi_employee_component)
        esi_employer_row = row.components.get(component=esi_employer_component)

        self.assertEqual(esi_employee_row.amount, Decimal("0.00"))
        self.assertEqual(esi_employer_row.amount, Decimal("0.00"))
        self.assertEqual(row.deduction_amount, Decimal("0.00"))
        self.assertEqual(row.employer_contribution_amount, Decimal("0.00"))

    def test_calculate_uses_monthly_tds_projection_snapshot(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "monthly_tds": "3500.00",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("3500.00"))
        self.assertEqual(row.deduction_amount, Decimal("3500.00"))
        self.assertEqual(tds_row.calculation_basis_snapshot["semantic_role"], "TDS")

    def test_calculate_derives_tds_from_annual_projection_balance(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "annual_tax": "120000.00",
                "tax_paid_ytd": "30000.00",
                "previous_employer_tds": "12000.00",
                "remaining_periods": "9",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("8666.67"))
        self.assertEqual(row.deduction_amount, Decimal("8666.67"))

    def test_calculate_derives_tds_from_income_and_declaration_projection_when_annual_tax_missing(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate": "10.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "other_income": "80000.00",
                "declared_deductions": "150000.00",
                "previous_employer_income": "250000.00",
                "previous_employer_tds": "12000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("6100.00"))
        self.assertEqual(row.deduction_amount, Decimal("6100.00"))

    def test_calculate_derives_tds_with_new_regime_rate_and_ignores_declared_deductions(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_projection_rate_new_regime": "12.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "new_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "other_income": "80000.00",
                "declared_deductions": "150000.00",
                "previous_employer_income": "250000.00",
                "previous_employer_tds": "12000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("9360.00"))
        self.assertEqual(row.deduction_amount, Decimal("9360.00"))

    def test_calculate_derives_tds_with_old_regime_structured_deduction_caps(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_80c_cap": "150000.00",
            "tds_80d_cap": "25000.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "other_income": "80000.00",
                "declared_deductions": "20000.00",
                "deduction_80c": "180000.00",
                "deduction_80d": "40000.00",
                "hra_exemption": "120000.00",
                "previous_employer_income": "250000.00",
                "previous_employer_tds": "12000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("4450.00"))
        self.assertEqual(row.deduction_amount, Decimal("4450.00"))

    def test_calculate_derives_tds_with_new_regime_standard_deduction(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_new_regime": "12.00",
            "tds_standard_deduction_new_regime": "50000.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "new_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "other_income": "80000.00",
                "declared_deductions": "150000.00",
                "previous_employer_income": "250000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("10560.00"))
        self.assertEqual(row.deduction_amount, Decimal("10560.00"))

    def test_calculate_uses_projected_taxable_income_and_previous_employer_taxable_income(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_standard_deduction_old_regime": "50000.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "projected_taxable_income": "640000.00",
                "other_income": "80000.00",
                "previous_employer_income": "400000.00",
                "previous_employer_taxable_income": "225000.00",
                "previous_employer_tds": "14000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("5000.00"))
        self.assertEqual(row.deduction_amount, Decimal("5000.00"))

    def test_calculate_prefers_old_regime_slabs_over_projection_rate_fallback(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "30.00",
            "tds_old_regime_slabs": [
                {"upto": "250000.00", "rate": "0.00"},
                {"upto": "500000.00", "rate": "5.00"},
                {"upto": "1000000.00", "rate": "20.00"},
                {"rate": "30.00"},
            ],
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "projected_taxable_income": "900000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("9250.00"))
        self.assertEqual(row.deduction_amount, Decimal("9250.00"))

    def test_calculate_applies_new_regime_rebate_when_slab_tax_is_below_rebate_cap(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_new_regime_slabs": [
                {"upto": "400000.00", "rate": "0.00"},
                {"upto": "800000.00", "rate": "5.00"},
                {"upto": "1200000.00", "rate": "10.00"},
                {"upto": "1600000.00", "rate": "15.00"},
                {"upto": "2000000.00", "rate": "20.00"},
                {"upto": "2400000.00", "rate": "25.00"},
                {"rate": "30.00"},
            ],
            "tds_rebate_threshold_new_regime": "1200000.00",
            "tds_rebate_max_new_regime": "60000.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "new_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "projected_taxable_income": "1000000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("0.00"))
        self.assertEqual(row.deduction_amount, Decimal("0.00"))

    def test_calculate_applies_old_regime_surcharge_and_cess_on_slab_tax(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_old_regime_slabs": [
                {"upto": "250000.00", "rate": "0.00"},
                {"upto": "500000.00", "rate": "5.00"},
                {"upto": "1000000.00", "rate": "20.00"},
                {"rate": "30.00"},
            ],
            "tds_old_regime_surcharge_slabs": [
                {"upto": "5000000.00", "rate": "0.00"},
                {"upto": "10000000.00", "rate": "10.00"},
                {"rate": "15.00"},
            ],
            "tds_health_education_cess_rate": "4.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "projected_taxable_income": "6000000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("184470.00"))
        self.assertEqual(row.deduction_amount, Decimal("184470.00"))

    def test_calculate_applies_marginal_relief_at_old_regime_surcharge_entry_point(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_old_regime_slabs": [
                {"upto": "250000.00", "rate": "0.00"},
                {"upto": "500000.00", "rate": "5.00"},
                {"upto": "1000000.00", "rate": "20.00"},
                {"rate": "30.00"},
            ],
            "tds_old_regime_surcharge_slabs": [
                {"upto": "5000000.00", "rate": "0.00"},
                {"upto": "10000000.00", "rate": "10.00"},
                {"rate": "15.00"},
            ],
            "tds_health_education_cess_rate": "4.00",
            "tds_apply_marginal_relief": True,
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "projected_taxable_income": "5100000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("146900.00"))
        self.assertEqual(row.deduction_amount, Decimal("146900.00"))

    def test_calculate_ignores_policy_disabled_old_regime_deduction_bucket(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_standard_deduction_old_regime": "50000.00",
            "tds_allow_80c_old_regime": False,
            "tds_allow_80d_old_regime": True,
            "tds_allow_hra_exemption_old_regime": True,
            "tds_80c_cap": "150000.00",
            "tds_80d_cap": "25000.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "other_income": "80000.00",
                "deduction_80c": "180000.00",
                "remaining_periods": "10",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("6300.00"))
        self.assertEqual(row.deduction_amount, Decimal("6300.00"))

    def test_calculate_caps_hra_exemption_using_support_inputs(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        hra_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="HRA",
            component_type=self.setup["component"].ComponentType.EARNING,
            posting_behavior=self.setup["component"].PostingBehavior.GROSS_EARNING,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=hra_component,
            fixed_amount="0.00",
            sequence=110,
        )
        hra_line = self.setup["version"].lines.get(component=hra_component)
        hra_line.calculation_basis = SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT
        hra_line.basis_component = self.setup["component"]
        hra_line.rate = Decimal("40.0000")
        hra_line.save(update_fields=["calculation_basis", "basis_component", "rate"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=hra_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_standard_deduction_old_regime": "50000.00",
            "tds_allow_hra_exemption_old_regime": True,
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "hra_exemption": "260000.00",
                "hra_rent_paid_annual": "300000.00",
                "hra_is_metro_city": True,
                "remaining_periods": "12",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("2583.33"))
        self.assertEqual(row.deduction_amount, Decimal("2583.33"))

    def test_calculate_derives_hra_exemption_from_support_inputs_when_not_declared(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        hra_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="HRA",
            component_type=self.setup["component"].ComponentType.EARNING,
            posting_behavior=self.setup["component"].PostingBehavior.GROSS_EARNING,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=hra_component,
            fixed_amount="0.00",
            sequence=110,
        )
        hra_line = self.setup["version"].lines.get(component=hra_component)
        hra_line.calculation_basis = SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT
        hra_line.basis_component = self.setup["component"]
        hra_line.rate = Decimal("40.0000")
        hra_line.save(update_fields=["calculation_basis", "basis_component", "rate"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=hra_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_standard_deduction_old_regime": "50000.00",
            "tds_allow_hra_exemption_old_regime": True,
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "hra_rent_paid_annual": "300000.00",
                "hra_is_metro_city": True,
                "remaining_periods": "12",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("2583.33"))
        self.assertEqual(row.deduction_amount, Decimal("2583.33"))

    def test_calculate_scales_hra_exemption_by_rent_months(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        hra_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="HRA",
            component_type=self.setup["component"].ComponentType.EARNING,
            posting_behavior=self.setup["component"].PostingBehavior.GROSS_EARNING,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=hra_component,
            fixed_amount="0.00",
            sequence=110,
        )
        hra_line = self.setup["version"].lines.get(component=hra_component)
        hra_line.calculation_basis = SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT
        hra_line.basis_component = self.setup["component"]
        hra_line.rate = Decimal("40.0000")
        hra_line.save(update_fields=["calculation_basis", "basis_component", "rate"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=hra_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="TDS",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=tds_component,
            fixed_amount="0.00",
            sequence=320,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=tds_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate_old_regime": "10.00",
            "tds_standard_deduction_old_regime": "50000.00",
            "tds_allow_hra_exemption_old_regime": True,
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].tax_regime = "old_regime"
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "hra_exemption": "260000.00",
                "hra_rent_paid_annual": "300000.00",
                "hra_rent_months": 6,
                "hra_is_metro_city": True,
                "remaining_periods": "12",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data", "tax_regime"]);
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(tds_row.amount, Decimal("3583.33"))
        self.assertEqual(row.deduction_amount, Decimal("3583.33"))

    def test_run_preflight_and_calculation_capture_policy_assumptions(self):
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "deduction_80c": "150000.00",
                "deduction_80c_evidence_verified": False,
                "hra_rent_paid_annual": "240000.00",
                "hra_evidence_verified": False,
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"]);
        self._sync_contract_native_from_profile()
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "ctc",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])

        second_account = PayrollFactory.gl_account(
            entity=self.setup["entity"],
            user=self.setup["user"],
            accounthead=self.setup["accounthead"],
            accountname="Second Salary Payable",
        )
        second_component = PayrollFactory.component(entity=self.setup["entity"], code="SPEC")
        second_structure = PayrollFactory.salary_structure(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
        )
        second_version = PayrollFactory.salary_structure_version(salary_structure=second_structure)
        second_version.calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "payable_days",
            "rounding_policy": "bankers",
        }
        second_version.save(update_fields=["calculation_policy_json"])
        PayrollFactory.salary_structure_line(
            salary_structure=second_structure,
            salary_structure_version=second_version,
            component=second_component,
            fixed_amount="500.00",
            sequence=10,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=second_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        second_profile = PayrollFactory.employee_profile(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payment_account=second_account,
            salary_structure=second_structure,
            salary_structure_version=second_version,
            employee_code="EMP-POLICY-2",
        )
        second_profile.extra_data = {
            "fixed_salary": "45000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        second_profile.save(update_fields=["extra_data"])
        second_contract_employee = PayrollFactory.hrms_employee(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee_number=second_profile.employee_code,
        )
        second_contract = PayrollFactory.hrms_contract(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee=second_contract_employee,
        )
        second_contract_profile = PayrollFactory.contract_payroll_profile(
            entity=self.setup["entity"],
            hrms_contract=second_contract,
            bank_account=second_account,
            payroll_status="ACTIVE",
        )
        ContractSalaryStructureAssignment.objects.create(
            contract_payroll_profile=second_contract_profile,
            salary_structure=second_structure,
            salary_structure_version=second_version,
            effective_from=self.setup["period"].period_start,
            assignment_status=ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
            ctc_amount=Decimal("0.00"),
            gross_amount=Decimal("45000.00"),
            is_active=True,
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

        preflight = (run.config_snapshot or {}).get("policy_preflight", {})
        self.assertIn("Resolved employees use mixed salary modes in their structure policies.", preflight.get("warnings", []))
        self.assertIn("Resolved employees use mixed proration bases in their structure policies.", preflight.get("warnings", []))
        self.assertIn("contract payroll profile(s) include HRA rent support that is not explicitly marked as verified", " ".join(preflight.get("warnings", [])))
        self.assertIn("contract payroll profile(s) include 80C or 80D declarations that are not explicitly marked as verified", " ".join(preflight.get("warnings", [])))
        self.assertEqual(preflight.get("unverified_hra_evidence_count"), 1)
        self.assertEqual(preflight.get("approval_blocked_hra_evidence_count"), 0)
        self.assertEqual(preflight.get("unverified_tax_declaration_count"), 1)
        self.assertEqual(preflight.get("approval_blocked_tax_declaration_count"), 0)

        PayrollRunService.calculate_run(run)
        run.refresh_from_db()
        self.assertIn("policy_preflight_warnings", run.calculation_payload)

        assumptions = list(run.employee_runs.values_list("calculation_assumptions", flat=True))
        self.assertTrue(any(item.get("salary_mode") == "ctc" for item in assumptions))
        self.assertTrue(any(item.get("salary_mode") == "gross" for item in assumptions))
        self.assertTrue(any(item.get("proration_basis") == "attendance_days" for item in assumptions))
        self.assertTrue(any(item.get("proration_basis") == "payable_days" for item in assumptions))

        summary = PayrollRunService.summary(run)
        self.assertIn("Resolved employees use mixed salary modes in their structure policies.", summary["warnings"])
        self.assertIn("payroll profile(s) include HRA rent support that is not explicitly marked as verified", " ".join(summary["warnings"]))

    def test_calculate_blocks_when_resolved_version_has_no_calculation_policy(self):
        self.setup["version"].calculation_policy_json = {}
        self.setup["version"].save(update_fields=["calculation_policy_json"])
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

        with self.assertRaises(ValueError) as error:
            PayrollRunService.calculate_run(run)

        payload = error.exception.args[0]
        self.assertIsInstance(payload, dict)
        self.assertIn("preflight", payload)
        self.assertIn("missing calculation policy metadata", " ".join(payload["preflight"]["blockers"]).lower())
        run.refresh_from_db()
        self.assertIn("policy_preflight", run.config_snapshot or {})

    def test_calculate_blocks_when_active_profile_has_no_resolved_structure_version(self):
        self.setup["profile"].salary_structure_version = None
        self.setup["profile"].save(update_fields=["salary_structure_version"])
        self.setup["version"].status = self.setup["version"].Status.DRAFT
        self.setup["version"].save(update_fields=["status"])
        self.setup["structure"].current_version = None
        self.setup["structure"].save(update_fields=["current_version"])

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

        with self.assertRaises(ValueError) as error:
            PayrollRunService.calculate_run(run)

        payload = error.exception.args[0]
        self.assertIsInstance(payload, dict)
        self.assertIn("approved salary structure version", " ".join(payload["preflight"]["blockers"]).lower())

    def test_legacy_component_codes_are_backfilled_to_explicit_semantic_codes(self):
        basic = PayrollComponent.objects.create(
            entity=self.setup["entity"],
            code="BASIC",
            name="Basic Salary",
            component_type=PayrollComponent.ComponentType.EARNING,
            posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
        )
        tds = PayrollComponent.objects.create(
            entity=self.setup["entity"],
            code="TDS",
            name="Tax Deducted at Source",
            component_type=PayrollComponent.ComponentType.DEDUCTION,
            posting_behavior=PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
        )

        self.assertEqual(basic.semantic_code, PayrollComponent.SemanticCode.BASIC_PAY)
        self.assertEqual(tds.semantic_code, PayrollComponent.SemanticCode.TDS)

    def test_calculate_custom_formula_salary_line(self):
        self.setup["line"].rule_mode = SalaryStructureLine.RuleMode.CUSTOM_FORMULA
        self.setup["line"].rule_json = {"formula": "ctc * 0.4"}
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["rule_mode", "rule_json", "fixed_amount"])

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
        row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(row.amount, Decimal("4000.00"))
        self.assertEqual(row.calculation_basis_snapshot["calculation_mode"], SalaryStructureLine.RuleMode.CUSTOM_FORMULA)
        self.assertEqual(row.calculation_basis_snapshot["formula_used"], "ctc * 0.4")
        self.assertEqual(row.calculation_basis_snapshot["final_amount"], "4000.00")

    def test_calculate_input_basis_uses_contract_native_input_snapshot(self):
        self.setup["component"].semantic_code = PayrollComponent.SemanticCode.OTHER_EARNING
        self.setup["component"].save(update_fields=["semantic_code"])
        self.setup["line"].calculation_basis = SalaryStructureLine.CalculationBasis.INPUT
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].rule_json = {"input_code": "monthly_adjustment"}
        self.setup["line"].save(update_fields=["calculation_basis", "fixed_amount", "rule_json"])
        PayrollFactory.contract_input_snapshot(
            entity=self.setup["entity"],
            contract_payroll_profile=self.setup["contract_profile"],
            payroll_period=self.setup["period"],
            input_type=ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
            input_json={"monthly_adjustment": "2450.00"},
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
        row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(row.amount, Decimal("2450.00"))
        self.assertEqual(row.calculation_basis_snapshot["calculation_mode"], SalaryStructureLine.CalculationBasis.INPUT)
        self.assertEqual(row.calculation_basis_snapshot["final_amount"], "2450.00")
        self.assertEqual(row.metadata["calculation_trace"]["input_source"], "manual_input_snapshot")

    def test_calculate_rule_json_cap_limits_amount(self):
        self.setup["line"].fixed_amount = Decimal("6500.00")
        self.setup["line"].rule_json = {"max_amount": "5000.00"}
        self.setup["line"].save(update_fields=["fixed_amount", "rule_json"])

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
        row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(row.amount, Decimal("5000.00"))
        self.assertEqual(row.calculation_basis_snapshot["rule_json_applied"]["steps"][-1]["type"], "max_cap")

    def test_calculate_rule_json_slab_uses_base_amount(self):
        self.setup["line"].fixed_amount = Decimal("15000.00")
        self.setup["line"].rule_json = {
            "slabs": [
                {"from": "0.00", "to": "10000.00", "amount": "1000.00"},
                {"from": "10000.01", "to": "20000.00", "amount": "1750.00"},
            ]
        }
        self.setup["line"].save(update_fields=["fixed_amount", "rule_json"])

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
        row = self._get_run_employee(run).components.get(component=self.setup["component"])
        self.assertEqual(row.amount, Decimal("1750.00"))
        self.assertEqual(row.calculation_basis_snapshot["rule_json_applied"]["steps"][0]["type"], "slab")

    def test_calculate_invalid_formula_fails_safely(self):
        self.setup["line"].rule_mode = SalaryStructureLine.RuleMode.CUSTOM_FORMULA
        self.setup["line"].rule_json = {"formula": "__import__('os')"}
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["rule_mode", "rule_json", "fixed_amount"])

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

        with self.assertRaises(PayrollCalculationError) as error:
            PayrollRunService.calculate_run(run)

        self.assertIn("Invalid salary line custom formula", str(error.exception))
        self.assertIn("Formula node Call is not allowed", str(error.exception))

    def test_calculate_formula_missing_variable_fails_clearly(self):
        self.setup["line"].rule_mode = SalaryStructureLine.RuleMode.CUSTOM_FORMULA
        self.setup["line"].rule_json = {"formula": "missing_component * 2"}
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["rule_mode", "rule_json", "fixed_amount"])

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

        with self.assertRaises(PayrollCalculationError) as error:
            PayrollRunService.calculate_run(run)

        self.assertIn("Unknown payroll formula variable 'missing_component'", str(error.exception))

    def test_calculate_uses_explicit_semantic_codes_not_component_code_prefixes(self):
        self.setup["component"].code = "BASE_PAY_CORE"
        self.setup["component"].name = "Base Pay Core"
        self.setup["component"].semantic_code = PayrollComponent.SemanticCode.BASIC_PAY
        self.setup["component"].save(update_fields=["code", "name", "semantic_code"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("40.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])

        pf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="DEDUCT_CORE_PF",
            semantic_code=PayrollComponent.SemanticCode.PF_EMPLOYEE,
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        pf_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="EMPLOYER_CORE_PF",
            semantic_code=PayrollComponent.SemanticCode.PF_EMPLOYER,
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        tds_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="WITHHOLDING_TAX_BUCKET",
            semantic_code=PayrollComponent.SemanticCode.TDS,
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )

        for component, sequence in (
            (pf_employee_component, 300),
            (pf_employer_component, 400),
            (tds_component, 320),
        ):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            line = self.setup["version"].lines.get(component=component)
            if component == tds_component:
                line.calculation_basis = line.CalculationBasis.INPUT
                line.fixed_amount = Decimal("0.00")
                line.save(update_fields=["calculation_basis", "fixed_amount"])
            else:
                line.calculation_basis = line.CalculationBasis.PERCENT_OF_COMPONENT
                line.basis_component = self.setup["component"]
                line.rate = Decimal("12.0000")
                line.save(update_fields=["calculation_basis", "basis_component", "rate"])
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "pf_wage_cap": "15000.00",
            "pf_employee_rate": "12.00",
            "pf_employer_rate": "12.00",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
            "tax_projection_snapshot": {
                "monthly_tds": "2500.00",
            },
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        basic_row = row.components.get(component=self.setup["component"])
        pf_employee_row = row.components.get(component=pf_employee_component)
        pf_employer_row = row.components.get(component=pf_employer_component)
        tds_row = row.components.get(component=tds_component)

        self.assertEqual(basic_row.amount, Decimal("20000.00"))
        self.assertEqual(pf_employee_row.amount, Decimal("1800.00"))
        self.assertEqual(pf_employer_row.amount, Decimal("1800.00"))
        self.assertEqual(tds_row.amount, Decimal("2500.00"))
        self.assertEqual(basic_row.calculation_basis_snapshot["semantic_role"], PayrollComponent.SemanticCode.BASIC_PAY)
        self.assertEqual(pf_employee_row.calculation_basis_snapshot["semantic_role"], PayrollComponent.SemanticCode.PF_EMPLOYEE)
        self.assertEqual(tds_row.calculation_basis_snapshot["semantic_role"], PayrollComponent.SemanticCode.TDS)

    def test_statutory_engine_calculates_pf_from_scheme_rule_with_wage_ceiling(self):
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("40.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        self._create_statutory_runtime_config(
            scheme_code="PF",
            scheme_type=StatutoryScheme.SchemeType.PF,
            rule_json={"employee_rate": "12.00", "employer_rate": "12.00", "wage_cap": "15000.00"},
        )

        pf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        pf_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYER",
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        for component, sequence in ((pf_employee_component, 300), (pf_employer_component, 400)):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            line = self.setup["version"].lines.get(component=component)
            line.calculation_basis = line.CalculationBasis.PERCENT_OF_COMPONENT
            line.basis_component = self.setup["component"]
            line.rate = Decimal("0.00")
            line.save(update_fields=["calculation_basis", "basis_component", "rate"])
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )

        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        pf_employee_row = row.components.get(component=pf_employee_component)
        pf_employer_row = row.components.get(component=pf_employer_component)

        self.assertEqual(pf_employee_row.amount, Decimal("1800.00"))
        self.assertEqual(pf_employer_row.amount, Decimal("1800.00"))
        self.assertEqual(
            pf_employee_row.metadata["calculation_trace"]["scheme"]["scheme_code"],
            "PF",
        )
        self.assertEqual(
            pf_employee_row.metadata["calculation_trace"]["cap_or_ceiling"],
            "15000.00",
        )

    def test_statutory_engine_skips_pf_when_contract_profile_marks_scheme_not_applicable(self):
        self._set_contract_statutory_flags(pf_applicable=False)
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("40.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        self._create_statutory_runtime_config(
            scheme_code="PF",
            scheme_type=StatutoryScheme.SchemeType.PF,
            rule_json={"employee_rate": "12.00", "wage_cap": "15000.00"},
            is_applicable=False,
        )

        pf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PF_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=pf_employee_component,
            fixed_amount="0.00",
            sequence=300,
        )
        line = self.setup["version"].lines.get(component=pf_employee_component)
        line.calculation_basis = line.CalculationBasis.PERCENT_OF_COMPONENT
        line.basis_component = self.setup["component"]
        line.rate = Decimal("0.00")
        line.save(update_fields=["calculation_basis", "basis_component", "rate"])
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pf_employee_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "50000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        pf_employee_row = row.components.get(component=pf_employee_component)

        self.assertEqual(pf_employee_row.amount, Decimal("0.00"))
        self.assertIn(
            "disabled",
            pf_employee_row.metadata["calculation_trace"]["applicability_decision"],
        )

    def test_statutory_engine_calculates_esi_under_wage_ceiling(self):
        self._set_contract_statutory_flags(esi_applicable=True)
        self._create_statutory_runtime_config(
            scheme_code="ESI",
            scheme_type=StatutoryScheme.SchemeType.ESI,
            rule_json={"employee_rate": "0.75", "employer_rate": "3.25", "wage_threshold": "21000.00"},
        )
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        esi_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        esi_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYER",
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        for component, sequence in ((esi_employee_component, 305), (esi_employer_component, 405)):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "18000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        self.assertEqual(row.components.get(component=esi_employee_component).amount, Decimal("135.00"))
        self.assertEqual(row.components.get(component=esi_employer_component).amount, Decimal("585.00"))

    def test_statutory_engine_skips_esi_above_wage_ceiling(self):
        self._set_contract_statutory_flags(esi_applicable=True)
        self._create_statutory_runtime_config(
            scheme_code="ESI",
            scheme_type=StatutoryScheme.SchemeType.ESI,
            rule_json={"employee_rate": "0.75", "employer_rate": "3.25", "wage_threshold": "21000.00"},
        )
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        esi_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="ESI_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=esi_employee_component,
            fixed_amount="0.00",
            sequence=305,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=esi_employee_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "22000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        esi_employee_row = row.components.get(component=esi_employee_component)

        self.assertEqual(esi_employee_row.amount, Decimal("0.00"))
        self.assertIn("exceed", esi_employee_row.metadata["calculation_trace"]["applicability_decision"])

    def test_statutory_engine_calculates_pt_from_slabs(self):
        self._set_contract_statutory_flags(pt_applicable=True)
        self._create_statutory_runtime_config(
            scheme_code="PT",
            scheme_type=StatutoryScheme.SchemeType.PT,
            rule_type="SLAB",
            slabs=[
                {"slab_from": "0.00", "slab_to": "14999.99", "amount": "0.00"},
                {"slab_from": "15000.00", "slab_to": None, "amount": "200.00"},
            ],
        )
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=pt_component,
            fixed_amount="0.00",
            sequence=310,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pt_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "20000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        pt_row = self._get_run_employee(run).components.get(component=pt_component)
        self.assertEqual(pt_row.amount, Decimal("200.00"))
        self.assertTrue(pt_row.metadata["calculation_trace"]["slab"])

    def test_statutory_engine_calculates_lwf_from_fixed_and_slab_config(self):
        self._set_contract_statutory_flags(lwf_applicable=True)
        self._create_statutory_runtime_config(
            scheme_code="LWF",
            scheme_type=StatutoryScheme.SchemeType.LWF,
            rule_type="SLAB",
            rule_json={"employee_amount": "20.00", "employer_amount": "40.00", "periodicity": "MONTHLY"},
            slabs=[{"slab_from": "0.00", "slab_to": None, "amount": "20.00"}],
        )
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        lwf_employee_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="LWF_EMPLOYEE",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        lwf_employer_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="LWF_EMPLOYER",
            component_type=self.setup["component"].ComponentType.EMPLOYER_CONTRIBUTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYER_LIABILITY,
        )
        for component, sequence in ((lwf_employee_component, 330), (lwf_employer_component, 430)):
            PayrollFactory.salary_structure_line(
                salary_structure=self.setup["structure"],
                salary_structure_version=self.setup["version"],
                component=component,
                fixed_amount="0.00",
                sequence=sequence,
            )
            PayrollFactory.component_posting(
                entity=self.setup["entity"],
                entityfinid=self.setup["entityfinid"],
                subentity=self.setup["subentity"],
                component=component,
                expense_account=self.setup["expense_account"],
                liability_account=self.setup["liability_account"],
                payable_account=self.setup["payable_account"],
            )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "20000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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
        row = self._get_run_employee(run)
        self.assertEqual(row.components.get(component=lwf_employee_component).amount, Decimal("20.00"))
        self.assertEqual(row.components.get(component=lwf_employer_component).amount, Decimal("40.00"))

    def test_statutory_engine_missing_config_fails_loudly(self):
        self._set_contract_statutory_flags(pt_applicable=True)
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=pt_component,
            fixed_amount="0.00",
            sequence=310,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pt_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "20000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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

        with self.assertRaises(PayrollCalculationError) as error:
            PayrollRunService.calculate_run(run)

        self.assertIn("Invalid statutory payroll configuration", str(error.exception))
        self.assertIn("PROFESSIONAL_TAX", str(error.exception))

    def test_payroll_run_service_delegates_statutory_components_to_engine(self):
        self._set_contract_statutory_flags(pt_applicable=True)
        self.setup["component"].code = "BASIC"
        self.setup["component"].name = "Basic Salary"
        self.setup["component"].save(update_fields=["code", "name"])
        self.setup["line"].calculation_basis = self.setup["line"].CalculationBasis.PERCENT_OF_CTC
        self.setup["line"].rate = Decimal("100.0000")
        self.setup["line"].fixed_amount = Decimal("0.00")
        self.setup["line"].save(update_fields=["calculation_basis", "rate", "fixed_amount"])
        pt_component = PayrollFactory.component(
            entity=self.setup["entity"],
            code="PROFESSIONAL_TAX",
            component_type=self.setup["component"].ComponentType.DEDUCTION,
            posting_behavior=self.setup["component"].PostingBehavior.EMPLOYEE_LIABILITY,
        )
        PayrollFactory.salary_structure_line(
            salary_structure=self.setup["structure"],
            salary_structure_version=self.setup["version"],
            component=pt_component,
            fixed_amount="0.00",
            sequence=310,
        )
        PayrollFactory.component_posting(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            component=pt_component,
            expense_account=self.setup["expense_account"],
            liability_account=self.setup["liability_account"],
            payable_account=self.setup["payable_account"],
        )
        self._create_statutory_runtime_config(
            scheme_code="PT",
            scheme_type=StatutoryScheme.SchemeType.PT,
            rule_json={"amount": "200.00"},
        )
        self.setup["version"].calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.setup["version"].save(update_fields=["calculation_policy_json"])
        self.setup["profile"].extra_data = {
            "fixed_salary": "20000.00",
            "attendance_days": 30,
            "payable_days": 30,
            "period_days": 30,
        }
        self.setup["profile"].save(update_fields=["extra_data"])
        self._sync_contract_native_from_profile()

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

        with patch("payroll.services.payroll_run_service.PayrollStatutoryEngine.calculate_component") as engine_mock:
            engine_mock.return_value = PayrollStatutoryResult(
                amount=Decimal("321.00"),
                trace={"applicability_decision": "patched", "scheme": {"scheme_code": "PT"}},
            )
            PayrollRunService.calculate_run(run)

        pt_row = self._get_run_employee(run).components.get(component=pt_component)
        self.assertTrue(engine_mock.called)
        self.assertEqual(pt_row.amount, Decimal("321.00"))
