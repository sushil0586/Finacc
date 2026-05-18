from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from Authentication.models import User
from entity.models import Entity
from hrms.models import (
    AttendanceApproval,
    AttendanceMonthlyClose,
    AttendancePolicy,
    DailyAttendance,
    HrEmployee,
    HrEmploymentContract,
    LeaveApplication,
    LeaveType,
)
from hrms.services import AttendanceCaptureService
from payroll.models import ContractAttendanceSummary, ContractPayrollProfile, PayrollPeriod
from payroll.services.payroll_calculation_input_resolver import PayrollCalculationInputResolver
from payroll.tests.factories import PayrollFactory


class AttendanceCaptureServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.user: User = self.scope["user"]
        self.entity: Entity = self.scope["entity"]
        self.subentity = self.scope["subentity"]
        self.entityfin = self.scope["entityfinid"]

        self.employee = HrEmployee.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee_number="EMP-AT-01",
            legal_first_name="Aanya",
            legal_last_name="Iyer",
            display_name="Aanya Iyer",
            work_email="aanya@example.com",
            linked_user=self.user,
            created_by=self.user,
            updated_by=self.user,
        )
        self.contract = HrEmploymentContract.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            employee=self.employee,
            contract_code="CTR-AT-01",
            start_date=date(2026, 4, 1),
            payroll_effective_from=date(2026, 4, 1),
            status=HrEmploymentContract.ContractStatus.ACTIVE,
            is_payroll_eligible=True,
            created_by=self.user,
            updated_by=self.user,
        )
        self.contract_profile = ContractPayrollProfile.objects.create(
            entity=self.entity,
            hrms_contract=self.contract,
            payroll_start_date=date(2026, 4, 1),
            payroll_status=ContractPayrollProfile.PayrollStatus.ACTIVE,
            pay_frequency="MONTHLY",
            is_active=True,
        )
        self.payroll_period = PayrollPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            code="APR-2026",
            pay_frequency=PayrollPeriod.PayFrequency.MONTHLY,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
        )
        self.leave_type = LeaveType.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="EL",
            name="Earned Leave",
            category=LeaveType.Category.EARNED,
            is_paid=True,
            requires_balance=True,
            counts_towards_attendance=True,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_daily_attendance_saves_and_generates_contract_summary(self):
        entry = AttendanceCaptureService.upsert_daily_entry(
            attrs={
                "contract": self.contract,
                "attendance_date": date(2026, 4, 10),
                "status": DailyAttendance.AttendanceStatus.PRESENT,
                "late_mark": True,
                "overtime_hours": Decimal("2.00"),
                "remarks": "Manual attendance entry",
            },
            actor=self.user,
        )

        self.assertEqual(entry.source, DailyAttendance.EntrySource.MANUAL)
        summary = ContractAttendanceSummary.objects.get(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )
        self.assertEqual(summary.source, ContractAttendanceSummary.Source.ATTENDANCE_ENGINE)
        self.assertEqual(summary.attendance_days, Decimal("1.00"))
        self.assertEqual(summary.payable_days, Decimal("1.00"))
        self.assertEqual(summary.lop_days, Decimal("0.00"))
        self.assertEqual(summary.overtime_hours, Decimal("2.00"))
        self.assertEqual(summary.late_count, 1)

    def test_approved_leave_is_folded_into_monthly_summary(self):
        LeaveApplication.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            contract=self.contract,
            leave_type=self.leave_type,
            start_date=date(2026, 4, 11),
            end_date=date(2026, 4, 11),
            requested_days=Decimal("1.00"),
            approved_days=Decimal("1.00"),
            paid_days=Decimal("1.00"),
            unpaid_days=Decimal("0.00"),
            status=LeaveApplication.Status.APPROVED,
            applied_by=self.user,
            approved_by=self.user,
            created_by=self.user,
            updated_by=self.user,
        )

        summary_data = AttendanceCaptureService.generate_monthly_summary(
            contract=self.contract,
            payroll_period=self.payroll_period,
        )
        persisted = ContractAttendanceSummary.objects.get(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )

        self.assertEqual(summary_data["paid_leave_days"], Decimal("1.00"))
        self.assertEqual(summary_data["unpaid_leave_days"], Decimal("0.00"))
        self.assertEqual(persisted.payable_days, Decimal("1.00"))
        self.assertEqual(persisted.attendance_days, Decimal("1.00"))
        self.assertTrue(persisted.metadata["leave_impact_applied"])

    def test_monthly_summary_generation_aggregates_statuses(self):
        AttendanceCaptureService.bulk_upsert_entries(
            contract=self.contract,
            actor=self.user,
            rows=[
                {"attendance_date": date(2026, 4, 1), "status": DailyAttendance.AttendanceStatus.PRESENT},
                {"attendance_date": date(2026, 4, 2), "status": DailyAttendance.AttendanceStatus.HALF_DAY},
                {"attendance_date": date(2026, 4, 3), "status": DailyAttendance.AttendanceStatus.WEEKLY_OFF},
                {"attendance_date": date(2026, 4, 4), "status": DailyAttendance.AttendanceStatus.HOLIDAY},
                {"attendance_date": date(2026, 4, 5), "status": DailyAttendance.AttendanceStatus.ABSENT},
            ],
            source=DailyAttendance.EntrySource.MANUAL,
        )

        summary_data = AttendanceCaptureService.generate_monthly_summary(
            contract=self.contract,
            payroll_period=self.payroll_period,
        )

        self.assertEqual(summary_data["attendance_days"], Decimal("1.50"))
        self.assertEqual(summary_data["payable_days"], Decimal("3.50"))
        self.assertEqual(summary_data["lop_days"], Decimal("1.50"))
        self.assertEqual(summary_data["weekly_off_days"], Decimal("1.00"))
        self.assertEqual(summary_data["holiday_days"], Decimal("1.00"))
        self.assertEqual(summary_data["half_days"], Decimal("0.50"))

    def test_closed_month_blocks_daily_edits(self):
        AttendanceCaptureService.upsert_daily_entry(
            attrs={
                "contract": self.contract,
                "attendance_date": date(2026, 4, 12),
                "status": DailyAttendance.AttendanceStatus.PRESENT,
            },
            actor=self.user,
        )
        monthly_close = AttendanceCaptureService.get_or_create_monthly_close(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            payroll_period=self.payroll_period,
        )
        AttendanceCaptureService.close_monthly_close(monthly_close=monthly_close, actor=self.user, close_note="Closed")

        with self.assertRaisesMessage(ValueError, "Attendance month is already closed"):
            AttendanceCaptureService.upsert_daily_entry(
                attrs={
                    "contract": self.contract,
                    "attendance_date": date(2026, 4, 12),
                    "status": DailyAttendance.AttendanceStatus.ABSENT,
                },
                actor=self.user,
            )

    def test_payroll_summary_uses_closed_attendance_when_policy_requires_it(self):
        AttendancePolicy.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="ATT-CLOSE",
            name="Attendance Close Required",
            is_default=True,
            policy_json={"payroll_attendance_requirement": "CLOSED"},
            created_by=self.user,
            updated_by=self.user,
        )
        AttendanceCaptureService.upsert_daily_entry(
            attrs={
                "contract": self.contract,
                "attendance_date": date(2026, 4, 15),
                "status": DailyAttendance.AttendanceStatus.PRESENT,
            },
            actor=self.user,
        )
        summary = ContractAttendanceSummary.objects.get(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )

        before_close = PayrollCalculationInputResolver._build_contract_attendance_payload(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )
        self.assertEqual(before_close[0], {})
        self.assertFalse(
            AttendanceCaptureService.summary_is_payroll_eligible(
                contract=self.contract,
                payroll_period=self.payroll_period,
                summary=summary,
            )
        )

    def test_payroll_summary_uses_approved_attendance_when_policy_requires_it(self):
        AttendancePolicy.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="ATT-APPROVE",
            name="Attendance Approval Required",
            is_default=True,
            policy_json={"payroll_attendance_requirement": "APPROVED"},
            created_by=self.user,
            updated_by=self.user,
        )
        AttendanceCaptureService.upsert_daily_entry(
            attrs={
                "contract": self.contract,
                "attendance_date": date(2026, 4, 16),
                "status": DailyAttendance.AttendanceStatus.PRESENT,
            },
            actor=self.user,
        )
        summary = ContractAttendanceSummary.objects.get(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )
        approval = AttendanceCaptureService.submit_approval(
            contract=self.contract,
            payroll_period=self.payroll_period,
            actor=self.user,
        )
        summary.refresh_from_db()

        submitted_payload = PayrollCalculationInputResolver._build_contract_attendance_payload(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )
        self.assertEqual(approval.status, approval.Status.SUBMITTED)
        self.assertEqual(summary.approval_status, ContractAttendanceSummary.ApprovalStatus.SUBMITTED)
        self.assertEqual(summary.metadata["attendance_approval_status"], approval.Status.SUBMITTED)
        self.assertEqual(submitted_payload[0], {})
        self.assertFalse(
            AttendanceCaptureService.summary_is_payroll_eligible(
                contract=self.contract,
                payroll_period=self.payroll_period,
                summary=summary,
            )
        )

        approval = AttendanceCaptureService.approve_approval(approval=approval, actor=self.user, review_note="Approved")
        summary.refresh_from_db()
        approved_payload = PayrollCalculationInputResolver._build_contract_attendance_payload(
            contract_payroll_profile=self.contract_profile,
            payroll_period=self.payroll_period,
        )

        self.assertEqual(approval.status, approval.Status.APPROVED)
        self.assertEqual(summary.approval_status, ContractAttendanceSummary.ApprovalStatus.APPROVED)
        self.assertEqual(summary.metadata["attendance_approval_status"], approval.Status.APPROVED)
        self.assertEqual(approved_payload[0]["summary_id"], str(summary.id))
        self.assertEqual(approved_payload[2], Decimal("1.00"))
        self.assertTrue(
            AttendanceCaptureService.summary_is_payroll_eligible(
                contract=self.contract,
                payroll_period=self.payroll_period,
                summary=summary,
            )
        )

    def test_monthly_close_state_transitions_capture_approval_counts(self):
        AttendanceCaptureService.upsert_daily_entry(
            attrs={
                "contract": self.contract,
                "attendance_date": date(2026, 4, 18),
                "status": DailyAttendance.AttendanceStatus.PRESENT,
            },
            actor=self.user,
        )
        approval = AttendanceCaptureService.submit_approval(
            contract=self.contract,
            payroll_period=self.payroll_period,
            actor=self.user,
        )
        monthly_close = AttendanceCaptureService.get_or_create_monthly_close(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            payroll_period=self.payroll_period,
        )
        monthly_close = AttendanceCaptureService.submit_monthly_close(monthly_close=monthly_close, actor=self.user)
        self.assertEqual(monthly_close.status, AttendanceMonthlyClose.Status.SUBMITTED)
        self.assertEqual(
            monthly_close.summary_json["approval_counts"],
            {AttendanceApproval.Status.SUBMITTED: 1},
        )
        self.assertEqual(monthly_close.summary_json["total_contracts"], 1)

        monthly_close = AttendanceCaptureService.approve_monthly_close(monthly_close=monthly_close, actor=self.user)
        self.assertEqual(monthly_close.status, AttendanceMonthlyClose.Status.APPROVED)
        self.assertEqual(
            monthly_close.summary_json["approval_counts"],
            {AttendanceApproval.Status.SUBMITTED: 1},
        )

        approval = AttendanceCaptureService.reject_approval(approval=approval, actor=self.user, review_note="Needs review")
        monthly_close = AttendanceCaptureService.close_monthly_close(
            monthly_close=monthly_close,
            actor=self.user,
            close_note="Attendance closed",
        )

        self.assertEqual(approval.status, approval.Status.REJECTED)
        self.assertEqual(monthly_close.status, AttendanceMonthlyClose.Status.CLOSED)
        self.assertEqual(monthly_close.close_note, "Attendance closed")
        self.assertEqual(
            monthly_close.summary_json["approval_counts"],
            {AttendanceApproval.Status.REJECTED: 1},
        )
        self.assertEqual(monthly_close.summary_json["total_contracts"], 1)
