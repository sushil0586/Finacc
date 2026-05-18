from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from entity.approval_workflow_service import ApprovalWorkflowService
from entity.notification_service import NotificationService
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from payroll.models import (
    ContractPayrollProfile,
    FnFSettlement,
    PayrollComponent,
    PayrollPeriod,
    PayrollRun,
    PayrollRunActionLog,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    OneTimePayItem,
    SalaryStructureLine,
    SalaryStructure,
    SalaryStructureVersion,
)
from payroll.services.entity_payroll_policy_service import EntityPayrollPolicyService
from payroll.services.contract_salary_assignment_service import ContractSalaryAssignmentService
from payroll.services.payroll_calculation_input_resolver import PayrollCalculationInput, PayrollCalculationInputResolver
from payroll.services.payroll_config_resolver import PayrollConfigResolver
from payroll.services.one_time_pay_item_service import OneTimePayItemService
from payroll.services.payroll_formula_engine import (
    PayrollFormulaEngine,
    PayrollFormulaEngineError,
)
from payroll.services.payroll_attendance_engine import (
    PayrollAttendanceEngine,
    PayrollAttendanceEngineError,
    PayrollAttendanceResult,
)
from payroll.services.payroll_rule_engine import PayrollRuleEngine, PayrollRuleEngineError
from payroll.services.payroll_statutory_engine import PayrollStatutoryEngine, PayrollStatutoryEngineError
from payroll.services.payroll_posting_service import PayrollPostingService
from payroll.services.payroll_policy_rule_service import PayrollPolicyRuleService
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService
from payroll.services.payroll_run_readiness_resolver_service import PayrollRunReadinessResolverService
from payroll.services.payroll_traceability_service import PayrollTraceabilityService
from Authentication.models import User

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


def _period_day_count(start_date: date, end_date: date) -> Decimal:
    return Decimal(max((end_date - start_date).days + 1, 1))


@dataclass(frozen=True)
class PayrollRunResult:
    run: PayrollRun
    message: str


class PayrollCalculationError(ValueError):
    pass


@dataclass(frozen=True)
class PayrollRuntimeProfileSnapshot:
    entity_id: int
    subentity_id: int | None
    employee_code: str
    full_name: str
    employee_user_id: int | None
    salary_structure: SalaryStructure | None
    salary_structure_version: SalaryStructureVersion | None
    salary_structure_version_id: int | None
    ctc_annual: Decimal
    pay_frequency: str
    tax_regime: str
    payment_account_id: int | None


class PayrollRunService:
    """
    Orchestrates payroll run lifecycle.

    Payroll calculations stay inside payroll. Accounting handoff is explicit and
    happens only through the posting adapter once the run is approved.
    """

    REQUIRED_CALCULATION_POLICY_KEYS = ("country_code", "salary_mode", "proration_basis", "rounding_policy")
    DEFAULT_PF_WAGE_CAP = Decimal("15000.00")
    DEFAULT_PF_EMPLOYEE_RATE = Decimal("12.00")
    DEFAULT_PF_EMPLOYER_RATE = Decimal("12.00")
    DEFAULT_ESI_WAGE_THRESHOLD = Decimal("21000.00")
    DEFAULT_ESI_EMPLOYEE_RATE = Decimal("0.75")
    DEFAULT_ESI_EMPLOYER_RATE = Decimal("3.25")

    @staticmethod
    def _notification_users_for_run(run: PayrollRun, *extra_user_ids: int | None):
        user_ids: set[int] = set()
        for field_name in ("created_by_id", "submitted_by_id", "approved_by_id", "rejected_by_id", "locked_by_id", "posted_by_id"):
            value = getattr(run, field_name, None)
            if value:
                user_ids.add(int(value))
        for value in extra_user_ids:
            if value:
                user_ids.add(int(value))
        return User.objects.filter(pk__in=sorted(user_ids))

    @staticmethod
    def _doc_type_id() -> Optional[int]:
        row = DocumentType.objects.filter(module="payroll", default_code="PRUN", is_active=True).first()
        return row.id if row else None

    @classmethod
    def _assign_number(cls, run: PayrollRun) -> None:
        if run.doc_no:
            return
        doc_type_id = cls._doc_type_id()
        if not doc_type_id:
            run.run_number = run.run_number or f"{run.doc_code}-{run.id}"
            return
        number = DocumentNumberService.allocate_final(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            doc_type_id=doc_type_id,
            doc_code=run.doc_code,
            on_date=run.posting_date,
        )
        run.doc_no = number.doc_no
        run.run_number = number.display_no

    @classmethod
    def _active_contract_profiles(cls, run: PayrollRun):
        qs = ContractPayrollProfile.objects.select_related("hrms_contract__employee").filter(
            entity_id=run.entity_id,
            is_active=True,
            payroll_status=ContractPayrollProfile.PayrollStatus.ACTIVE,
            payroll_start_date__lte=run.payroll_period.period_end,
            hrms_contract__is_payroll_eligible=True,
            hrms_contract__status__in=PayrollRunReadinessResolverService.CONTRACT_READY_STATUSES,
            hrms_contract__payroll_effective_from__lte=run.payroll_period.period_end,
        ).filter(
            models.Q(payroll_end_date__isnull=True) | models.Q(payroll_end_date__gte=run.payroll_period.period_start)
        ).filter(
            models.Q(hrms_contract__end_date__isnull=True) | models.Q(hrms_contract__end_date__gte=run.payroll_period.period_start)
        )
        if run.subentity_id is None:
            qs = qs.filter(hrms_contract__subentity__isnull=True)
        else:
            qs = qs.filter(hrms_contract__subentity_id=run.subentity_id)
        qs = cls._exclude_fnf_contracts_from_regular_payroll(run=run, queryset=qs)
        return qs.order_by("hrms_contract__contract_code", "id")

    @classmethod
    def _exclude_fnf_contracts_from_regular_payroll(cls, *, run: PayrollRun, queryset):
        if run.run_type != PayrollRun.RunType.REGULAR:
            return queryset
        policy = EntityPayrollPolicyService.resolve_active_policy(
            entity_id=run.entity_id,
            payroll_date=run.payroll_period.period_end,
            pay_frequency=run.payroll_period.pay_frequency,
        )
        if policy is None:
            return queryset
        exclude_fnf = False
        for rule in PayrollPolicyRuleService.resolve_active_rules(policy=policy, rule_date=run.payroll_period.period_end):
            if str(rule.rule_key or "").strip().lower() != "exclude_fnf_contracts_from_regular_payroll":
                continue
            raw = (rule.rule_value_json or {}).get("value")
            exclude_fnf = raw if isinstance(raw, bool) else str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}
            break
        if not exclude_fnf:
            return queryset
        fnf_contract_ids = FnFSettlement.objects.filter(
            entity_id=run.entity_id,
            subentity_id=run.subentity_id,
        ).exclude(status=FnFSettlement.Status.CANCELLED).values_list("hrms_contract_id", flat=True)
        return queryset.exclude(hrms_contract_id__in=fnf_contract_ids)

    @classmethod
    def _build_runtime_profile_snapshot(
        cls,
        *,
        run: PayrollRun,
        contract_payroll_profile: ContractPayrollProfile,
        salary_assignment,
    ) -> PayrollRuntimeProfileSnapshot:
        salary_structure = getattr(salary_assignment, "salary_structure", None)
        salary_structure_version = getattr(salary_assignment, "salary_structure_version", None)
        ctc_annual = q2(getattr(salary_assignment, "ctc_amount", None) or ZERO2) * Decimal("12.00")
        return PayrollRuntimeProfileSnapshot(
            entity_id=run.entity_id,
            subentity_id=run.subentity_id,
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

    @staticmethod
    def _contract_readiness_enabled() -> bool:
        return bool(getattr(settings, "PAYROLL_USE_CONTRACT_READINESS", False))

    @classmethod
    def _build_contract_readiness_summary(cls, *, run: PayrollRun) -> dict[str, Any]:
        results = PayrollRunReadinessResolverService.resolve_entity_readiness(
            entity=run.entity,
            payroll_period=run.payroll_period,
        )
        ready_count = sum(1 for result in results if result.readiness_status == result.READY)
        warning_count = sum(1 for result in results if result.readiness_status == result.WARNING)
        blocked_results = [result for result in results if result.readiness_status == result.BLOCKED]
        blocked_contracts = [
            {
                "contract_id": str(result.contract.id),
                "contract_code": result.contract.contract_code,
                "employee_id": str(result.contract.employee_id),
                "employee_number": result.contract.employee.employee_number,
                "employee_user_id": result.contract.employee.linked_user_id,
                "blocking_issues": list(result.blocking_issues),
                "warnings": list(result.warnings),
            }
            for result in blocked_results
        ]
        summaries = [
            {
                "contract_id": str(result.contract.id),
                "contract_code": result.contract.contract_code,
                "employee_number": result.contract.employee.employee_number,
                "employee_user_id": result.contract.employee.linked_user_id,
                "readiness_status": result.readiness_status,
                "salary_structure_code": getattr(result.salary_structure, "code", ""),
                "salary_structure_version_no": getattr(result.salary_structure_version, "version_no", None),
                "payroll_policy_code": getattr(result.payroll_policy, "code", ""),
                "warnings": list(result.warnings),
                "blocking_issues": list(result.blocking_issues),
            }
            for result in results
        ]
        return {
            "enabled": True,
            "payroll_date": str(run.payroll_period.period_end),
            "ready_count": ready_count,
            "warning_count": warning_count,
            "blocked_count": len(blocked_results),
            "blocked_contracts": blocked_contracts,
            "contract_summaries": summaries,
            "blocked_employee_user_ids": sorted(
                {
                    int(result.contract.employee.linked_user_id)
                    for result in blocked_results
                    if result.contract.employee.linked_user_id
                }
            ),
            "generated_snapshots": [result.generated_snapshot_json for result in results],
        }

    @staticmethod
    def _contract_readiness_snapshot_map(contract_readiness_summary: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not contract_readiness_summary:
            return {}
        return {
            str(snapshot.get("contract", {}).get("id")): snapshot
            for snapshot in (contract_readiness_summary.get("generated_snapshots", []) or [])
            if snapshot.get("contract", {}).get("id")
        }

    @classmethod
    def _active_runtime_contexts(
        cls,
        run: PayrollRun,
        *,
        excluded_employee_user_ids: set[int] | None = None,
        contract_readiness_summary: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        readiness_map = cls._contract_readiness_snapshot_map(contract_readiness_summary)
        contexts: list[dict[str, Any]] = []
        seen_employee_keys: set[str] = set()
        for contract_payroll_profile in cls._active_contract_profiles(run):
            employee = contract_payroll_profile.hrms_contract.employee
            if excluded_employee_user_ids and employee.linked_user_id and int(employee.linked_user_id) in excluded_employee_user_ids:
                continue
            employee_key = str(employee.linked_user_id or employee.employee_number or contract_payroll_profile.id)
            if employee_key in seen_employee_keys:
                continue
            seen_employee_keys.add(employee_key)
            salary_assignment = ContractSalaryAssignmentService.get_active_assignment_for_payroll_date(
                contract_payroll_profile=contract_payroll_profile,
                payroll_date=run.payroll_period.period_end,
            )
            contexts.append(
                {
                    "profile": cls._build_runtime_profile_snapshot(
                        run=run,
                        contract_payroll_profile=contract_payroll_profile,
                        salary_assignment=salary_assignment,
                    ),
                    "contract_payroll_profile": contract_payroll_profile,
                    "salary_assignment": salary_assignment,
                    "readiness_snapshot": readiness_map.get(str(contract_payroll_profile.hrms_contract_id)) or {},
                }
            )
        return contexts

    @staticmethod
    def _scope_check(run: PayrollRun, *, profile: PayrollRuntimeProfileSnapshot) -> None:
        if profile.entity_id != run.entity_id:
            raise ValueError("Employee payroll profile entity does not match payroll run.")
        if profile.subentity_id != run.subentity_id:
            raise ValueError("Employee payroll profile subentity does not match payroll run.")

    @staticmethod
    def _resolve_structure_version(*, run: PayrollRun, profile: PayrollRuntimeProfileSnapshot) -> SalaryStructureVersion | None:
        return getattr(profile, "salary_structure_version", None) or getattr(getattr(profile, "salary_structure", None), "current_version", None)

    @classmethod
    def _build_policy_preflight(cls, *, run: PayrollRun, readiness_summary: dict[str, Any] | None = None) -> dict:
        blockers: list[str] = []
        warnings: list[str] = []
        inactive_structure_count = 0
        unresolved_version_count = 0
        gross_mode_missing_basis_count = 0
        outdated_version_count = 0
        missing_policy_count = 0
        incomplete_policy_count = 0
        unverified_hra_evidence_count = 0
        approval_blocked_hra_evidence_count = 0
        unverified_tax_declaration_count = 0
        approval_blocked_tax_declaration_count = 0
        resolved_profile_count = 0
        salary_modes: set[str] = set()
        proration_bases: set[str] = set()
        rounding_policies: set[str] = set()

        readiness_summary = readiness_summary if readiness_summary is not None else (
            cls._build_contract_readiness_summary(run=run) if cls._contract_readiness_enabled() else None
        )
        for runtime_context in cls._active_runtime_contexts(run, contract_readiness_summary=readiness_summary):
            profile = runtime_context["profile"]
            calculation_input = PayrollCalculationInputResolver.resolve(
                contract_payroll_profile=runtime_context.get("contract_payroll_profile"),
                salary_assignment=runtime_context.get("salary_assignment"),
                readiness_snapshot=runtime_context.get("readiness_snapshot"),
                payroll_date=run.payroll_period.period_end,
                payroll_period=run.payroll_period,
            )
            structure = calculation_input.salary_structure or profile.salary_structure
            version = calculation_input.salary_structure_version or cls._resolve_structure_version(run=run, profile=profile)
            if not structure or structure.status != structure.Status.ACTIVE:
                inactive_structure_count += 1
                continue
            if not version or version.status != version.Status.APPROVED:
                unresolved_version_count += 1
                continue

            resolved_profile_count += 1
            current_version_id = getattr(structure, "current_version_id", None)
            if profile.salary_structure_version_id and current_version_id and profile.salary_structure_version_id != current_version_id:
                outdated_version_count += 1

            policy = version.calculation_policy_json or {}
            if not policy:
                missing_policy_count += 1
                continue

            tax_projection = calculation_input.tax_projection_snapshot or {}
            has_unverified_hra_evidence = (
                q2(tax_projection.get("hra_rent_paid_annual")) > ZERO2
                and tax_projection.get("hra_evidence_verified") is not True
            )
            if has_unverified_hra_evidence:
                unverified_hra_evidence_count += 1
                if cls._policy_flag(policy, "tds_require_verified_hra_evidence_for_approval", False):
                    approval_blocked_hra_evidence_count += 1

            has_unverified_tax_declaration = cls._has_unverified_tax_declaration_evidence(tax_projection=tax_projection)
            if has_unverified_tax_declaration:
                unverified_tax_declaration_count += 1
                if cls._policy_flag(policy, "tds_require_verified_tax_declarations_for_approval", False):
                    approval_blocked_tax_declaration_count += 1

            if any(not policy.get(key) for key in cls.REQUIRED_CALCULATION_POLICY_KEYS):
                incomplete_policy_count += 1

            salary_mode = str(policy.get("salary_mode") or "").lower()
            proration_basis = policy.get("proration_basis")
            rounding_policy = policy.get("rounding_policy")

            if salary_mode == "gross" and q2(getattr(calculation_input, "gross_amount", ZERO2)) <= ZERO2:
                gross_mode_missing_basis_count += 1

            if salary_mode:
                salary_modes.add(str(salary_mode))
            if proration_basis:
                proration_bases.add(str(proration_basis))
            if rounding_policy:
                rounding_policies.add(str(rounding_policy))

        if inactive_structure_count:
            blockers.append(f"{inactive_structure_count} active contract payroll profile(s) do not resolve to an active salary structure.")
        if unresolved_version_count:
            blockers.append(f"{unresolved_version_count} active contract payroll profile(s) do not resolve to an approved salary structure version.")
        if missing_policy_count:
            blockers.append(f"{missing_policy_count} resolved structure version(s) are missing calculation policy metadata.")
        if gross_mode_missing_basis_count:
            blockers.append(f"{gross_mode_missing_basis_count} gross-mode contract payroll profile(s) are missing fixed salary basis.")
        if outdated_version_count:
            warnings.append(f"{outdated_version_count} contract payroll profile(s) are pinned to older salary structure versions.")
        if incomplete_policy_count:
            warnings.append(f"{incomplete_policy_count} resolved structure version(s) have incomplete calculation policy metadata.")
        if unverified_hra_evidence_count:
            warnings.append(f"{unverified_hra_evidence_count} contract payroll profile(s) include HRA rent support that is not explicitly marked as verified.")
        if approval_blocked_hra_evidence_count:
            warnings.append(f"{approval_blocked_hra_evidence_count} contract payroll profile(s) will block approval until HRA evidence is verified because their structure policy requires it.")
        if unverified_tax_declaration_count:
            warnings.append(f"{unverified_tax_declaration_count} contract payroll profile(s) include 80C or 80D declarations that are not explicitly marked as verified.")
        if approval_blocked_tax_declaration_count:
            warnings.append(f"{approval_blocked_tax_declaration_count} contract payroll profile(s) will block approval until 80C or 80D declaration evidence is verified because their structure policy requires it.")
        if len(salary_modes) > 1:
            warnings.append("Resolved employees use mixed salary modes in their structure policies.")
        if len(proration_bases) > 1:
            warnings.append("Resolved employees use mixed proration bases in their structure policies.")
        if len(rounding_policies) > 1:
            warnings.append("Resolved employees use mixed rounding policies in their structure policies.")

        return {
            "inactive_structure_count": inactive_structure_count,
            "contract_snapshot_gap_count": 0,
            "unresolved_structure_version_count": unresolved_version_count,
            "gross_mode_missing_basis_count": gross_mode_missing_basis_count,
            "resolved_profile_count": resolved_profile_count,
            "outdated_structure_version_count": outdated_version_count,
            "missing_calculation_policy_count": missing_policy_count,
            "incomplete_calculation_policy_count": incomplete_policy_count,
            "unverified_hra_evidence_count": unverified_hra_evidence_count,
            "approval_blocked_hra_evidence_count": approval_blocked_hra_evidence_count,
            "unverified_tax_declaration_count": unverified_tax_declaration_count,
            "approval_blocked_tax_declaration_count": approval_blocked_tax_declaration_count,
            "salary_modes": sorted(salary_modes),
            "proration_bases": sorted(proration_bases),
            "rounding_policies": sorted(rounding_policies),
            "blockers": blockers,
            "warnings": warnings,
        }

    @classmethod
    def _persist_policy_preflight(cls, *, run: PayrollRun, preflight: dict) -> None:
        run.config_snapshot = {
            **(run.config_snapshot or {}),
            "policy_preflight": preflight,
        }
        run.save(update_fields=["config_snapshot"])

    @classmethod
    def _assert_calculation_preflight(cls, *, run: PayrollRun, readiness_summary: dict[str, Any] | None = None) -> dict:
        preflight = cls._build_policy_preflight(run=run, readiness_summary=readiness_summary)
        cls._persist_policy_preflight(run=run, preflight=preflight)
        blockers = preflight.get("blockers") or []
        if blockers:
            raise ValueError(
                {
                    "detail": "Payroll run preflight failed. Resolve structure-policy blockers before calculation.",
                    "preflight": preflight,
                }
            )
        return preflight

    @classmethod
    def _approval_preflight_blockers(cls, *, run: PayrollRun) -> list[str]:
        blockers: list[str] = []
        readiness_summary = cls._build_contract_readiness_summary(run=run) if cls._contract_readiness_enabled() else None
        for runtime_context in cls._active_runtime_contexts(run, contract_readiness_summary=readiness_summary):
            profile = runtime_context["profile"]
            calculation_input = PayrollCalculationInputResolver.resolve(
                contract_payroll_profile=runtime_context.get("contract_payroll_profile"),
                salary_assignment=runtime_context.get("salary_assignment"),
                readiness_snapshot=runtime_context.get("readiness_snapshot"),
                payroll_date=run.payroll_period.period_end,
                payroll_period=run.payroll_period,
            )
            structure = calculation_input.salary_structure or profile.salary_structure
            version = calculation_input.salary_structure_version or cls._resolve_structure_version(run=run, profile=profile)
            if not structure or structure.status != structure.Status.ACTIVE or not version or version.status != version.Status.APPROVED:
                continue
            policy = version.calculation_policy_json or {}
            tax_projection = calculation_input.tax_projection_snapshot or {}
            if cls._policy_flag(policy, "tds_require_verified_hra_evidence_for_approval", False) and q2(tax_projection.get("hra_rent_paid_annual")) > ZERO2 and tax_projection.get("hra_evidence_verified") is not True:
                blockers.append(
                    f"Contract payroll profile {profile.employee_code or runtime_context['contract_payroll_profile'].id} requires verified HRA evidence before approval under its structure policy."
                )
            if cls._policy_flag(policy, "tds_require_verified_tax_declarations_for_approval", False) and cls._has_unverified_tax_declaration_evidence(tax_projection=tax_projection):
                blockers.append(
                    f"Contract payroll profile {profile.employee_code or runtime_context['contract_payroll_profile'].id} requires verified 80C or 80D declaration evidence before approval under its structure policy."
                )
        return blockers

    @staticmethod
    def _approved_one_time_items(run: PayrollRun):
        qs = OneTimePayItem.objects.filter(
            entity_id=run.entity_id,
            is_active=True,
            approval_status=OneTimePayItem.ApprovalStatus.APPROVED,
        )
        if run.subentity_id is None:
            qs = qs.filter(contract_payroll_profile__hrms_contract__subentity__isnull=True)
        else:
            qs = qs.filter(contract_payroll_profile__hrms_contract__subentity_id=run.subentity_id)
        qs = qs.filter(
            models.Q(payroll_period_id=run.payroll_period_id)
            | models.Q(payroll_period__isnull=True, effective_date__lte=run.payroll_period.period_end)
        )
        return qs.select_related("payroll_component", "contract_payroll_profile")

    @staticmethod
    def _resolve_proration_context(
        *,
        structure_version: SalaryStructureVersion,
        line: SalaryStructureLine,
        attendance_result: PayrollAttendanceResult,
    ) -> dict:
        default_context = {
            "basis": None,
            "method": attendance_result.proration_method,
            "numerator": None,
            "denominator": None,
            "multiplier": Decimal("1.00"),
            "trace": attendance_result.to_trace(),
        }
        if not line.is_pro_rated:
            return default_context
        policy = structure_version.calculation_policy_json or {}
        proration_basis = str(policy.get("proration_basis") or "").lower() or attendance_result.basis_label
        numerator = attendance_result.attendance_days if attendance_result.proration_method == "ACTUAL_ATTENDANCE" else attendance_result.payable_days
        denominator = attendance_result.base_days if attendance_result.base_days > ZERO2 else Decimal("1")
        return {
            "basis": proration_basis,
            "method": attendance_result.proration_method,
            "numerator": numerator,
            "denominator": denominator,
            "multiplier": attendance_result.proration_factor,
            "trace": attendance_result.to_trace(),
        }

    @staticmethod
    def _resolve_contract_item_amount(
        *,
        item_payload: dict[str, Any],
        salary_basis_amount: Decimal,
    ) -> Decimal:
        explicit_amount = q2(item_payload.get("amount"))
        if explicit_amount > ZERO2:
            return explicit_amount
        percentage = q2(item_payload.get("percentage"))
        if percentage > ZERO2 and salary_basis_amount > ZERO2:
            return q2(salary_basis_amount * percentage / Decimal("100.00"))
        return ZERO2

    @staticmethod
    def _normalize_variable_name(value: str | None) -> str:
        normalized = []
        previous_was_separator = False
        for char in str(value or ""):
            if char.isalnum():
                normalized.append(char.lower())
                previous_was_separator = False
                continue
            if not previous_was_separator:
                normalized.append("_")
            previous_was_separator = True
        return "".join(normalized).strip("_")

    @classmethod
    def _variable_aliases(cls, value: str | None) -> set[str]:
        raw = str(value or "").strip()
        if not raw:
            return set()
        normalized = cls._normalize_variable_name(raw)
        aliases = {raw}
        if normalized:
            aliases.add(normalized)
            aliases.add(normalized.upper())
        return aliases

    @classmethod
    def _snapshot_lookup_map(cls, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, value in (snapshot or {}).items():
            for alias in cls._variable_aliases(str(key)):
                values[alias] = value
        return values

    @classmethod
    def _resolve_input_value(
        cls,
        *,
        line: SalaryStructureLine,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> tuple[Decimal, dict[str, Any]]:
        rule_json = line.rule_json if isinstance(line.rule_json, dict) else {}
        input_candidates: list[tuple[str, str]] = []
        configured_input_key = rule_json.get("input_code") or rule_json.get("input_key") or rule_json.get("manual_input_key")
        if configured_input_key:
            input_candidates.append(("configured", str(configured_input_key)))

        semantic_code = cls._component_semantic_code(getattr(line, "component", None))
        if semantic_code:
            input_candidates.append(("semantic_code", semantic_code))
        input_candidates.append(("component_code", getattr(line.component, "code", "")))

        lookup_sources = [
            ("manual_input_snapshot", cls._snapshot_lookup_map(getattr(calculation_input, "manual_input_snapshot", None))),
            ("attendance_snapshot", cls._snapshot_lookup_map(getattr(calculation_input, "attendance_snapshot", None))),
            ("payable_days_snapshot", cls._snapshot_lookup_map(getattr(calculation_input, "payable_days_snapshot", None))),
            ("tax_projection_snapshot", cls._snapshot_lookup_map(getattr(calculation_input, "tax_projection_snapshot", None))),
        ]
        for source_name, lookup_map in lookup_sources:
            if not lookup_map:
                continue
            for candidate_type, candidate_value in input_candidates:
                for alias in cls._variable_aliases(candidate_value):
                    if alias not in lookup_map:
                        continue
                    resolved_amount = q2(lookup_map[alias])
                    return resolved_amount, {
                        "input_source": source_name,
                        "input_key": candidate_value,
                        "input_alias": alias,
                        "input_candidate_type": candidate_type,
                    }

        fallback_amount = q2(line.fixed_amount)
        if fallback_amount > ZERO2:
            return fallback_amount, {
                "input_source": "line_fixed_amount_fallback",
                "input_key": None,
                "input_alias": None,
                "input_candidate_type": "fixed_amount_fallback",
            }
        return ZERO2, {
            "input_source": "missing_input_default_zero",
            "input_key": configured_input_key or getattr(line.component, "code", ""),
            "input_alias": None,
            "input_candidate_type": "missing",
        }

    @staticmethod
    def _component_semantic_code(component: PayrollComponent | None) -> str | None:
        if not component:
            return None
        semantic_code = str(getattr(component, "semantic_code", "") or "").strip()
        return semantic_code or None

    @classmethod
    def _line_context_label(
        cls,
        *,
        line: SalaryStructureLine,
        profile: PayrollRuntimeProfileSnapshot,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> str:
        contract_code = getattr(calculation_input, "contract_code", None) or "unknown-contract"
        employee_code = getattr(calculation_input, "employee_code", None) or profile.employee_code or "unknown-employee"
        component = getattr(line, "component", None)
        component_code = getattr(component, "code", "") or "unknown-component"
        return (
            f"contract={contract_code}, employee={employee_code}, component={component_code}, "
            f"salary_line_id={getattr(line, 'id', None)}"
        )

    @classmethod
    def _unsupported_line_configuration(
        cls,
        *,
        line: SalaryStructureLine,
        profile: PayrollRuntimeProfileSnapshot,
        calculation_input: PayrollCalculationInput | None = None,
        reason: str,
    ) -> PayrollCalculationError:
        context_label = cls._line_context_label(
            line=line,
            profile=profile,
            calculation_input=calculation_input,
        )
        return PayrollCalculationError(
            f"{reason}. {context_label}, rule_mode={line.rule_mode}, calculation_basis={line.calculation_basis}"
        )

    @classmethod
    def _wrap_engine_error(
        cls,
        *,
        line: SalaryStructureLine,
        profile: PayrollRuntimeProfileSnapshot,
        calculation_input: PayrollCalculationInput | None = None,
        reason: str,
        error: Exception,
    ) -> PayrollCalculationError:
        context_label = cls._line_context_label(
            line=line,
            profile=profile,
            calculation_input=calculation_input,
        )
        return PayrollCalculationError(
            f"{reason}: {error}. {context_label}, rule_mode={line.rule_mode}, calculation_basis={line.calculation_basis}"
        )

    @staticmethod
    def _policy_decimal(policy: dict, key: str, default: Decimal) -> Decimal:
        raw = (policy or {}).get(key)
        if raw in (None, ""):
            return default
        try:
            return Decimal(str(raw))
        except Exception:
            return default

    @staticmethod
    def _policy_flag(policy: dict | None, key: str, default: bool = True) -> bool:
        raw = (policy or {}).get(key)
        if raw in (None, ""):
            return default
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _has_unverified_tax_declaration_evidence(cls, *, tax_projection: dict | None) -> bool:
        projection = tax_projection or {}
        return (
            q2(projection.get("deduction_80c")) > ZERO2 and projection.get("deduction_80c_evidence_verified") is not True
        ) or (
            q2(projection.get("deduction_80d")) > ZERO2 and projection.get("deduction_80d_evidence_verified") is not True
        )

    @staticmethod
    def _normalize_tax_regime(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"new", "new_regime"}:
            return "new_regime"
        if normalized in {"old", "old_regime"}:
            return "old_regime"
        return normalized or "old_regime"

    @staticmethod
    def _policy_slabs(policy: dict | None, key: str) -> list[dict]:
        raw = (policy or {}).get(key)
        if not isinstance(raw, list):
            return []

        normalized: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                rate = Decimal(str(item.get("rate") or "0"))
            except Exception:
                continue

            upto_raw = item.get("upto")
            upto: Decimal | None = None
            if upto_raw not in (None, ""):
                try:
                    upto = Decimal(str(upto_raw))
                except Exception:
                    continue

            normalized.append({"upto": upto, "rate": rate})
        return normalized

    @classmethod
    def _resolve_policy_slabs(cls, *, tax_regime: str, policy: dict | None) -> list[dict]:
        if tax_regime == "new_regime":
            return cls._policy_slabs(policy, "tds_new_regime_slabs")
        return cls._policy_slabs(policy, "tds_old_regime_slabs")

    @staticmethod
    def _compute_tax_from_slabs(*, taxable_income: Decimal, slabs: list[dict]) -> Decimal:
        if taxable_income <= ZERO2 or not slabs:
            return ZERO2

        previous_limit = ZERO2
        annual_tax = ZERO2

        for slab in slabs:
            upper_limit = slab.get("upto")
            rate = q2(slab.get("rate"))
            if rate <= ZERO2 and upper_limit is None:
                continue

            if upper_limit is None:
                taxable_slice = max(q2(taxable_income - previous_limit), ZERO2)
            else:
                taxable_slice = max(min(q2(taxable_income), q2(upper_limit)) - previous_limit, ZERO2)

            if taxable_slice > ZERO2 and rate > ZERO2:
                annual_tax = q2(annual_tax + q2(taxable_slice * rate / Decimal("100.00")))

            if upper_limit is None or q2(taxable_income) <= q2(upper_limit):
                break
            previous_limit = q2(upper_limit)

        return annual_tax

    @classmethod
    def _apply_regime_rebate(
        cls,
        *,
        annual_tax: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict | None,
    ) -> Decimal:
        threshold_key = (
            "tds_rebate_threshold_new_regime"
            if tax_regime == "new_regime"
            else "tds_rebate_threshold_old_regime"
        )
        max_key = (
            "tds_rebate_max_new_regime"
            if tax_regime == "new_regime"
            else "tds_rebate_max_old_regime"
        )
        rebate_threshold = cls._policy_decimal(policy or {}, threshold_key, ZERO2)
        rebate_max = cls._policy_decimal(policy or {}, max_key, ZERO2)

        if rebate_threshold <= ZERO2 or rebate_max <= ZERO2:
            return annual_tax
        if projected_taxable_income > q2(rebate_threshold):
            return annual_tax

        return max(q2(annual_tax - min(annual_tax, rebate_max)), ZERO2)

    @classmethod
    def _resolve_surcharge_rate(cls, *, projected_taxable_income: Decimal, tax_regime: str, policy: dict | None) -> Decimal:
        bracket = cls._resolve_surcharge_bracket(
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        return bracket["rate"]

    @classmethod
    def _resolve_surcharge_bracket(cls, *, projected_taxable_income: Decimal, tax_regime: str, policy: dict | None) -> dict:
        if projected_taxable_income <= ZERO2:
            return {"rate": ZERO2, "threshold_income": ZERO2, "previous_rate": ZERO2}
        slabs = cls._policy_slabs(
            policy,
            "tds_new_regime_surcharge_slabs" if tax_regime == "new_regime" else "tds_old_regime_surcharge_slabs",
        )
        if not slabs:
            return {"rate": ZERO2, "threshold_income": ZERO2, "previous_rate": ZERO2}

        previous_rate = ZERO2
        previous_upper_limit = ZERO2
        for slab in slabs:
            upper_limit = slab.get("upto")
            rate = q2(slab.get("rate"))
            if upper_limit is None:
                return {
                    "rate": rate,
                    "threshold_income": previous_upper_limit,
                    "previous_rate": previous_rate,
                }
            if projected_taxable_income <= q2(upper_limit):
                return {
                    "rate": rate,
                    "threshold_income": previous_upper_limit,
                    "previous_rate": previous_rate,
                }
            previous_rate = rate
            previous_upper_limit = q2(upper_limit)
        return {"rate": ZERO2, "threshold_income": ZERO2, "previous_rate": ZERO2}

    @classmethod
    def _apply_marginal_relief(
        cls,
        *,
        tax_before_surcharge: Decimal,
        subtotal_with_surcharge: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict | None,
    ) -> Decimal:
        if subtotal_with_surcharge <= ZERO2:
            return ZERO2
        if not cls._policy_flag(policy, "tds_apply_marginal_relief", True):
            return subtotal_with_surcharge

        surcharge_bracket = cls._resolve_surcharge_bracket(
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        current_rate = q2(surcharge_bracket.get("rate"))
        previous_rate = q2(surcharge_bracket.get("previous_rate"))
        threshold_income = q2(surcharge_bracket.get("threshold_income"))

        if current_rate <= previous_rate or threshold_income <= ZERO2 or projected_taxable_income <= threshold_income:
            return subtotal_with_surcharge

        slabs = cls._resolve_policy_slabs(tax_regime=tax_regime, policy=policy)
        if not slabs:
            return subtotal_with_surcharge

        threshold_tax = cls._compute_tax_from_slabs(
            taxable_income=threshold_income,
            slabs=slabs,
        )
        threshold_tax = cls._apply_regime_rebate(
            annual_tax=threshold_tax,
            projected_taxable_income=threshold_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        threshold_subtotal = q2(threshold_tax + q2(threshold_tax * previous_rate / Decimal("100.00")))
        max_subtotal = q2(threshold_subtotal + q2(projected_taxable_income - threshold_income))
        return min(subtotal_with_surcharge, max_subtotal)

    @classmethod
    def _apply_surcharge_and_cess(
        cls,
        *,
        annual_tax: Decimal,
        projected_taxable_income: Decimal,
        tax_regime: str,
        policy: dict | None,
    ) -> Decimal:
        if annual_tax <= ZERO2:
            return ZERO2

        surcharge_rate = cls._resolve_surcharge_rate(
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        surcharge_amount = ZERO2
        if surcharge_rate > ZERO2:
            surcharge_amount = q2(annual_tax * surcharge_rate / Decimal("100.00"))

        cess_rate = cls._policy_decimal(policy or {}, "tds_health_education_cess_rate", ZERO2)
        subtotal = q2(annual_tax + surcharge_amount)
        subtotal = cls._apply_marginal_relief(
            tax_before_surcharge=annual_tax,
            subtotal_with_surcharge=subtotal,
            projected_taxable_income=projected_taxable_income,
            tax_regime=tax_regime,
            policy=policy,
        )
        if cess_rate <= ZERO2:
            return subtotal
        cess_amount = q2(subtotal * cess_rate / Decimal("100.00"))
        return q2(subtotal + cess_amount)

    @staticmethod
    def _profile_structure_version(
        profile: PayrollRuntimeProfileSnapshot,
        *,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> SalaryStructureVersion | None:
        return (
            getattr(calculation_input, "salary_structure_version", None)
            or getattr(profile, "salary_structure_version", None)
            or getattr(getattr(profile, "salary_structure", None), "current_version", None)
        )

    @classmethod
    def _estimate_annual_component_amount(
        cls,
        *,
        profile: PayrollRuntimeProfileSnapshot,
        component_role: str,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> Decimal:
        structure_version = cls._profile_structure_version(profile, calculation_input=calculation_input)
        if not structure_version:
            return ZERO2

        lines = list(
            SalaryStructureLine.objects.filter(
                salary_structure_version=structure_version,
                is_active=True,
            )
            .select_related("component", "basis_component")
            .order_by("sequence", "id")
        )
        if not lines:
            return ZERO2

        structure_policy = structure_version.calculation_policy_json or {}
        salary_basis_amount = cls._resolve_salary_basis_amount(
            profile=profile,
            structure_version=structure_version,
            calculation_input=calculation_input,
        )
        salary_mode = str(structure_policy.get("salary_mode") or "ctc").lower()
        resolved: Dict[int, Decimal] = {}
        earning_amount = ZERO2
        component_map = {line.component_id: line.component for line in lines if getattr(line, "component", None)}

        for line in lines:
            component = getattr(line, "component", None)
            if not component:
                continue
            if component.component_type in {
                component.ComponentType.DEDUCTION,
                component.ComponentType.EMPLOYER_CONTRIBUTION,
                component.ComponentType.RECOVERY,
            }:
                continue
            monthly_amount = cls._line_amount(
                line=line,
                ctc_annual=q2(salary_basis_amount * Decimal("12.00")),
                resolved=resolved,
                profile=profile,
                proration_context={"multiplier": Decimal("1.00")},
                policy=structure_policy,
                salary_mode=salary_mode,
                salary_basis_amount=salary_basis_amount,
                current_earning_total=earning_amount,
                calculation_input=calculation_input,
                component_map=component_map,
            )
            resolved[line.component_id] = monthly_amount[0]
            earning_amount = q2(earning_amount + monthly_amount[0])
            if cls._component_semantic_code(line.component) == component_role:
                return q2(monthly_amount[0] * Decimal("12.00"))

        return ZERO2

    @classmethod
    def _resolve_hra_exemption_amount(
        cls,
        *,
        profile: PayrollRuntimeProfileSnapshot,
        snapshot: dict,
        policy: dict | None,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> Decimal:
        declared_hra = q2(snapshot.get("hra_exemption"))
        annual_hra_received = cls._estimate_annual_component_amount(
            profile=profile,
            component_role=PayrollComponent.SemanticCode.HRA,
            calculation_input=calculation_input,
        )
        annual_basic = cls._estimate_annual_component_amount(
            profile=profile,
            component_role=PayrollComponent.SemanticCode.BASIC_PAY,
            calculation_input=calculation_input,
        )
        rent_paid_annual = q2(snapshot.get("hra_rent_paid_annual"))
        metro_flag = snapshot.get("hra_is_metro_city")
        if (
            annual_hra_received <= ZERO2
            or annual_basic <= ZERO2
            or rent_paid_annual <= ZERO2
            or metro_flag is None
        ):
            return declared_hra

        rent_months = q2(snapshot.get("hra_rent_months"))
        if Decimal("1.00") <= rent_months <= Decimal("12.00"):
            month_multiplier = (rent_months / Decimal("12.00")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            annual_hra_received = q2(annual_hra_received * month_multiplier)
            annual_basic = q2(annual_basic * month_multiplier)

        city_basic_percent = Decimal("0.50") if bool(metro_flag) else Decimal("0.40")
        rent_minus_basic_threshold = max(q2(rent_paid_annual - q2(annual_basic * Decimal("0.10"))), ZERO2)
        city_cap = q2(annual_basic * city_basic_percent)
        derived_cap = min(
            annual_hra_received,
            rent_minus_basic_threshold,
            city_cap,
        )
        if declared_hra > ZERO2:
            return min(declared_hra, derived_cap)
        return derived_cap

    @classmethod
    def _resolve_declared_deductions(
        cls,
        *,
        profile: PayrollRuntimeProfileSnapshot,
        snapshot: dict,
        tax_regime: str,
        policy: dict | None,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> Decimal:
        if tax_regime == "new_regime":
            return ZERO2

        generic_declared = q2(
            snapshot.get("other_old_regime_deductions")
            or snapshot.get("declared_deductions")
        )
        deduction_80c = ZERO2
        deduction_80d = ZERO2
        hra_exemption = ZERO2
        if PayrollRunService._policy_flag(policy, "tds_allow_80c_old_regime", True):
            deduction_80c = min(
                q2(snapshot.get("deduction_80c")),
                PayrollRunService._policy_decimal(policy or {}, "tds_80c_cap", Decimal("150000.00")),
            )
        if PayrollRunService._policy_flag(policy, "tds_allow_80d_old_regime", True):
            deduction_80d = min(
                q2(snapshot.get("deduction_80d")),
                PayrollRunService._policy_decimal(policy or {}, "tds_80d_cap", Decimal("25000.00")),
            )
        if PayrollRunService._policy_flag(policy, "tds_allow_hra_exemption_old_regime", True):
            hra_exemption = cls._resolve_hra_exemption_amount(
                profile=profile,
                snapshot=snapshot,
                policy=policy,
                calculation_input=calculation_input,
            )
        return q2(generic_declared + deduction_80c + deduction_80d + hra_exemption)

    @staticmethod
    def _resolve_standard_deduction(*, tax_regime: str, policy: dict | None) -> Decimal:
        if tax_regime == "new_regime":
            return PayrollRunService._policy_decimal(
                policy or {},
                "tds_standard_deduction_new_regime",
                Decimal("50000.00"),
            )
        return PayrollRunService._policy_decimal(
            policy or {},
            "tds_standard_deduction_old_regime",
            Decimal("50000.00"),
        )

    @staticmethod
    def _resolve_projected_taxable_income(
        *,
        profile: PayrollRuntimeProfileSnapshot,
        policy: dict | None,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> Decimal:
        snapshot = getattr(calculation_input, "tax_projection_snapshot", None) or {}
        explicit_taxable_income = q2(snapshot.get("projected_taxable_income") or snapshot.get("annual_taxable_income"))
        if explicit_taxable_income > ZERO2:
            return explicit_taxable_income

        manual_input_snapshot = getattr(calculation_input, "manual_input_snapshot", None) or {}
        annual_salary_basis = q2(manual_input_snapshot.get("fixed_salary"))
        if annual_salary_basis <= ZERO2:
            annual_salary_basis = (
                q2(getattr(calculation_input, "gross_amount", ZERO2))
                or q2(getattr(calculation_input, "ctc_amount", ZERO2))
                or q2(q2(profile.ctc_annual) / Decimal("12.00"))
            )
        annualized_current_salary = q2(annual_salary_basis * Decimal("12.00"))
        other_income = q2(snapshot.get("other_income"))
        previous_employer_taxable_income = q2(
            snapshot.get("previous_employer_taxable_income") or snapshot.get("previous_employer_income")
        )
        tax_regime = PayrollRunService._normalize_tax_regime(
            getattr(calculation_input, "tax_regime", None) or profile.tax_regime
        )
        standard_deduction = PayrollRunService._resolve_standard_deduction(
            tax_regime=tax_regime,
            policy=policy,
        )
        declared_deductions = PayrollRunService._resolve_declared_deductions(
            profile=profile,
            snapshot=snapshot,
            tax_regime=tax_regime,
            policy=policy,
            calculation_input=calculation_input,
        )
        return max(
            q2(annualized_current_salary + other_income + previous_employer_taxable_income - standard_deduction - declared_deductions),
            ZERO2,
        )

    @staticmethod
    def _resolve_tds_amount(
        *,
        profile: PayrollRuntimeProfileSnapshot,
        policy: dict | None,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> Decimal:
        snapshot = getattr(calculation_input, "tax_projection_snapshot", None) or {}
        for key in ("monthly_tds", "projected_monthly_tds", "current_month_tds"):
            value = q2(snapshot.get(key))
            if value > ZERO2:
                return value

        annual_tax = q2(snapshot.get("annual_tax") or snapshot.get("projected_annual_tax"))
        if annual_tax <= ZERO2:
            tax_regime = PayrollRunService._normalize_tax_regime(
                getattr(calculation_input, "tax_regime", None) or profile.tax_regime
            )
            projected_taxable_income = PayrollRunService._resolve_projected_taxable_income(
                profile=profile,
                policy=policy,
                calculation_input=calculation_input,
            )
            slabs = PayrollRunService._resolve_policy_slabs(
                tax_regime=tax_regime,
                policy=policy,
            )
            if slabs:
                annual_tax = PayrollRunService._compute_tax_from_slabs(
                    taxable_income=projected_taxable_income,
                    slabs=slabs,
                )
                annual_tax = PayrollRunService._apply_regime_rebate(
                    annual_tax=annual_tax,
                    projected_taxable_income=projected_taxable_income,
                    tax_regime=tax_regime,
                    policy=policy,
                )
            else:
                if tax_regime == "new_regime":
                    projection_rate = PayrollRunService._policy_decimal(
                        policy or {},
                        "tds_projection_rate_new_regime",
                        PayrollRunService._policy_decimal(policy or {}, "tds_projection_rate", Decimal("10.00")),
                    )
                else:
                    projection_rate = PayrollRunService._policy_decimal(
                        policy or {},
                        "tds_projection_rate_old_regime",
                        PayrollRunService._policy_decimal(policy or {}, "tds_projection_rate", Decimal("10.00")),
                    )
                annual_tax = q2(projected_taxable_income * projection_rate / Decimal("100.00"))
            annual_tax = PayrollRunService._apply_surcharge_and_cess(
                annual_tax=annual_tax,
                projected_taxable_income=projected_taxable_income,
                tax_regime=tax_regime,
                policy=policy,
            )
        if annual_tax <= ZERO2:
            return ZERO2

        tax_paid_ytd = q2(snapshot.get("tax_paid_ytd") or snapshot.get("tds_deducted_ytd"))
        previous_employer_tds = q2(snapshot.get("previous_employer_tds"))
        tax_paid_ytd = q2(tax_paid_ytd + previous_employer_tds)
        default_remaining_periods = PayrollRunService._policy_decimal(
            policy or {},
            "tds_default_remaining_periods",
            Decimal("12"),
        )
        remaining_periods = q2(
            snapshot.get("remaining_periods")
            or snapshot.get("months_remaining")
            or default_remaining_periods
        )
        if remaining_periods <= ZERO2:
            remaining_periods = Decimal("1.00")

        balance_tax = max(q2(annual_tax - tax_paid_ytd), ZERO2)
        return q2(balance_tax / remaining_periods)

    @classmethod
    def _build_formula_variables(
        cls,
        *,
        profile: PayrollRuntimeProfileSnapshot,
        resolved: Dict[int, Decimal],
        line: SalaryStructureLine,
        current_earning_total: Decimal,
        salary_basis_amount: Decimal,
        calculation_input: PayrollCalculationInput | None = None,
        attendance_result: PayrollAttendanceResult | None = None,
        component_map: dict[int, PayrollComponent] | None = None,
    ) -> dict[str, Any]:
        component_map = component_map or {}
        attendance_result = attendance_result or PayrollAttendanceResult(
            proration_method="ACTUAL_ATTENDANCE",
            basis_label=None,
            base_days=Decimal("1.00"),
            calendar_days=Decimal("0.00"),
            working_days=Decimal("0.00"),
            attendance_days=q2(getattr(calculation_input, "attendance_days", ZERO2)),
            payable_days=q2(getattr(calculation_input, "payable_days", ZERO2)),
            lop_days=q2(getattr(calculation_input, "lop_days", ZERO2)),
            paid_leave_days=ZERO2,
            unpaid_leave_days=ZERO2,
            half_days=q2(getattr(calculation_input, "half_days", ZERO2)),
            overtime_hours=q2(getattr(calculation_input, "overtime_hours", ZERO2)),
            late_instances=int(getattr(calculation_input, "late_count", 0) or 0),
            late_deduction_days=ZERO2,
            adjustment_impact={"adjustments_applied": [], "manual_payable_override": None},
            missing_attendance_behavior="WARN",
            warnings=[],
            proration_factor=Decimal("1.0000"),
            summary_snapshot={},
        )
        variables: dict[str, Any] = {
            "ctc": q2(salary_basis_amount),
            "gross_earnings": q2(current_earning_total),
            "calendar_days": q2(attendance_result.calendar_days),
            "working_days": q2(attendance_result.working_days),
            "attendance_days": q2(attendance_result.attendance_days),
            "payable_days": q2(attendance_result.payable_days),
            "lop_days": q2(attendance_result.lop_days),
            "paid_leave_days": q2(attendance_result.paid_leave_days),
            "unpaid_leave_days": q2(attendance_result.unpaid_leave_days),
            "overtime_hours": q2(attendance_result.overtime_hours),
            "half_days": q2(attendance_result.half_days),
            "late_count": Decimal(str(attendance_result.late_instances or 0)),
            "late_instances": Decimal(str(attendance_result.late_instances or 0)),
            "late_deduction_days": q2(attendance_result.late_deduction_days),
            "proration_factor": q2(attendance_result.proration_factor),
        }
        statutory_flags = getattr(calculation_input, "statutory_flags", None) or {}
        for key, value in statutory_flags.items():
            for alias in cls._variable_aliases(key):
                variables[alias] = value

        for snapshot_name in ("manual_input_snapshot", "attendance_snapshot", "payable_days_snapshot", "tax_projection_snapshot"):
            snapshot = getattr(calculation_input, snapshot_name, None) or {}
            for key, value in snapshot.items():
                for alias in cls._variable_aliases(str(key)):
                    variables[alias] = value

        for component_id, amount in resolved.items():
            component = component_map.get(component_id)
            if component is None:
                continue
            for alias in cls._variable_aliases(component.code):
                variables[alias] = q2(amount)
            semantic_code = cls._component_semantic_code(component)
            if semantic_code:
                for alias in cls._variable_aliases(semantic_code):
                    variables[alias] = q2(amount)

        basis_component = getattr(line, "basis_component", None)
        if basis_component and line.basis_component_id in resolved:
            basis_amount = q2(resolved.get(line.basis_component_id, ZERO2))
            for alias in cls._variable_aliases(basis_component.code):
                variables[alias] = basis_amount
            semantic_code = cls._component_semantic_code(basis_component)
            if semantic_code:
                for alias in cls._variable_aliases(semantic_code):
                    variables[alias] = basis_amount

        if getattr(line, "component", None):
            current_component_amount = q2(resolved.get(line.component_id, ZERO2))
            for alias in cls._variable_aliases(line.component.code):
                variables.setdefault(alias, current_component_amount)
            semantic_code = cls._component_semantic_code(line.component)
            if semantic_code:
                for alias in cls._variable_aliases(semantic_code):
                    variables.setdefault(alias, current_component_amount)
        return variables

    @staticmethod
    def _rounding_trace() -> dict[str, str]:
        return {
            "mode": "ROUND_HALF_UP",
            "quantize": "0.01",
        }

    @classmethod
    def _line_amount(
        cls,
        *,
        line: SalaryStructureLine,
        ctc_annual: Decimal,
        resolved: Dict[int, Decimal],
        profile: PayrollRuntimeProfileSnapshot,
        calculation_input: PayrollCalculationInput | None = None,
        proration_context: dict | None = None,
        policy: dict | None = None,
        salary_mode: str | None = None,
        salary_basis_amount: Decimal = ZERO2,
        current_earning_total: Decimal = ZERO2,
        component_map: dict[int, PayrollComponent] | None = None,
        attendance_result: PayrollAttendanceResult | None = None,
    ) -> tuple[Decimal, dict[str, Any]]:
        basis = line.calculation_basis
        proration_multiplier = (proration_context or {}).get("multiplier", Decimal("1.00"))
        semantic_code = PayrollRunService._component_semantic_code(getattr(line, "component", None))
        trace: dict[str, Any] = {
            "calculation_mode": line.rule_mode if line.rule_mode != SalaryStructureLine.RuleMode.STANDARD else basis,
            "formula_used": None,
            "input_variables": {},
            "rule_json_applied": {},
            "rounding_applied": cls._rounding_trace(),
        }
        variables = cls._build_formula_variables(
            profile=profile,
            resolved=resolved,
            line=line,
            current_earning_total=current_earning_total,
            salary_basis_amount=q2(ctc_annual / Decimal("12.00")) if ctc_annual > ZERO2 else salary_basis_amount,
            calculation_input=calculation_input,
            attendance_result=attendance_result,
            component_map=component_map,
        )
        trace["input_variables"] = {
            key: str(q2(value)) if isinstance(value, (Decimal, int, float, str)) and str(value).strip() not in {"", "True", "False"} else value
            for key, value in variables.items()
            if key in {
                "ctc",
                "gross_earnings",
                "basic_pay",
                "payable_days",
                "attendance_days",
                "lop_days",
                "overtime_hours",
            }
        }
        trace["attendance_proration"] = (proration_context or {}).get("trace", {})

        if line.rule_mode not in {
            SalaryStructureLine.RuleMode.STANDARD,
            SalaryStructureLine.RuleMode.CUSTOM_FORMULA,
        }:
            raise cls._unsupported_line_configuration(
                line=line,
                profile=profile,
                calculation_input=calculation_input,
                reason="Unsupported salary line rule mode",
            )

        if (
            semantic_code == PayrollComponent.SemanticCode.SPECIAL_ALLOWANCE
            and getattr(line.component, "component_type", None) == line.component.ComponentType.EARNING
            and str(salary_mode or "").lower() == "gross"
            and basis in {
                SalaryStructureLine.CalculationBasis.FIXED,
                SalaryStructureLine.CalculationBasis.INPUT,
            }
            and q2(line.fixed_amount) == ZERO2
        ):
            target_amount = q2(q2(salary_basis_amount) * proration_multiplier)
            amount = max(q2(target_amount - current_earning_total), ZERO2)
            trace["calculation_mode"] = "SPECIAL_ALLOWANCE_BALANCING"
            trace["final_amount"] = str(amount)
            return amount, trace

        if PayrollStatutoryEngine.supports_component(getattr(line, "component", None)):
            try:
                result = PayrollStatutoryEngine.calculate_component(
                    component=line.component,
                    line=line,
                    resolved=resolved,
                    component_map=component_map or {},
                    calculation_input=calculation_input,
                    policy=policy or {},
                    profile=profile,
                    current_earning_total=current_earning_total,
                    payroll_date=getattr(getattr(calculation_input, "payroll_period", None), "period_end", None)
                    or timezone.localdate(),
                )
            except PayrollStatutoryEngineError as error:
                raise cls._wrap_engine_error(
                    line=line,
                    profile=profile,
                    calculation_input=calculation_input,
                    reason="Invalid statutory payroll configuration",
                    error=error,
                ) from error
            trace.update(result.trace)
            trace["calculation_mode"] = "STATUTORY_ENGINE"
            trace["final_amount"] = str(result.amount)
            return q2(result.amount), trace

        if line.rule_mode == SalaryStructureLine.RuleMode.CUSTOM_FORMULA:
            rule_json = line.rule_json if isinstance(line.rule_json, dict) else {}
            formula = str(
                rule_json.get("formula")
                or rule_json.get("custom_formula")
                or rule_json.get("expression")
                or ""
            ).strip()
            if not formula:
                raise cls._unsupported_line_configuration(
                    line=line,
                    profile=profile,
                    calculation_input=calculation_input,
                    reason="Custom formula salary line is missing a formula definition",
                )
            try:
                amount = PayrollFormulaEngine.evaluate(formula=formula, variables=variables)
            except PayrollFormulaEngineError as error:
                raise cls._wrap_engine_error(
                    line=line,
                    profile=profile,
                    calculation_input=calculation_input,
                    reason="Invalid salary line custom formula",
                    error=error,
                ) from error
            trace["formula_used"] = formula
        elif basis == SalaryStructureLine.CalculationBasis.FIXED:
            amount = q2(line.fixed_amount)
            trace["before_proration_amount"] = str(amount)
            amount = q2(amount * proration_multiplier)
            trace["after_proration_amount"] = str(amount)
        elif basis == SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC:
            amount = q2(q2(ctc_annual) / Decimal("12.00") * q2(line.rate) / Decimal("100.00"))
            trace["before_proration_amount"] = str(amount)
            amount = q2(amount * proration_multiplier)
            trace["after_proration_amount"] = str(amount)
        elif basis == SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT:
            if not line.basis_component_id:
                raise cls._unsupported_line_configuration(
                    line=line,
                    profile=profile,
                    calculation_input=calculation_input,
                    reason="Percent-of-component salary line is missing a basis component",
                )
            basis_amount = q2(resolved.get(line.basis_component_id, ZERO2))
            amount = q2(basis_amount * q2(line.rate) / Decimal("100.00"))
            trace["before_proration_amount"] = str(amount)
            amount = q2(amount * proration_multiplier)
            trace["after_proration_amount"] = str(amount)
        elif basis == SalaryStructureLine.CalculationBasis.INPUT:
            amount, input_trace = cls._resolve_input_value(
                line=line,
                calculation_input=calculation_input,
            )
            trace["before_proration_amount"] = str(amount)
            amount = q2(amount * proration_multiplier)
            trace["after_proration_amount"] = str(amount)
            trace.update(input_trace)
        else:
            raise cls._unsupported_line_configuration(
                line=line,
                profile=profile,
                calculation_input=calculation_input,
                reason="Unsupported salary line calculation basis",
            )

        rule_json = line.rule_json if isinstance(line.rule_json, dict) else {}
        supported_rule_json = {
            key: value
            for key, value in rule_json.items()
            if key in {
                "percentage",
                "slabs",
                "slab",
                "slab_basis",
                "basis",
                "min_amount",
                "minimum",
                "max_amount",
                "maximum",
                "cap_amount",
                "fixed_amount_fallback",
                "fallback_amount",
                "default_amount",
                "applicability",
                "condition",
                "applicable_if",
                "rule_type",
            }
        }
        if supported_rule_json and not (
            semantic_code in {
                PayrollComponent.SemanticCode.PT,
                PayrollComponent.SemanticCode.TDS,
                PayrollComponent.SemanticCode.PF_EMPLOYEE,
                PayrollComponent.SemanticCode.PF_EMPLOYER,
                PayrollComponent.SemanticCode.ESI_EMPLOYEE,
                PayrollComponent.SemanticCode.ESI_EMPLOYER,
            }
            and rule_json.get("scheme_code")
        ):
            variables["base_amount"] = amount
            try:
                rule_result = PayrollRuleEngine.apply(
                    amount=amount,
                    rule_json=supported_rule_json,
                    variables=variables,
                )
            except PayrollRuleEngineError as error:
                raise cls._wrap_engine_error(
                    line=line,
                    profile=profile,
                    calculation_input=calculation_input,
                    reason="Invalid salary line rule_json",
                    error=error,
                ) from error
            amount = rule_result.amount
            trace["rule_json_applied"] = rule_result.trace

        amount = q2(amount)
        trace["final_amount"] = str(amount)
        return amount, trace

    @staticmethod
    def _resolve_salary_basis_amount(
        *,
        profile: PayrollRuntimeProfileSnapshot,
        structure_version: SalaryStructureVersion,
        calculation_input: PayrollCalculationInput | None = None,
    ) -> Decimal:
        policy = structure_version.calculation_policy_json or {}
        salary_mode = str(policy.get("salary_mode") or "ctc").lower()
        if salary_mode == "gross":
            gross_basis = q2(getattr(calculation_input, "gross_amount", ZERO2))
            if gross_basis > ZERO2:
                return gross_basis
            gross_basis = (
                getattr(calculation_input, "manual_input_snapshot", {}) or {}
            ).get("fixed_salary")
            if q2(gross_basis) > ZERO2:
                return q2(gross_basis)
            return ZERO2
        ctc_basis = q2(getattr(calculation_input, "ctc_amount", ZERO2))
        if ctc_basis > ZERO2:
            return ctc_basis
        return q2(q2(profile.ctc_annual) / Decimal("12.00"))

    @classmethod
    @transaction.atomic
    def create_run(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        payroll_period_id: int,
        subentity_id: Optional[int],
        run_type: str,
        posting_date,
        payout_date,
        created_by_id: Optional[int],
    ) -> PayrollRunResult:
        period = PayrollPeriod.objects.select_for_update().get(
            id=payroll_period_id,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id != period.subentity_id:
            raise ValueError("Payroll period scope does not match the requested run scope.")
        if period.status != PayrollPeriod.Status.OPEN:
            raise ValueError("Payroll period must be open before a run can be created.")

        run = PayrollRun.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            payroll_period=period,
            run_type=run_type,
            posting_date=posting_date or period.period_end,
            payout_date=payout_date or period.payout_date,
            created_by_id=created_by_id,
        )
        run.config_snapshot = {
            "policy_preflight": cls._build_policy_preflight(run=run),
        }
        cls._assign_number(run)
        run.save(update_fields=["config_snapshot", "doc_no", "run_number"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.CREATED,
            user_id=created_by_id,
            comment="Payroll run created.",
        )
        return PayrollRunResult(run=run, message="Payroll run created.")

    @classmethod
    @transaction.atomic
    def calculate_run(cls, run: PayrollRun, *, force: bool = False) -> PayrollRunResult:
        PayrollRunHardeningService.assert_mutable(run)
        if run.status not in {PayrollRun.Status.DRAFT, PayrollRun.Status.CALCULATED}:
            raise ValueError("Only draft or calculated payroll runs can be recalculated.")
        if run.status == PayrollRun.Status.CALCULATED and not force:
            raise ValueError("Payroll run is already calculated. Use force=true to recalculate.")

        ledger_policy = PayrollConfigResolver.resolve_ledger_policy(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            on_date=run.payroll_period.period_end,
        )
        if not ledger_policy:
            raise ValueError("No active payroll ledger policy found for the payroll run scope.")

        contract_readiness_summary: dict[str, Any] | None = None
        excluded_employee_user_ids: set[int] = set()
        if cls._contract_readiness_enabled():
            contract_readiness_summary = cls._build_contract_readiness_summary(run=run)
            excluded_employee_user_ids = set(contract_readiness_summary.get("blocked_employee_user_ids", []))
            run.config_snapshot = {
                **(run.config_snapshot or {}),
                "contract_readiness": contract_readiness_summary,
            }
        preflight = cls._assert_calculation_preflight(run=run, readiness_summary=contract_readiness_summary)

        run.employee_runs.all().delete()

        employee_count = 0
        gross_total = ZERO2
        deduction_total = ZERO2
        employer_total = ZERO2
        reimbursement_total = ZERO2
        net_total = ZERO2
        input_snapshots: list[dict[str, Any]] = []
        runtime_contexts = cls._active_runtime_contexts(
            run,
            excluded_employee_user_ids=excluded_employee_user_ids,
            contract_readiness_summary=contract_readiness_summary,
        )
        missing_assignment_contracts = [
            {
                "contract_payroll_profile_id": str(context["contract_payroll_profile"].id),
                "contract_code": context["contract_payroll_profile"].hrms_contract.contract_code,
                "employee_code": context["profile"].employee_code,
            }
            for context in runtime_contexts
            if context.get("salary_assignment") is None
        ]
        if missing_assignment_contracts:
            raise ValueError(
                {
                    "message": "One or more contract payroll profiles are missing an active salary structure assignment.",
                    "missing_salary_assignments": missing_assignment_contracts,
                }
            )

        for runtime_context in runtime_contexts:
            profile = runtime_context["profile"]
            contract_payroll_profile = runtime_context["contract_payroll_profile"]
            cls._scope_check(run, profile=profile)
            calculation_input = PayrollCalculationInputResolver.resolve(
                contract_payroll_profile=contract_payroll_profile,
                salary_assignment=runtime_context.get("salary_assignment"),
                readiness_snapshot=runtime_context.get("readiness_snapshot"),
                payroll_date=run.payroll_period.period_end,
                payroll_period=run.payroll_period,
            )
            structure = calculation_input.salary_structure or profile.salary_structure
            structure_version = calculation_input.salary_structure_version or cls._resolve_structure_version(run=run, profile=profile)
            if not structure or structure.status != structure.Status.ACTIVE or not structure_version or structure_version.status != structure_version.Status.APPROVED:
                continue
            try:
                attendance_result = PayrollAttendanceEngine.evaluate(
                    contract_payroll_profile=contract_payroll_profile,
                    payroll_period=run.payroll_period,
                    structure_version=structure_version,
                    payroll_policy_snapshot=calculation_input.payroll_policy_snapshot,
                    attendance_required=bool(getattr(contract_payroll_profile, "attendance_required", False)),
                )
            except PayrollAttendanceEngineError as error:
                raise PayrollCalculationError(str(error)) from error

            lines = list(
                SalaryStructureLine.objects.filter(
                    salary_structure_version=structure_version,
                    is_active=True,
                )
                .select_related("component", "basis_component")
                .order_by("sequence", "id")
            )
            resolved: Dict[int, Decimal] = {}
            gross_amount = ZERO2
            deduction_amount = ZERO2
            employer_amount = ZERO2
            reimbursement_amount = ZERO2
            earning_amount = ZERO2
            structure_policy = structure_version.calculation_policy_json or {}
            salary_basis_amount = cls._resolve_salary_basis_amount(
                profile=profile,
                structure_version=structure_version,
                calculation_input=calculation_input,
            )
            salary_mode = str(structure_policy.get("salary_mode") or "ctc").lower()
            component_map = {line.component_id: line.component for line in lines if getattr(line, "component", None)}

            run_employee = PayrollRunEmployee.objects.create(
                payroll_run=run,
                contract_payroll_profile=contract_payroll_profile,
                salary_structure=structure,
                salary_structure_version=structure_version,
                ledger_policy_version=ledger_policy,
                statutory_policy_version_ref=run.statutory_policy_version_ref,
            )

            for line in lines:
                proration_context = cls._resolve_proration_context(
                    structure_version=structure_version,
                    line=line,
                    attendance_result=attendance_result,
                )
                amount = cls._line_amount(
                    line=line,
                    ctc_annual=q2(salary_basis_amount * Decimal("12.00")),
                    resolved=resolved,
                    profile=profile,
                    calculation_input=calculation_input,
                    proration_context=proration_context,
                    policy=structure_policy,
                    salary_mode=salary_mode,
                    salary_basis_amount=salary_basis_amount,
                    current_earning_total=earning_amount,
                    component_map=component_map,
                    attendance_result=attendance_result,
                )
                line_amount, line_trace = amount
                resolved[line.component_id] = line_amount
                component_posting = PayrollConfigResolver.resolve_component_posting(
                    entity_id=run.entity_id,
                    entityfinid_id=run.entityfinid_id,
                    subentity_id=run.subentity_id,
                    component_id=line.component_id,
                    on_date=run.payroll_period.period_end,
                )
                PayrollRunEmployeeComponent.objects.create(
                    payroll_run_employee=run_employee,
                    component=line.component,
                    component_code=line.component.code,
                    component_name=line.component.name,
                    component_type=line.component.component_type,
                    posting_behavior=line.component.posting_behavior,
                    component_posting_version=component_posting,
                    source_structure_line=line,
                    sequence=line.sequence,
                    amount=line_amount,
                    taxable_amount=line_amount if line.component.is_taxable else ZERO2,
                    is_employer_cost=line.component.component_type == line.component.ComponentType.EMPLOYER_CONTRIBUTION,
                    metadata={
                        "component_snapshot": {
                            "component_id": line.component_id,
                            "code": line.component.code,
                            "name": line.component.name,
                            "semantic_code": cls._component_semantic_code(line.component),
                            "semantic_role": cls._component_semantic_code(line.component),
                            "component_type": line.component.component_type,
                            "posting_behavior": line.component.posting_behavior,
                            "is_taxable": line.component.is_taxable,
                            "affects_net_pay": line.component.affects_net_pay,
                        },
                        "posting_snapshot": (
                            {
                                "posting_id": component_posting.id,
                                "version_no": component_posting.version_no,
                                "expense_account_id": component_posting.expense_account_id,
                                "liability_account_id": component_posting.liability_account_id,
                                "payable_account_id": component_posting.payable_account_id,
                            }
                            if component_posting
                            else {}
                        ),
                        "calculation_trace": line_trace,
                    },
                    calculation_basis_snapshot={
                        "basis": line.calculation_basis,
                        "rate": str(line.rate),
                        "fixed_amount": str(line.fixed_amount),
                        "is_pro_rated": line.is_pro_rated,
                        "semantic_code": cls._component_semantic_code(line.component),
                        "semantic_role": cls._component_semantic_code(line.component),
                        "proration_basis": proration_context.get("basis"),
                        "proration_method": proration_context.get("method"),
                        "proration_numerator": (
                            str(proration_context["numerator"])
                            if proration_context.get("numerator") is not None
                            else None
                        ),
                        "proration_denominator": (
                            str(proration_context["denominator"])
                            if proration_context.get("denominator") is not None
                            else None
                        ),
                        "proration_multiplier": str(proration_context.get("multiplier", Decimal("1.00"))),
                        "attendance_trace": proration_context.get("trace"),
                        "calculation_mode": line_trace.get("calculation_mode"),
                        "formula_used": line_trace.get("formula_used"),
                        "input_variables": line_trace.get("input_variables"),
                        "rule_json_applied": line_trace.get("rule_json_applied"),
                        "rounding_applied": line_trace.get("rounding_applied"),
                        "final_amount": line_trace.get("final_amount"),
                        "source_markers": calculation_input.source_markers,
                    },
                )
                if line.component.component_type == line.component.ComponentType.DEDUCTION:
                    deduction_amount = q2(deduction_amount + line_amount)
                elif line.component.component_type == line.component.ComponentType.EMPLOYER_CONTRIBUTION:
                    employer_amount = q2(employer_amount + line_amount)
                elif line.component.component_type == line.component.ComponentType.REIMBURSEMENT:
                    reimbursement_amount = q2(reimbursement_amount + line_amount)
                    gross_amount = q2(gross_amount + line_amount)
                elif line.component.component_type == line.component.ComponentType.RECOVERY:
                    deduction_amount = q2(deduction_amount + line_amount)
                else:
                    earning_amount = q2(earning_amount + line_amount)
                    gross_amount = q2(gross_amount + line_amount)

            component_ids = {
                int(item.get("payroll_component_id") or item.get("component_id"))
                for item in [*calculation_input.recurring_items, *calculation_input.one_time_items]
                if item.get("payroll_component_id") or item.get("component_id")
            }
            components_by_id = {
                component.id: component
                for component in PayrollComponent.objects.filter(id__in=component_ids)
            }

            for item_payload in calculation_input.recurring_items:
                component_ref = item_payload.get("payroll_component_id") or item_payload.get("component_id")
                if not component_ref:
                    continue
                component = components_by_id.get(int(component_ref))
                if component is None:
                    continue
                item_amount = cls._resolve_contract_item_amount(
                    item_payload=item_payload,
                    salary_basis_amount=salary_basis_amount,
                )
                if item_amount <= ZERO2:
                    continue
                component_posting = PayrollConfigResolver.resolve_component_posting(
                    entity_id=run.entity_id,
                    entityfinid_id=run.entityfinid_id,
                    subentity_id=run.subentity_id,
                    component_id=component.id,
                    on_date=run.payroll_period.period_end,
                )
                PayrollRunEmployeeComponent.objects.create(
                    payroll_run_employee=run_employee,
                    component=component,
                    component_code=component.code,
                    component_name=component.name,
                    component_type=component.component_type,
                    posting_behavior=component.posting_behavior,
                    component_posting_version=component_posting,
                    sequence=850,
                    amount=item_amount,
                    taxable_amount=item_amount if component.is_taxable else ZERO2,
                    is_employer_cost=component.component_type == component.ComponentType.EMPLOYER_CONTRIBUTION,
                    metadata={
                        "recurring_pay_item_source": item_payload,
                        "source_type": "contract_native",
                    },
                    calculation_basis_snapshot={
                        "contract_native_source": "recurring_pay_item",
                        "item_id": item_payload.get("id"),
                        "item_type": item_payload.get("item_type"),
                        "amount": item_payload.get("amount"),
                        "percentage": item_payload.get("percentage"),
                        "formula_override": item_payload.get("formula_override"),
                        "priority": item_payload.get("priority"),
                        "calculation_mode": "RECURRING_PAY_ITEM",
                        "formula_used": item_payload.get("formula_override") or None,
                        "input_variables": {
                            "ctc": str(salary_basis_amount),
                        },
                        "rule_json_applied": {},
                        "rounding_applied": cls._rounding_trace(),
                        "final_amount": str(item_amount),
                        "source_markers": calculation_input.source_markers,
                    },
                )
                if component.component_type == component.ComponentType.DEDUCTION or component.component_type == component.ComponentType.RECOVERY:
                    deduction_amount = q2(deduction_amount + item_amount)
                elif component.component_type == component.ComponentType.REIMBURSEMENT:
                    reimbursement_amount = q2(reimbursement_amount + item_amount)
                    gross_amount = q2(gross_amount + item_amount)
                elif component.component_type == component.ComponentType.EMPLOYER_CONTRIBUTION:
                    employer_amount = q2(employer_amount + item_amount)
                else:
                    gross_amount = q2(gross_amount + item_amount)

            for item_payload in calculation_input.one_time_items:
                component_ref = item_payload.get("payroll_component_id") or item_payload.get("component_id")
                if not component_ref:
                    continue
                component = components_by_id.get(int(component_ref))
                if component is None:
                    continue
                component_type = component.component_type
                posting_behavior = component.posting_behavior
                component_posting = (
                    PayrollConfigResolver.resolve_component_posting(
                        entity_id=run.entity_id,
                        entityfinid_id=run.entityfinid_id,
                        subentity_id=run.subentity_id,
                        component_id=component.id,
                        on_date=run.payroll_period.period_end,
                    )
                    if component
                    else None
                )
                item_amount = q2(item_payload.get("amount"))
                item_id = item_payload.get("id")
                PayrollRunEmployeeComponent.objects.create(
                    payroll_run_employee=run_employee,
                    component=component,
                    one_time_pay_item=OneTimePayItem.objects.filter(id=item_id).first() if item_id else None,
                    component_code=component.code,
                    component_name=component.name,
                    component_type=component_type,
                    posting_behavior=posting_behavior,
                    component_posting_version=component_posting,
                    sequence=900,
                    amount=item_amount,
                    taxable_amount=item_amount if component.is_taxable else ZERO2,
                    is_employer_cost=component_type == component.ComponentType.REIMBURSEMENT,
                    metadata={
                        "one_time_pay_item_source": item_payload.get("source_type"),
                        "one_time_item_snapshot": item_payload,
                        "source_type": "contract_native",
                    },
                    calculation_basis_snapshot={
                        "contract_native_source": "one_time_pay_item",
                        "one_time_pay_item_source": item_payload.get("source_type"),
                        "item_id": item_id,
                        "quantity": item_payload.get("quantity"),
                        "calculation_mode": "ONE_TIME_PAY_ITEM",
                        "formula_used": None,
                        "input_variables": {},
                        "rule_json_applied": {},
                        "rounding_applied": cls._rounding_trace(),
                        "final_amount": str(item_amount),
                        "source_markers": calculation_input.source_markers,
                    },
                )
                if component_type == component.ComponentType.DEDUCTION or component_type == component.ComponentType.RECOVERY:
                    deduction_amount = q2(deduction_amount + item_amount)
                elif component_type == component.ComponentType.REIMBURSEMENT:
                    reimbursement_amount = q2(reimbursement_amount + item_amount)
                    gross_amount = q2(gross_amount + item_amount)
                elif component_type == component.ComponentType.EMPLOYER_CONTRIBUTION:
                    employer_amount = q2(employer_amount + item_amount)
                else:
                    gross_amount = q2(gross_amount + item_amount)

            payable_amount = q2(gross_amount - deduction_amount)
            run_employee.gross_amount = gross_amount
            run_employee.deduction_amount = deduction_amount
            run_employee.employer_contribution_amount = employer_amount
            run_employee.reimbursement_amount = reimbursement_amount
            run_employee.payable_amount = payable_amount
            run_employee.calculation_payload = {
                "structure_code": structure.code,
                "structure_version": structure_version.version_no,
                "period_code": run.payroll_period.code,
                "salary_structure_snapshot": {
                    "salary_structure_id": structure.id,
                    "code": structure.code,
                    "name": structure.name,
                    "version_no": structure_version.version_no,
                },
                "payroll_profile_snapshot": {
                    "contract_payroll_profile_id": str(contract_payroll_profile.id),
                    "employee_code": calculation_input.employee_code or profile.employee_code,
                    "full_name": calculation_input.employee_name or profile.full_name,
                    "tax_regime": calculation_input.tax_regime or profile.tax_regime,
                    "pay_frequency": calculation_input.pay_frequency or profile.pay_frequency,
                },
                "contract_payroll_profile_snapshot": calculation_input.to_snapshot(),
                "attendance_snapshot": calculation_input.attendance_snapshot,
                "attendance_execution": attendance_result.to_trace(),
                "payable_days_snapshot": calculation_input.payable_days_snapshot,
                "tax_projection_snapshot": calculation_input.tax_projection_snapshot,
                "source_markers": calculation_input.source_markers,
            }
            run_employee.calculation_assumptions = {
                "ctc_annual": str(q2(salary_basis_amount * Decimal("12.00")) if salary_mode == "ctc" else q2(getattr(calculation_input, "ctc_amount", ZERO2) * Decimal("12.00"))),
                "pay_frequency": calculation_input.pay_frequency or profile.pay_frequency,
                "period_end": str(run.payroll_period.period_end),
                "salary_mode": (structure_version.calculation_policy_json or {}).get("salary_mode"),
                "salary_basis_amount": str(salary_basis_amount),
                "proration_basis": (structure_version.calculation_policy_json or {}).get("proration_basis"),
                "proration_method": attendance_result.proration_method,
                "rounding_policy": (structure_version.calculation_policy_json or {}).get("rounding_policy"),
                "country_code": (structure_version.calculation_policy_json or {}).get("country_code"),
                "attendance_days": str(attendance_result.attendance_days),
                "payable_days": str(attendance_result.payable_days),
                "lop_days": str(attendance_result.lop_days),
                "calendar_days": str(attendance_result.calendar_days),
                "working_days": str(attendance_result.working_days),
                "paid_leave_days": str(attendance_result.paid_leave_days),
                "unpaid_leave_days": str(attendance_result.unpaid_leave_days),
                "half_days": str(attendance_result.half_days),
                "overtime_hours": str(attendance_result.overtime_hours),
                "late_instances": attendance_result.late_instances,
                "late_deduction_days": str(attendance_result.late_deduction_days),
                "period_days": str(attendance_result.base_days),
                "proration_factor": str(attendance_result.proration_factor),
                "attendance_trace": attendance_result.to_trace(),
                "structure_binding_mode": (
                    "pinned"
                    if getattr(structure_version, "id", None) and getattr(structure, "current_version_id", None) and getattr(structure_version, "id", None) != getattr(structure, "current_version_id", None)
                    else "current"
                ),
                "source_markers": calculation_input.source_markers,
            }
            input_snapshots.append(
                {
                    "contract_payroll_profile_id": str(contract_payroll_profile.id),
                    "employee_code": calculation_input.employee_code or profile.employee_code,
                    "contract_code": calculation_input.contract_code,
                    "salary_structure_version_id": getattr(structure_version, "id", None),
                    "input": calculation_input.to_snapshot(),
                }
            )
            run_employee.save(
                update_fields=[
                    "gross_amount",
                    "deduction_amount",
                    "employer_contribution_amount",
                    "reimbursement_amount",
                    "payable_amount",
                    "calculation_payload",
                    "calculation_assumptions",
                ]
            )

            employee_count += 1
            gross_total = q2(gross_total + gross_amount)
            deduction_total = q2(deduction_total + deduction_amount)
            employer_total = q2(employer_total + employer_amount)
            reimbursement_total = q2(reimbursement_total + reimbursement_amount)
            net_total = q2(net_total + payable_amount)

        run.status = PayrollRun.Status.CALCULATED
        run.employee_count = employee_count
        run.gross_amount = gross_total
        run.deduction_amount = deduction_total
        run.employer_contribution_amount = employer_total
        run.reimbursement_amount = reimbursement_total
        run.net_pay_amount = net_total
        run.calculation_payload = {
            "calculated_at": timezone.now().isoformat(),
            "employee_count": employee_count,
            "policy_preflight_warnings": preflight.get("warnings", []),
        }
        if contract_readiness_summary is not None:
            run.calculation_payload["contract_readiness"] = {
                "ready_count": contract_readiness_summary.get("ready_count", 0),
                "warning_count": contract_readiness_summary.get("warning_count", 0),
                "blocked_count": contract_readiness_summary.get("blocked_count", 0),
                "blocked_contracts": contract_readiness_summary.get("blocked_contracts", []),
                "warnings": sorted(
                    {
                        warning
                        for summary in contract_readiness_summary.get("contract_summaries", [])
                        for warning in summary.get("warnings", [])
                    }
                ),
            }
        if input_snapshots:
            run.calculation_payload["calculation_input_summaries"] = input_snapshots
        run.ledger_policy_version = ledger_policy
        run.config_snapshot = {
            **(run.config_snapshot or {}),
            "ledger_policy_id": ledger_policy.id,
            "ledger_policy_version": ledger_policy.version_no,
            "ledger_policy_snapshot": {
                "salary_payable_account_id": ledger_policy.salary_payable_account_id,
                "payroll_clearing_account_id": ledger_policy.payroll_clearing_account_id,
                "reimbursement_payable_account_id": ledger_policy.reimbursement_payable_account_id,
                "employer_contribution_payable_account_id": ledger_policy.employer_contribution_payable_account_id,
                "effective_from": str(ledger_policy.effective_from),
                "effective_to": str(ledger_policy.effective_to) if ledger_policy.effective_to else None,
            },
            "structure_versions": [
                {
                    "contract_payroll_profile_id": str(row.contract_payroll_profile_id),
                    "salary_structure_version_id": row.salary_structure_version_id,
                }
                for row in run.employee_runs.all()
            ],
        }
        run.save(
            update_fields=[
                "status",
                "employee_count",
                "gross_amount",
                "deduction_amount",
                "employer_contribution_amount",
                "reimbursement_amount",
                "net_pay_amount",
                "calculation_payload",
                "ledger_policy_version",
                "config_snapshot",
            ]
        )
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.CALCULATED,
            user_id=None,
            old_status=PayrollRun.Status.DRAFT if not force else PayrollRun.Status.CALCULATED,
            new_status=run.status,
            comment=(
                "Payroll run calculated with contract readiness validation."
                if contract_readiness_summary is not None
                else ""
            ),
            payload={
                "employee_count": employee_count,
                **(
                    {
                        "contract_readiness_enabled": True,
                        "ready_count": contract_readiness_summary.get("ready_count", 0),
                        "warning_count": contract_readiness_summary.get("warning_count", 0),
                        "blocked_count": contract_readiness_summary.get("blocked_count", 0),
                        "blocked_contracts": contract_readiness_summary.get("blocked_contracts", []),
                    }
                    if contract_readiness_summary is not None
                    else {}
                ),
            },
        )
        return PayrollRunResult(run=run, message="Payroll run calculated.")

    @staticmethod
    @transaction.atomic
    def submit_run(run: PayrollRun, *, submitted_by_id: int, note: str = "", reason_code: str = "") -> PayrollRunResult:
        if run.status != PayrollRun.Status.CALCULATED:
            raise ValueError("Only calculated payroll runs can be submitted.")
        old_status = run.status
        ApprovalWorkflowService.submit_for_approval(
            instance=run,
            workflow_key="payroll_run",
            actor_id=submitted_by_id,
            remarks=note,
            title=run.run_number or f"{run.doc_code}-{run.id}",
        )
        run.submitted_by_id = submitted_by_id
        run.submitted_at = timezone.now()
        run.status_comment = note or run.status_comment
        run.status_reason_code = reason_code or run.status_reason_code
        run.save(update_fields=["submitted_by", "submitted_at", "status_comment", "status_reason_code", "updated_at"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.SUBMITTED,
            user_id=submitted_by_id,
            old_status=old_status,
            new_status=run.status,
            reason_code=reason_code,
            comment=note,
        )
        return PayrollRunResult(run=run, message="Payroll run submitted.")

    @staticmethod
    @transaction.atomic
    def approve_run(run: PayrollRun, *, approved_by_id: int, note: str = "") -> PayrollRunResult:
        if run.status != PayrollRun.Status.CALCULATED:
            raise ValueError("Only calculated payroll runs can be approved.")
        if not run.employee_runs.exists():
            raise ValueError("Payroll run has no employee rows to approve.")
        approval_blockers = PayrollRunService._approval_preflight_blockers(run=run)
        if approval_blockers:
            NotificationService.emit(
                instance=run,
                workflow_key="payroll_run",
                event_code="PAYROLL_RUN_BLOCKED",
                title="Payroll Run Blocked",
                message="Payroll run approval is blocked until setup and policy blockers are resolved.",
                users=PayrollRunService._notification_users_for_run(run, approved_by_id),
                actor=User.objects.filter(pk=approved_by_id).first(),
                target_url=NotificationService.default_target_url(workflow_key="payroll_run", instance=run),
                payload={"blocking_issues": approval_blockers},
            )
            raise ValueError(
                {
                    "detail": "Payroll run approval failed. Resolve policy-controlled approval blockers before approving.",
                    "blocking_issues": approval_blockers,
                }
            )
        if run.approval_status == PayrollRun.ApprovalStatus.DRAFT:
            PayrollRunService.submit_run(run, submitted_by_id=approved_by_id, note=note)
        old_status = run.status
        ApprovalWorkflowService.approve(
            instance=run,
            workflow_key="payroll_run",
            actor_id=approved_by_id,
            remarks=note,
        )
        run.status = PayrollRun.Status.APPROVED
        run.approved_by_id = approved_by_id
        run.approved_at = timezone.now()
        run.approval_note = note or ""
        run.save(update_fields=["status", "approved_by", "approved_at", "approval_note", "updated_at"])
        PayrollRunHardeningService.freeze_run(run, user_id=approved_by_id)
        ApprovalWorkflowService.lock_after_approval(
            instance=run,
            workflow_key="payroll_run",
            actor_id=approved_by_id,
            remarks=note,
        )
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.APPROVED,
            user_id=approved_by_id,
            old_status=old_status,
            new_status=run.status,
            comment=note,
        )
        return PayrollRunResult(run=run, message="Payroll run approved.")

    @staticmethod
    @transaction.atomic
    def post_run(run: PayrollRun, *, posted_by_id: int) -> PayrollRunResult:
        if run.status != PayrollRun.Status.APPROVED:
            raise ValueError("Only approved payroll runs can be posted.")
        if run.approval_status not in {
            PayrollRun.ApprovalStatus.APPROVED,
            PayrollRun.ApprovalStatus.LOCKED,
        }:
            raise ValueError("Payroll run must be approval-cleared before posting.")
        if not run.is_immutable:
            raise ValueError("Payroll run must be locked before posting.")
        old_status = run.status
        entry = PayrollPostingService.post_run(run, user_id=posted_by_id)
        run.status = PayrollRun.Status.POSTED
        run.posted_by_id = posted_by_id
        run.posted_at = timezone.now()
        run.posted_entry_id = entry.id
        run.post_reference = entry.voucher_no or ""
        run.save(update_fields=["status", "posted_by", "posted_at", "posted_entry_id", "post_reference"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.POSTED,
            user_id=posted_by_id,
            old_status=old_status,
            new_status=run.status,
            payload={"entry_id": entry.id},
        )
        NotificationService.emit(
            instance=run,
            workflow_key="payroll_run",
            event_code="PAYROLL_RUN_POSTED",
            title="Payroll Run Posted",
            message=f"Payroll run {run.run_number or run.id} was posted successfully.",
            users=PayrollRunService._notification_users_for_run(run, posted_by_id),
            actor=User.objects.filter(pk=posted_by_id).first(),
            target_url=NotificationService.default_target_url(workflow_key="payroll_run", instance=run),
            payload={"entry_id": entry.id, "post_reference": run.post_reference},
        )
        return PayrollRunResult(run=run, message="Payroll run posted.")

    @staticmethod
    def summary(run: PayrollRun) -> dict:
        rows = run.employee_runs.aggregate(
            gross_amount=Sum("gross_amount"),
            deduction_amount=Sum("deduction_amount"),
            employer_contribution_amount=Sum("employer_contribution_amount"),
            reimbursement_amount=Sum("reimbursement_amount"),
            payable_amount=Sum("payable_amount"),
        )
        traceability = PayrollTraceabilityService.build_traceability(run=run)
        policy_preflight = ((run.config_snapshot or {}).get("policy_preflight", {}) or {})
        policy_warnings = (policy_preflight.get("warnings", []))[:]
        policy_blockers = (policy_preflight.get("blockers", []))[:]
        return {
            "run_id": run.id,
            "employee_count": run.employee_count,
            "gross_amount": q2(rows.get("gross_amount")),
            "deduction_amount": q2(rows.get("deduction_amount")),
            "employer_contribution_amount": q2(rows.get("employer_contribution_amount")),
            "reimbursement_amount": q2(rows.get("reimbursement_amount")),
            "payable_amount": q2(rows.get("payable_amount")),
            "status": run.status,
            "warnings": policy_warnings,
            "blocking_issues": policy_blockers,
            "actors": PayrollTraceabilityService.build_actor_summary(run=run),
            "traceability": traceability,
            "timeline": PayrollTraceabilityService.build_timeline(run=run),
            "employee_rows": PayrollTraceabilityService.build_employee_rows(run=run),
            "component_totals": PayrollTraceabilityService.build_component_totals(run=run),
            "posting_verification_issues": traceability["posting"]["verification_issues"],
            "payment_verification_issues": traceability["payment"]["verification_issues"],
        }
