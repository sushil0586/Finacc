from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from payroll.models import ContractAttendanceAdjustment, ContractAttendanceSummary
from payroll.services import (
    ContractAttendanceAdjustmentService,
    ContractAttendanceSummaryService,
    ContractPayrollProfileService,
)
from payroll.tests.factories import PayrollFactory


class ContractAttendanceServicesTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )
        self.period = PayrollFactory.payroll_period(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )

    def test_create_list_update_summary(self):
        summary = ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "attendance_days": Decimal("25.00"),
                "payable_days": Decimal("24.00"),
                "lop_days": Decimal("1.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("1.00"),
                "overtime_hours": Decimal("2.50"),
                "late_count": 2,
                "half_days": Decimal("0.50"),
                "source": ContractAttendanceSummary.Source.MANUAL,
                "approval_status": ContractAttendanceSummary.ApprovalStatus.DRAFT,
                "is_active": True,
            }
        )
        listed = list(
            ContractAttendanceSummaryService.list_summaries(
                entity_id=self.scope["entity"].id,
                contract_payroll_profile_id=str(self.profile.id),
                payroll_period_id=self.period.id,
            )
        )

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, summary.id)

        updated = ContractAttendanceSummaryService.create_or_update_summary(
            {
                "approval_status": ContractAttendanceSummary.ApprovalStatus.APPROVED,
                "payable_days": Decimal("25.00"),
            },
            instance=summary,
        )
        self.assertEqual(updated.approval_status, ContractAttendanceSummary.ApprovalStatus.APPROVED)
        self.assertEqual(updated.payable_days, Decimal("25.00"))

    def test_resolve_summary(self):
        submitted = ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "attendance_days": Decimal("25.00"),
                "payable_days": Decimal("24.00"),
                "lop_days": Decimal("1.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("1.00"),
                "overtime_hours": Decimal("0.00"),
                "late_count": 0,
                "half_days": Decimal("0.00"),
                "source": ContractAttendanceSummary.Source.IMPORT,
                "approval_status": ContractAttendanceSummary.ApprovalStatus.SUBMITTED,
                "is_active": False,
            }
        )
        approved = ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "attendance_days": Decimal("26.00"),
                "payable_days": Decimal("26.00"),
                "lop_days": Decimal("0.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("0.00"),
                "overtime_hours": Decimal("1.00"),
                "late_count": 0,
                "half_days": Decimal("0.00"),
                "source": ContractAttendanceSummary.Source.MANUAL,
                "approval_status": ContractAttendanceSummary.ApprovalStatus.APPROVED,
                "is_active": True,
            }
        )

        fetched = ContractAttendanceSummaryService.get_summary(
            contract_payroll_profile=self.profile,
            payroll_period=self.period,
        )
        resolved = ContractAttendanceSummaryService.resolve_summary(
            contract_payroll_profile=self.profile,
            payroll_period=self.period,
        )

        self.assertIn(fetched.id, {submitted.id, approved.id})
        self.assertEqual(resolved.id, approved.id)

    def test_create_list_adjustment(self):
        adjustment = ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.OVERTIME,
                "adjustment_value": Decimal("3.50"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.DRAFT,
                "remarks": "Pending review",
                "is_active": True,
            }
        )

        listed = list(
            ContractAttendanceAdjustmentService.list_adjustments(
                entity_id=self.scope["entity"].id,
                contract_payroll_profile_id=str(self.profile.id),
                payroll_period_id=self.period.id,
            )
        )
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, adjustment.id)

        updated = ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
                "remarks": "Approved correction",
            },
            instance=adjustment,
        )
        self.assertEqual(updated.approval_status, ContractAttendanceAdjustment.ApprovalStatus.APPROVED)
        self.assertEqual(updated.remarks, "Approved correction")

    def test_aggregate_approved_adjustments(self):
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY,
                "adjustment_value": Decimal("1.50"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
                "is_active": True,
            }
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY,
                "adjustment_value": Decimal("0.50"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
                "is_active": True,
            }
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.OVERTIME,
                "adjustment_value": Decimal("2.00"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
                "is_active": True,
            }
        )

        aggregate = ContractAttendanceAdjustmentService.aggregate_adjustments(
            contract_payroll_profile=self.profile,
            payroll_period=self.period,
        )

        self.assertEqual(aggregate["adjustment_count"], 3)
        self.assertEqual(aggregate["totals_by_type"][ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY], Decimal("2.00"))
        self.assertEqual(aggregate["totals_by_type"][ContractAttendanceAdjustment.AdjustmentType.OVERTIME], Decimal("2.00"))
        self.assertEqual(aggregate["total_adjustment_value"], Decimal("4.00"))

    def test_ignore_draft_rejected_adjustments(self):
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.LOP,
                "adjustment_value": Decimal("1.00"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.DRAFT,
                "is_active": True,
            }
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.HALF_DAY,
                "adjustment_value": Decimal("0.50"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.REJECTED,
                "is_active": True,
            }
        )
        approved = ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_period": self.period,
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.OVERTIME,
                "adjustment_value": Decimal("1.25"),
                "approval_status": ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
                "is_active": True,
            }
        )

        approved_items = list(
            ContractAttendanceAdjustmentService.list_approved_adjustments(
                contract_payroll_profile=self.profile,
                payroll_period=self.period,
            )
        )
        aggregate = ContractAttendanceAdjustmentService.aggregate_adjustments(
            contract_payroll_profile=self.profile,
            payroll_period=self.period,
        )

        self.assertEqual(len(approved_items), 1)
        self.assertEqual(approved_items[0].id, approved.id)
        self.assertEqual(aggregate["adjustment_count"], 1)
        self.assertEqual(aggregate["total_adjustment_value"], Decimal("1.25"))
