from __future__ import annotations

from decimal import Decimal

from django.apps import apps
from django.db import models

from numbering.models import DocumentType
from payroll.models import (
    ContractPayrollInputSnapshot,
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    PayrollComponent,
    PayrollComponentPosting,
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

    REQUIRED_CALCULATION_POLICY_KEYS = ("country_code", "salary_mode", "proration_basis", "rounding_policy")
    REQUIRED_TAX_POLICY_METADATA_KEYS = (
        "tax_policy_code",
        "tax_policy_version",
        "tax_policy_financial_year",
        "tax_policy_effective_from",
    )

    @staticmethod
    def _q(value) -> Decimal:
        try:
            return Decimal(str(value or 0))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _normalize_tax_regime(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"new", "new_regime"}:
            return "new_regime"
        if normalized in {"old", "old_regime"}:
            return "old_regime"
        return normalized or "old_regime"

    @staticmethod
    def _policy_flag(policy: dict | None, key: str, default: bool = True) -> bool:
        raw = (policy or {}).get(key)
        if raw in (None, ""):
            return default
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _has_tds_policy_content(policy: dict | None) -> bool:
        if not policy:
            return False
        return any(str(key).startswith("tds_") for key in policy.keys())

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
        profiles = ContractPayrollProfile.objects.filter(
            entity_id=entity_id,
            is_active=True,
        ).select_related(
            "hrms_contract__subentity",
            "bank_account",
        )
        if subentity_id is not None:
            profiles = profiles.filter(hrms_contract__subentity_id=subentity_id)
        else:
            profiles = profiles.filter(hrms_contract__subentity__isnull=True)
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

        profile_rows = list(profiles)
        assignment_qs = ContractSalaryStructureAssignment.objects.select_related(
            "salary_structure_version",
            "salary_structure__current_version",
        ).prefetch_related(
            "salary_structure_version__lines__component",
            "salary_structure__current_version__lines__component",
        ).filter(
            contract_payroll_profile_id__in=[profile.id for profile in profile_rows],
            is_active=True,
        )
        assignment_by_profile: dict[str, ContractSalaryStructureAssignment] = {}
        for assignment in assignment_qs.order_by("contract_payroll_profile_id", "-effective_from", "-id"):
            assignment_by_profile.setdefault(str(assignment.contract_payroll_profile_id), assignment)

        projection_qs = ContractPayrollInputSnapshot.objects.filter(
            contract_payroll_profile_id__in=[profile.id for profile in profile_rows],
            input_type=ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
            is_active=True,
        )
        if period_code:
            projection_qs = projection_qs.filter(payroll_period__code=period_code)
        projection_by_profile: dict[str, dict] = {}
        for snapshot in projection_qs.order_by("contract_payroll_profile_id", "-effective_from", "-id"):
            projection_by_profile.setdefault(str(snapshot.contract_payroll_profile_id), snapshot.input_json or {})

        result.summary = {
            "component_count": components.count(),
            "salary_structure_count": structures.count(),
            "salary_structure_version_count": structure_versions.count(),
            "employee_profile_count": len(profile_rows),
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
        if not profile_rows:
            result.add_issue("missing_employee_profiles", "No active contract payroll profiles found.")
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

        result.checks["scoped_profile_count"] = len(profile_rows)

        missing_structure_versions = sum(
            1
            for assignment in assignment_by_profile.values()
            if assignment.salary_structure_id and assignment.salary_structure_version_id is None
        )
        result.checks["profiles_missing_structure_version"] = missing_structure_versions
        if missing_structure_versions:
            result.add_issue(
                "profiles_missing_structure_version",
                "Some contract payroll profiles do not point to an explicit salary structure version.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_structure_versions},
            )

        pinned_outdated_versions = sum(
            1
            for assignment in assignment_by_profile.values()
            if assignment.salary_structure_id
            and assignment.salary_structure_version_id
            and getattr(assignment.salary_structure, "current_version_id", None)
            and assignment.salary_structure_version_id != assignment.salary_structure.current_version_id
        )
        result.checks["profiles_outdated_structure_version"] = pinned_outdated_versions
        if pinned_outdated_versions:
            result.add_issue(
                "profiles_outdated_structure_version",
                "Some payroll employee profiles are pinned to an older salary structure version.",
                severity=IssueSeverity.WARNING,
                detail={"count": pinned_outdated_versions},
            )

        versions_missing_policy = 0
        versions_with_incomplete_policy = 0
        versions_missing_tax_policy_metadata = 0
        for version in structure_versions.only("id", "calculation_policy_json"):
            policy = version.calculation_policy_json or {}
            if not policy:
                versions_missing_policy += 1
                continue
            if any(not policy.get(key) for key in cls.REQUIRED_CALCULATION_POLICY_KEYS):
                versions_with_incomplete_policy += 1
            if cls._has_tds_policy_content(policy) and any(not policy.get(key) for key in cls.REQUIRED_TAX_POLICY_METADATA_KEYS):
                versions_missing_tax_policy_metadata += 1

        result.checks["approved_versions_missing_calculation_policy"] = versions_missing_policy
        if versions_missing_policy:
            result.add_issue(
                "approved_versions_missing_calculation_policy",
                "Some approved salary structure versions do not define calculation policy metadata.",
                severity=IssueSeverity.WARNING,
                detail={"count": versions_missing_policy},
            )

        result.checks["approved_versions_incomplete_calculation_policy"] = versions_with_incomplete_policy
        if versions_with_incomplete_policy:
            result.add_issue(
                "approved_versions_incomplete_calculation_policy",
                "Some approved salary structure versions are missing required calculation policy fields.",
                severity=IssueSeverity.WARNING,
                detail={
                    "count": versions_with_incomplete_policy,
                    "required_keys": list(cls.REQUIRED_CALCULATION_POLICY_KEYS),
                },
            )

        result.checks["approved_versions_missing_tax_policy_metadata"] = versions_missing_tax_policy_metadata
        if versions_missing_tax_policy_metadata:
            result.add_issue(
                "approved_versions_missing_tax_policy_metadata",
                "Some approved salary structure versions define TDS policy controls without tax policy identity metadata.",
                severity=IssueSeverity.WARNING,
                detail={
                    "count": versions_missing_tax_policy_metadata,
                    "required_keys": list(cls.REQUIRED_TAX_POLICY_METADATA_KEYS),
                },
            )

        missing_payment_accounts = sum(1 for profile in profile_rows if not profile.bank_account_id)
        result.checks["profiles_missing_payment_account"] = missing_payment_accounts
        if missing_payment_accounts:
            result.add_issue(
                "profiles_missing_payment_account",
                "Some active contract payroll profiles are missing payment accounts.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_payment_accounts},
            )

        new_regime_with_old_regime_deductions = 0
        missing_previous_employer_taxable_income = 0
        conflicting_tds_projection_inputs = 0
        policy_disabled_old_regime_bucket_count = 0
        mixed_generic_and_structured_deductions_count = 0
        hra_exemption_without_hra_component_count = 0
        hra_exemption_missing_support_inputs_count = 0
        invalid_hra_rent_months_count = 0
        missing_hra_landlord_pan_flag_count = 0
        unverified_hra_evidence_count = 0
        unverified_80c_evidence_count = 0
        unverified_80d_evidence_count = 0
        profiles_with_unverified_tax_declarations_count = 0
        deduction_values_above_policy_caps_count = 0
        profiles_using_legacy_declared_deductions_count = 0
        for profile in profile_rows:
            projection = projection_by_profile.get(str(profile.id), {})
            tax_regime = cls._normalize_tax_regime(profile.tax_regime)
            assignment = assignment_by_profile.get(str(profile.id))
            version = None if assignment is None else assignment.salary_structure_version or getattr(assignment.salary_structure, "current_version", None)
            policy = getattr(version, "calculation_policy_json", None) or {}
            version_lines = []
            if version is not None:
                lines_manager = getattr(version, "lines", None)
                if lines_manager is not None:
                    version_lines = list(lines_manager.all())
            has_hra_component = any(
                str(getattr(getattr(line, "component", None), "code", "")).upper().startswith("HRA")
                for line in version_lines
            )
            old_regime_only_inputs = (
                cls._q(projection.get("declared_deductions"))
                + cls._q(projection.get("deduction_80c"))
                + cls._q(projection.get("deduction_80d"))
                + cls._q(projection.get("hra_exemption"))
            )
            previous_employer_income = cls._q(projection.get("previous_employer_income"))
            previous_employer_taxable_income = cls._q(projection.get("previous_employer_taxable_income"))
            projected_taxable_income = cls._q(projection.get("projected_taxable_income"))
            annual_tax = cls._q(projection.get("annual_tax"))

            if tax_regime == "new_regime" and old_regime_only_inputs > 0:
                new_regime_with_old_regime_deductions += 1
            if tax_regime == "old_regime":
                if cls._q(projection.get("declared_deductions")) > 0 and cls._q(projection.get("other_old_regime_deductions")) <= 0:
                    profiles_using_legacy_declared_deductions_count += 1
                if (
                    cls._q(projection.get("declared_deductions")) > 0
                    and (
                        cls._q(projection.get("deduction_80c")) > 0
                        or cls._q(projection.get("deduction_80d")) > 0
                        or cls._q(projection.get("hra_exemption")) > 0
                    )
                ):
                    mixed_generic_and_structured_deductions_count += 1
                if (
                    cls._q(projection.get("deduction_80c")) > 0
                    and not cls._policy_flag(policy, "tds_allow_80c_old_regime", True)
                ) or (
                    cls._q(projection.get("deduction_80d")) > 0
                    and not cls._policy_flag(policy, "tds_allow_80d_old_regime", True)
                ) or (
                    cls._q(projection.get("hra_exemption")) > 0
                    and not cls._policy_flag(policy, "tds_allow_hra_exemption_old_regime", True)
                ):
                    policy_disabled_old_regime_bucket_count += 1
                if cls._q(projection.get("hra_exemption")) > 0 and not has_hra_component:
                    hra_exemption_without_hra_component_count += 1
                if (
                    cls._q(projection.get("hra_exemption")) > 0
                    and (
                        cls._q(projection.get("hra_rent_paid_annual")) <= 0
                        or projection.get("hra_is_metro_city") is None
                    )
                ):
                    hra_exemption_missing_support_inputs_count += 1
                if (
                    cls._q(projection.get("hra_rent_paid_annual")) > 0
                    and (
                        cls._q(projection.get("hra_rent_months")) <= 0
                        or cls._q(projection.get("hra_rent_months")) > 12
                    )
                ):
                    invalid_hra_rent_months_count += 1
                if (
                    cls._q(projection.get("hra_rent_paid_annual")) > 0
                    and projection.get("hra_landlord_pan_available") is None
                ):
                    missing_hra_landlord_pan_flag_count += 1
                if (
                    cls._q(projection.get("hra_rent_paid_annual")) > 0
                    and projection.get("hra_evidence_verified") is not True
                ):
                    unverified_hra_evidence_count += 1
                has_unverified_80c = (
                    cls._q(projection.get("deduction_80c")) > 0
                    and projection.get("deduction_80c_evidence_verified") is not True
                )
                has_unverified_80d = (
                    cls._q(projection.get("deduction_80d")) > 0
                    and projection.get("deduction_80d_evidence_verified") is not True
                )
                if has_unverified_80c:
                    unverified_80c_evidence_count += 1
                if has_unverified_80d:
                    unverified_80d_evidence_count += 1
                if has_unverified_80c or has_unverified_80d:
                    profiles_with_unverified_tax_declarations_count += 1
                if (
                    cls._q(projection.get("deduction_80c")) > cls._q(policy.get("tds_80c_cap") or "150000.00")
                    or cls._q(projection.get("deduction_80d")) > cls._q(policy.get("tds_80d_cap") or "25000.00")
                ):
                    deduction_values_above_policy_caps_count += 1
            if previous_employer_income > 0 and previous_employer_taxable_income <= 0:
                missing_previous_employer_taxable_income += 1
            if projected_taxable_income > 0 and annual_tax > 0:
                conflicting_tds_projection_inputs += 1

        result.checks["profiles_with_new_regime_old_regime_tds_declarations"] = new_regime_with_old_regime_deductions
        if new_regime_with_old_regime_deductions:
            result.add_issue(
                "profiles_with_new_regime_old_regime_tds_declarations",
                "Some new-regime contract payroll profiles still carry old-regime TDS deduction declarations.",
                severity=IssueSeverity.WARNING,
                detail={"count": new_regime_with_old_regime_deductions},
            )

        result.checks["profiles_missing_previous_employer_taxable_income"] = missing_previous_employer_taxable_income
        if missing_previous_employer_taxable_income:
            result.add_issue(
                "profiles_missing_previous_employer_taxable_income",
                "Some payroll profiles have previous-employer income but no explicit taxable carry-in amount.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_previous_employer_taxable_income},
            )

        result.checks["profiles_with_conflicting_tds_projection_inputs"] = conflicting_tds_projection_inputs
        if conflicting_tds_projection_inputs:
            result.add_issue(
                "profiles_with_conflicting_tds_projection_inputs",
                "Some payroll profiles define both projected taxable income and projected annual tax for TDS.",
                severity=IssueSeverity.WARNING,
                detail={"count": conflicting_tds_projection_inputs},
            )

        result.checks["profiles_with_policy_disabled_old_regime_tds_buckets"] = policy_disabled_old_regime_bucket_count
        if policy_disabled_old_regime_bucket_count:
            result.add_issue(
                "profiles_with_policy_disabled_old_regime_tds_buckets",
                "Some old-regime payroll profiles declare TDS deduction buckets that are disabled by structure policy.",
                severity=IssueSeverity.WARNING,
                detail={"count": policy_disabled_old_regime_bucket_count},
            )

        result.checks["profiles_with_mixed_generic_and_structured_tds_deductions"] = mixed_generic_and_structured_deductions_count
        if mixed_generic_and_structured_deductions_count:
            result.add_issue(
                "profiles_with_mixed_generic_and_structured_tds_deductions",
                "Some old-regime payroll profiles define both generic declared deductions and structured TDS deduction buckets.",
                severity=IssueSeverity.WARNING,
                detail={"count": mixed_generic_and_structured_deductions_count},
            )

        result.checks["profiles_with_hra_exemption_without_hra_component"] = hra_exemption_without_hra_component_count
        if hra_exemption_without_hra_component_count:
            result.add_issue(
                "profiles_with_hra_exemption_without_hra_component",
                "Some payroll profiles declare HRA exemption but the linked structure version has no HRA component line.",
                severity=IssueSeverity.WARNING,
                detail={"count": hra_exemption_without_hra_component_count},
            )

        result.checks["profiles_with_hra_exemption_missing_support_inputs"] = hra_exemption_missing_support_inputs_count
        if hra_exemption_missing_support_inputs_count:
            result.add_issue(
                "profiles_with_hra_exemption_missing_support_inputs",
                "Some payroll profiles declare HRA exemption without complete HRA support inputs like annual rent paid or metro/non-metro status.",
                severity=IssueSeverity.WARNING,
                detail={"count": hra_exemption_missing_support_inputs_count},
            )

        result.checks["profiles_with_invalid_hra_rent_months"] = invalid_hra_rent_months_count
        if invalid_hra_rent_months_count:
            result.add_issue(
                "profiles_with_invalid_hra_rent_months",
                "Some payroll profiles capture annual HRA rent paid but do not provide a valid rent-month count between 1 and 12.",
                severity=IssueSeverity.WARNING,
                detail={"count": invalid_hra_rent_months_count},
            )

        result.checks["profiles_with_hra_missing_landlord_pan_flag"] = missing_hra_landlord_pan_flag_count
        if missing_hra_landlord_pan_flag_count:
            result.add_issue(
                "profiles_with_hra_missing_landlord_pan_flag",
                "Some payroll profiles capture HRA rent support but do not explicitly record landlord PAN evidence availability.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_hra_landlord_pan_flag_count},
            )

        result.checks["profiles_with_unverified_hra_evidence"] = unverified_hra_evidence_count
        if unverified_hra_evidence_count:
            result.add_issue(
                "profiles_with_unverified_hra_evidence",
                "Some payroll profiles capture HRA rent support but the underlying HRA evidence is not explicitly marked as verified yet.",
                severity=IssueSeverity.WARNING,
                detail={"count": unverified_hra_evidence_count},
            )

        result.checks["profiles_with_unverified_80c_evidence"] = unverified_80c_evidence_count
        if unverified_80c_evidence_count:
            result.add_issue(
                "profiles_with_unverified_80c_evidence",
                "Some payroll profiles declare 80C deductions but the underlying 80C evidence is not explicitly marked as verified yet.",
                severity=IssueSeverity.WARNING,
                detail={"count": unverified_80c_evidence_count},
            )

        result.checks["profiles_with_unverified_80d_evidence"] = unverified_80d_evidence_count
        if unverified_80d_evidence_count:
            result.add_issue(
                "profiles_with_unverified_80d_evidence",
                "Some payroll profiles declare 80D deductions but the underlying 80D evidence is not explicitly marked as verified yet.",
                severity=IssueSeverity.WARNING,
                detail={"count": unverified_80d_evidence_count},
            )

        result.checks["profiles_with_unverified_tax_declaration_evidence"] = profiles_with_unverified_tax_declarations_count
        if profiles_with_unverified_tax_declarations_count:
            result.add_issue(
                "profiles_with_unverified_tax_declaration_evidence",
                "Some payroll profiles declare 80C or 80D deductions without explicitly verified declaration evidence.",
                severity=IssueSeverity.WARNING,
                detail={"count": profiles_with_unverified_tax_declarations_count},
            )

        result.checks["profiles_with_tds_deduction_values_above_policy_caps"] = deduction_values_above_policy_caps_count
        if deduction_values_above_policy_caps_count:
            result.add_issue(
                "profiles_with_tds_deduction_values_above_policy_caps",
                "Some payroll profiles declare TDS deduction bucket values above configured policy caps.",
                severity=IssueSeverity.WARNING,
                detail={"count": deduction_values_above_policy_caps_count},
            )

        result.checks["profiles_using_legacy_tds_declared_deductions"] = profiles_using_legacy_declared_deductions_count
        if profiles_using_legacy_declared_deductions_count:
            result.add_issue(
                "profiles_using_legacy_tds_declared_deductions",
                "Some old-regime payroll profiles still rely on the legacy generic declared-deductions field instead of the explicit other old-regime deductions bucket.",
                severity=IssueSeverity.WARNING,
                detail={"count": profiles_using_legacy_declared_deductions_count},
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
        try:
            Role = apps.get_model("entity", "Role")
        except LookupError:
            return {
                "status": "warn",
                "message": "Entity role model is not available. Approval segregation could not be verified.",
            }
        role_count = Role.objects.filter(entity_id=entity_id).count()
        if role_count == 0:
            return {"status": "warn", "message": "No entity roles found. Approval segregation may be incomplete."}
        return {"status": "pass", "message": f"{role_count} entity roles found."}
