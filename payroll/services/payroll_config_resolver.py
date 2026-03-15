from __future__ import annotations

from django.db.models import Q

from payroll.models import PayrollComponentPosting, PayrollLedgerPolicy, SalaryStructureVersion


class PayrollConfigResolver:
    """
    Resolve effective-dated payroll configuration for a payroll run date.
    """

    @staticmethod
    def resolve_salary_structure_version(*, profile, on_date):
        if getattr(profile, "salary_structure_version_id", None):
            return profile.salary_structure_version
        if not getattr(profile, "salary_structure_id", None):
            return None
        return (
            SalaryStructureVersion.objects.filter(
                salary_structure_id=profile.salary_structure_id,
                status=SalaryStructureVersion.Status.APPROVED,
                effective_from__lte=on_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
            .order_by("-effective_from", "-version_no")
            .first()
        )

    @staticmethod
    def resolve_ledger_policy(*, entity_id, entityfinid_id, subentity_id, on_date):
        return (
            PayrollLedgerPolicy.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                is_active=True,
                effective_from__lte=on_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
            .order_by("-effective_from", "-version_no")
            .first()
        )

    @staticmethod
    def resolve_component_posting(*, entity_id, entityfinid_id, subentity_id, component_id, on_date):
        return (
            PayrollComponentPosting.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                component_id=component_id,
                is_active=True,
                effective_from__lte=on_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
            .order_by("-effective_from", "-version_no")
            .first()
        )
