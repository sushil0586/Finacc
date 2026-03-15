from __future__ import annotations

from django.apps import apps

from numbering.models import DocumentType
from payroll.models import (
    PayrollComponent,
    PayrollComponentPosting,
    PayrollEmployeeProfile,
    PayrollLedgerPolicy,
    PayrollPeriod,
    SalaryStructure,
    SalaryStructureVersion,
)
from payroll.services.dto.payroll_rollout_results import IssueSeverity, RolloutValidationResult


class PayrollRolloutValidationService:
    """
    Validates whether one payroll scope is ready for shadow mode or live cutover.
    """

    @staticmethod
    def _scope(entity_id: int, entityfinid_id: int, subentity_id: int | None) -> dict[str, int | None]:
        return {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
        }

    @classmethod
    def validate_setup(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None = None,
        period_code: str | None = None,
    ) -> RolloutValidationResult:
        result = RolloutValidationResult(
            name="payroll-rollout-setup",
            scope=cls._scope(entity_id, entityfinid_id, subentity_id),
        )

        components = PayrollComponent.objects.filter(entity_id=entity_id, is_active=True)
        structures = SalaryStructure.objects.filter(entity_id=entity_id, is_active=True)
        structure_versions = SalaryStructureVersion.objects.filter(
            salary_structure__entity_id=entity_id,
            status=SalaryStructureVersion.Status.APPROVED,
        )
        profiles = PayrollEmployeeProfile.objects.filter(entity_id=entity_id, status=PayrollEmployeeProfile.Status.ACTIVE)
        posting_maps = PayrollComponentPosting.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            is_active=True,
        )
        ledger_policy = PayrollLedgerPolicy.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            is_active=True,
        )
        periods = PayrollPeriod.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        if period_code:
            periods = periods.filter(code=period_code)

        result.summary = {
            "component_count": components.count(),
            "salary_structure_count": structures.count(),
            "salary_structure_version_count": structure_versions.count(),
            "employee_profile_count": profiles.count(),
            "posting_map_count": posting_maps.count(),
            "ledger_policy_count": ledger_policy.count(),
            "period_count": periods.count(),
        }

        if not components.exists():
            result.add_issue("missing_components", "No active payroll components configured for the entity.")
        if not structures.exists():
            result.add_issue("missing_salary_structures", "No active salary structures configured for the entity.")
        if not structure_versions.exists():
            result.add_issue("missing_salary_structure_versions", "No approved salary structure versions found.")
        if not profiles.exists():
            result.add_issue("missing_employee_profiles", "No active payroll employee profiles found.")
        if not posting_maps.exists():
            result.add_issue("missing_component_posting", "No active payroll component posting mappings found for the rollout scope.")
        if not ledger_policy.exists():
            result.add_issue("missing_ledger_policy", "No active payroll ledger policy found for the rollout scope.")
        if not periods.exists():
            result.add_issue("missing_payroll_period", "No payroll period found for the rollout scope.")

        if periods.filter(status__in=[PayrollPeriod.Status.LOCKED, PayrollPeriod.Status.CLOSED]).exists():
            result.add_issue(
                "period_not_open",
                "Requested payroll period is not open.",
                severity=IssueSeverity.WARNING,
            )

        scoped_profiles = profiles.filter(subentity_id=subentity_id) if subentity_id is not None else profiles.filter(subentity__isnull=True)
        result.checks["scoped_profile_count"] = scoped_profiles.count()
        if profiles.exists() and not scoped_profiles.exists():
            result.add_issue("profile_scope_mismatch", "Employee payroll profiles exist, but none match the requested subentity scope.")

        missing_structure_versions = profiles.filter(salary_structure__isnull=False, salary_structure_version__isnull=True).count()
        result.checks["profiles_missing_structure_version"] = missing_structure_versions
        if missing_structure_versions:
            result.add_issue(
                "profiles_missing_structure_version",
                "Some payroll employee profiles do not point to an explicit salary structure version.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_structure_versions},
            )

        missing_payment_accounts = profiles.filter(payment_account__isnull=True).count()
        result.checks["profiles_missing_payment_account"] = missing_payment_accounts
        if missing_payment_accounts:
            result.add_issue(
                "profiles_missing_payment_account",
                "Some active employee profiles are missing payment accounts.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_payment_accounts},
            )

        numbering_ok = DocumentType.objects.filter(module="payroll", default_code="PRUN", is_active=True).exists()
        result.checks["numbering_document_type_present"] = numbering_ok
        if not numbering_ok:
            result.add_issue(
                "missing_numbering_document_type",
                "Payroll document type PRUN is not configured in numbering.",
                severity=IssueSeverity.WARNING,
            )

        role_check = cls._validate_permissions(entity_id=entity_id)
        result.checks["permission_check"] = role_check
        if role_check["status"] != "pass":
            result.add_issue(
                "permission_setup_incomplete",
                role_check["message"],
                severity=IssueSeverity.WARNING,
            )

        return result

    @staticmethod
    def _validate_permissions(*, entity_id: int) -> dict[str, str]:
        Role = apps.get_model("entity", "Role")
        role_count = Role.objects.filter(entity_id=entity_id).count()
        if role_count == 0:
            return {"status": "warn", "message": "No entity roles found. Approval segregation may be incomplete."}
        return {"status": "pass", "message": f"{role_count} entity roles found."}
