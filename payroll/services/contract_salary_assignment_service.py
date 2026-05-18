from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import ContractPayrollProfile, ContractSalaryStructureAssignment, SalaryStructure, SalaryStructureVersion


class ContractSalaryAssignmentService:
    @staticmethod
    def list_assignments(*, contract_payroll_profile_id: str):
        return ContractSalaryStructureAssignment.objects.select_related(
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_version",
        ).filter(contract_payroll_profile_id=contract_payroll_profile_id).order_by("-effective_from", "-id")

    @classmethod
    def validate_assignment(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        salary_structure: SalaryStructure,
        salary_structure_version: SalaryStructureVersion,
        effective_from: date,
        effective_to: date | None,
        instance: ContractSalaryStructureAssignment | None = None,
    ) -> None:
        if effective_to and effective_to < effective_from:
            raise ValueError("Effective end date must be on or after effective start date.")
        if salary_structure_version.salary_structure_id != salary_structure.id:
            raise ValueError("Selected salary structure version must belong to the selected salary structure.")
        if salary_structure.entity_id != contract_payroll_profile.entity_id:
            raise ValueError("Salary structure must belong to the same entity as the contract payroll profile.")
        if salary_structure_version.salary_structure.entity_id != contract_payroll_profile.entity_id:
            raise ValueError("Salary structure version must belong to the same entity as the contract payroll profile.")
        overlap_qs = ContractSalaryStructureAssignment.objects.filter(
            contract_payroll_profile=contract_payroll_profile,
            is_active=True,
        ).exclude(pk=getattr(instance, "pk", None))
        for candidate in overlap_qs:
            candidate_end = candidate.effective_to
            overlaps = (
                (candidate_end is None or effective_from <= candidate_end)
                and (effective_to is None or candidate.effective_from <= effective_to)
            )
            if overlaps:
                raise ValueError("Salary assignment dates overlap with an existing active assignment for this contract payroll profile.")

    @classmethod
    @transaction.atomic
    def assign_salary_structure(
        cls,
        payload: dict[str, Any],
        *,
        instance: ContractSalaryStructureAssignment | None = None,
        close_previous_active: bool = False,
    ) -> ContractSalaryStructureAssignment:
        contract_payroll_profile = payload.get("contract_payroll_profile") or getattr(instance, "contract_payroll_profile", None)
        salary_structure = payload.get("salary_structure") or getattr(instance, "salary_structure", None)
        salary_structure_version = payload.get("salary_structure_version") or getattr(instance, "salary_structure_version", None)
        effective_from = payload.get("effective_from") or getattr(instance, "effective_from", None)
        effective_to = payload.get("effective_to", getattr(instance, "effective_to", None))
        if not all([contract_payroll_profile, salary_structure, salary_structure_version, effective_from]):
            raise ValueError("Contract payroll profile, salary structure, salary structure version, and effective from date are required.")

        if close_previous_active and instance is None:
            previous = cls.get_active_assignment_for_payroll_date(
                contract_payroll_profile=contract_payroll_profile,
                payroll_date=effective_from,
            )
            if previous and previous.effective_from < effective_from:
                previous.effective_to = effective_from - timedelta(days=1)
                previous.assignment_status = ContractSalaryStructureAssignment.AssignmentStatus.SUPERSEDED
                previous.is_active = False
                previous.full_clean()
                previous.save(update_fields=["effective_to", "assignment_status", "is_active", "updated_at"])

        cls.validate_assignment(
            contract_payroll_profile=contract_payroll_profile,
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            effective_from=effective_from,
            effective_to=effective_to,
            instance=instance,
        )

        assignment = instance or ContractSalaryStructureAssignment(contract_payroll_profile=contract_payroll_profile)
        for field in (
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_version",
            "effective_from",
            "effective_to",
            "assignment_status",
            "ctc_amount",
            "gross_amount",
            "metadata",
            "is_active",
        ):
            if field in payload:
                setattr(assignment, field, payload[field])
        if assignment.metadata is None:
            assignment.metadata = {}
        try:
            assignment.full_clean()
            assignment.save()
        except DjangoValidationError as err:
            if hasattr(err, "message_dict"):
                first_message = next(iter(err.message_dict.values()))[0]
                raise ValueError(first_message) from err
            raise ValueError(str(err)) from err
        return assignment

    @staticmethod
    def get_active_assignment_for_payroll_date(*, contract_payroll_profile: ContractPayrollProfile, payroll_date: date):
        return (
            ContractSalaryStructureAssignment.objects.select_related("salary_structure", "salary_structure_version")
            .filter(
                contract_payroll_profile=contract_payroll_profile,
                is_active=True,
                effective_from__lte=payroll_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=payroll_date))
            .exclude(assignment_status=ContractSalaryStructureAssignment.AssignmentStatus.ENDED)
            .order_by("-effective_from", "-id")
            .first()
        )

    @classmethod
    def resolve_contract_salary_assignment(cls, contract, payroll_date: date):
        profile = ContractPayrollProfile.objects.filter(hrms_contract=contract, is_active=True).order_by("-payroll_start_date").first()
        if profile is None:
            return None
        return cls.get_active_assignment_for_payroll_date(contract_payroll_profile=profile, payroll_date=payroll_date)
