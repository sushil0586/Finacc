from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import ContractPayrollProfile, ContractStatutoryProfile, StatutoryScheme


class ContractStatutoryProfileService:
    @staticmethod
    def list_profiles(
        *,
        entity_id: int,
        search: str | None = None,
        contract_payroll_profile_id: str | None = None,
        scheme_id: str | None = None,
        is_active: bool | None = None,
        is_applicable: bool | None = None,
    ):
        queryset = ContractStatutoryProfile.objects.select_related(
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "scheme",
        ).filter(contract_payroll_profile__entity_id=entity_id)
        if search:
            queryset = queryset.filter(
                Q(contract_payroll_profile__hrms_contract__contract_code__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__employee_number__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__display_name__icontains=search)
                | Q(scheme__code__icontains=search)
                | Q(scheme__name__icontains=search)
            )
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if scheme_id:
            queryset = queryset.filter(scheme_id=scheme_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if is_applicable is not None:
            queryset = queryset.filter(is_applicable=is_applicable)
        return queryset.order_by("contract_payroll_profile__hrms_contract__contract_code", "scheme__code", "-effective_from")

    @classmethod
    @transaction.atomic
    def create_or_update_profile(cls, attrs: dict, *, instance: ContractStatutoryProfile | None = None) -> ContractStatutoryProfile:
        profile = instance or ContractStatutoryProfile()
        for key, value in attrs.items():
            setattr(profile, key, value)
        cls._validate_overlap(profile=profile)
        try:
            profile.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        profile.save()
        return profile

    @staticmethod
    def _validate_overlap(*, profile: ContractStatutoryProfile) -> None:
        if not profile.is_active:
            return
        existing = ContractStatutoryProfile.objects.filter(
            contract_payroll_profile=profile.contract_payroll_profile,
            scheme=profile.scheme,
            is_active=True,
        )
        if profile.pk:
            existing = existing.exclude(pk=profile.pk)
        start = profile.effective_from
        end = profile.effective_to or date.max
        for item in existing:
            item_end = item.effective_to or date.max
            if item.effective_from <= end and start <= item_end:
                raise ValueError("Active contract statutory profiles cannot overlap for the same contract and scheme.")

    @staticmethod
    def resolve_contract_statutory_profile(*, contract_payroll_profile: ContractPayrollProfile, scheme: StatutoryScheme, profile_date: date):
        return (
            ContractStatutoryProfile.objects.select_related("scheme")
            .filter(
                contract_payroll_profile=contract_payroll_profile,
                scheme=scheme,
                is_active=True,
                effective_from__lte=profile_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=profile_date))
            .order_by("-effective_from", "-id")
            .first()
        )

    @staticmethod
    def list_applicable_schemes(*, contract_payroll_profile: ContractPayrollProfile, profile_date: date):
        return StatutoryScheme.objects.filter(
            contract_profiles__contract_payroll_profile=contract_payroll_profile,
            contract_profiles__is_active=True,
            contract_profiles__is_applicable=True,
            contract_profiles__effective_from__lte=profile_date,
        ).filter(
            Q(contract_profiles__effective_to__isnull=True) | Q(contract_profiles__effective_to__gte=profile_date)
        ).distinct().order_by("scheme_type", "code")
