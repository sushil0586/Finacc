from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.apps import apps
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from Authentication.models import User
from entity.notification_service import NotificationService
from hrms.models import (
    AttendanceApproval,
    AttendanceMonthlyClose,
    AttendancePolicy,
    DailyAttendance,
    HrEmploymentContract,
    LeaveApplication,
)
from hrms.services.hrms_runtime_policy_service import HrmsRuntimePolicyService

ZERO = Decimal("0.00")
ONE = Decimal("1.00")
HALF = Decimal("0.50")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return ZERO


def _daterange(start_date: date, end_date: date):
    cursor = start_date
    while cursor <= end_date:
        yield cursor
        cursor += timedelta(days=1)


@dataclass(frozen=True)
class AttendancePayrollRequirement:
    level: str
    policy_id: str | None
    policy_code: str | None


def _get_payroll_period_model():
    return apps.get_model("payroll", "PayrollPeriod")


def _get_contract_payroll_profile_model():
    return apps.get_model("payroll", "ContractPayrollProfile")


def _get_contract_attendance_summary_model():
    return apps.get_model("payroll", "ContractAttendanceSummary")


def _get_contract_attendance_summary_service():
    from payroll.services.contract_attendance_summary_service import ContractAttendanceSummaryService

    return ContractAttendanceSummaryService


class AttendanceCaptureService:
    PAYROLL_REQUIREMENT_NONE = "NONE"
    PAYROLL_REQUIREMENT_APPROVED = "APPROVED"
    PAYROLL_REQUIREMENT_CLOSED = "CLOSED"

    @staticmethod
    def _notification_users_for_approval(approval: AttendanceApproval, *extra_user_ids: int | None):
        user_ids: set[int] = set()
        for field_name in ("submitted_by_id", "approved_by_id", "rejected_by_id"):
            value = getattr(approval, field_name, None)
            if value:
                user_ids.add(int(value))
        linked_user_id = getattr(getattr(approval.contract, "employee", None), "linked_user_id", None)
        if linked_user_id:
            user_ids.add(int(linked_user_id))
        for value in extra_user_ids:
            if value:
                user_ids.add(int(value))
        return User.objects.filter(pk__in=sorted(user_ids))

    @staticmethod
    def _notification_users_for_monthly_close(monthly_close: AttendanceMonthlyClose, *extra_user_ids: int | None):
        user_ids: set[int] = set()
        for field_name in ("submitted_by_id", "approved_by_id", "closed_by_id", "reopened_by_id"):
            value = getattr(monthly_close, field_name, None)
            if value:
                user_ids.add(int(value))
        for value in extra_user_ids:
            if value:
                user_ids.add(int(value))
        return User.objects.filter(pk__in=sorted(user_ids))

    @staticmethod
    def list_daily_entries(
        *,
        entity_id: int,
        subentity_id: int | None = None,
        contract_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        queryset = DailyAttendance.objects.select_related(
            "contract",
            "contract__employee",
            "leave_application",
            "monthly_close",
            "import_batch",
        ).filter(entity_id=entity_id, deleted_at__isnull=True)
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        if contract_id:
            queryset = queryset.filter(contract_id=contract_id)
        if start_date:
            queryset = queryset.filter(attendance_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(attendance_date__lte=end_date)
        return queryset.order_by("attendance_date", "contract__contract_code", "created_at")

    @classmethod
    def _resolve_payroll_period_for_date(cls, *, contract: HrEmploymentContract, attendance_date: date):
        PayrollPeriod = _get_payroll_period_model()
        return (
            PayrollPeriod.objects.filter(
                entity_id=contract.entity_id,
                subentity_id=contract.subentity_id,
                period_start__lte=attendance_date,
                period_end__gte=attendance_date,
            )
            .order_by("-period_start", "-id")
            .first()
        )

    @classmethod
    def _resolve_monthly_close(
        cls,
        *,
        entity_id: int,
        subentity_id: int | None,
        payroll_period,
    ) -> AttendanceMonthlyClose | None:
        if payroll_period is None:
            return None
        return AttendanceMonthlyClose.objects.filter(
            entity_id=entity_id,
            subentity_id=subentity_id,
            payroll_period_code=payroll_period.code,
            deleted_at__isnull=True,
        ).first()

    @classmethod
    def _ensure_not_closed(cls, *, contract: HrEmploymentContract, attendance_date: date):
        payroll_period = cls._resolve_payroll_period_for_date(contract=contract, attendance_date=attendance_date)
        monthly_close = cls._resolve_monthly_close(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            payroll_period=payroll_period,
        )
        if monthly_close and monthly_close.status == AttendanceMonthlyClose.Status.CLOSED:
            raise ValueError({"attendance_date": ["Attendance month is already closed and cannot be edited."]})
        return payroll_period, monthly_close

    @staticmethod
    def _default_metrics_for_status(status_value: str) -> tuple[Decimal, Decimal, Decimal]:
        status_key = str(status_value or "").strip().lower()
        if status_key == DailyAttendance.AttendanceStatus.PRESENT:
            return ONE, ONE, ZERO
        if status_key == DailyAttendance.AttendanceStatus.ABSENT:
            return ZERO, ZERO, ONE
        if status_key == DailyAttendance.AttendanceStatus.HALF_DAY:
            return HALF, HALF, HALF
        if status_key in {DailyAttendance.AttendanceStatus.WEEKLY_OFF, DailyAttendance.AttendanceStatus.HOLIDAY}:
            return ZERO, ONE, ZERO
        if status_key == DailyAttendance.AttendanceStatus.LEAVE:
            return ZERO, ZERO, ZERO
        return ZERO, ZERO, ZERO

    @classmethod
    @transaction.atomic
    def upsert_daily_entry(
        cls,
        *,
        attrs: dict[str, Any],
        actor,
        instance: DailyAttendance | None = None,
    ) -> DailyAttendance:
        contract = attrs.get("contract") or getattr(instance, "contract", None)
        attendance_date = attrs.get("attendance_date") or getattr(instance, "attendance_date", None)
        if contract is None or attendance_date is None:
            raise ValueError({"detail": ["contract and attendance_date are required."]})
        payroll_period, monthly_close = cls._ensure_not_closed(contract=contract, attendance_date=attendance_date)

        entry = instance or DailyAttendance()
        for key, value in attrs.items():
            setattr(entry, key, value)
        entry.entity = contract.entity
        entry.subentity = getattr(contract, "subentity", None)
        entry.monthly_close = monthly_close
        if not attrs.get("attendance_fraction") and not attrs.get("payable_fraction") and not attrs.get("lop_fraction"):
            att_fraction, pay_fraction, lop_fraction = cls._default_metrics_for_status(entry.status)
            entry.attendance_fraction = att_fraction
            entry.payable_fraction = pay_fraction
            entry.lop_fraction = lop_fraction
        entry.updated_by = actor
        if not entry.pk:
            entry.created_by = actor
        try:
            entry.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        entry.save()
        if payroll_period:
            cls.generate_monthly_summary(contract=contract, payroll_period=payroll_period)
        return entry

    @classmethod
    @transaction.atomic
    def bulk_upsert_entries(
        cls,
        *,
        contract: HrEmploymentContract,
        rows: list[dict[str, Any]],
        actor,
        source: str = DailyAttendance.EntrySource.MANUAL,
    ) -> list[DailyAttendance]:
        items: list[DailyAttendance] = []
        touched_period_ids: set[str] = set()
        for payload in rows:
            attendance_date = payload.get("attendance_date")
            payroll_period, monthly_close = cls._ensure_not_closed(contract=contract, attendance_date=attendance_date)
            instance = DailyAttendance.objects.filter(contract=contract, attendance_date=attendance_date, deleted_at__isnull=True).first()
            attrs = {
                "contract": contract,
                "entity": contract.entity,
                "subentity": contract.subentity,
                "attendance_date": attendance_date,
                "status": payload.get("status", DailyAttendance.AttendanceStatus.PRESENT),
                "source": payload.get("source") or source,
                "overtime_hours": payload.get("overtime_hours", ZERO),
                "late_mark": payload.get("late_mark", False),
                "attendance_fraction": payload.get("attendance_fraction") or None,
                "payable_fraction": payload.get("payable_fraction") or None,
                "lop_fraction": payload.get("lop_fraction") or None,
                "remarks": payload.get("remarks", ""),
                "leave_application": payload.get("leave_application"),
                "import_batch": payload.get("import_batch"),
                "trace_json": payload.get("trace_json") or {},
                "monthly_close": monthly_close,
            }
            entry = cls.upsert_daily_entry(attrs=attrs, actor=actor, instance=instance)
            items.append(entry)
            if payroll_period:
                touched_period_ids.add(str(payroll_period.id))
        PayrollPeriod = _get_payroll_period_model()
        for period_id in touched_period_ids:
            payroll_period = PayrollPeriod.objects.get(pk=period_id)
            cls.generate_monthly_summary(contract=contract, payroll_period=payroll_period)
        return items

    @staticmethod
    def _resolve_contract_profile(*, contract: HrEmploymentContract, payroll_period):
        ContractPayrollProfile = _get_contract_payroll_profile_model()
        return (
            ContractPayrollProfile.objects.filter(
                hrms_contract=contract,
                entity_id=contract.entity_id,
                is_active=True,
                payroll_start_date__lte=payroll_period.period_end,
            )
            .filter(Q(payroll_end_date__isnull=True) | Q(payroll_end_date__gte=payroll_period.period_start))
            .order_by("-payroll_start_date", "-updated_at")
            .first()
        )

    @classmethod
    def _resolve_leave_days(cls, *, contract: HrEmploymentContract, payroll_period) -> dict[date, dict[str, Any]]:
        approved = (
            LeaveApplication.objects.select_related("leave_type")
            .filter(
                entity_id=contract.entity_id,
                contract=contract,
                status=LeaveApplication.Status.APPROVED,
                start_date__lte=payroll_period.period_end,
                end_date__gte=payroll_period.period_start,
                deleted_at__isnull=True,
            )
            .order_by("start_date", "created_at")
        )
        by_date: dict[date, dict[str, Any]] = {}
        for application in approved:
            start_date = max(application.start_date, payroll_period.period_start)
            end_date = min(application.end_date, payroll_period.period_end)
            covered_dates = list(_daterange(start_date, end_date))
            covered_count = Decimal(str(max(len(covered_dates), 1)))
            approved_per_day = _decimal(application.approved_days) / covered_count
            paid_per_day = _decimal(application.paid_days) / covered_count
            unpaid_per_day = _decimal(application.unpaid_days) / covered_count
            for entry_date in covered_dates:
                by_date[entry_date] = {
                    "application_id": str(application.id),
                    "approved_days": approved_per_day,
                    "paid_days": paid_per_day,
                    "unpaid_days": unpaid_per_day,
                    "leave_type_id": str(application.leave_type_id),
                    "leave_type_code": application.leave_type.code,
                    "leave_type_name": application.leave_type.name,
                    "is_paid": application.leave_type.is_paid,
                    "counts_towards_attendance": application.leave_type.counts_towards_attendance,
                }
        return by_date

    @classmethod
    def _compute_contract_summary(
        cls,
        *,
        contract: HrEmploymentContract,
        payroll_period,
    ) -> dict[str, Any]:
        rows = list(
            DailyAttendance.objects.filter(
                contract=contract,
                attendance_date__gte=payroll_period.period_start,
                attendance_date__lte=payroll_period.period_end,
                deleted_at__isnull=True,
            )
            .select_related("leave_application")
            .order_by("attendance_date", "created_at")
        )
        rows_by_date = {item.attendance_date: item for item in rows}
        leave_days = cls._resolve_leave_days(contract=contract, payroll_period=payroll_period)

        attendance_days = ZERO
        payable_days = ZERO
        lop_days = ZERO
        weekly_off_days = ZERO
        holiday_days = ZERO
        overtime_hours = ZERO
        late_count = 0
        half_days = ZERO
        paid_leave_days = ZERO
        unpaid_leave_days = ZERO
        used_dates: set[date] = set()
        trace_items: list[dict[str, Any]] = []

        for entry_date in _daterange(payroll_period.period_start, payroll_period.period_end):
            row = rows_by_date.get(entry_date)
            leave_info = leave_days.get(entry_date)
            if row is not None:
                attendance_days += _decimal(row.attendance_fraction)
                payable_days += _decimal(row.payable_fraction)
                lop_days += _decimal(row.lop_fraction)
                overtime_hours += _decimal(row.overtime_hours)
                if row.late_mark:
                    late_count += 1
                if row.status == DailyAttendance.AttendanceStatus.HALF_DAY:
                    half_days += HALF
                if row.status == DailyAttendance.AttendanceStatus.WEEKLY_OFF:
                    weekly_off_days += ONE
                if row.status == DailyAttendance.AttendanceStatus.HOLIDAY:
                    holiday_days += ONE
                if row.status == DailyAttendance.AttendanceStatus.LEAVE and not leave_info:
                    lop_days += ONE
                trace_items.append(
                    {
                        "date": entry_date.isoformat(),
                        "source": "daily_attendance",
                        "status": row.status,
                        "attendance_fraction": str(row.attendance_fraction),
                        "payable_fraction": str(row.payable_fraction),
                        "lop_fraction": str(row.lop_fraction),
                        "leave_application_id": str(row.leave_application_id) if row.leave_application_id else None,
                    }
                )
                used_dates.add(entry_date)
            if leave_info and (row is None or row.status in {DailyAttendance.AttendanceStatus.ABSENT, DailyAttendance.AttendanceStatus.LEAVE}):
                paid_leave_days += _decimal(leave_info["paid_days"])
                unpaid_leave_days += _decimal(leave_info["unpaid_days"])
                if leave_info.get("counts_towards_attendance"):
                    attendance_days += _decimal(leave_info["approved_days"])
                payable_days += _decimal(leave_info["paid_days"])
                lop_days += _decimal(leave_info["unpaid_days"])
                trace_items.append(
                    {
                        "date": entry_date.isoformat(),
                        "source": "approved_leave",
                        "leave_type_code": leave_info.get("leave_type_code"),
                        "paid_days": str(leave_info.get("paid_days")),
                        "unpaid_days": str(leave_info.get("unpaid_days")),
                        "counts_towards_attendance": bool(leave_info.get("counts_towards_attendance")),
                        "application_id": leave_info.get("application_id"),
                    }
                )
                used_dates.add(entry_date)

        covered_days = Decimal(str(len(used_dates)))
        monthly_close = cls._resolve_monthly_close(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            payroll_period=payroll_period,
        )
        approval = AttendanceApproval.objects.filter(
            contract=contract,
            payroll_period_code=payroll_period.code,
            deleted_at__isnull=True,
        ).first()
        return {
            "contract_id": str(contract.id),
            "contract_code": contract.contract_code,
            "employee_name": getattr(contract.employee, "display_name", ""),
            "attendance_days": attendance_days.quantize(HALF),
            "payable_days": payable_days.quantize(HALF),
            "lop_days": lop_days.quantize(HALF),
            "weekly_off_days": weekly_off_days.quantize(HALF),
            "holiday_days": holiday_days.quantize(HALF),
            "overtime_hours": overtime_hours.quantize(HALF),
            "late_count": late_count,
            "half_days": half_days.quantize(HALF),
            "paid_leave_days": paid_leave_days.quantize(HALF),
            "unpaid_leave_days": unpaid_leave_days.quantize(HALF),
            "covered_days": covered_days.quantize(HALF),
            "approval_status": approval.status if approval else AttendanceApproval.Status.DRAFT,
            "monthly_close_status": monthly_close.status if monthly_close else AttendanceMonthlyClose.Status.DRAFT,
            "trace_items": trace_items,
        }

    @classmethod
    @transaction.atomic
    def generate_monthly_summary(
        cls,
        *,
        contract: HrEmploymentContract,
        payroll_period,
    ) -> dict[str, Any]:
        summary_data = cls._compute_contract_summary(contract=contract, payroll_period=payroll_period)
        monthly_close = cls._resolve_monthly_close(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            payroll_period=payroll_period,
        )
        approval, _ = AttendanceApproval.objects.get_or_create(
            entity=contract.entity,
            subentity=contract.subentity,
            contract=contract,
            payroll_period_code=payroll_period.code,
            defaults={
                "period_start": payroll_period.period_start,
                "period_end": payroll_period.period_end,
                "monthly_close": monthly_close,
                "summary_json": {},
            },
        )
        approval.period_start = payroll_period.period_start
        approval.period_end = payroll_period.period_end
        approval.monthly_close = monthly_close
        approval.summary_json = {
            "attendance_days": str(summary_data["attendance_days"]),
            "payable_days": str(summary_data["payable_days"]),
            "lop_days": str(summary_data["lop_days"]),
            "weekly_off_days": str(summary_data["weekly_off_days"]),
            "holiday_days": str(summary_data["holiday_days"]),
            "overtime_hours": str(summary_data["overtime_hours"]),
            "late_count": summary_data["late_count"],
            "half_days": str(summary_data["half_days"]),
            "paid_leave_days": str(summary_data["paid_leave_days"]),
            "unpaid_leave_days": str(summary_data["unpaid_leave_days"]),
            "covered_days": str(summary_data["covered_days"]),
            "trace_items": summary_data["trace_items"],
        }
        approval.save(update_fields=["period_start", "period_end", "monthly_close", "summary_json", "updated_at"])

        contract_profile = cls._resolve_contract_profile(contract=contract, payroll_period=payroll_period)
        if contract_profile is not None:
            ContractAttendanceSummaryService = _get_contract_attendance_summary_service()
            ContractAttendanceSummary = _get_contract_attendance_summary_model()
            existing = ContractAttendanceSummaryService.get_summary(
                contract_payroll_profile=contract_profile,
                payroll_period=payroll_period,
            )
            metadata = {
                "attendance_capture_enabled": True,
                "leave_impact_applied": True,
                "paid_leave_days": str(summary_data["paid_leave_days"]),
                "unpaid_leave_days": str(summary_data["unpaid_leave_days"]),
                "attendance_approval_status": approval.status,
                "monthly_close_status": monthly_close.status if monthly_close else AttendanceMonthlyClose.Status.DRAFT,
                "trace_items": summary_data["trace_items"],
            }
            ContractAttendanceSummaryService.create_or_update_summary(
                {
                    "entity": contract.entity,
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": payroll_period,
                    "attendance_days": summary_data["attendance_days"],
                    "payable_days": summary_data["payable_days"],
                    "lop_days": summary_data["lop_days"],
                    "weekly_off_days": summary_data["weekly_off_days"],
                    "holiday_days": summary_data["holiday_days"],
                    "overtime_hours": summary_data["overtime_hours"],
                    "late_count": summary_data["late_count"],
                    "half_days": summary_data["half_days"],
                    "source": ContractAttendanceSummary.Source.ATTENDANCE_ENGINE,
                    "approval_status": {
                        AttendanceApproval.Status.DRAFT: ContractAttendanceSummary.ApprovalStatus.DRAFT,
                        AttendanceApproval.Status.SUBMITTED: ContractAttendanceSummary.ApprovalStatus.SUBMITTED,
                        AttendanceApproval.Status.APPROVED: ContractAttendanceSummary.ApprovalStatus.APPROVED,
                        AttendanceApproval.Status.REJECTED: ContractAttendanceSummary.ApprovalStatus.REJECTED,
                    }.get(approval.status, ContractAttendanceSummary.ApprovalStatus.DRAFT),
                    "metadata": metadata,
                    "is_active": True,
                },
                instance=existing,
            )
        return summary_data

    @classmethod
    def list_monthly_summaries(
        cls,
        *,
        entity_id: int,
        payroll_period,
        subentity_id: int | None = None,
        contract_id: str | None = None,
        employee_user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        queryset = HrEmploymentContract.objects.select_related("employee").filter(
            entity_id=entity_id,
            deleted_at__isnull=True,
        )
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        if contract_id:
            queryset = queryset.filter(pk=contract_id)
        if employee_user_id is not None:
            queryset = queryset.filter(employee__linked_user_id=employee_user_id)
        items: list[dict[str, Any]] = []
        for contract in queryset.order_by("contract_code"):
            items.append(cls.generate_monthly_summary(contract=contract, payroll_period=payroll_period))
        return items

    @classmethod
    def resolve_payroll_requirement(cls, *, contract: HrEmploymentContract) -> AttendancePayrollRequirement:
        runtime = HrmsRuntimePolicyService.resolve_runtime_setup(contract=contract)
        policy_id = runtime.get("attendance_policy_id")
        policy = AttendancePolicy.objects.filter(pk=policy_id).first() if policy_id else None
        policy_json = (policy.policy_json or {}) if policy else {}
        level = str(
            policy_json.get("payroll_attendance_requirement")
            or policy_json.get("payroll_attendance_status")
            or (
                cls.PAYROLL_REQUIREMENT_CLOSED
                if policy_json.get("payroll_requires_closed_attendance")
                else cls.PAYROLL_REQUIREMENT_APPROVED
                if policy_json.get("payroll_requires_approved_attendance")
                else cls.PAYROLL_REQUIREMENT_NONE
            )
        ).strip().upper()
        if level not in {cls.PAYROLL_REQUIREMENT_NONE, cls.PAYROLL_REQUIREMENT_APPROVED, cls.PAYROLL_REQUIREMENT_CLOSED}:
            level = cls.PAYROLL_REQUIREMENT_NONE
        return AttendancePayrollRequirement(
            level=level,
            policy_id=str(policy.id) if policy else None,
            policy_code=policy.code if policy else None,
        )

    @classmethod
    def summary_is_payroll_eligible(
        cls,
        *,
        contract: HrEmploymentContract,
        payroll_period,
        summary,
    ) -> bool:
        if summary is None:
            return False
        requirement = cls.resolve_payroll_requirement(contract=contract)
        if requirement.level == cls.PAYROLL_REQUIREMENT_NONE:
            return True
        close = cls._resolve_monthly_close(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            payroll_period=payroll_period,
        )
        approval = AttendanceApproval.objects.filter(
            contract=contract,
            payroll_period_code=payroll_period.code,
            deleted_at__isnull=True,
        ).first()
        if requirement.level == cls.PAYROLL_REQUIREMENT_APPROVED:
            return bool(approval and approval.status == AttendanceApproval.Status.APPROVED)
        if requirement.level == cls.PAYROLL_REQUIREMENT_CLOSED:
            return bool(close and close.status == AttendanceMonthlyClose.Status.CLOSED)
        return True

    @classmethod
    @transaction.atomic
    def submit_approval(cls, *, contract: HrEmploymentContract, payroll_period, actor) -> AttendanceApproval:
        cls.generate_monthly_summary(contract=contract, payroll_period=payroll_period)
        approval = AttendanceApproval.objects.get(
            contract=contract,
            payroll_period_code=payroll_period.code,
            deleted_at__isnull=True,
        )
        approval.status = AttendanceApproval.Status.SUBMITTED
        approval.submitted_at = timezone.now()
        approval.submitted_by = actor
        approval.updated_by = actor
        approval.save(update_fields=["status", "submitted_at", "submitted_by", "updated_by", "updated_at"])
        cls.generate_monthly_summary(contract=contract, payroll_period=payroll_period)
        NotificationService.emit(
            instance=approval,
            workflow_key="attendance_approval",
            event_code="ATTENDANCE_MONTH_SUBMITTED",
            title="Attendance Submitted",
            message=f"Attendance approval for {contract.contract_code} and period {payroll_period.code} was submitted.",
            users=cls._notification_users_for_approval(approval, getattr(actor, "id", None)),
            actor=actor,
            target_url="/hrms/attendance-approvals",
            payload={"payroll_period_code": payroll_period.code},
        )
        return approval

    @classmethod
    @transaction.atomic
    def approve_approval(cls, *, approval: AttendanceApproval, actor, review_note: str = "") -> AttendanceApproval:
        approval.status = AttendanceApproval.Status.APPROVED
        approval.approved_at = timezone.now()
        approval.approved_by = actor
        approval.review_note = review_note or ""
        approval.updated_by = actor
        approval.save(
            update_fields=["status", "approved_at", "approved_by", "review_note", "updated_by", "updated_at"]
        )
        payroll_period = _get_payroll_period_model().objects.filter(
            entity_id=approval.entity_id,
            subentity_id=approval.subentity_id,
            code=approval.payroll_period_code,
        ).first()
        if payroll_period is not None:
            cls.generate_monthly_summary(contract=approval.contract, payroll_period=payroll_period)
        NotificationService.emit(
            instance=approval,
            workflow_key="attendance_approval",
            event_code="ATTENDANCE_MONTH_APPROVED",
            title="Attendance Approved",
            message=f"Attendance approval for {approval.contract.contract_code} and period {approval.payroll_period_code} was approved.",
            users=cls._notification_users_for_approval(approval, getattr(actor, "id", None)),
            actor=actor,
            target_url="/hrms/attendance-approvals",
            payload={"payroll_period_code": approval.payroll_period_code},
        )
        return approval

    @classmethod
    @transaction.atomic
    def reject_approval(cls, *, approval: AttendanceApproval, actor, review_note: str = "") -> AttendanceApproval:
        approval.status = AttendanceApproval.Status.REJECTED
        approval.rejected_at = timezone.now()
        approval.rejected_by = actor
        approval.review_note = review_note or ""
        approval.updated_by = actor
        approval.save(
            update_fields=["status", "rejected_at", "rejected_by", "review_note", "updated_by", "updated_at"]
        )
        payroll_period = _get_payroll_period_model().objects.filter(
            entity_id=approval.entity_id,
            subentity_id=approval.subentity_id,
            code=approval.payroll_period_code,
        ).first()
        if payroll_period is not None:
            cls.generate_monthly_summary(contract=approval.contract, payroll_period=payroll_period)
        NotificationService.emit(
            instance=approval,
            workflow_key="attendance_approval",
            event_code="ATTENDANCE_MONTH_REJECTED",
            title="Attendance Rejected",
            message=f"Attendance approval for {approval.contract.contract_code} and period {approval.payroll_period_code} was rejected.",
            users=cls._notification_users_for_approval(approval, getattr(actor, "id", None)),
            actor=actor,
            target_url="/hrms/attendance-approvals",
            payload={"payroll_period_code": approval.payroll_period_code, "review_note": review_note},
        )
        return approval

    @classmethod
    @transaction.atomic
    def get_or_create_monthly_close(
        cls,
        *,
        entity_id: int,
        subentity_id: int | None,
        payroll_period,
    ) -> AttendanceMonthlyClose:
        runtime_policy = None
        sample_contract = (
            HrEmploymentContract.objects.filter(
                entity_id=entity_id,
                subentity_id=subentity_id,
                deleted_at__isnull=True,
            )
            .order_by("contract_code")
            .first()
        )
        if sample_contract is not None:
            runtime = HrmsRuntimePolicyService.resolve_runtime_setup(contract=sample_contract)
            runtime_policy = AttendancePolicy.objects.filter(pk=runtime.get("attendance_policy_id")).first()
        monthly_close, _ = AttendanceMonthlyClose.objects.get_or_create(
            entity_id=entity_id,
            subentity_id=subentity_id,
            payroll_period_code=payroll_period.code,
            defaults={
                "entity_id": entity_id,
                "subentity_id": subentity_id,
                "attendance_policy": runtime_policy,
                "period_start": payroll_period.period_start,
                "period_end": payroll_period.period_end,
            },
        )
        monthly_close.period_start = payroll_period.period_start
        monthly_close.period_end = payroll_period.period_end
        if runtime_policy and monthly_close.attendance_policy_id != runtime_policy.id:
            monthly_close.attendance_policy = runtime_policy
            monthly_close.save(update_fields=["attendance_policy", "period_start", "period_end", "updated_at"])
        elif monthly_close.period_start != payroll_period.period_start or monthly_close.period_end != payroll_period.period_end:
            monthly_close.save(update_fields=["period_start", "period_end", "updated_at"])
        return monthly_close

    @classmethod
    @transaction.atomic
    def submit_monthly_close(cls, *, monthly_close: AttendanceMonthlyClose, actor) -> AttendanceMonthlyClose:
        monthly_close.status = AttendanceMonthlyClose.Status.SUBMITTED
        monthly_close.submitted_at = timezone.now()
        monthly_close.submitted_by = actor
        monthly_close.updated_by = actor
        monthly_close.summary_json = cls._build_monthly_close_summary(monthly_close=monthly_close)
        monthly_close.save(
            update_fields=["status", "submitted_at", "submitted_by", "updated_by", "summary_json", "updated_at"]
        )
        NotificationService.emit(
            instance=monthly_close,
            workflow_key="attendance_monthly_close",
            event_code="ATTENDANCE_CLOSE_SUBMITTED",
            title="Attendance Close Submitted",
            message=f"Attendance monthly close for {monthly_close.payroll_period_code} was submitted.",
            users=cls._notification_users_for_monthly_close(monthly_close, getattr(actor, "id", None)),
            actor=actor,
            target_url="/hrms/attendance-monthly-closes",
            payload={"payroll_period_code": monthly_close.payroll_period_code},
        )
        return monthly_close

    @classmethod
    @transaction.atomic
    def approve_monthly_close(cls, *, monthly_close: AttendanceMonthlyClose, actor) -> AttendanceMonthlyClose:
        monthly_close.status = AttendanceMonthlyClose.Status.APPROVED
        monthly_close.approved_at = timezone.now()
        monthly_close.approved_by = actor
        monthly_close.updated_by = actor
        monthly_close.summary_json = cls._build_monthly_close_summary(monthly_close=monthly_close)
        monthly_close.save(
            update_fields=["status", "approved_at", "approved_by", "updated_by", "summary_json", "updated_at"]
        )
        NotificationService.emit(
            instance=monthly_close,
            workflow_key="attendance_monthly_close",
            event_code="ATTENDANCE_CLOSE_APPROVED",
            title="Attendance Close Approved",
            message=f"Attendance monthly close for {monthly_close.payroll_period_code} was approved.",
            users=cls._notification_users_for_monthly_close(monthly_close, getattr(actor, "id", None)),
            actor=actor,
            target_url="/hrms/attendance-monthly-closes",
            payload={"payroll_period_code": monthly_close.payroll_period_code},
        )
        return monthly_close

    @classmethod
    @transaction.atomic
    def close_monthly_close(cls, *, monthly_close: AttendanceMonthlyClose, actor, close_note: str = "") -> AttendanceMonthlyClose:
        monthly_close.status = AttendanceMonthlyClose.Status.CLOSED
        monthly_close.closed_at = timezone.now()
        monthly_close.closed_by = actor
        monthly_close.close_note = close_note or ""
        monthly_close.updated_by = actor
        monthly_close.summary_json = cls._build_monthly_close_summary(monthly_close=monthly_close)
        monthly_close.save(
            update_fields=["status", "closed_at", "closed_by", "close_note", "updated_by", "summary_json", "updated_at"]
        )
        DailyAttendance.objects.filter(
            contract__entity_id=monthly_close.entity_id,
            contract__subentity_id=monthly_close.subentity_id,
            attendance_date__gte=monthly_close.period_start,
            attendance_date__lte=monthly_close.period_end,
            deleted_at__isnull=True,
        ).update(monthly_close=monthly_close, updated_at=timezone.now())
        NotificationService.emit(
            instance=monthly_close,
            workflow_key="attendance_monthly_close",
            event_code="ATTENDANCE_CLOSE_CLOSED",
            title="Attendance Month Closed",
            message=f"Attendance monthly close for {monthly_close.payroll_period_code} was closed.",
            users=cls._notification_users_for_monthly_close(monthly_close, getattr(actor, "id", None)),
            actor=actor,
            target_url="/hrms/attendance-monthly-closes",
            payload={"payroll_period_code": monthly_close.payroll_period_code, "close_note": close_note},
        )
        return monthly_close

    @classmethod
    def _build_monthly_close_summary(cls, *, monthly_close: AttendanceMonthlyClose) -> dict[str, Any]:
        approvals = list(
            AttendanceApproval.objects.filter(
                entity_id=monthly_close.entity_id,
                subentity_id=monthly_close.subentity_id,
                payroll_period_code=monthly_close.payroll_period_code,
                deleted_at__isnull=True,
            )
        )
        counts = defaultdict(int)
        for item in approvals:
            counts[item.status] += 1
        return {
            "payroll_period_code": monthly_close.payroll_period_code,
            "period_start": monthly_close.period_start.isoformat(),
            "period_end": monthly_close.period_end.isoformat(),
            "approval_counts": dict(counts),
            "total_contracts": len(approvals),
            "closed_at": monthly_close.closed_at.isoformat() if monthly_close.closed_at else None,
        }
