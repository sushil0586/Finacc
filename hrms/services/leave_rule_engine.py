from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db.models import Q

from hrms.models import HrEmploymentContract, LeavePolicy, LeavePolicyRule, LeaveType
from hrms.services.leave_year_service import LeaveYearService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def _decimal(value: Any, default: Decimal = ZERO2) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default)).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return default


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class LeaveRuleEvaluation:
    contract_id: str
    leave_policy_id: str | None
    leave_type_id: str
    as_of_date: date
    leave_year_start: date
    leave_year_end: date
    accrual_frequency: str
    accrual_days: Decimal
    attendance_percentage: Decimal
    attendance_threshold: Decimal
    attendance_condition_met: bool
    probation_completed: bool
    probation_condition_met: bool
    max_balance_cap: Decimal | None
    carry_forward_cap: Decimal | None
    lapse_enabled: bool
    encashment_enabled: bool
    encashment_cap: Decimal | None
    payroll_impact: str
    trace: dict[str, Any]


class LeaveRuleEngine:
    @staticmethod
    def _months_inclusive(start_date: date, end_date: date) -> int:
        if end_date < start_date:
            return 0
        return ((end_date.year - start_date.year) * 12) + (end_date.month - start_date.month) + 1

    @classmethod
    def resolve_entitlement_start_date(cls, *, contract: HrEmploymentContract, leave_year_start: date) -> date:
        contract_start = contract.payroll_effective_from or contract.start_date
        return max(contract_start, leave_year_start)

    @classmethod
    def resolve_prorated_annual_quota(
        cls,
        *,
        contract: HrEmploymentContract,
        leave_year_start: date,
        leave_year_end: date,
        annual_quota: Decimal,
    ) -> Decimal:
        annual_quota = _decimal(annual_quota)
        if annual_quota <= ZERO2:
            return ZERO2
        entitlement_start = cls.resolve_entitlement_start_date(contract=contract, leave_year_start=leave_year_start)
        if entitlement_start > leave_year_end:
            return ZERO2
        total_months = cls._months_inclusive(leave_year_start, leave_year_end)
        eligible_months = cls._months_inclusive(entitlement_start, leave_year_end)
        if total_months <= 0 or eligible_months <= 0:
            return ZERO2
        return ((annual_quota * Decimal(eligible_months)) / Decimal(total_months)).quantize(Q2, rounding=ROUND_HALF_UP)

    @staticmethod
    def resolve_leave_policy(*, contract: HrEmploymentContract, as_of_date: date) -> LeavePolicy | None:
        return (
            LeavePolicy.objects.filter(
                entity_id=contract.entity_id,
                is_active=True,
                status=LeavePolicy.Status.ACTIVE,
                deleted_at__isnull=True,
            )
            .filter(Q(subentity_id__isnull=True) | Q(subentity_id=contract.subentity_id))
            .filter(effective_from__lte=as_of_date)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
            .order_by("-subentity_id", "-is_default", "code")
            .first()
        )

    @staticmethod
    def resolve_active_rules(*, leave_policy: LeavePolicy, leave_type: LeaveType, as_of_date: date):
        return list(
            LeavePolicyRule.objects.filter(
                leave_policy=leave_policy,
                leave_type=leave_type,
                is_active=True,
                deleted_at__isnull=True,
                effective_from__lte=as_of_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
            .order_by("sequence", "rule_code")
        )

    @staticmethod
    def resolve_attendance_percentage(*, contract, payroll_period=None) -> Decimal:
        if payroll_period is None:
            return Decimal("100.00")
        from payroll.models import ContractAttendanceSummary

        contract_payroll_profile = getattr(contract, "payroll_profiles", None)
        if contract_payroll_profile is None:
            return Decimal("100.00")
        active_profile = contract_payroll_profile.filter(is_active=True).order_by("-payroll_start_date").first()
        if active_profile is None:
            return Decimal("100.00")
        summary = (
            ContractAttendanceSummary.objects.filter(
                contract_payroll_profile=active_profile,
                payroll_period=payroll_period,
                is_active=True,
            )
            .exclude(approval_status=ContractAttendanceSummary.ApprovalStatus.REJECTED)
            .order_by("-updated_at", "-id")
            .first()
        )
        if summary is None:
            return Decimal("100.00")
        attendance_days = _decimal(summary.attendance_days)
        weekly_off_days = _decimal(summary.weekly_off_days)
        holiday_days = _decimal(summary.holiday_days)
        calendar_days = Decimal(max((payroll_period.period_end - payroll_period.period_start).days + 1, 1))
        working_days = max(calendar_days - weekly_off_days - holiday_days, Decimal("1.00"))
        return ((attendance_days / working_days) * Decimal("100.00")).quantize(Q2, rounding=ROUND_HALF_UP)

    @staticmethod
    def resolve_probation_completed(*, contract: HrEmploymentContract, as_of_date: date) -> bool:
        if contract.confirmation_date:
            return contract.confirmation_date <= as_of_date
        if contract.probation_end:
            return contract.probation_end <= as_of_date
        return True

    @classmethod
    def evaluate_leave_type(
        cls,
        *,
        contract: HrEmploymentContract,
        leave_type: LeaveType,
        as_of_date: date,
        payroll_period=None,
        leave_policy: LeavePolicy | None = None,
    ) -> LeaveRuleEvaluation:
        leave_policy = leave_policy or cls.resolve_leave_policy(contract=contract, as_of_date=as_of_date)
        leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        rules = cls.resolve_active_rules(leave_policy=leave_policy, leave_type=leave_type, as_of_date=as_of_date) if leave_policy else []

        merged_rule_json: dict[str, Any] = {}
        matched_rule_ids: list[str] = []
        for rule in rules:
            merged_rule_json = _deep_merge(merged_rule_json, rule.rule_json or {})
            matched_rule_ids.append(str(rule.id))

        conditions = merged_rule_json.get("conditions", {}) or {}
        carry_forward = merged_rule_json.get("carry_forward", {}) or {}
        lapse = merged_rule_json.get("lapse", {}) or {}
        encashment = merged_rule_json.get("encashment", {}) or {}
        payroll_impact = merged_rule_json.get("payroll_impact", {}) or {}
        max_balance = merged_rule_json.get("max_balance", {}) or {}

        attendance_percentage = cls.resolve_attendance_percentage(contract=contract, payroll_period=payroll_period)
        attendance_threshold = _decimal(
            conditions.get("attendance_percentage_gte", merged_rule_json.get("attendance_percentage_gte", "0"))
        )
        attendance_condition_met = attendance_percentage >= attendance_threshold if attendance_threshold > ZERO2 else True

        probation_completed = cls.resolve_probation_completed(contract=contract, as_of_date=as_of_date)
        requires_probation = bool(conditions.get("probation_completed", merged_rule_json.get("probation_completed", False)))
        probation_condition_met = probation_completed if requires_probation else True

        accrual_frequency = str(merged_rule_json.get("accrual_frequency", "") or "").strip().lower()
        accrual_days = ZERO2
        annual_quota = _decimal(merged_rule_json.get("annual_quota", "0"))
        prorated_annual_quota = ZERO2
        entitlement_start = cls.resolve_entitlement_start_date(contract=contract, leave_year_start=leave_year.start_date)
        if attendance_condition_met and probation_condition_met:
            if accrual_frequency == "monthly":
                accrual_days = _decimal(merged_rule_json.get("monthly_quota", "0"))
            elif accrual_frequency == "yearly":
                prorated_annual_quota = cls.resolve_prorated_annual_quota(
                    contract=contract,
                    leave_year_start=leave_year.start_date,
                    leave_year_end=leave_year.end_date,
                    annual_quota=annual_quota,
                )
                accrual_days = prorated_annual_quota

        max_balance_cap = _decimal(
            max_balance.get("max_days", merged_rule_json.get("max_balance_cap", "0"))
        )
        if max_balance_cap <= ZERO2:
            max_balance_cap = None

        carry_forward_cap = None
        if carry_forward.get("enabled"):
            carry_forward_cap_value = _decimal(carry_forward.get("max_days", "0"))
            carry_forward_cap = carry_forward_cap_value if carry_forward_cap_value > ZERO2 else None

        encashment_enabled = bool(encashment.get("enabled"))
        encashment_cap = None
        if encashment_enabled:
            encashment_cap_value = _decimal(encashment.get("max_days", "0"))
            encashment_cap = encashment_cap_value if encashment_cap_value > ZERO2 else None

        impact_kind = "paid" if leave_type.is_paid else "unpaid"
        if payroll_impact.get("force_unpaid") is True:
            impact_kind = "unpaid"

        return LeaveRuleEvaluation(
            contract_id=str(contract.id),
            leave_policy_id=str(leave_policy.id) if leave_policy else None,
            leave_type_id=str(leave_type.id),
            as_of_date=as_of_date,
            leave_year_start=leave_year.start_date,
            leave_year_end=leave_year.end_date,
            accrual_frequency=accrual_frequency,
            accrual_days=accrual_days,
            attendance_percentage=attendance_percentage,
            attendance_threshold=attendance_threshold,
            attendance_condition_met=attendance_condition_met,
            probation_completed=probation_completed,
            probation_condition_met=probation_condition_met,
            max_balance_cap=max_balance_cap,
            carry_forward_cap=carry_forward_cap,
            lapse_enabled=bool(lapse.get("enabled") or carry_forward.get("enabled")),
            encashment_enabled=encashment_enabled,
            encashment_cap=encashment_cap,
            payroll_impact=impact_kind,
            trace={
                "matched_rule_ids": matched_rule_ids,
                "leave_year_start": leave_year.start_date.isoformat(),
                "leave_year_end": leave_year.end_date.isoformat(),
                "merged_rule_json": merged_rule_json,
                "entitlement_start_date": entitlement_start.isoformat(),
                "annual_quota": str(annual_quota),
                "prorated_annual_quota": str(prorated_annual_quota),
                "attendance_percentage": str(attendance_percentage),
                "attendance_threshold": str(attendance_threshold),
                "attendance_condition_met": attendance_condition_met,
                "probation_completed": probation_completed,
                "probation_condition_met": probation_condition_met,
                "payroll_impact": impact_kind,
            },
        )
