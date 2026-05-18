from __future__ import annotations

from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from hrms.models import HrEmploymentContract
from payroll.models import ContractPayrollProfile


class ContractPayrollProfileService:
    ACTIVE_CONTRACT_STATUSES = {
        HrEmploymentContract.ContractStatus.ACTIVE,
        HrEmploymentContract.ContractStatus.SUSPENDED,
        HrEmploymentContract.ContractStatus.NOTICE,
    }

    @staticmethod
    def list_profiles(
        *,
        entity_id: int,
        subentity_id: int | None = None,
        search: str | None = None,
        payroll_status: str | None = None,
        pay_frequency: str | None = None,
        is_active: bool | None = None,
        hrms_contract_id: str | None = None,
    ):
        queryset = ContractPayrollProfile.objects.select_related(
            "entity",
            "hrms_contract",
            "hrms_contract__employee",
            "bank_account",
        ).filter(entity_id=entity_id)
        if subentity_id is not None:
            queryset = queryset.filter(hrms_contract__subentity_id=subentity_id)
        if search:
            queryset = queryset.filter(
                Q(hrms_contract__contract_code__icontains=search)
                | Q(hrms_contract__employee__employee_number__icontains=search)
                | Q(hrms_contract__employee__display_name__icontains=search)
            )
        if payroll_status:
            queryset = queryset.filter(payroll_status=payroll_status)
        if pay_frequency:
            queryset = queryset.filter(pay_frequency=pay_frequency)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if hrms_contract_id:
            queryset = queryset.filter(hrms_contract_id=hrms_contract_id)
        return queryset.order_by("-payroll_start_date", "hrms_contract__contract_code")

    @classmethod
    def validate_hrms_contract(cls, *, contract: HrEmploymentContract, entity_id: int) -> None:
        if contract.entity_id != entity_id:
            raise ValueError("HRMS contract must belong to the selected entity.")
        if not contract.is_payroll_eligible:
            raise ValueError("Selected HRMS contract is not payroll eligible.")
        if contract.status not in cls.ACTIVE_CONTRACT_STATUSES:
            raise ValueError("Selected HRMS contract is not in a payroll-eligible status.")

    @classmethod
    @transaction.atomic
    def create_or_update_profile(
        cls,
        payload: dict[str, Any],
        *,
        instance: ContractPayrollProfile | None = None,
    ) -> ContractPayrollProfile:
        entity_id = getattr(payload.get("entity"), "id", None) or payload.get("entity_id") or getattr(instance, "entity_id", None)
        contract = payload.get("hrms_contract") or getattr(instance, "hrms_contract", None)
        if contract is None:
            raise ValueError("HRMS contract is required.")
        if entity_id is None:
            raise ValueError("Entity is required.")
        cls.validate_hrms_contract(contract=contract, entity_id=entity_id)

        profile = instance or ContractPayrollProfile(entity_id=entity_id, hrms_contract=contract)
        incoming_is_active = payload.get("is_active", getattr(profile, "is_active", True))
        if incoming_is_active:
            duplicate = ContractPayrollProfile.objects.filter(hrms_contract=contract, is_active=True)
            if instance:
                duplicate = duplicate.exclude(pk=instance.pk)
            if duplicate.exists():
                raise ValueError("An active contract payroll profile already exists for this HRMS contract.")
        for field in (
            "entity",
            "hrms_contract",
            "pay_frequency",
            "payroll_status",
            "tax_regime",
            "payment_mode",
            "bank_account",
            "bank_account_details",
            "payroll_start_date",
            "payroll_end_date",
            "pf_applicable",
            "esi_applicable",
            "pt_applicable",
            "tds_applicable",
            "lwf_applicable",
            "overtime_eligible",
            "attendance_required",
            "metadata",
            "is_active",
        ):
            if field in payload:
                setattr(profile, field, payload[field])
        if profile.metadata is None:
            profile.metadata = {}
        if profile.bank_account_details is None:
            profile.bank_account_details = {}
        try:
            profile.full_clean()
            profile.save()
        except DjangoValidationError as err:
            if hasattr(err, "message_dict"):
                first_message = next(iter(err.message_dict.values()))[0]
                raise ValueError(first_message) from err
            raise ValueError(str(err)) from err
        return profile

    @staticmethod
    def get_active_profile_for_contract(*, hrms_contract: HrEmploymentContract, as_of_date: date | None = None):
        as_of_date = as_of_date or hrms_contract.payroll_effective_from
        return (
            ContractPayrollProfile.objects.select_related("hrms_contract", "bank_account")
            .filter(
                hrms_contract=hrms_contract,
                is_active=True,
                payroll_start_date__lte=as_of_date,
            )
            .filter(Q(payroll_end_date__isnull=True) | Q(payroll_end_date__gte=as_of_date))
            .exclude(payroll_status=ContractPayrollProfile.PayrollStatus.ENDED)
            .order_by("-payroll_start_date", "-id")
            .first()
        )

    @classmethod
    def resolve_contract_payroll_profile(cls, contract: HrEmploymentContract, as_of_date: date | None = None):
        return cls.get_active_profile_for_contract(hrms_contract=contract, as_of_date=as_of_date)
