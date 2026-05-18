from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from hrms.services import LeavePayrollImpactService
from hrms.services.attendance_capture_service import AttendanceCaptureService
from payroll.models import (
    ContractAttendanceAdjustment,
    ContractPayrollProfile,
    EntityPayrollPolicy,
    PayrollPeriod,
    SalaryStructureVersion,
)
from payroll.services.contract_attendance_adjustment_service import ContractAttendanceAdjustmentService
from payroll.services.contract_attendance_summary_service import ContractAttendanceSummaryService
from payroll.services.entity_payroll_policy_service import EntityPayrollPolicyService
from payroll.services.payroll_policy_rule_service import PayrollPolicyRuleService

ZERO = Decimal("0.00")
Q4 = Decimal("0.0001")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return ZERO


def _period_day_count(start_date: date, end_date: date) -> Decimal:
    return Decimal(max((end_date - start_date).days + 1, 1))


class PayrollAttendanceEngineError(ValueError):
    pass


@dataclass(frozen=True)
class PayrollAttendanceResult:
    proration_method: str
    basis_label: str | None
    base_days: Decimal
    calendar_days: Decimal
    working_days: Decimal
    attendance_days: Decimal
    payable_days: Decimal
    lop_days: Decimal
    paid_leave_days: Decimal
    unpaid_leave_days: Decimal
    half_days: Decimal
    overtime_hours: Decimal
    late_instances: int
    late_deduction_days: Decimal
    adjustment_impact: dict[str, Any]
    missing_attendance_behavior: str
    warnings: list[str]
    proration_factor: Decimal
    summary_snapshot: dict[str, Any]

    def to_trace(self) -> dict[str, Any]:
        return {
            "proration_method": self.proration_method,
            "basis_label": self.basis_label,
            "base_days": str(self.base_days),
            "calendar_days": str(self.calendar_days),
            "working_days": str(self.working_days),
            "attendance_days": str(self.attendance_days),
            "payable_days": str(self.payable_days),
            "lop_days": str(self.lop_days),
            "paid_leave_days": str(self.paid_leave_days),
            "unpaid_leave_days": str(self.unpaid_leave_days),
            "half_days": str(self.half_days),
            "overtime_hours": str(self.overtime_hours),
            "late_instances": self.late_instances,
            "late_deduction_days": str(self.late_deduction_days),
            "adjustments_applied": self.adjustment_impact.get("adjustments_applied", []),
            "manual_payable_override": self.adjustment_impact.get("manual_payable_override"),
            "proration_factor": str(self.proration_factor),
            "missing_attendance_behavior": self.missing_attendance_behavior,
            "warnings": list(self.warnings),
        }


class PayrollAttendanceEngine:
    SUPPORTED_METHODS = {
        "CALENDAR_DAYS",
        "WORKING_DAYS",
        "FIXED_26_DAYS",
        "FIXED_30_DAYS",
        "ACTUAL_ATTENDANCE",
        "MANUAL_PAYABLE_DAYS",
    }

    @staticmethod
    def _context_label(
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
        structure_version: SalaryStructureVersion | None,
    ) -> str:
        return (
            f"contract={contract_payroll_profile.hrms_contract.contract_code}, "
            f"employee={contract_payroll_profile.employee_code or contract_payroll_profile.id}, "
            f"period={payroll_period.code}, "
            f"salary_structure_version={getattr(structure_version, 'id', None)}"
        )

    @classmethod
    def _error(
        cls,
        message: str,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
        structure_version: SalaryStructureVersion | None,
    ) -> PayrollAttendanceEngineError:
        return PayrollAttendanceEngineError(
            f"{message}. {cls._context_label(contract_payroll_profile=contract_payroll_profile, payroll_period=payroll_period, structure_version=structure_version)}"
        )

    @staticmethod
    def _normalize_rule_map(rules) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for rule in rules:
            key = str(rule.rule_key or "").strip().lower()
            if key and key not in normalized:
                normalized[key] = rule.rule_value_json or {}
        return normalized

    @staticmethod
    def _coalesce_mapping_value(mapping: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in mapping and mapping.get(key) not in (None, ""):
                return mapping.get(key)
        return None

    @classmethod
    def _resolve_policy(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
        payroll_policy_snapshot: dict[str, Any] | None,
    ) -> EntityPayrollPolicy | None:
        policy_id = payroll_policy_snapshot.get("id") if isinstance(payroll_policy_snapshot, dict) else None
        if policy_id:
            try:
                return EntityPayrollPolicy.objects.filter(pk=policy_id, is_active=True).first()
            except Exception:
                pass
        return EntityPayrollPolicyService.resolve_active_policy(
            entity_id=contract_payroll_profile.entity_id,
            payroll_date=payroll_period.period_end,
            pay_frequency=contract_payroll_profile.pay_frequency or "MONTHLY",
        )

    @classmethod
    def _resolve_method(
        cls,
        *,
        policy: EntityPayrollPolicy | None,
        structure_version: SalaryStructureVersion | None,
        payroll_period: PayrollPeriod,
    ) -> tuple[str, dict[str, Any], str | None]:
        rules = {}
        if policy is not None:
            rules = cls._normalize_rule_map(
                PayrollPolicyRuleService.resolve_active_rules(policy=policy, rule_date=payroll_period.period_end)
            )

        method_value = cls._coalesce_mapping_value(
            rules.get("proration_method", {}),
            "method",
            "value",
            "proration_method",
        )
        if method_value:
            method = str(method_value).strip().upper()
            if method not in cls.SUPPORTED_METHODS:
                raise PayrollAttendanceEngineError(f"Unknown attendance proration method '{method}'")
            return method, rules, "policy_rule"

        policy_json = getattr(structure_version, "calculation_policy_json", None) or {}
        legacy_basis = str(policy_json.get("proration_basis") or "").strip().lower()
        legacy_map = {
            "calendar_days": "CALENDAR_DAYS",
            "attendance_days": "ACTUAL_ATTENDANCE",
            "payable_days": "MANUAL_PAYABLE_DAYS",
        }
        if legacy_basis in legacy_map:
            return legacy_map[legacy_basis], rules, legacy_basis

        compatibility_map = {
            getattr(EntityPayrollPolicy.LOPCalculationMethod, "CALENDAR_DAYS", ""): "CALENDAR_DAYS",
            getattr(EntityPayrollPolicy.LOPCalculationMethod, "WORKING_DAYS", ""): "WORKING_DAYS",
            getattr(EntityPayrollPolicy.LOPCalculationMethod, "ATTENDANCE_DAYS", ""): "ACTUAL_ATTENDANCE",
        }
        policy_method = compatibility_map.get(getattr(policy, "lop_calculation_method", ""))
        if policy_method:
            return policy_method, rules, getattr(policy, "lop_calculation_method", None)
        return "ACTUAL_ATTENDANCE", rules, legacy_basis or getattr(policy, "lop_calculation_method", None)

    @classmethod
    def evaluate(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
        structure_version: SalaryStructureVersion | None,
        payroll_policy_snapshot: dict[str, Any] | None,
        attendance_required: bool,
    ) -> PayrollAttendanceResult:
        context_kwargs = {
            "contract_payroll_profile": contract_payroll_profile,
            "payroll_period": payroll_period,
            "structure_version": structure_version,
        }
        policy = cls._resolve_policy(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
            payroll_policy_snapshot=payroll_policy_snapshot,
        )
        method, rule_map, basis_label = cls._resolve_method(
            policy=policy,
            structure_version=structure_version,
            payroll_period=payroll_period,
        )

        behavior = str(
            cls._coalesce_mapping_value(
                rule_map.get("missing_attendance_behavior", {}),
                "behavior",
                "value",
                "missing_attendance_behavior",
            )
            or ("BLOCK" if attendance_required else "WARN")
        ).strip().upper()
        if behavior not in {"BLOCK", "WARN", "ALLOW"}:
            behavior = "WARN"

        summary = ContractAttendanceSummaryService.resolve_summary(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
        )
        if summary is not None and not AttendanceCaptureService.summary_is_payroll_eligible(
            contract=contract_payroll_profile.hrms_contract,
            payroll_period=payroll_period,
            summary=summary,
        ):
            summary = None
        calendar_days = _period_day_count(payroll_period.period_start, payroll_period.period_end)
        warnings: list[str] = []
        if summary is None:
            if behavior == "BLOCK":
                raise cls._error("Missing approved/submitted attendance summary for required payroll calculation", **context_kwargs)
            warnings.append("Attendance summary missing; defaulting payable and attendance values to full base days.")
            working_days = calendar_days
            attendance_days = calendar_days
            payable_days = calendar_days
            lop_days = ZERO
            paid_leave_days = ZERO
            unpaid_leave_days = ZERO
            half_days = ZERO
            overtime_hours = ZERO
            late_instances = 0
            late_deduction_days = ZERO
            summary_snapshot: dict[str, Any] = {}
            adjustments = []
        else:
            weekly_off_days = _decimal(summary.weekly_off_days)
            holiday_days = _decimal(summary.holiday_days)
            working_days = max(calendar_days - weekly_off_days - holiday_days, ZERO)
            attendance_days = _decimal(summary.attendance_days)
            payable_days = _decimal(summary.payable_days)
            lop_days = _decimal(summary.lop_days)
            half_days = _decimal(summary.half_days)
            overtime_hours = _decimal(summary.overtime_hours)
            late_instances = int(summary.late_count or 0)
            metadata = summary.metadata or {}
            paid_leave_days = _decimal(
                metadata.get("paid_leave_days")
                or metadata.get("approved_paid_leave_days")
                or metadata.get("leave_days_paid")
            )
            unpaid_leave_days = _decimal(
                metadata.get("unpaid_leave_days")
                or metadata.get("approved_unpaid_leave_days")
                or metadata.get("leave_days_unpaid")
            )
            late_deduction_days = _decimal(
                metadata.get("late_deduction_days")
                or metadata.get("late_penalty_days")
            )
            summary_snapshot = {
                "summary_id": str(summary.id),
                "approval_status": summary.approval_status,
                "source": summary.source,
                "weekly_off_days": str(weekly_off_days),
                "holiday_days": str(holiday_days),
                "metadata": metadata,
            }
            adjustments = list(
                ContractAttendanceAdjustmentService.list_approved_adjustments(
                    contract_payroll_profile=contract_payroll_profile,
                    payroll_period=payroll_period,
                )
            )

        leave_impact_applied = bool(summary and (summary.metadata or {}).get("leave_impact_applied"))
        leave_impact = (
            {"paid_leave_days": "0", "unpaid_leave_days": "0", "lop_days": "0", "items": []}
            if leave_impact_applied
            else LeavePayrollImpactService.summarize_period(
                contract=contract_payroll_profile.hrms_contract,
                payroll_period=payroll_period,
            )
        )
        leave_paid_days = _decimal(leave_impact.get("paid_leave_days"))
        leave_unpaid_days = _decimal(leave_impact.get("unpaid_leave_days"))
        if leave_paid_days > ZERO:
            paid_leave_days += leave_paid_days
            payable_days += leave_paid_days
        if leave_unpaid_days > ZERO:
            unpaid_leave_days += leave_unpaid_days
            lop_days += leave_unpaid_days
            payable_days -= leave_unpaid_days
        if leave_impact.get("items"):
            summary_snapshot["leave_impact"] = leave_impact

        manual_payable_override: str | None = None
        adjustments_applied: list[dict[str, Any]] = []
        for adjustment in adjustments:
            value = _decimal(adjustment.adjustment_value)
            if value == ZERO:
                continue
            metadata = adjustment.metadata or {}
            entry = {
                "adjustment_id": str(adjustment.id),
                "type": adjustment.adjustment_type,
                "value": str(value),
                "remarks": adjustment.remarks,
                "metadata": metadata,
            }
            if adjustment.adjustment_type == ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY:
                if metadata.get("override") is True or str(metadata.get("mode", "")).strip().lower() == "override":
                    payable_days = value
                    manual_payable_override = str(value)
                    entry["impact"] = "manual_payable_day_override"
                else:
                    payable_days += value
                    entry["impact"] = "payable_day_adjustment"
                if metadata.get("leave_kind") == "paid":
                    paid_leave_days += max(value, ZERO)
                if metadata.get("leave_kind") == "unpaid":
                    unpaid_leave_days += abs(min(value, ZERO))
            elif adjustment.adjustment_type == ContractAttendanceAdjustment.AdjustmentType.LOP:
                lop_days += value
                payable_days -= value
                if metadata.get("leave_kind") == "unpaid" or metadata.get("leave_adjustment"):
                    unpaid_leave_days += max(value, ZERO)
                entry["impact"] = "lop_adjustment"
            elif adjustment.adjustment_type == ContractAttendanceAdjustment.AdjustmentType.OVERTIME:
                overtime_hours += value
                entry["impact"] = "overtime_adjustment"
            elif adjustment.adjustment_type == ContractAttendanceAdjustment.AdjustmentType.HALF_DAY:
                half_days += value
                payable_days -= value
                entry["impact"] = "half_day_adjustment"
            elif adjustment.adjustment_type == ContractAttendanceAdjustment.AdjustmentType.LATE_DEDUCTION:
                if metadata.get("unit") == "days":
                    late_deduction_days += value
                else:
                    try:
                        late_instances += int(value)
                    except Exception:
                        raise cls._error("Late deduction adjustment must be numeric", **context_kwargs)
                payable_days -= value if metadata.get("unit") == "days" else ZERO
                entry["impact"] = "late_deduction_adjustment"
            else:
                raise cls._error(f"Unsupported attendance adjustment type {adjustment.adjustment_type}", **context_kwargs)
            adjustments_applied.append(entry)

        late_days_per_instance = _decimal(
            cls._coalesce_mapping_value(
                rule_map.get("late_deduction_days_per_instance", {}),
                "days",
                "value",
                "late_deduction_days_per_instance",
            )
        )
        if late_instances > 0 and late_days_per_instance > ZERO:
            derived_late_days = _decimal(late_instances) * late_days_per_instance
            late_deduction_days += derived_late_days
            payable_days -= derived_late_days
            adjustments_applied.append(
                {
                    "adjustment_id": None,
                    "type": "POLICY_LATE_DEDUCTION",
                    "value": str(derived_late_days),
                    "impact": "policy_late_deduction_days",
                    "metadata": {"late_instances": late_instances, "days_per_instance": str(late_days_per_instance)},
                    "remarks": "",
                }
            )

        for label, value in (
            ("attendance_days", attendance_days),
            ("payable_days", payable_days),
            ("lop_days", lop_days),
            ("paid_leave_days", paid_leave_days),
            ("unpaid_leave_days", unpaid_leave_days),
            ("half_days", half_days),
            ("overtime_hours", overtime_hours),
            ("late_deduction_days", late_deduction_days),
        ):
            if value < ZERO:
                raise cls._error(f"Negative attendance metric {label} is not allowed", **context_kwargs)

        if method == "CALENDAR_DAYS":
            base_days = calendar_days
            numerator = payable_days
        elif method == "WORKING_DAYS":
            base_days = working_days if working_days > ZERO else calendar_days
            numerator = payable_days
        elif method == "FIXED_26_DAYS":
            base_days = Decimal("26.00")
            numerator = payable_days
        elif method == "FIXED_30_DAYS":
            base_days = Decimal("30.00")
            numerator = payable_days
        elif method == "ACTUAL_ATTENDANCE":
            base_days = calendar_days
            numerator = attendance_days
        elif method == "MANUAL_PAYABLE_DAYS":
            configured_base = _decimal(
                cls._coalesce_mapping_value(
                    rule_map.get("manual_payable_days_base", {}),
                    "base_days",
                    "value",
                    "manual_payable_days_base",
                )
            )
            base_days = configured_base if configured_base > ZERO else calendar_days
            numerator = payable_days
        else:
            raise cls._error(f"Unknown proration method {method}", **context_kwargs)

        if base_days <= ZERO:
            raise cls._error("Attendance proration base days must be positive", **context_kwargs)

        allow_payable_days_exceed_base = str(
            cls._coalesce_mapping_value(
                rule_map.get("allow_payable_days_exceed_base", {}),
                "value",
                "allow",
                "allow_payable_days_exceed_base",
            )
            or ""
        ).strip().lower() in {"1", "true", "yes", "y", "on"}

        if numerator > base_days and not allow_payable_days_exceed_base:
            raise cls._error(
                f"Computed payable/attendance numerator {numerator} exceeds base days {base_days}",
                **context_kwargs,
            )

        bounded_numerator = numerator if allow_payable_days_exceed_base else min(max(numerator, ZERO), base_days)
        proration_factor = (bounded_numerator / base_days).quantize(Q4, rounding=ROUND_HALF_UP)
        return PayrollAttendanceResult(
            proration_method=method,
            basis_label=basis_label,
            base_days=base_days,
            calendar_days=calendar_days,
            working_days=working_days,
            attendance_days=attendance_days,
            payable_days=payable_days,
            lop_days=lop_days,
            paid_leave_days=paid_leave_days,
            unpaid_leave_days=unpaid_leave_days,
            half_days=half_days,
            overtime_hours=overtime_hours,
            late_instances=late_instances,
            late_deduction_days=late_deduction_days,
            adjustment_impact={
                "adjustments_applied": adjustments_applied,
                "manual_payable_override": manual_payable_override,
            },
            missing_attendance_behavior=behavior,
            warnings=warnings,
            proration_factor=proration_factor,
            summary_snapshot=summary_snapshot,
        )
