from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from payroll.models import ContractAttendanceAdjustment
from payroll.services import (
    ContractAttendanceAdjustmentService,
    ContractAttendanceSummaryService,
    ContractPayrollProfileService,
    PayrollCalculationInputResolver,
)
from payroll.tests.factories import PayrollFactory


class ContractAttendanceResolverTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["profile"].employee_user = self.setup["user"]
        self.setup["profile"].save(update_fields=["employee_user"])
        self.hrms_employee = PayrollFactory.hrms_employee(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            user=self.setup["user"],
            employee_number=self.setup["profile"].employee_code,
        )
        self.contract = PayrollFactory.hrms_contract(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee=self.hrms_employee,
        )
        self.contract.payroll_effective_from = date(2025, 4, 1)
        self.contract.start_date = date(2025, 4, 1)
        self.contract.save(update_fields=["payroll_effective_from", "start_date", "updated_at"])
        self.contract_profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.setup["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "attendance_required": True,
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

    def _resolve(self):
        return PayrollCalculationInputResolver.resolve(
            contract_payroll_profile=self.contract_profile,
            salary_assignment=None,
            readiness_snapshot={},
            payroll_date=self.setup["period"].period_end,
            payroll_period=self.setup["period"],
        )

    def test_resolver_prefers_contract_summary(self):
        ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "attendance_days": Decimal("30.00"),
                "payable_days": Decimal("29.00"),
                "lop_days": Decimal("1.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("1.00"),
                "overtime_hours": Decimal("3.00"),
                "late_count": 2,
                "half_days": Decimal("0.50"),
                "source": "IMPORT",
                "approval_status": "APPROVED",
                "is_active": True,
            },
            instance=self.setup["attendance_summary"],
        )

        resolved = self._resolve()

        self.assertEqual(resolved.attendance_days, Decimal("30.00"))
        self.assertEqual(resolved.payable_days, Decimal("29.00"))
        self.assertEqual(resolved.lop_days, Decimal("1.00"))
        self.assertEqual(resolved.overtime_hours, Decimal("3.00"))
        self.assertEqual(resolved.late_count, 2)
        self.assertEqual(resolved.half_days, Decimal("0.50"))
        self.assertEqual(resolved.source_markers.get("attendance_source"), "contract_native")

    def test_resolver_applies_approved_adjustments(self):
        ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "attendance_days": Decimal("30.00"),
                "payable_days": Decimal("28.00"),
                "lop_days": Decimal("2.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("0.00"),
                "overtime_hours": Decimal("1.50"),
                "late_count": 1,
                "half_days": Decimal("0.50"),
                "source": "MANUAL",
                "approval_status": "APPROVED",
                "is_active": True,
            },
            instance=self.setup["attendance_summary"],
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY,
                "adjustment_value": Decimal("1.00"),
                "approval_status": "APPROVED",
                "is_active": True,
            }
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.OVERTIME,
                "adjustment_value": Decimal("2.00"),
                "approval_status": "APPROVED",
                "is_active": True,
            }
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.LATE_DEDUCTION,
                "adjustment_value": Decimal("2.00"),
                "approval_status": "APPROVED",
                "is_active": True,
            }
        )
        ContractAttendanceAdjustmentService.create_or_update_adjustment(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.HALF_DAY,
                "adjustment_value": Decimal("0.50"),
                "approval_status": "APPROVED",
                "is_active": True,
            }
        )

        resolved = self._resolve()

        self.assertEqual(resolved.payable_days, Decimal("29.00"))
        self.assertEqual(resolved.overtime_hours, Decimal("3.50"))
        self.assertEqual(resolved.late_count, 3)
        self.assertEqual(resolved.half_days, Decimal("1.00"))

    def test_resolver_ignores_draft_rejected_adjustments(self):
        ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "attendance_days": Decimal("30.00"),
                "payable_days": Decimal("28.00"),
                "lop_days": Decimal("2.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("0.00"),
                "overtime_hours": Decimal("1.50"),
                "late_count": 1,
                "half_days": Decimal("0.50"),
                "source": "MANUAL",
                "approval_status": "APPROVED",
                "is_active": True,
            },
            instance=self.setup["attendance_summary"],
        )
        for status in ("DRAFT", "REJECTED"):
            ContractAttendanceAdjustmentService.create_or_update_adjustment(
                {
                    "entity": self.setup["entity"],
                    "contract_payroll_profile": self.contract_profile,
                    "payroll_period": self.setup["period"],
                    "adjustment_type": ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY,
                    "adjustment_value": Decimal("1.00"),
                    "approval_status": status,
                    "is_active": True,
                }
            )

        resolved = self._resolve()

        self.assertEqual(resolved.payable_days, Decimal("28.00"))
        self.assertEqual(resolved.source_markers.get("attendance_source"), "contract_native")

    def test_resolver_returns_zeroed_attendance_when_no_contract_summary_exists(self):
        self.setup["attendance_summary"].is_active = False
        self.setup["attendance_summary"].save(update_fields=["is_active"])
        resolved = self._resolve()

        self.assertEqual(resolved.attendance_days, Decimal("0"))
        self.assertEqual(resolved.payable_days, Decimal("0"))
        self.assertEqual(resolved.lop_days, Decimal("0"))
        self.assertEqual(resolved.overtime_hours, Decimal("0"))
        self.assertEqual(resolved.late_count, 0)
        self.assertEqual(resolved.half_days, Decimal("0"))
        self.assertIsNone(resolved.source_markers.get("attendance_source"))

    def test_resolver_source_marker_is_correct(self):
        ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "attendance_days": Decimal("27.00"),
                "payable_days": Decimal("27.00"),
                "lop_days": Decimal("0.00"),
                "weekly_off_days": Decimal("4.00"),
                "holiday_days": Decimal("0.00"),
                "overtime_hours": Decimal("0.00"),
                "late_count": 0,
                "half_days": Decimal("0.00"),
                "source": "MANUAL",
                "approval_status": "APPROVED",
                "is_active": True,
            },
            instance=self.setup["attendance_summary"],
        )

        resolved = self._resolve()

        self.assertEqual(resolved.source_markers.get("attendance_source"), "contract_native")
        self.assertEqual(resolved.source_markers.get("attendance_snapshot"), "contract_native")
        self.assertEqual(resolved.source_markers.get("payable_days_snapshot"), "contract_native")
