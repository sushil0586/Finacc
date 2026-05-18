from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import ContractPayrollProfile, OneTimePayItem, PayrollPeriod


class OneTimePayItemService:
    PAYABLE_STATUSES = {
        OneTimePayItem.ApprovalStatus.APPROVED,
    }

    @staticmethod
    def list_items(
        *,
        entity_id: int,
        search: str | None = None,
        item_type: str | None = None,
        approval_status: str | None = None,
        source_type: str | None = None,
        payroll_component_id: int | None = None,
        contract_payroll_profile_id: str | None = None,
        payroll_period_id: int | None = None,
        is_active: bool | None = None,
    ):
        queryset = OneTimePayItem.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_component",
            "payroll_period",
        ).filter(entity_id=entity_id)
        if search:
            queryset = queryset.filter(
                Q(contract_payroll_profile__hrms_contract__contract_code__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__employee_number__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__display_name__icontains=search)
                | Q(payroll_component__code__icontains=search)
                | Q(payroll_component__name__icontains=search)
                | Q(remarks__icontains=search)
            )
        if item_type:
            queryset = queryset.filter(item_type=item_type)
        if approval_status:
            queryset = queryset.filter(approval_status=approval_status)
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        if payroll_component_id:
            queryset = queryset.filter(payroll_component_id=payroll_component_id)
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if payroll_period_id:
            queryset = queryset.filter(payroll_period_id=payroll_period_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("-effective_date", "-requested_date", "payroll_component__default_sequence", "payroll_component__code")

    @classmethod
    @transaction.atomic
    def create_or_update_item(cls, attrs: dict, *, instance: OneTimePayItem | None = None) -> OneTimePayItem:
        item = instance or OneTimePayItem()
        for key, value in attrs.items():
            setattr(item, key, value)
        cls._validate_approval_status(item)
        try:
            item.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        item.save()
        return item

    @classmethod
    def _validate_approval_status(cls, item: OneTimePayItem) -> None:
        if item.approval_status in {OneTimePayItem.ApprovalStatus.REJECTED, OneTimePayItem.ApprovalStatus.CANCELLED} and item.is_active:
            raise ValueError({"approval_status": ["Rejected or cancelled items must be inactive."]})

    @classmethod
    def resolve_payable_items(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_date: date | None = None,
        payroll_period: PayrollPeriod | None = None,
    ):
        queryset = OneTimePayItem.objects.select_related("payroll_component", "payroll_period").filter(
            contract_payroll_profile=contract_payroll_profile,
            is_active=True,
            approval_status__in=cls.PAYABLE_STATUSES,
        )
        if payroll_period is not None:
            queryset = queryset.filter(Q(payroll_period=payroll_period) | Q(payroll_period__isnull=True, effective_date__lte=payroll_period.period_end))
        elif payroll_date is not None:
            queryset = queryset.filter(effective_date__lte=payroll_date)
        return queryset.order_by("effective_date", "payroll_component__default_sequence", "payroll_component__code")
