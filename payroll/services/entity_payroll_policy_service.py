from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import EntityPayrollPolicy


class EntityPayrollPolicyService:
    @staticmethod
    def list_policies(
        *,
        entity_id: int,
        search: str | None = None,
        pay_frequency: str | None = None,
        is_active: bool | None = None,
        is_default: bool | None = None,
    ):
        queryset = EntityPayrollPolicy.objects.filter(entity_id=entity_id)
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        if pay_frequency:
            queryset = queryset.filter(pay_frequency=pay_frequency)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if is_default is not None:
            queryset = queryset.filter(is_default=is_default)
        return queryset.order_by("pay_frequency", "code")

    @classmethod
    @transaction.atomic
    def create_or_update_policy(cls, attrs: dict, *, instance: EntityPayrollPolicy | None = None) -> EntityPayrollPolicy:
        policy = instance or EntityPayrollPolicy()
        for key, value in attrs.items():
            setattr(policy, key, value)
        if policy.is_default and policy.is_active and policy.entity_id:
            EntityPayrollPolicy.objects.filter(
                entity_id=policy.entity_id,
                pay_frequency=policy.pay_frequency,
                is_default=True,
            ).exclude(pk=policy.pk).update(is_default=False)
        try:
            policy.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        policy.save()
        return policy

    @classmethod
    @transaction.atomic
    def set_default_policy(cls, *, policy: EntityPayrollPolicy) -> EntityPayrollPolicy:
        EntityPayrollPolicy.objects.filter(
            entity_id=policy.entity_id,
            pay_frequency=policy.pay_frequency,
            is_default=True,
        ).exclude(pk=policy.pk).update(is_default=False)
        if not policy.is_default:
            policy.is_default = True
            try:
                policy.full_clean()
            except DjangoValidationError as err:
                raise ValueError(err.message_dict or err.messages)
            policy.save(update_fields=["is_default", "updated_at"])
        return policy

    @staticmethod
    def resolve_active_policy(*, entity_id: int, payroll_date: date, pay_frequency: str) -> EntityPayrollPolicy | None:
        queryset = EntityPayrollPolicy.objects.filter(
            entity_id=entity_id,
            pay_frequency=pay_frequency,
            is_active=True,
            effective_from__lte=payroll_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=payroll_date))
        default_policy = queryset.filter(is_default=True).order_by("-effective_from", "-updated_at").first()
        if default_policy:
            return default_policy
        return queryset.order_by("-effective_from", "-updated_at").first()
