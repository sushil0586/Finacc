from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db.models import Q

from hrms.models import HrEmploymentContract
from payroll.models import (
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    ContractStatutoryProfile,
    EntityPayrollPolicy,
    EntityStatutoryRegistration,
    PayrollPeriod,
    RecurringPayItem,
    OneTimePayItem,
    StatutoryScheme,
)
from payroll.services.contract_payroll_profile_service import ContractPayrollProfileService
from payroll.services.contract_salary_assignment_service import ContractSalaryAssignmentService
from payroll.services.contract_statutory_profile_service import ContractStatutoryProfileService
from payroll.services.entity_payroll_policy_service import EntityPayrollPolicyService
from payroll.services.entity_statutory_registration_service import EntityStatutoryRegistrationService
from payroll.services.one_time_pay_item_service import OneTimePayItemService
from payroll.services.recurring_pay_item_service import RecurringPayItemService


@dataclass
class PayrollRunReadinessResult:
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"

    contract: HrEmploymentContract
    payroll_profile: ContractPayrollProfile | None = None
    salary_assignment: ContractSalaryStructureAssignment | None = None
    salary_structure: Any | None = None
    salary_structure_version: Any | None = None
    payroll_policy: EntityPayrollPolicy | None = None
    recurring_items: list[RecurringPayItem] = field(default_factory=list)
    one_time_items: list[OneTimePayItem] = field(default_factory=list)
    statutory_profiles: list[ContractStatutoryProfile] = field(default_factory=list)
    statutory_registrations: list[EntityStatutoryRegistration] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    readiness_status: str = READY
    generated_snapshot_json: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> PayrollRunReadinessResult:
        if self.blocking_issues:
            self.readiness_status = self.BLOCKED
        elif self.warnings:
            self.readiness_status = self.WARNING
        else:
            self.readiness_status = self.READY
        return self

    def to_summary(self) -> dict[str, Any]:
        snapshot = self.generated_snapshot_json or {}
        return {
            "contract_id": str(self.contract.id),
            "contract_code": self.contract.contract_code,
            "employee_id": str(self.contract.employee_id),
            "employee_number": getattr(self.contract.employee, "employee_number", "") or "",
            "employee_name": getattr(self.contract.employee, "display_name", "") or "",
            "subentity_id": self.contract.subentity_id,
            "readiness_status": self.readiness_status,
            "warnings": self.warnings,
            "blocking_issues": self.blocking_issues,
            "pay_frequency": snapshot.get("payroll_profile", {}).get("pay_frequency"),
            "salary_structure_code": snapshot.get("salary_structure", {}).get("code"),
            "salary_structure_version_no": snapshot.get("salary_structure_version", {}).get("version_no"),
            "payroll_policy_code": snapshot.get("payroll_policy", {}).get("code"),
            "recurring_item_count": len(self.recurring_items),
            "one_time_item_count": len(self.one_time_items),
            "statutory_profile_count": len(self.statutory_profiles),
            "statutory_registration_count": len(self.statutory_registrations),
            "snapshot": snapshot,
        }


class PayrollRunReadinessResolverService:
    REQUIRED_SCHEME_FLAGS = {
        "PF": "pf_applicable",
        "ESI": "esi_applicable",
        "PT": "pt_applicable",
        "TDS": "tds_applicable",
        "LWF": "lwf_applicable",
    }

    CONTRACT_READY_STATUSES = {
        HrEmploymentContract.ContractStatus.ACTIVE,
        HrEmploymentContract.ContractStatus.SUSPENDED,
        HrEmploymentContract.ContractStatus.NOTICE,
    }

    @staticmethod
    def _model_ref(instance: Any, *, include_entity: bool = False) -> dict[str, Any] | None:
        if instance is None:
            return None
        payload: dict[str, Any] = {
            "id": str(getattr(instance, "pk", "")),
        }
        for field in ("code", "name", "status", "is_active", "effective_from", "effective_to"):
            if hasattr(instance, field):
                value = getattr(instance, field)
                if isinstance(value, date):
                    payload[field] = value.isoformat()
                else:
                    payload[field] = value
        if include_entity and hasattr(instance, "entity_id"):
            payload["entity_id"] = getattr(instance, "entity_id")
        return payload

    @classmethod
    def _serialize_contract(cls, contract: HrEmploymentContract) -> dict[str, Any]:
        return {
            "id": str(contract.id),
            "contract_code": contract.contract_code,
            "status": contract.status,
            "employee_id": str(contract.employee_id),
            "employee_number": getattr(contract.employee, "employee_number", "") or "",
            "employee_name": getattr(contract.employee, "display_name", "") or "",
            "subentity_id": contract.subentity_id,
            "pay_group_code": contract.pay_group_code or "",
            "payroll_effective_from": contract.payroll_effective_from.isoformat(),
            "payroll_effective_to": contract.end_date.isoformat() if contract.end_date else None,
            "is_payroll_eligible": bool(contract.is_payroll_eligible),
        }

    @classmethod
    def _serialize_payroll_profile(cls, profile: ContractPayrollProfile | None) -> dict[str, Any] | None:
        if profile is None:
            return None
        return {
            "id": str(profile.id),
            "pay_frequency": profile.pay_frequency,
            "payroll_status": profile.payroll_status,
            "tax_regime": profile.tax_regime,
            "payment_mode": profile.payment_mode,
            "payroll_start_date": profile.payroll_start_date.isoformat(),
            "payroll_end_date": profile.payroll_end_date.isoformat() if profile.payroll_end_date else None,
            "pf_applicable": profile.pf_applicable,
            "esi_applicable": profile.esi_applicable,
            "pt_applicable": profile.pt_applicable,
            "tds_applicable": profile.tds_applicable,
            "lwf_applicable": profile.lwf_applicable,
            "overtime_eligible": profile.overtime_eligible,
            "attendance_required": profile.attendance_required,
            "bank_account_id": profile.bank_account_id,
            "metadata": profile.metadata or {},
            "is_active": profile.is_active,
        }

    @classmethod
    def _serialize_salary_assignment(cls, assignment: ContractSalaryStructureAssignment | None) -> dict[str, Any] | None:
        if assignment is None:
            return None
        return {
            "id": str(assignment.id),
            "salary_structure_id": assignment.salary_structure_id,
            "salary_structure_version_id": assignment.salary_structure_version_id,
            "assignment_status": assignment.assignment_status,
            "effective_from": assignment.effective_from.isoformat(),
            "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
            "ctc_amount": str(assignment.ctc_amount),
            "gross_amount": str(assignment.gross_amount),
            "metadata": assignment.metadata or {},
            "is_active": assignment.is_active,
        }

    @classmethod
    def _serialize_recurring_item(cls, item: RecurringPayItem) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "component_id": item.payroll_component_id,
            "component_code": item.payroll_component.code,
            "component_name": item.payroll_component.name,
            "item_type": item.item_type,
            "amount": str(item.amount),
            "percentage": str(item.percentage),
            "formula_override": item.formula_override or "",
            "recurrence_frequency": item.recurrence_frequency,
            "effective_from": item.effective_from.isoformat(),
            "effective_to": item.effective_to.isoformat() if item.effective_to else None,
            "priority": item.priority,
            "remarks": item.remarks or "",
            "metadata": item.metadata or {},
            "is_active": item.is_active,
        }

    @classmethod
    def _serialize_one_time_item(cls, item: OneTimePayItem) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "component_id": item.payroll_component_id,
            "component_code": item.payroll_component.code,
            "component_name": item.payroll_component.name,
            "item_type": item.item_type,
            "payroll_period_id": item.payroll_period_id,
            "requested_date": item.requested_date.isoformat(),
            "effective_date": item.effective_date.isoformat(),
            "amount": str(item.amount),
            "quantity": str(item.quantity),
            "approval_status": item.approval_status,
            "source_type": item.source_type,
            "remarks": item.remarks or "",
            "metadata": item.metadata or {},
            "is_active": item.is_active,
        }

    @classmethod
    def _serialize_statutory_profile(cls, profile: ContractStatutoryProfile) -> dict[str, Any]:
        return {
            "id": str(profile.id),
            "scheme_id": str(profile.scheme_id),
            "scheme_code": profile.scheme.code,
            "scheme_name": profile.scheme.name,
            "scheme_type": profile.scheme.scheme_type,
            "is_applicable": profile.is_applicable,
            "effective_from": profile.effective_from.isoformat(),
            "effective_to": profile.effective_to.isoformat() if profile.effective_to else None,
            "override_rule_json": profile.override_rule_json or {},
            "metadata": profile.metadata or {},
            "is_active": profile.is_active,
        }

    @classmethod
    def _serialize_statutory_registration(cls, registration: EntityStatutoryRegistration) -> dict[str, Any]:
        return {
            "id": str(registration.id),
            "scheme_id": str(registration.scheme_id),
            "scheme_code": registration.scheme.code,
            "scheme_name": registration.scheme.name,
            "scheme_type": registration.scheme.scheme_type,
            "registration_number": registration.registration_number,
            "registration_state": registration.registration_state,
            "effective_from": registration.effective_from.isoformat(),
            "effective_to": registration.effective_to.isoformat() if registration.effective_to else None,
            "metadata": registration.metadata or {},
            "is_active": registration.is_active,
        }

    @classmethod
    def _find_overlapping_assignments(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_date: date,
    ):
        return ContractSalaryStructureAssignment.objects.filter(
            contract_payroll_profile=contract_payroll_profile,
            is_active=True,
            effective_from__lte=payroll_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=payroll_date)).exclude(
            assignment_status=ContractSalaryStructureAssignment.AssignmentStatus.ENDED
        )

    @classmethod
    def _resolve_required_schemes(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_date: date,
        warnings: list[str],
    ) -> list[StatutoryScheme]:
        explicit_schemes = list(
            ContractStatutoryProfileService.list_applicable_schemes(
                contract_payroll_profile=contract_payroll_profile,
                profile_date=payroll_date,
            )
        )
        scheme_map: dict[str, StatutoryScheme] = {scheme.scheme_type: scheme for scheme in explicit_schemes}
        for scheme_type, flag_name in cls.REQUIRED_SCHEME_FLAGS.items():
            if not getattr(contract_payroll_profile, flag_name, False):
                continue
            if scheme_type in scheme_map:
                continue
            fallback = (
                StatutoryScheme.objects.filter(
                    scheme_type=scheme_type,
                    country_code="IN",
                    state_code="",
                    is_active=True,
                )
                .order_by("-is_system", "code")
                .first()
            )
            if fallback:
                scheme_map[scheme_type] = fallback
                warnings.append(
                    f"No active contract statutory profile found for {scheme_type}; using the active entity-wide scheme {fallback.code}."
                )
            else:
                warnings.append(f"No active statutory scheme configured for applicable scheme type {scheme_type}.")
        return list(scheme_map.values())

    @staticmethod
    def _resolve_registration_for_scheme(
        *,
        entity_id: int,
        scheme: StatutoryScheme,
        payroll_date: date,
    ) -> EntityStatutoryRegistration | None:
        return EntityStatutoryRegistrationService.resolve_active_registration(
            entity_id=entity_id,
            scheme=scheme,
            registration_date=payroll_date,
            registration_state=scheme.state_code or "",
        )

    @classmethod
    def build_runtime_snapshot(cls, contract: HrEmploymentContract, payroll_date: date) -> dict[str, Any]:
        result = cls.resolve_contract_readiness(contract=contract, payroll_date=payroll_date)
        return result.generated_snapshot_json

    @classmethod
    def resolve_contract_readiness(
        cls,
        *,
        contract: HrEmploymentContract,
        payroll_date: date,
        payroll_period: PayrollPeriod | None = None,
    ) -> PayrollRunReadinessResult:
        result = PayrollRunReadinessResult(contract=contract)

        if not contract.is_payroll_eligible:
            result.blocking_issues.append("Contract is not marked payroll eligible.")
        if contract.status not in cls.CONTRACT_READY_STATUSES:
            result.blocking_issues.append("Contract is not in a payroll-ready status.")

        payroll_profile = ContractPayrollProfileService.resolve_contract_payroll_profile(contract, as_of_date=payroll_date)
        result.payroll_profile = payroll_profile
        if payroll_profile is None:
            result.blocking_issues.append("Missing active contract payroll profile.")
        else:
            if not payroll_profile.is_active or payroll_profile.payroll_status != ContractPayrollProfile.PayrollStatus.ACTIVE:
                result.blocking_issues.append("Payroll profile is inactive or not in active status.")

            overlapping_assignments = cls._find_overlapping_assignments(
                contract_payroll_profile=payroll_profile,
                payroll_date=payroll_date,
            )
            if overlapping_assignments.count() > 1:
                result.blocking_issues.append("Multiple active salary assignments overlap for the payroll date.")

            salary_assignment = ContractSalaryAssignmentService.get_active_assignment_for_payroll_date(
                contract_payroll_profile=payroll_profile,
                payroll_date=payroll_date,
            )
            result.salary_assignment = salary_assignment
            if salary_assignment is None:
                result.blocking_issues.append("Missing active salary structure assignment.")
            else:
                result.salary_structure = salary_assignment.salary_structure
                result.salary_structure_version = salary_assignment.salary_structure_version
                if not salary_assignment.salary_structure.is_active:
                    result.blocking_issues.append("Assigned salary structure is inactive.")
                if salary_assignment.salary_structure_version.status != salary_assignment.salary_structure_version.Status.APPROVED:
                    result.blocking_issues.append("Assigned salary structure version is not approved.")
                if (
                    salary_assignment.salary_structure.current_version_id
                    and salary_assignment.salary_structure.current_version_id != salary_assignment.salary_structure_version_id
                ):
                    result.warnings.append("Assigned salary structure version is not the current active version.")

            payroll_policy = EntityPayrollPolicyService.resolve_active_policy(
                entity_id=contract.entity_id,
                payroll_date=payroll_date,
                pay_frequency=payroll_profile.pay_frequency,
            )
            result.payroll_policy = payroll_policy
            if payroll_policy is None:
                result.blocking_issues.append("No active payroll policy found for the entity and pay frequency.")
            elif not payroll_policy.is_active:
                result.blocking_issues.append("Resolved payroll policy is inactive.")

            recurring_items = list(
                RecurringPayItemService.resolve_active_recurring_items(
                    contract_payroll_profile=payroll_profile,
                    payroll_date=payroll_date,
                )
            )
            result.recurring_items = recurring_items

            future_recurring = payroll_profile.recurring_pay_items.filter(is_active=True, effective_from__gt=payroll_date).count()
            if future_recurring:
                result.warnings.append(f"{future_recurring} recurring pay item(s) are future-dated and not yet effective.")

            one_time_items = list(
                OneTimePayItemService.resolve_payable_items(
                    contract_payroll_profile=payroll_profile,
                    payroll_date=payroll_date,
                    payroll_period=payroll_period,
                )
            )
            result.one_time_items = one_time_items

            expired_one_time = payroll_profile.one_time_pay_items.filter(
                is_active=True,
                approval_status=OneTimePayItem.ApprovalStatus.APPROVED,
                effective_date__lt=payroll_date,
            ).exclude(id__in=[item.id for item in one_time_items]).count()
            if expired_one_time:
                result.warnings.append(f"{expired_one_time} approved one-time pay item(s) are expired for the selected payroll date.")

            reimbursement_gaps = [
                item.payroll_component.code
                for item in recurring_items
                if item.item_type == RecurringPayItem.ItemType.REIMBURSEMENT and not item.metadata
            ]
            reimbursement_gaps.extend(
                item.payroll_component.code
                for item in one_time_items
                if item.item_type == OneTimePayItem.ItemType.REIMBURSEMENT and not item.metadata
            )
            if reimbursement_gaps:
                result.warnings.append(
                    f"Reimbursement metadata is incomplete for component(s): {', '.join(sorted(set(reimbursement_gaps)))}."
                )

            applicable_schemes = cls._resolve_required_schemes(
                contract_payroll_profile=payroll_profile,
                payroll_date=payroll_date,
                warnings=result.warnings,
            )
            statutory_profiles: list[ContractStatutoryProfile] = []
            statutory_registrations: list[EntityStatutoryRegistration] = []
            for scheme in applicable_schemes:
                profile = ContractStatutoryProfileService.resolve_contract_statutory_profile(
                    contract_payroll_profile=payroll_profile,
                    scheme=scheme,
                    profile_date=payroll_date,
                )
                if profile:
                    statutory_profiles.append(profile)
                elif scheme.scheme_type not in cls.REQUIRED_SCHEME_FLAGS:
                    result.warnings.append(f"Missing optional statutory profile for scheme {scheme.code}.")
                else:
                    result.warnings.append(f"Missing explicit contract statutory profile for scheme {scheme.code}.")

                registration = cls._resolve_registration_for_scheme(
                    entity_id=contract.entity_id,
                    scheme=scheme,
                    payroll_date=payroll_date,
                )
                if registration:
                    statutory_registrations.append(registration)
                else:
                    result.blocking_issues.append(f"Missing statutory registration for scheme {scheme.code}.")
            result.statutory_profiles = statutory_profiles
            result.statutory_registrations = statutory_registrations

        result.generated_snapshot_json = {
            "contract": cls._serialize_contract(contract),
            "payroll_profile": cls._serialize_payroll_profile(result.payroll_profile),
            "salary_assignment": cls._serialize_salary_assignment(result.salary_assignment),
            "salary_structure": cls._model_ref(result.salary_structure) if result.salary_structure else None,
            "salary_structure_version": {
                **(cls._model_ref(result.salary_structure_version) or {}),
                "version_no": getattr(result.salary_structure_version, "version_no", None),
                "status": getattr(result.salary_structure_version, "status", None),
            } if result.salary_structure_version else None,
            "payroll_policy": {
                **(cls._model_ref(result.payroll_policy, include_entity=True) or {}),
                "pay_frequency": getattr(result.payroll_policy, "pay_frequency", None),
            } if result.payroll_policy else None,
            "recurring_items": [cls._serialize_recurring_item(item) for item in result.recurring_items],
            "one_time_items": [cls._serialize_one_time_item(item) for item in result.one_time_items],
            "statutory_profiles": [cls._serialize_statutory_profile(item) for item in result.statutory_profiles],
            "statutory_registrations": [cls._serialize_statutory_registration(item) for item in result.statutory_registrations],
            "warnings": result.warnings,
            "blocking_issues": result.blocking_issues,
        }
        return result.finalize()

    @classmethod
    def resolve_entity_readiness(cls, *, entity, payroll_period: PayrollPeriod) -> list[PayrollRunReadinessResult]:
        contracts = HrEmploymentContract.objects.select_related("employee").filter(
            entity=entity,
            is_payroll_eligible=True,
            payroll_effective_from__lte=payroll_period.period_end,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=payroll_period.period_start)
        )
        if payroll_period.subentity_id:
            contracts = contracts.filter(subentity_id=payroll_period.subentity_id)
        contracts = contracts.filter(status__in=cls.CONTRACT_READY_STATUSES).order_by("contract_code")
        return [
            cls.resolve_contract_readiness(contract=contract, payroll_date=payroll_period.period_end, payroll_period=payroll_period)
            for contract in contracts
        ]

    @classmethod
    def list_blocked_contracts(cls, *, entity, payroll_period: PayrollPeriod) -> list[PayrollRunReadinessResult]:
        return [result for result in cls.resolve_entity_readiness(entity=entity, payroll_period=payroll_period) if result.readiness_status == PayrollRunReadinessResult.BLOCKED]
