from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hrms.models import ContractLeaveBalanceSnapshot, LeaveType, LeavePolicy, LeavePolicyRule
from hrms.services import LeaveApplicationService, LeaveApprovalService, LeaveBalanceService, LeaveRuleEngine, LeaveYearService


class LeaveRuleEnginePhase1Tests(TestCase):
    def setUp(self):
        from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
        from hrms.models import HrEmployee, HrEmploymentContract
        from payroll.models import (
            ContractAttendanceSummary,
            ContractPayrollProfile,
            ContractSalaryStructureAssignment,
            PayrollComponent,
            PayrollPeriod,
            SalaryStructure,
            SalaryStructureLine,
            SalaryStructureVersion,
        )

        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="leave-engine-user",
            email="leave-engine@example.com",
            password="pass123",
        )
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular GST")
        entity = Entity.objects.create(
            entityname="Leave Engine Entity",
            legalname="Leave Engine Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        subentity = SubEntity.objects.create(
            entity=entity,
            subentityname="Head Office",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )
        entityfinid = EntityFinancialYear.objects.create(
            entity=entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        employee = HrEmployee.objects.create(
            entity=entity,
            subentity=subentity,
            linked_user=self.user,
            employee_number="EMP001",
            legal_first_name="Leave",
            legal_last_name="Tester",
            display_name="Leave Tester",
            work_email="leave.tester@example.com",
        )
        contract = HrEmploymentContract.objects.create(
            entity=entity,
            subentity=subentity,
            employee=employee,
            contract_code="CON001",
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            start_date=date(2025, 4, 1),
            payroll_effective_from=date(2025, 4, 1),
            is_payroll_eligible=True,
        )
        component = PayrollComponent.objects.create(
            entity=entity,
            code="BASIC",
            name="Basic Pay",
            component_type=PayrollComponent.ComponentType.EARNING,
            posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
            is_taxable=True,
            affects_net_pay=True,
            default_sequence=100,
            semantic_code=PayrollComponent.SemanticCode.BASIC_PAY,
        )
        structure = SalaryStructure.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code="SAL001",
            name="Standard Structure",
            status=SalaryStructure.Status.ACTIVE,
        )
        version = SalaryStructureVersion.objects.create(
            salary_structure=structure,
            version_no=1,
            effective_from=date(2025, 4, 1),
            status=SalaryStructureVersion.Status.APPROVED,
            calculation_policy_json={"proration_basis": "attendance_days"},
        )
        structure.current_version = version
        structure.save(update_fields=["current_version", "updated_at"])
        SalaryStructureLine.objects.create(
            salary_structure=structure,
            salary_structure_version=version,
            component=component,
            sequence=100,
            calculation_basis=SalaryStructureLine.CalculationBasis.FIXED,
            fixed_amount=Decimal("3000.00"),
            is_pro_rated=True,
            is_active=True,
        )
        profile = ContractPayrollProfile.objects.create(
            entity=entity,
            hrms_contract=contract,
            pay_frequency="MONTHLY",
            payroll_status=ContractPayrollProfile.PayrollStatus.ACTIVE,
            payroll_start_date=date(2025, 4, 1),
            attendance_required=False,
            is_active=True,
        )
        ContractSalaryStructureAssignment.objects.create(
            contract_payroll_profile=profile,
            salary_structure=structure,
            salary_structure_version=version,
            effective_from=date(2025, 4, 1),
            assignment_status=ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
            ctc_amount=Decimal("3000.00"),
            gross_amount=Decimal("3000.00"),
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code="APR-2025",
            pay_frequency=PayrollPeriod.PayFrequency.MONTHLY,
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
            payout_date=date(2025, 4, 30),
            status=PayrollPeriod.Status.OPEN,
        )
        attendance_summary = ContractAttendanceSummary.objects.create(
            entity=entity,
            contract_payroll_profile=profile,
            payroll_period=period,
            attendance_days=Decimal("30.00"),
            payable_days=Decimal("30.00"),
            lop_days=Decimal("0.00"),
            weekly_off_days=Decimal("0.00"),
            holiday_days=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            late_count=0,
            half_days=Decimal("0.00"),
            source=ContractAttendanceSummary.Source.MANUAL,
            approval_status=ContractAttendanceSummary.ApprovalStatus.APPROVED,
            is_active=True,
        )
        self.setup = {
            "user": self.user,
            "entity": entity,
            "subentity": subentity,
            "entityfinid": entityfinid,
            "employee": employee,
            "hrms_contract": contract,
            "component": component,
            "structure": structure,
            "version": version,
            "contract_profile": profile,
            "period": period,
            "attendance_summary": attendance_summary,
        }
        self.contract = contract
        self.profile = profile
        self.period = period
        self.version = version
        self.contract.probation_end = date(2025, 4, 1)
        self.contract.save(update_fields=["probation_end"])

    def _create_leave_runtime(self, *, code: str, name: str, is_paid: bool = True, requires_balance: bool = True, rule_json: dict | None = None):
        leave_type = LeaveType.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            code=code,
            name=name,
            category=LeaveType.Category.EARNED if code == "EL" else LeaveType.Category.LOP,
            is_paid=is_paid,
            requires_balance=requires_balance,
            counts_towards_attendance=is_paid,
            payroll_impact_code="PAID_LEAVE" if is_paid else "LOSS_OF_PAY",
            effective_from=date(2025, 4, 1),
        )
        policy = LeavePolicy.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            code=f"{code}_POL",
            name=f"{name} Policy",
            status=LeavePolicy.Status.ACTIVE,
            is_default=True,
            employee_category=LeavePolicy.EmployeeCategory.SERVICES,
            effective_from=date(2025, 4, 1),
        )
        LeavePolicyRule.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            leave_policy=policy,
            leave_type=leave_type,
            rule_code=f"{code}_RULE",
            rule_name=f"{name} Rule",
            rule_json=rule_json or {},
            effective_from=date(2025, 4, 1),
        )
        return leave_type, policy

    def test_earned_leave_accrual_with_90_percent_attendance(self):
        leave_type, _ = self._create_leave_runtime(
            code="EL",
            name="Earned Leave",
            rule_json={
                "accrual_frequency": "monthly",
                "monthly_quota": "1.50",
                "conditions": {"attendance_percentage_gte": 90, "probation_completed": True},
            },
        )
        self.setup["attendance_summary"].attendance_days = Decimal("27.00")
        self.setup["attendance_summary"].payable_days = Decimal("27.00")
        self.setup["attendance_summary"].save(update_fields=["attendance_days", "payable_days"])

        result = LeaveBalanceService.accrue_for_period(
            contract=self.contract,
            leave_type=leave_type,
            as_of_date=self.period.period_end,
            payroll_period=self.period,
        )

        self.assertEqual(result["accrued_days"], "1.50")
        self.assertEqual(
            LeaveBalanceService.get_balance_days(
                contract=self.contract,
                leave_type=leave_type,
                as_of_date=self.period.period_end,
            ),
            Decimal("1.50"),
        )

    def test_accrual_blocked_below_90_percent(self):
        leave_type, _ = self._create_leave_runtime(
            code="EL",
            name="Earned Leave",
            rule_json={
                "accrual_frequency": "monthly",
                "monthly_quota": "1.50",
                "conditions": {"attendance_percentage_gte": 90},
            },
        )
        self.setup["attendance_summary"].attendance_days = Decimal("26.00")
        self.setup["attendance_summary"].payable_days = Decimal("26.00")
        self.setup["attendance_summary"].save(update_fields=["attendance_days", "payable_days"])

        result = LeaveBalanceService.accrue_for_period(
            contract=self.contract,
            leave_type=leave_type,
            as_of_date=self.period.period_end,
            payroll_period=self.period,
        )

        self.assertEqual(result["accrued_days"], "0.00")
        self.assertEqual(LeaveBalanceService.get_balance_days(contract=self.contract, leave_type=leave_type), Decimal("0.00"))

    def test_paid_leave_payable_day_impact(self):
        leave_type, policy = self._create_leave_runtime(
            code="CL",
            name="Casual Leave",
            rule_json={"payroll_impact": {"lop_on_exhaustion": True}},
        )
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            contract=self.contract,
            leave_policy=policy,
            leave_type=leave_type,
            snapshot_date=self.period.period_start,
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance=Decimal("5.00"),
            closing_balance=Decimal("5.00"),
        )
        self.version.calculation_policy_json["proration_basis"] = "payable_days"
        self.version.save(update_fields=["calculation_policy_json"])
        self.setup["attendance_summary"].attendance_days = Decimal("20.00")
        self.setup["attendance_summary"].payable_days = Decimal("20.00")
        self.setup["attendance_summary"].save(update_fields=["attendance_days", "payable_days"])

        application = LeaveApplicationService.create_application(
            attrs={
                "contract": self.contract,
                "leave_type": leave_type,
                "start_date": self.period.period_start,
                "end_date": self.period.period_start + timedelta(days=1),
                "requested_days": "2.00",
                "reason": "Casual leave",
            },
            actor=self.setup["user"],
        )
        LeaveApprovalService.approve(application=application, approver=self.setup["user"], approved_days=Decimal("2.00"))

        from payroll.services import PayrollAttendanceEngine

        result = PayrollAttendanceEngine.evaluate(
            contract_payroll_profile=self.profile,
            payroll_period=self.period,
            structure_version=self.version,
            payroll_policy_snapshot=None,
            attendance_required=False,
        )

        self.assertEqual(result.paid_leave_days, Decimal("2.00"))
        self.assertEqual(result.payable_days, Decimal("22.00"))

    def test_unpaid_leave_lop_impact(self):
        leave_type, _ = self._create_leave_runtime(
            code="LWP",
            name="Leave Without Pay",
            is_paid=False,
            requires_balance=False,
            rule_json={"payroll_impact": {"force_unpaid": True}},
        )
        self.version.calculation_policy_json["proration_basis"] = "payable_days"
        self.version.save(update_fields=["calculation_policy_json"])
        self.setup["attendance_summary"].attendance_days = Decimal("20.00")
        self.setup["attendance_summary"].payable_days = Decimal("20.00")
        self.setup["attendance_summary"].lop_days = Decimal("0.00")
        self.setup["attendance_summary"].save(update_fields=["attendance_days", "payable_days", "lop_days"])

        application = LeaveApplicationService.create_application(
            attrs={
                "contract": self.contract,
                "leave_type": leave_type,
                "start_date": self.period.period_start,
                "end_date": self.period.period_start + timedelta(days=2),
                "requested_days": "3.00",
                "reason": "LWP",
            },
            actor=self.setup["user"],
        )
        LeaveApprovalService.approve(application=application, approver=self.setup["user"], approved_days=Decimal("3.00"))

        from payroll.services import PayrollAttendanceEngine

        result = PayrollAttendanceEngine.evaluate(
            contract_payroll_profile=self.profile,
            payroll_period=self.period,
            structure_version=self.version,
            payroll_policy_snapshot=None,
            attendance_required=False,
        )

        self.assertEqual(result.unpaid_leave_days, Decimal("3.00"))
        self.assertEqual(result.lop_days, Decimal("3.00"))
        self.assertEqual(result.payable_days, Decimal("17.00"))

    def test_carry_forward_and_lapse_cap(self):
        leave_type, policy = self._create_leave_runtime(
            code="EL",
            name="Earned Leave",
            rule_json={"carry_forward": {"enabled": True, "max_days": 30}, "lapse": {"enabled": True}},
        )
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            contract=self.contract,
            leave_policy=policy,
            leave_type=leave_type,
            snapshot_date=date(2025, 3, 31),
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance=Decimal("40.00"),
            closing_balance=Decimal("40.00"),
        )

        result = LeaveBalanceService.apply_carry_forward(
            contract=self.contract,
            leave_type=leave_type,
            as_of_date=date(2025, 4, 1),
        )

        self.assertEqual(result["carried_forward_days"], "30.00")
        self.assertEqual(result["lapsed_days"], "10.00")
        self.assertEqual(
            LeaveBalanceService.get_balance_days(
                contract=self.contract,
                leave_type=leave_type,
                as_of_date=date(2025, 4, 1),
            ),
            Decimal("30.00"),
        )

    def test_fnf_leave_encashment_eligibility(self):
        leave_type, policy = self._create_leave_runtime(
            code="EL",
            name="Earned Leave",
            rule_json={"encashment": {"enabled": True, "max_days": 10}},
        )
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            contract=self.contract,
            leave_policy=policy,
            leave_type=leave_type,
            snapshot_date=date(2025, 4, 30),
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance=Decimal("12.00"),
            closing_balance=Decimal("12.00"),
        )
        self.version.calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
        }
        self.version.save(update_fields=["calculation_policy_json"])
        manual_input = self.setup["contract_profile"].input_snapshots.filter(
            input_type="MANUAL_PAYROLL_INPUT",
            payroll_period=self.period,
        ).first()
        if manual_input is None:
            from payroll.models import ContractPayrollInputSnapshot

            ContractPayrollInputSnapshot.objects.create(
                entity=self.setup["entity"],
                contract_payroll_profile=self.profile,
                payroll_period=self.period,
                input_type=ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
                input_json={"fixed_salary": "3000.00"},
                source=ContractPayrollInputSnapshot.SourceType.MANUAL,
                effective_from=self.period.period_start,
            )

        from payroll.services import PayrollFnFEngine

        settlement = PayrollFnFEngine.calculate_fnf(
            self.contract.id,
            separation_date=date(2025, 4, 30),
            inputs={},
        )

        leave_row = settlement.components.get(source_type="LEAVE_ENCASHMENT")
        self.assertEqual(leave_row.days, Decimal("10.00"))
        self.assertEqual(leave_row.amount, Decimal("1000.00"))

    def test_calendar_year_balance_period(self):
        _, policy = self._create_leave_runtime(code="CL", name="Calendar Leave", rule_json={"accrual_frequency": "yearly", "annual_quota": 12})
        policy.leave_year_type = LeavePolicy.LeaveYearType.CALENDAR_YEAR
        policy.save(update_fields=["leave_year_type"])

        window = LeaveYearService.current_leave_year(leave_policy=policy, anchor_date=date(2026, 5, 18))

        self.assertEqual(window.start_date, date(2026, 1, 1))
        self.assertEqual(window.end_date, date(2026, 12, 31))

    def test_financial_year_balance_period(self):
        _, policy = self._create_leave_runtime(code="CL", name="Financial Leave", rule_json={"accrual_frequency": "yearly", "annual_quota": 12})
        policy.leave_year_type = LeavePolicy.LeaveYearType.FINANCIAL_YEAR
        policy.save(update_fields=["leave_year_type"])

        window = LeaveYearService.current_leave_year(leave_policy=policy, anchor_date=date(2026, 5, 18))

        self.assertEqual(window.start_date, date(2026, 4, 1))
        self.assertEqual(window.end_date, date(2027, 3, 31))

    def test_custom_year_period(self):
        _, policy = self._create_leave_runtime(code="CL", name="Custom Leave", rule_json={"accrual_frequency": "yearly", "annual_quota": 12})
        policy.leave_year_type = LeavePolicy.LeaveYearType.CUSTOM_RANGE
        policy.year_start_month = 7
        policy.year_start_day = 1
        policy.year_end_month = 6
        policy.year_end_day = 30
        policy.save(update_fields=["leave_year_type", "year_start_month", "year_start_day", "year_end_month", "year_end_day"])

        window = LeaveYearService.current_leave_year(leave_policy=policy, anchor_date=date(2026, 5, 18))

        self.assertEqual(window.start_date, date(2025, 7, 1))
        self.assertEqual(window.end_date, date(2026, 6, 30))

    def test_accrual_uses_configured_leave_year(self):
        leave_type, policy = self._create_leave_runtime(
            code="CL",
            name="Casual Leave",
            rule_json={"accrual_frequency": "yearly", "annual_quota": 12},
        )
        policy.leave_year_type = LeavePolicy.LeaveYearType.CALENDAR_YEAR
        policy.save(update_fields=["leave_year_type"])

        first = LeaveBalanceService.accrue_for_period(contract=self.contract, leave_type=leave_type, as_of_date=date(2026, 2, 1))
        second = LeaveBalanceService.accrue_for_period(contract=self.contract, leave_type=leave_type, as_of_date=date(2026, 9, 1))

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(
            LeaveBalanceService.get_balance_days(contract=self.contract, leave_type=leave_type, as_of_date=date(2026, 12, 31)),
            Decimal("12.00"),
        )

    def test_yearly_quota_prorates_from_contract_join_month_within_calendar_year(self):
        leave_type, policy = self._create_leave_runtime(
            code="SL",
            name="Sick Leave",
            rule_json={"accrual_frequency": "yearly", "annual_quota": 12},
        )
        policy.leave_year_type = LeavePolicy.LeaveYearType.CALENDAR_YEAR
        policy.save(update_fields=["leave_year_type"])
        self.contract.start_date = date(2026, 4, 1)
        self.contract.payroll_effective_from = date(2026, 4, 1)
        self.contract.probation_end = date(2026, 4, 1)
        self.contract.save(update_fields=["start_date", "payroll_effective_from", "probation_end"])

        evaluation = LeaveRuleEngine.evaluate_leave_type(
            contract=self.contract,
            leave_type=leave_type,
            as_of_date=date(2026, 4, 1),
            leave_policy=policy,
        )

        self.assertEqual(evaluation.accrual_days, Decimal("9.00"))
        self.assertEqual(evaluation.trace["prorated_annual_quota"], "9.00")

    def test_carry_forward_uses_previous_configured_leave_year(self):
        leave_type, policy = self._create_leave_runtime(
            code="EL",
            name="Earned Leave",
            rule_json={"carry_forward": {"enabled": True, "max_days": 30}, "lapse": {"enabled": True}},
        )
        policy.leave_year_type = LeavePolicy.LeaveYearType.FINANCIAL_YEAR
        policy.save(update_fields=["leave_year_type"])
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            contract=self.contract,
            leave_policy=policy,
            leave_type=leave_type,
            snapshot_date=date(2026, 3, 31),
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance=Decimal("40.00"),
            closing_balance=Decimal("40.00"),
        )

        result = LeaveBalanceService.apply_carry_forward(contract=self.contract, leave_type=leave_type, as_of_date=date(2026, 4, 15))

        self.assertTrue(result["created"])
        self.assertEqual(result["carried_forward_days"], "30.00")
        self.assertEqual(
            LeaveBalanceService.get_balance_days(contract=self.contract, leave_type=leave_type, as_of_date=date(2026, 4, 15)),
            Decimal("30.00"),
        )

    def test_lapse_uses_configured_leave_year_end(self):
        leave_type, policy = self._create_leave_runtime(
            code="CL",
            name="Casual Leave",
            rule_json={"lapse": {"enabled": True}},
        )
        policy.leave_year_type = LeavePolicy.LeaveYearType.CALENDAR_YEAR
        policy.save(update_fields=["leave_year_type"])
        ContractLeaveBalanceSnapshot.objects.create(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            contract=self.contract,
            leave_policy=policy,
            leave_type=leave_type,
            snapshot_date=date(2026, 12, 31),
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            opening_balance=Decimal("5.00"),
            closing_balance=Decimal("5.00"),
        )

        result = LeaveBalanceService.apply_carry_forward(contract=self.contract, leave_type=leave_type, as_of_date=date(2027, 1, 5))

        self.assertTrue(result["created"])
        self.assertEqual(result["lapsed_days"], "5.00")
        self.assertEqual(
            LeaveBalanceService.get_balance_days(contract=self.contract, leave_type=leave_type, as_of_date=date(2027, 1, 5)),
            Decimal("0.00"),
        )
