from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from payroll.models import ContractAttendanceAdjustment, ContractAttendanceSummary
from payroll.tests.factories import PayrollFactory


class ContractAttendanceModelTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.hrms_employee = PayrollFactory.hrms_employee(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            user=self.setup["user"],
        )
        self.contract = PayrollFactory.hrms_contract(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee=self.hrms_employee,
        )
        self.contract_payroll_profile = PayrollFactory.contract_payroll_profile(
            entity=self.setup["entity"],
            hrms_contract=self.contract,
        )

    def test_create_valid_summary(self):
        summary = PayrollFactory.contract_attendance_summary(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
            attendance_days="25.50",
            payable_days="24.50",
            lop_days="1.00",
            overtime_hours="3.50",
            approval_status=ContractAttendanceSummary.ApprovalStatus.SUBMITTED,
        )

        self.assertEqual(summary.entity, self.setup["entity"])
        self.assertEqual(summary.attendance_days, Decimal("25.50"))
        self.assertEqual(summary.payable_days, Decimal("24.50"))
        self.assertEqual(summary.overtime_hours, Decimal("3.50"))

    def test_block_duplicate_active_summary(self):
        PayrollFactory.contract_attendance_summary(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
        )

        duplicate = ContractAttendanceSummary(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
            attendance_days=Decimal("26.00"),
            payable_days=Decimal("26.00"),
            lop_days=Decimal("0.00"),
            weekly_off_days=Decimal("4.00"),
            holiday_days=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            late_count=0,
            half_days=Decimal("0.00"),
            source=ContractAttendanceSummary.Source.MANUAL,
            approval_status=ContractAttendanceSummary.ApprovalStatus.DRAFT,
            is_active=True,
        )

        with self.assertRaises((ValidationError, IntegrityError)):
            duplicate.full_clean()
            duplicate.save()

    def test_block_summary_entity_mismatch(self):
        other_scope = PayrollFactory.entity_scope()

        summary = ContractAttendanceSummary(
            entity=other_scope["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
            attendance_days=Decimal("26.00"),
            payable_days=Decimal("26.00"),
            lop_days=Decimal("0.00"),
            weekly_off_days=Decimal("4.00"),
            holiday_days=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            late_count=0,
            half_days=Decimal("0.00"),
            source=ContractAttendanceSummary.Source.MANUAL,
            approval_status=ContractAttendanceSummary.ApprovalStatus.DRAFT,
        )

        with self.assertRaises(ValidationError):
            summary.full_clean()

    def test_block_negative_days(self):
        summary = ContractAttendanceSummary(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
            attendance_days=Decimal("-1.00"),
            payable_days=Decimal("26.00"),
            lop_days=Decimal("0.00"),
            weekly_off_days=Decimal("4.00"),
            holiday_days=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            late_count=0,
            half_days=Decimal("0.00"),
            source=ContractAttendanceSummary.Source.MANUAL,
            approval_status=ContractAttendanceSummary.ApprovalStatus.DRAFT,
        )

        with self.assertRaises(ValidationError):
            summary.full_clean()

    def test_create_valid_adjustment(self):
        adjustment = PayrollFactory.contract_attendance_adjustment(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
            adjustment_type=ContractAttendanceAdjustment.AdjustmentType.OVERTIME,
            adjustment_value="2.50",
            approval_status=ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
            remarks="Manual correction",
        )

        self.assertEqual(adjustment.adjustment_value, Decimal("2.50"))
        self.assertEqual(adjustment.adjustment_type, ContractAttendanceAdjustment.AdjustmentType.OVERTIME)

    def test_block_zero_adjustment_value(self):
        adjustment = ContractAttendanceAdjustment(
            entity=self.setup["entity"],
            contract_payroll_profile=self.contract_payroll_profile,
            payroll_period=self.setup["period"],
            adjustment_type=ContractAttendanceAdjustment.AdjustmentType.LOP,
            adjustment_value=Decimal("0.00"),
            approval_status=ContractAttendanceAdjustment.ApprovalStatus.DRAFT,
        )

        with self.assertRaises(ValidationError):
            adjustment.full_clean()
