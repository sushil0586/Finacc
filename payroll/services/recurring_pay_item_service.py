from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import ContractPayrollProfile, RecurringPayItem


class RecurringPayItemService:
    @staticmethod
    def list_items(
        *,
        entity_id: int,
        search: str | None = None,
        item_type: str | None = None,
        payroll_component_id: int | None = None,
        contract_payroll_profile_id: str | None = None,
        pay_frequency: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = RecurringPayItem.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_component",
        ).filter(entity_id=entity_id)
        if search:
            queryset = queryset.filter(
                Q(contract_payroll_profile__hrms_contract__contract_code__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__employee_number__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__display_name__icontains=search)
                | Q(payroll_component__code__icontains=search)
                | Q(payroll_component__name__icontains=search)
            )
        if item_type:
            queryset = queryset.filter(item_type=item_type)
        if payroll_component_id:
            queryset = queryset.filter(payroll_component_id=payroll_component_id)
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if pay_frequency:
            queryset = queryset.filter(contract_payroll_profile__pay_frequency=pay_frequency)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("priority", "effective_from", "payroll_component__default_sequence", "payroll_component__code")

    @staticmethod
    @transaction.atomic
    def create_or_update_item(attrs: dict, *, instance: RecurringPayItem | None = None) -> RecurringPayItem:
        item = instance or RecurringPayItem()
        for key, value in attrs.items():
            setattr(item, key, value)
        try:
            item.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        item.save()
        return item

    @staticmethod
    def resolve_active_recurring_items(*, contract_payroll_profile: ContractPayrollProfile, payroll_date: date):
        return RecurringPayItem.objects.select_related("payroll_component").filter(
            contract_payroll_profile=contract_payroll_profile,
            is_active=True,
            effective_from__lte=payroll_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=payroll_date)).order_by(
            "priority",
            "payroll_component__default_sequence",
            "payroll_component__code",
        )
