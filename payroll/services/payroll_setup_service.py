from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Max, Q
from django.utils import timezone

from payroll.models import (
    ContractAttendanceSummary,
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    PayrollComponentPosting,
    PayrollLedgerPolicy,
    PayrollPeriod,
    PayrollRun,
    PayrollRunEmployee,
    SalaryStructureLine,
    SalaryStructureVersion,
)


class PayrollSetupService:
    """
    Setup validation helpers for payroll master APIs.
    """

    REQUIRED_CALCULATION_POLICY_KEYS = ("country_code", "salary_mode", "proration_basis", "rounding_policy")

    @staticmethod
    def validate_period_overlap(*, instance: PayrollPeriod | None, attrs: dict) -> None:
        entity = attrs.get("entity") or getattr(instance, "entity", None)
        entityfinid = attrs.get("entityfinid") or getattr(instance, "entityfinid", None)
        subentity = attrs.get("subentity") if "subentity" in attrs else getattr(instance, "subentity", None)
        pay_frequency = attrs.get("pay_frequency") or getattr(instance, "pay_frequency", None)
        period_start = attrs.get("period_start") or getattr(instance, "period_start", None)
        period_end = attrs.get("period_end") or getattr(instance, "period_end", None)
        if not all([entity, entityfinid, pay_frequency, period_start, period_end]):
            return

        overlap_qs = PayrollPeriod.objects.filter(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            pay_frequency=pay_frequency,
            period_start__lte=period_end,
            period_end__gte=period_start,
        )
        if instance and instance.pk:
            overlap_qs = overlap_qs.exclude(pk=instance.pk)
        if overlap_qs.exists():
            raise ValidationError("Overlapping payroll periods are not allowed for the same scope and pay frequency.")

    @staticmethod
    def assert_period_dates_editable(period: PayrollPeriod, changed_fields: set[str]) -> None:
        critical_fields = {"period_start", "period_end", "payout_date", "pay_frequency", "entity", "entityfinid", "subentity"}
        if changed_fields.intersection(critical_fields) and period.runs.exists():
            raise ValidationError("Payroll period dates and scope cannot be edited once payroll runs exist.")

    @staticmethod
    def assert_period_can_lock(period: PayrollPeriod) -> None:
        unfinished_runs = period.runs.exclude(
            status__in=[PayrollRun.Status.POSTED, PayrollRun.Status.CANCELLED, PayrollRun.Status.REVERSED]
        )
        if unfinished_runs.exists():
            raise ValidationError("Payroll period cannot be locked while unfinished payroll runs exist.")

    @staticmethod
    def assert_period_can_close(period: PayrollPeriod) -> None:
        unfinished_runs = period.runs.exclude(status=PayrollRun.Status.POSTED)
        if unfinished_runs.exclude(status=PayrollRun.Status.REVERSED).exclude(status=PayrollRun.Status.CANCELLED).exists():
            raise ValidationError("Payroll period cannot be closed until all runs are posted, cancelled, or reversed.")

    @staticmethod
    def transition_period(*, period: PayrollPeriod, action: str, user=None, note: str = "") -> PayrollPeriod:
        if action == "open":
            period.status = PayrollPeriod.Status.OPEN
        elif action == "lock":
            PayrollSetupService.assert_period_can_lock(period)
            period.status = PayrollPeriod.Status.LOCKED
            period.locked_at = timezone.now()
            if user:
                period.locked_by = user
        elif action == "close":
            PayrollSetupService.assert_period_can_close(period)
            period.status = PayrollPeriod.Status.CLOSED
            period.closed_at = timezone.now()
            period.close_note = note or period.close_note
            if user:
                period.closed_by = user
        else:
            raise ValidationError("Unsupported payroll period action.")
        period.save()
        return period

    @staticmethod
    def create_structure_version(*, structure, lines: list[dict], approved_by=None, calculation_policy_json: dict | None = None) -> SalaryStructureVersion:
        next_version = (
            structure.versions.aggregate(max_version=Max("version_no")).get("max_version") or 0
        ) + 1
        version = SalaryStructureVersion.objects.create(
            salary_structure=structure,
            version_no=next_version,
            effective_from=timezone.localdate(),
            status=SalaryStructureVersion.Status.APPROVED,
            calculation_policy_json=calculation_policy_json or {},
            approved_by=approved_by,
            approved_at=timezone.now() if approved_by else None,
            notes=f"Generated from setup API on version {next_version}.",
        )
        for line in lines:
            SalaryStructureLine.objects.create(
                salary_structure=structure,
                salary_structure_version=version,
                component=line["component"],
                sequence=line.get("sequence", 100),
                rule_mode=line.get("rule_mode", SalaryStructureLine.RuleMode.STANDARD),
                calculation_basis=line.get("calculation_basis", SalaryStructureLine.CalculationBasis.INPUT),
                basis_component=line.get("basis_component"),
                rate=line.get("rate", 0),
                fixed_amount=line.get("fixed_amount", 0),
                is_pro_rated=line.get("is_pro_rated", True),
                is_override_allowed=line.get("is_override_allowed", False),
                is_active=line.get("is_active", True),
                recurrence_frequency=line.get("recurrence_frequency", SalaryStructureLine.RecurrenceFrequency.MONTHLY),
                compensation_bucket=line.get("compensation_bucket", SalaryStructureLine.CompensationBucket.FIXED_PAY),
                ctc_treatment=line.get("ctc_treatment", SalaryStructureLine.CTCTreatment.INCLUDED),
                gross_treatment=line.get("gross_treatment", SalaryStructureLine.GrossTreatment.INCLUDED),
                rule_json=line.get("rule_json"),
            )
        structure.current_version = version
        structure.save(update_fields=["current_version"])
        return version

    @staticmethod
    def readiness_summary(*, entity_id: int | None = None, entityfinid_id: int | None = None, subentity_id: int | None = None):
        profiles = ContractPayrollProfile.objects.select_related("hrms_contract__subentity", "bank_account")
        if entity_id:
            profiles = profiles.filter(entity_id=entity_id)
        if subentity_id is not None:
            profiles = profiles.filter(hrms_contract__subentity_id=subentity_id)
        profile_rows = list(profiles)

        assignment_qs = ContractSalaryStructureAssignment.objects.select_related(
            "salary_structure",
            "salary_structure__current_version",
            "salary_structure_version",
        ).filter(
            contract_payroll_profile_id__in=[profile.id for profile in profile_rows],
            is_active=True,
        )
        assignment_by_profile: dict[str, ContractSalaryStructureAssignment] = {}
        for assignment in assignment_qs.order_by("contract_payroll_profile_id", "-effective_from", "-id"):
            assignment_by_profile.setdefault(str(assignment.contract_payroll_profile_id), assignment)

        summary_qs = ContractAttendanceSummary.objects.filter(
            contract_payroll_profile_id__in=[profile.id for profile in profile_rows],
            is_active=True,
        )
        summary_by_profile: dict[str, ContractAttendanceSummary] = {}
        for summary in summary_qs.order_by("contract_payroll_profile_id", "-payroll_period__period_end", "-id"):
            summary_by_profile.setdefault(str(summary.contract_payroll_profile_id), summary)

        posting_maps = PayrollComponentPosting.objects.filter(is_active=True)
        ledger_policies = PayrollLedgerPolicy.objects.filter(is_active=True)
        if entity_id:
            posting_maps = posting_maps.filter(entity_id=entity_id)
            ledger_policies = ledger_policies.filter(entity_id=entity_id)
        if entityfinid_id:
            posting_maps = posting_maps.filter(entityfinid_id=entityfinid_id)
            ledger_policies = ledger_policies.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            posting_maps = posting_maps.filter(subentity_id=subentity_id)
            ledger_policies = ledger_policies.filter(subentity_id=subentity_id)

        negative_rows = PayrollRunEmployee.objects.filter(payable_amount__lt=0)
        if entity_id:
            negative_rows = negative_rows.filter(payroll_run__entity_id=entity_id)
        if entityfinid_id:
            negative_rows = negative_rows.filter(payroll_run__entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            negative_rows = negative_rows.filter(payroll_run__subentity_id=subentity_id)

        missing_attendance_or_days = 0
        outdated_structure_versions = 0
        profiles_missing_calculation_policy = 0
        profiles_incomplete_calculation_policy = 0
        for profile in profile_rows:
            assignment = assignment_by_profile.get(str(profile.id))
            summary = summary_by_profile.get(str(profile.id))
            if summary is None or not summary.attendance_days or not summary.payable_days:
                missing_attendance_or_days += 1

            current_version_id = getattr(assignment.salary_structure, "current_version_id", None) if assignment and assignment.salary_structure_id else None
            if assignment and assignment.salary_structure_id and assignment.salary_structure_version_id and current_version_id and assignment.salary_structure_version_id != current_version_id:
                outdated_structure_versions += 1

            version = None
            if assignment is not None:
                version = assignment.salary_structure_version or getattr(assignment.salary_structure, "current_version", None)
            if assignment and assignment.salary_structure_id and version is not None:
                policy = version.calculation_policy_json or {}
                if not policy:
                    profiles_missing_calculation_policy += 1
                elif any(not policy.get(key) for key in PayrollSetupService.REQUIRED_CALCULATION_POLICY_KEYS):
                    profiles_incomplete_calculation_policy += 1

        return {
            "missing_payroll_profile_count": sum(1 for profile in profile_rows if str(profile.id) not in assignment_by_profile),
            "missing_payment_details_count": sum(1 for profile in profile_rows if not profile.bank_account_id),
            "missing_tax_regime_count": sum(1 for profile in profile_rows if not profile.tax_regime),
            "missing_attendance_payable_days_count": missing_attendance_or_days,
            "missing_ledger_mapping_count": 0 if posting_maps.exists() and ledger_policies.exists() else len(profile_rows),
            "negative_net_pay_count": negative_rows.count(),
            "outdated_structure_version_count": outdated_structure_versions,
            "missing_calculation_policy_count": profiles_missing_calculation_policy,
            "incomplete_calculation_policy_count": profiles_incomplete_calculation_policy,
        }
