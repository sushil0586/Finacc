from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from hrms.models import HrEmploymentContract, LeaveApplication
from hrms.services.leave_balance_service import LeaveBalanceService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def _overlap_days(*, start_date: date, end_date: date, period_start: date, period_end: date) -> Decimal:
    overlap_start = max(start_date, period_start)
    overlap_end = min(end_date, period_end)
    if overlap_end < overlap_start:
        return ZERO2
    return Decimal((overlap_end - overlap_start).days + 1).quantize(Q2, rounding=ROUND_HALF_UP)


class LeavePayrollImpactService:
    @classmethod
    def summarize_period(cls, *, contract: HrEmploymentContract, payroll_period) -> dict:
        paid_leave_days = ZERO2
        unpaid_leave_days = ZERO2
        items = []
        applications = (
            LeaveApplication.objects.select_related("leave_type")
            .filter(
                entity_id=contract.entity_id,
                contract=contract,
                status=LeaveApplication.Status.APPROVED,
                deleted_at__isnull=True,
                start_date__lte=payroll_period.period_end,
                end_date__gte=payroll_period.period_start,
            )
            .order_by("start_date", "id")
        )
        for application in applications:
            span_days = max((application.end_date - application.start_date).days + 1, 1)
            overlap_days = _overlap_days(
                start_date=application.start_date,
                end_date=application.end_date,
                period_start=payroll_period.period_start,
                period_end=payroll_period.period_end,
            )
            if overlap_days <= ZERO2:
                continue
            ratio = (overlap_days / Decimal(span_days)).quantize(Q2, rounding=ROUND_HALF_UP)
            paid_days = (application.paid_days * ratio).quantize(Q2, rounding=ROUND_HALF_UP)
            unpaid_days = (application.unpaid_days * ratio).quantize(Q2, rounding=ROUND_HALF_UP)
            paid_leave_days += paid_days
            unpaid_leave_days += unpaid_days
            items.append(
                {
                    "application_id": str(application.id),
                    "leave_type_code": application.leave_type.code,
                    "leave_type_name": application.leave_type.name,
                    "approved_days": str(application.approved_days),
                    "overlap_days": str(overlap_days),
                    "paid_days": str(paid_days),
                    "unpaid_days": str(unpaid_days),
                    "payroll_impact_json": application.payroll_impact_json or {},
                }
            )
        return {
            "paid_leave_days": str(paid_leave_days),
            "unpaid_leave_days": str(unpaid_leave_days),
            "lop_days": str(unpaid_leave_days),
            "items": items,
        }

    @classmethod
    def fnf_encashment_eligibility(cls, *, contract: HrEmploymentContract, as_of_date: date) -> dict:
        return LeaveBalanceService.get_encashment_eligibility(contract=contract, as_of_date=as_of_date)
