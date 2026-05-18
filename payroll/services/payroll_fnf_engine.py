from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction
from django.utils import timezone

from entity.approval_workflow_service import ApprovalWorkflowService
from entity.notification_service import NotificationService
from hrms.services import LeavePayrollImpactService
from hrms.models import HrEmploymentContract
from Authentication.models import User
from payroll.models import (
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    FnFSettlement,
    FnFSettlementComponent,
    PayrollComponent,
    PayrollPeriod,
    SalaryStructureLine,
)
from payroll.services.contract_payroll_profile_service import ContractPayrollProfileService
from payroll.services.contract_salary_assignment_service import ContractSalaryAssignmentService
from payroll.services.payroll_attendance_engine import PayrollAttendanceEngine, PayrollAttendanceResult
from payroll.services.payroll_calculation_input_resolver import PayrollCalculationInputResolver
from payroll.services.payroll_config_resolver import PayrollConfigResolver
from payroll.services.payroll_posting_service import PayrollPostingService
from payroll.services.payroll_run_service import PayrollCalculationError, PayrollRunService, PayrollRuntimeProfileSnapshot, q2

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


def _to_decimal(value: Any, default: Decimal = ZERO2) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except Exception:
        return default


def _q4(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.0000")


class PayrollFnFEngineError(ValueError):
    pass


class PayrollFnFEngine:
    ACTIVE_SETTLEMENT_STATUSES = {
        FnFSettlement.Status.DRAFT,
        FnFSettlement.Status.CALCULATED,
        FnFSettlement.Status.APPROVED,
        FnFSettlement.Status.POSTED,
    }
    ELIGIBLE_CONTRACT_STATUSES = {
        HrEmploymentContract.ContractStatus.ACTIVE,
        HrEmploymentContract.ContractStatus.SUSPENDED,
        HrEmploymentContract.ContractStatus.NOTICE,
        HrEmploymentContract.ContractStatus.TERMINATED,
    }

    @staticmethod
    def _notification_users_for_settlement(settlement: FnFSettlement, *extra_user_ids: int | None):
        user_ids: set[int] = set()
        for field_name in (
            "requested_by_id",
            "approved_by_id",
            "rejected_by_id",
            "posted_by_id",
            "paid_by_id",
            "cancelled_by_id",
            "locked_by_id",
        ):
            value = getattr(settlement, field_name, None)
            if value:
                user_ids.add(int(value))
        employee_user_id = settlement.contract_payroll_profile.employee_user_id
        if employee_user_id:
            user_ids.add(int(employee_user_id))
        for value in extra_user_ids:
            if value:
                user_ids.add(int(value))
        return User.objects.filter(pk__in=sorted(user_ids))

    @classmethod
    def _error(cls, message: str, *, contract: HrEmploymentContract | None = None, settlement: FnFSettlement | None = None) -> PayrollFnFEngineError:
        contract_code = getattr(contract, "contract_code", None) or getattr(getattr(settlement, "hrms_contract", None), "contract_code", None)
        suffix = f" contract={contract_code}" if contract_code else ""
        return PayrollFnFEngineError(f"{message}.{suffix}")

    @staticmethod
    def _normalize_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
        return dict(inputs or {})

    @staticmethod
    def _resolve_payroll_period(*, contract_payroll_profile: ContractPayrollProfile, separation_date: date) -> PayrollPeriod | None:
        return (
            PayrollPeriod.objects.filter(
                entity_id=contract_payroll_profile.entity_id,
                subentity_id=contract_payroll_profile.hrms_contract.subentity_id,
                pay_frequency=contract_payroll_profile.pay_frequency or PayrollPeriod.PayFrequency.MONTHLY,
                period_start__lte=separation_date,
                period_end__gte=separation_date,
            )
            .order_by("-period_start", "-id")
            .first()
        )

    @classmethod
    def _validate_contract(cls, contract: HrEmploymentContract, *, separation_date: date) -> None:
        if separation_date is None:
            raise cls._error("Separation date is required", contract=contract)
        if contract.status not in cls.ELIGIBLE_CONTRACT_STATUSES:
            raise cls._error("Contract must be active, suspended, notice-period, or terminated for FnF calculation", contract=contract)

    @classmethod
    def _resolve_profile_and_assignment(
        cls,
        *,
        contract: HrEmploymentContract,
        separation_date: date,
    ) -> tuple[ContractPayrollProfile, ContractSalaryStructureAssignment]:
        profile = ContractPayrollProfileService.resolve_contract_payroll_profile(contract, as_of_date=separation_date)
        if profile is None:
            raise cls._error("Missing active contract payroll profile for FnF settlement", contract=contract)
        assignment = ContractSalaryAssignmentService.get_active_assignment_for_payroll_date(
            contract_payroll_profile=profile,
            payroll_date=separation_date,
        )
        if assignment is None:
            raise cls._error("Missing active salary structure assignment for FnF settlement", contract=contract)
        return profile, assignment

    @classmethod
    def _build_runtime_profile_snapshot(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        salary_assignment: ContractSalaryStructureAssignment,
    ) -> PayrollRuntimeProfileSnapshot:
        salary_structure = getattr(salary_assignment, "salary_structure", None)
        salary_structure_version = getattr(salary_assignment, "salary_structure_version", None)
        ctc_annual = q2(getattr(salary_assignment, "ctc_amount", ZERO2) * Decimal("12.00"))
        return PayrollRuntimeProfileSnapshot(
            entity_id=contract_payroll_profile.entity_id,
            subentity_id=contract_payroll_profile.hrms_contract.subentity_id,
            employee_code=contract_payroll_profile.employee_code or "",
            full_name=contract_payroll_profile.employee_name or "",
            employee_user_id=contract_payroll_profile.employee_user_id,
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            salary_structure_version_id=getattr(salary_structure_version, "id", None),
            ctc_annual=ctc_annual,
            pay_frequency=contract_payroll_profile.pay_frequency or "MONTHLY",
            tax_regime=contract_payroll_profile.tax_regime or "",
            payment_account_id=contract_payroll_profile.bank_account_id,
        )

    @classmethod
    def _override_attendance_result(
        cls,
        *,
        attendance_result: PayrollAttendanceResult,
        payroll_period: PayrollPeriod,
        separation_date: date,
        inputs: dict[str, Any],
    ) -> PayrollAttendanceResult:
        cutoff_days = Decimal(max((separation_date - payroll_period.period_start).days + 1, 1))
        payable_days = _to_decimal(inputs.get("payable_days"), min(attendance_result.payable_days, cutoff_days))
        attendance_days = _to_decimal(inputs.get("attendance_days"), min(attendance_result.attendance_days, cutoff_days))
        lop_days = _to_decimal(inputs.get("lop_days"), attendance_result.lop_days)
        half_days = _to_decimal(inputs.get("half_days"), attendance_result.half_days)
        overtime_hours = _to_decimal(inputs.get("overtime_hours"), attendance_result.overtime_hours)
        paid_leave_days = _to_decimal(inputs.get("paid_leave_days"), attendance_result.paid_leave_days)
        unpaid_leave_days = _to_decimal(inputs.get("unpaid_leave_days"), attendance_result.unpaid_leave_days)
        late_instances = int(inputs.get("late_instances", attendance_result.late_instances or 0) or 0)
        late_deduction_days = _to_decimal(inputs.get("late_deduction_days"), attendance_result.late_deduction_days)
        numerator = attendance_days if attendance_result.proration_method == "ACTUAL_ATTENDANCE" else payable_days
        if attendance_result.base_days <= ZERO2:
            raise PayrollFnFEngineError("FnF attendance base days must be positive.")
        if numerator < ZERO2 or payable_days < ZERO2:
            raise PayrollFnFEngineError("FnF attendance inputs cannot be negative.")
        proration_factor = (min(max(numerator, ZERO2), attendance_result.base_days) / attendance_result.base_days).quantize(
            Q4,
            rounding=ROUND_HALF_UP,
        )
        return replace(
            attendance_result,
            attendance_days=attendance_days,
            payable_days=payable_days,
            lop_days=lop_days,
            half_days=half_days,
            overtime_hours=overtime_hours,
            paid_leave_days=paid_leave_days,
            unpaid_leave_days=unpaid_leave_days,
            late_instances=late_instances,
            late_deduction_days=late_deduction_days,
            proration_factor=proration_factor,
        )

    @staticmethod
    def _component_source_type(component: PayrollComponent | None) -> str:
        semantic = str(getattr(component, "semantic_code", "") or "").strip()
        code = str(getattr(component, "code", "") or "").upper()
        if semantic in {
            PayrollComponent.SemanticCode.PF_EMPLOYEE,
            PayrollComponent.SemanticCode.PF_EMPLOYER,
            PayrollComponent.SemanticCode.ESI_EMPLOYEE,
            PayrollComponent.SemanticCode.ESI_EMPLOYER,
            PayrollComponent.SemanticCode.PT,
            PayrollComponent.SemanticCode.LWF_EMPLOYEE,
            PayrollComponent.SemanticCode.LWF_EMPLOYER,
        }:
            return FnFSettlementComponent.SourceType.STATUTORY
        if semantic == PayrollComponent.SemanticCode.TDS:
            return FnFSettlementComponent.SourceType.TDS_HOOK
        if "BONUS" in code:
            return FnFSettlementComponent.SourceType.BONUS_PAYOUT
        if "INCENTIVE" in code:
            return FnFSettlementComponent.SourceType.INCENTIVE_PAYOUT
        return FnFSettlementComponent.SourceType.SALARY_LINE

    @classmethod
    def _create_component(
        cls,
        *,
        settlement: FnFSettlement,
        source_type: str,
        component: PayrollComponent | None,
        sequence: int,
        amount: Decimal,
        base_amount: Decimal = ZERO2,
        quantity: Decimal = ZERO2,
        days: Decimal = ZERO2,
        rate: Decimal = ZERO2,
        metadata: dict[str, Any] | None = None,
        calculation_trace: dict[str, Any] | None = None,
        source_structure_line: SalaryStructureLine | None = None,
        component_code: str = "",
        component_name: str = "",
        component_type: str = "",
        posting_behavior: str = "",
    ) -> FnFSettlementComponent:
        return FnFSettlementComponent.objects.create(
            settlement=settlement,
            component=component,
            source_structure_line=source_structure_line,
            source_type=source_type,
            component_code=component.code if component else component_code,
            component_name=component.name if component else component_name,
            component_type=component.component_type if component else component_type,
            posting_behavior=component.posting_behavior if component else posting_behavior,
            sequence=sequence,
            amount=q2(amount),
            base_amount=q2(base_amount),
            quantity=q2(quantity),
            days=q2(days),
            rate=_q4(rate),
            metadata=metadata or {},
            calculation_trace=calculation_trace or {},
        )

    @staticmethod
    def _daily_rate(*, salary_basis_amount: Decimal, attendance_result: PayrollAttendanceResult) -> Decimal:
        if attendance_result.base_days <= ZERO2:
            return ZERO2
        return _q4(q2(salary_basis_amount) / attendance_result.base_days)

    @classmethod
    def _build_notice_components(
        cls,
        *,
        settlement: FnFSettlement,
        salary_basis_amount: Decimal,
        attendance_result: PayrollAttendanceResult,
        inputs: dict[str, Any],
        sequence: int,
    ) -> tuple[Decimal, Decimal]:
        recovery_amount = ZERO2
        payout_amount = ZERO2
        daily_rate = cls._daily_rate(salary_basis_amount=salary_basis_amount, attendance_result=attendance_result)
        shortfall_days = _to_decimal(inputs.get("notice_recovery_days") or inputs.get("notice_shortfall_days"))
        payout_days = _to_decimal(inputs.get("notice_payout_days"))
        if shortfall_days > ZERO2:
            recovery_amount = q2(daily_rate * shortfall_days)
            cls._create_component(
                settlement=settlement,
                source_type=FnFSettlementComponent.SourceType.NOTICE_PAY_RECOVERY,
                component=None,
                sequence=sequence,
                amount=recovery_amount,
                base_amount=q2(salary_basis_amount),
                days=shortfall_days,
                rate=daily_rate,
                component_code="NOTICE_PAY_RECOVERY",
                component_name="Notice Pay Recovery",
                component_type=PayrollComponent.ComponentType.RECOVERY,
                posting_behavior=PayrollComponent.PostingBehavior.RECOVERY,
                calculation_trace={"formula": "daily_rate * shortfall_days", "daily_rate": str(daily_rate)},
            )
            sequence += 1
        if payout_days > ZERO2:
            payout_amount = q2(daily_rate * payout_days)
            cls._create_component(
                settlement=settlement,
                source_type=FnFSettlementComponent.SourceType.NOTICE_PAY_PAYOUT,
                component=None,
                sequence=sequence,
                amount=payout_amount,
                base_amount=q2(salary_basis_amount),
                days=payout_days,
                rate=daily_rate,
                component_code="NOTICE_PAY_PAYOUT",
                component_name="Notice Pay Payout",
                component_type=PayrollComponent.ComponentType.EARNING,
                posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
                calculation_trace={"formula": "daily_rate * payout_days", "daily_rate": str(daily_rate)},
            )
        return payout_amount, recovery_amount

    @classmethod
    def _build_hook_components(
        cls,
        *,
        settlement: FnFSettlement,
        salary_basis_amount: Decimal,
        attendance_result: PayrollAttendanceResult,
        inputs: dict[str, Any],
        sequence: int,
    ) -> dict[str, Decimal]:
        totals = {
            "earning": ZERO2,
            "deduction": ZERO2,
            "recovery": ZERO2,
            "reimbursement": ZERO2,
        }
        daily_rate = cls._daily_rate(salary_basis_amount=salary_basis_amount, attendance_result=attendance_result)
        encashment_eligibility = LeavePayrollImpactService.fnf_encashment_eligibility(
            contract=settlement.hrms_contract,
            as_of_date=settlement.last_working_day,
        )
        eligible_leave_days = _to_decimal(encashment_eligibility.get("eligible_days"))
        requested_leave_days = _to_decimal(inputs.get("leave_encashment_days"), eligible_leave_days)
        leave_days = min(requested_leave_days, eligible_leave_days) if eligible_leave_days > ZERO2 else ZERO2
        if leave_days > ZERO2:
            amount = q2(daily_rate * leave_days)
            cls._create_component(
                settlement=settlement,
                source_type=FnFSettlementComponent.SourceType.LEAVE_ENCASHMENT,
                component=None,
                sequence=sequence,
                amount=amount,
                base_amount=q2(salary_basis_amount),
                days=leave_days,
                rate=daily_rate,
                component_code="LEAVE_ENCASHMENT",
                component_name="Leave Encashment",
                component_type=PayrollComponent.ComponentType.EARNING,
                posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
                calculation_trace={
                    "formula": "daily_rate * leave_encashment_days",
                    "daily_rate": str(daily_rate),
                    "eligible_leave_days": str(eligible_leave_days),
                    "requested_leave_days": str(requested_leave_days),
                    "encashment_eligibility": encashment_eligibility,
                },
            )
            totals["earning"] += amount
            sequence += 1
        for key, source_type, code, name, bucket in (
            ("gratuity_amount", FnFSettlementComponent.SourceType.GRATUITY_HOOK, "GRATUITY_HOOK", "Gratuity Hook", "earning"),
            ("bonus_amount", FnFSettlementComponent.SourceType.BONUS_PAYOUT, "BONUS_PAYOUT", "Bonus Payout", "earning"),
            ("incentive_amount", FnFSettlementComponent.SourceType.INCENTIVE_PAYOUT, "INCENTIVE_PAYOUT", "Incentive Payout", "earning"),
            ("reimbursement_amount", FnFSettlementComponent.SourceType.REIMBURSEMENT_PAYABLE, "REIMBURSEMENT_PAYABLE", "Reimbursement Payable", "reimbursement"),
            ("loan_recovery_amount", FnFSettlementComponent.SourceType.LOAN_RECOVERY, "LOAN_RECOVERY", "Loan Recovery", "recovery"),
            ("advance_recovery_amount", FnFSettlementComponent.SourceType.ADVANCE_RECOVERY, "ADVANCE_RECOVERY", "Advance Recovery", "recovery"),
            ("asset_recovery_amount", FnFSettlementComponent.SourceType.ASSET_RECOVERY, "ASSET_RECOVERY", "Asset Recovery", "recovery"),
            ("final_tds_amount", FnFSettlementComponent.SourceType.TDS_HOOK, "FINAL_TDS_HOOK", "Final TDS Hook", "deduction"),
        ):
            amount = q2(inputs.get(key))
            if amount <= ZERO2:
                continue
            component_type = PayrollComponent.ComponentType.EARNING
            posting_behavior = PayrollComponent.PostingBehavior.GROSS_EARNING
            if bucket == "reimbursement":
                component_type = PayrollComponent.ComponentType.REIMBURSEMENT
                posting_behavior = PayrollComponent.PostingBehavior.REIMBURSEMENT
            elif bucket == "recovery":
                component_type = PayrollComponent.ComponentType.RECOVERY
                posting_behavior = PayrollComponent.PostingBehavior.RECOVERY
            elif bucket == "deduction":
                component_type = PayrollComponent.ComponentType.DEDUCTION
                posting_behavior = PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY
            cls._create_component(
                settlement=settlement,
                source_type=source_type,
                component=None,
                sequence=sequence,
                amount=amount,
                base_amount=amount,
                component_code=code,
                component_name=name,
                component_type=component_type,
                posting_behavior=posting_behavior,
                calculation_trace={"source": "fnf_input_hook", "limitation": "amount supplied explicitly"},
            )
            totals[bucket] += amount
            sequence += 1
        return totals

    @classmethod
    def _build_items_from_contract_native_sources(
        cls,
        *,
        settlement: FnFSettlement,
        calculation_input,
        salary_basis_amount: Decimal,
        sequence: int,
    ) -> dict[str, Decimal]:
        totals = {
            "earning": ZERO2,
            "deduction": ZERO2,
            "recovery": ZERO2,
            "reimbursement": ZERO2,
        }
        component_ids = {
            int(item.get("payroll_component_id") or item.get("component_id"))
            for item in [*calculation_input.recurring_items, *calculation_input.one_time_items]
            if item.get("payroll_component_id") or item.get("component_id")
        }
        components = {
            component.id: component
            for component in PayrollComponent.objects.filter(id__in=component_ids)
        }
        for item in [*calculation_input.recurring_items, *calculation_input.one_time_items]:
            component_ref = item.get("payroll_component_id") or item.get("component_id")
            if not component_ref:
                continue
            component = components.get(int(component_ref))
            if component is None:
                continue
            amount = q2(item.get("amount"))
            if amount <= ZERO2:
                percentage = q2(item.get("percentage"))
                if percentage > ZERO2:
                    amount = q2(q2(salary_basis_amount) * percentage / Decimal("100.00"))
            if amount <= ZERO2:
                continue
            source_type = cls._component_source_type(component)
            if component.component_type == component.ComponentType.REIMBURSEMENT:
                source_type = FnFSettlementComponent.SourceType.REIMBURSEMENT_PAYABLE
            elif component.component_type == component.ComponentType.RECOVERY:
                code = component.code.upper()
                if "LOAN" in code:
                    source_type = FnFSettlementComponent.SourceType.LOAN_RECOVERY
                elif "ADVANCE" in code:
                    source_type = FnFSettlementComponent.SourceType.ADVANCE_RECOVERY
            cls._create_component(
                settlement=settlement,
                source_type=source_type,
                component=component,
                sequence=sequence,
                amount=amount,
                base_amount=amount,
                quantity=_to_decimal(item.get("quantity")),
                metadata={"contract_native_item": item},
                calculation_trace={"source": "contract_native_item"},
            )
            sequence += 1
            if component.component_type == component.ComponentType.REIMBURSEMENT:
                totals["reimbursement"] += amount
            elif component.component_type == component.ComponentType.RECOVERY:
                totals["recovery"] += amount
            elif component.component_type == component.ComponentType.DEDUCTION:
                totals["deduction"] += amount
            else:
                totals["earning"] += amount
        return totals

    @classmethod
    def _calculate_components(
        cls,
        *,
        settlement: FnFSettlement,
        contract_payroll_profile: ContractPayrollProfile,
        salary_assignment: ContractSalaryStructureAssignment,
        payroll_period: PayrollPeriod,
        separation_date: date,
        inputs: dict[str, Any],
    ) -> FnFSettlement:
        calculation_input = PayrollCalculationInputResolver.resolve(
            contract_payroll_profile=contract_payroll_profile,
            salary_assignment=salary_assignment,
            readiness_snapshot=None,
            payroll_date=separation_date,
            payroll_period=payroll_period,
        )
        structure = calculation_input.salary_structure or salary_assignment.salary_structure
        structure_version = calculation_input.salary_structure_version or salary_assignment.salary_structure_version
        base_attendance = PayrollAttendanceEngine.evaluate(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
            structure_version=structure_version,
            payroll_policy_snapshot=calculation_input.payroll_policy_snapshot,
            attendance_required=bool(getattr(contract_payroll_profile, "attendance_required", False)),
        )
        attendance_result = cls._override_attendance_result(
            attendance_result=base_attendance,
            payroll_period=payroll_period,
            separation_date=inputs.get("last_working_day") or separation_date,
            inputs=inputs,
        )
        profile_snapshot = cls._build_runtime_profile_snapshot(
            contract_payroll_profile=contract_payroll_profile,
            salary_assignment=salary_assignment,
        )
        lines = list(
            SalaryStructureLine.objects.filter(
                salary_structure_version=structure_version,
                is_active=True,
            )
            .select_related("component", "basis_component")
            .order_by("sequence", "id")
        )
        component_map = {line.component_id: line.component for line in lines}
        structure_policy = structure_version.calculation_policy_json or {}
        salary_basis_amount = PayrollRunService._resolve_salary_basis_amount(
            profile=profile_snapshot,
            structure_version=structure_version,
            calculation_input=calculation_input,
        )
        ctc_annual = q2(salary_basis_amount * Decimal("12.00"))
        earning_total = ZERO2
        deduction_total = ZERO2
        recovery_total = ZERO2
        reimbursement_total = ZERO2
        resolved: dict[int, Decimal] = {}
        settlement.components.all().delete()
        sequence = 100
        for line in lines:
            proration_context = PayrollRunService._resolve_proration_context(
                structure_version=structure_version,
                line=line,
                attendance_result=attendance_result,
            )
            line_amount, line_trace = PayrollRunService._line_amount(
                line=line,
                ctc_annual=ctc_annual,
                resolved=resolved,
                profile=profile_snapshot,
                calculation_input=calculation_input,
                proration_context=proration_context,
                policy=structure_policy,
                salary_mode=str(structure_policy.get("salary_mode") or "ctc").lower(),
                salary_basis_amount=salary_basis_amount,
                current_earning_total=earning_total,
                component_map=component_map,
                attendance_result=attendance_result,
            )
            resolved[line.component_id] = line_amount
            source_type = cls._component_source_type(line.component)
            cls._create_component(
                settlement=settlement,
                source_type=source_type,
                component=line.component,
                source_structure_line=line,
                sequence=sequence,
                amount=line_amount,
                base_amount=_to_decimal(line_trace.get("before_proration_amount") or line_amount),
                days=attendance_result.payable_days if line.is_pro_rated else ZERO2,
                rate=_to_decimal(line.rate),
                metadata={"component_snapshot": {"semantic_code": getattr(line.component, "semantic_code", "")}},
                calculation_trace=line_trace,
            )
            sequence += 10
            if line.component.component_type == line.component.ComponentType.REIMBURSEMENT:
                reimbursement_total += line_amount
            elif line.component.component_type == line.component.ComponentType.RECOVERY:
                recovery_total += line_amount
            elif line.component.component_type == line.component.ComponentType.DEDUCTION:
                deduction_total += line_amount
            elif line.component.component_type == line.component.ComponentType.EMPLOYER_CONTRIBUTION:
                continue
            else:
                earning_total += line_amount

        item_totals = cls._build_items_from_contract_native_sources(
            settlement=settlement,
            calculation_input=calculation_input,
            salary_basis_amount=salary_basis_amount,
            sequence=sequence,
        )
        earning_total += item_totals["earning"]
        deduction_total += item_totals["deduction"]
        recovery_total += item_totals["recovery"]
        reimbursement_total += item_totals["reimbursement"]
        sequence += 200

        notice_payout, notice_recovery = cls._build_notice_components(
            settlement=settlement,
            salary_basis_amount=salary_basis_amount,
            attendance_result=attendance_result,
            inputs=inputs,
            sequence=sequence,
        )
        earning_total += notice_payout
        recovery_total += notice_recovery
        sequence += 50

        hook_totals = cls._build_hook_components(
            settlement=settlement,
            salary_basis_amount=salary_basis_amount,
            attendance_result=attendance_result,
            inputs=inputs,
            sequence=sequence,
        )
        earning_total += hook_totals["earning"]
        deduction_total += hook_totals["deduction"]
        recovery_total += hook_totals["recovery"]
        reimbursement_total += hook_totals["reimbursement"]

        gross_receivable = q2(earning_total + reimbursement_total)
        gross_deductions = q2(deduction_total + recovery_total)
        net_balance = q2(gross_receivable - gross_deductions)
        settlement.salary_structure = structure
        settlement.salary_structure_version = structure_version
        settlement.earned_amount = q2(earning_total)
        settlement.deduction_amount = q2(deduction_total)
        settlement.recovery_amount = q2(recovery_total)
        settlement.reimbursement_amount = q2(reimbursement_total)
        settlement.net_payable_amount = net_balance if net_balance > ZERO2 else ZERO2
        settlement.net_recoverable_amount = abs(net_balance) if net_balance < ZERO2 else ZERO2
        settlement.status = FnFSettlement.Status.CALCULATED
        settlement.calculation_payload = {
            "inputs": inputs,
            "attendance_trace": attendance_result.to_trace(),
            "contract_native_input": calculation_input.to_snapshot(),
        }
        settlement.settlement_snapshot = {
            "contract_id": str(contract_payroll_profile.hrms_contract_id),
            "contract_code": contract_payroll_profile.hrms_contract.contract_code,
            "employee_code": contract_payroll_profile.employee_code,
            "separation_date": str(separation_date),
            "last_working_day": str(inputs.get("last_working_day") or separation_date),
            "salary_basis_amount": str(salary_basis_amount),
            "structure_code": getattr(structure, "code", ""),
            "structure_version": getattr(structure_version, "version_no", None),
            "attendance_trace": attendance_result.to_trace(),
        }
        settlement.save(
            update_fields=[
                "salary_structure",
                "salary_structure_version",
                "earned_amount",
                "deduction_amount",
                "recovery_amount",
                "reimbursement_amount",
                "net_payable_amount",
                "net_recoverable_amount",
                "status",
                "calculation_payload",
                "settlement_snapshot",
                "updated_at",
            ]
        )
        return settlement

    @classmethod
    @transaction.atomic
    def calculate_fnf(
        cls,
        contract_id,
        separation_date: date,
        inputs: dict[str, Any] | None = None,
    ) -> FnFSettlement:
        contract = HrEmploymentContract.objects.select_related("employee").get(pk=contract_id)
        cls._validate_contract(contract, separation_date=separation_date)
        duplicate = FnFSettlement.objects.filter(
            hrms_contract=contract,
            status__in=cls.ACTIVE_SETTLEMENT_STATUSES,
        ).first()
        if duplicate:
            raise cls._error("Duplicate active FnF settlement already exists for this contract", contract=contract)
        contract_payroll_profile, salary_assignment = cls._resolve_profile_and_assignment(
            contract=contract,
            separation_date=separation_date,
        )
        payroll_period = cls._resolve_payroll_period(
            contract_payroll_profile=contract_payroll_profile,
            separation_date=separation_date,
        )
        if payroll_period is None:
            raise cls._error("Missing payroll period covering the separation date for FnF settlement", contract=contract)
        normalized_inputs = cls._normalize_inputs(inputs)
        settlement = FnFSettlement.objects.create(
            entity_id=contract.entity_id,
            entityfinid_id=payroll_period.entityfinid_id,
            subentity_id=contract.subentity_id,
            hrms_contract=contract,
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
            separation_date=separation_date,
            last_working_day=normalized_inputs.get("last_working_day") or separation_date,
            settlement_date=normalized_inputs.get("settlement_date") or timezone.localdate(),
            settlement_number="",
        )
        settlement.settlement_number = normalized_inputs.get("settlement_number") or f"FNF-{settlement.id}"
        settlement.save(update_fields=["settlement_number", "updated_at"])
        return cls._calculate_components(
            settlement=settlement,
            contract_payroll_profile=contract_payroll_profile,
            salary_assignment=salary_assignment,
            payroll_period=payroll_period,
            separation_date=separation_date,
            inputs=normalized_inputs,
        )

    @classmethod
    @transaction.atomic
    def recalculate_fnf(cls, settlement_id, inputs: dict[str, Any] | None = None) -> FnFSettlement:
        settlement = FnFSettlement.objects.select_related(
            "hrms_contract",
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_version",
            "payroll_period",
        ).get(pk=settlement_id)
        if settlement.status in {FnFSettlement.Status.APPROVED, FnFSettlement.Status.POSTED, FnFSettlement.Status.PAID} and not settlement.is_recalculation_unlocked:
            raise cls._error("Approved or finalized FnF settlement cannot be recalculated unless explicitly unlocked", settlement=settlement)
        contract = settlement.hrms_contract
        contract_payroll_profile, salary_assignment = cls._resolve_profile_and_assignment(
            contract=contract,
            separation_date=settlement.separation_date,
        )
        normalized_inputs = {
            **(settlement.calculation_payload.get("inputs") or {}),
            **cls._normalize_inputs(inputs),
        }
        return cls._calculate_components(
            settlement=settlement,
            contract_payroll_profile=contract_payroll_profile,
            salary_assignment=salary_assignment,
            payroll_period=settlement.payroll_period,
            separation_date=settlement.separation_date,
            inputs=normalized_inputs,
        )

    @classmethod
    @transaction.atomic
    def submit_fnf(cls, settlement_id, user_id: int | None = None, note: str = "") -> FnFSettlement:
        settlement = FnFSettlement.objects.get(pk=settlement_id)
        if settlement.status not in {FnFSettlement.Status.CALCULATED, FnFSettlement.Status.APPROVED}:
            raise cls._error("Only calculated FnF settlements can be submitted for approval", settlement=settlement)
        ApprovalWorkflowService.submit_for_approval(
            instance=settlement,
            workflow_key="fnf_settlement",
            actor_id=user_id,
            remarks=note,
            title=settlement.settlement_number or f"FNF-{settlement.id}",
        )
        settlement.requested_by_id = user_id
        settlement.requested_at = timezone.now()
        settlement.approval_note = note or settlement.approval_note
        settlement.save(update_fields=["requested_by", "requested_at", "approval_note", "updated_at"])
        return settlement

    @classmethod
    @transaction.atomic
    def approve_fnf(cls, settlement_id, user_id: int | None = None, note: str = "") -> FnFSettlement:
        settlement = FnFSettlement.objects.get(pk=settlement_id)
        if settlement.status != FnFSettlement.Status.CALCULATED:
            raise cls._error("Only calculated FnF settlements can be approved", settlement=settlement)
        if settlement.approval_status == FnFSettlement.ApprovalStatus.DRAFT:
            cls.submit_fnf(settlement_id, user_id=user_id, note=note)
        ApprovalWorkflowService.approve(
            instance=settlement,
            workflow_key="fnf_settlement",
            actor_id=user_id,
            remarks=note,
        )
        settlement.status = FnFSettlement.Status.APPROVED
        settlement.approved_by_id = user_id
        settlement.approved_at = timezone.now()
        settlement.approval_note = note or settlement.approval_note
        settlement.save(update_fields=["status", "approved_by", "approved_at", "approval_note", "updated_at"])
        return settlement

    @classmethod
    @transaction.atomic
    def reject_fnf(cls, settlement_id, user_id: int | None = None, note: str = "") -> FnFSettlement:
        settlement = FnFSettlement.objects.get(pk=settlement_id)
        ApprovalWorkflowService.reject(
            instance=settlement,
            workflow_key="fnf_settlement",
            actor_id=user_id,
            remarks=note,
        )
        settlement.rejected_by_id = user_id
        settlement.rejected_at = timezone.now()
        settlement.approval_note = note or settlement.approval_note
        settlement.save(update_fields=["rejected_by", "rejected_at", "approval_note", "updated_at"])
        return settlement

    @classmethod
    @transaction.atomic
    def mark_posted(cls, settlement_id, post_reference: str = "", user_id: int | None = None) -> FnFSettlement:
        settlement = FnFSettlement.objects.get(pk=settlement_id)
        if settlement.status != FnFSettlement.Status.APPROVED:
            raise cls._error("Only approved FnF settlements can be marked posted", settlement=settlement)
        entry = PayrollPostingService.post_fnf(settlement, user_id=user_id or 0)
        settlement.status = FnFSettlement.Status.POSTED
        settlement.post_reference = post_reference or entry.voucher_no or str(entry.id)
        settlement.posted_by_id = user_id
        settlement.posted_at = timezone.now()
        settlement.save(update_fields=["status", "post_reference", "posted_by", "posted_at", "updated_at"])
        return settlement

    @classmethod
    @transaction.atomic
    def mark_paid(cls, settlement_id, payment_reference: str = "", user_id: int | None = None) -> FnFSettlement:
        settlement = FnFSettlement.objects.get(pk=settlement_id)
        if settlement.status not in {FnFSettlement.Status.APPROVED, FnFSettlement.Status.POSTED}:
            raise cls._error("Only approved or posted FnF settlements can be marked paid", settlement=settlement)
        if settlement.approval_status not in {
            FnFSettlement.ApprovalStatus.APPROVED,
            FnFSettlement.ApprovalStatus.LOCKED,
        }:
            raise cls._error("FnF settlement must be approval-cleared before payment", settlement=settlement)
        settlement.status = FnFSettlement.Status.PAID
        settlement.payment_reference = payment_reference or settlement.payment_reference
        settlement.paid_by_id = user_id
        settlement.paid_at = timezone.now()
        settlement.save(update_fields=["status", "payment_reference", "paid_by", "paid_at", "updated_at"])
        NotificationService.emit(
            instance=settlement,
            workflow_key="fnf_settlement",
            event_code="FNF_SETTLEMENT_PAID",
            title="FnF Settlement Paid",
            message=f"FnF settlement {settlement.settlement_number or settlement.id} was marked paid.",
            users=cls._notification_users_for_settlement(settlement, user_id),
            actor=User.objects.filter(pk=user_id).first() if user_id else None,
            target_url=NotificationService.default_target_url(workflow_key="fnf_settlement", instance=settlement),
            payload={"payment_reference": settlement.payment_reference},
        )
        return settlement

    @classmethod
    @transaction.atomic
    def cancel_fnf(cls, settlement_id, user_id: int | None = None, note: str = "") -> FnFSettlement:
        settlement = FnFSettlement.objects.get(pk=settlement_id)
        if settlement.status in {FnFSettlement.Status.PAID, FnFSettlement.Status.CANCELLED}:
            raise cls._error("Paid or already cancelled FnF settlement cannot be cancelled", settlement=settlement)
        ApprovalWorkflowService.cancel(
            instance=settlement,
            workflow_key="fnf_settlement",
            actor_id=user_id,
            remarks=note,
        )
        settlement.status = FnFSettlement.Status.CANCELLED
        settlement.cancelled_by_id = user_id
        settlement.cancelled_at = timezone.now()
        settlement.approval_note = note or settlement.approval_note
        settlement.save(update_fields=["status", "cancelled_by", "cancelled_at", "approval_note", "updated_at"])
        return settlement
