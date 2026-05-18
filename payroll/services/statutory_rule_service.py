from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import StatutoryRule, StatutoryScheme


class StatutoryRuleService:
    @staticmethod
    def list_rules(
        *,
        entity_id: int | None = None,
        search: str | None = None,
        scheme_id: str | None = None,
        rule_type: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = StatutoryRule.objects.select_related("entity", "scheme")
        if entity_id is not None:
            queryset = queryset.filter(Q(entity_id=entity_id) | Q(entity__isnull=True))
        if search:
            queryset = queryset.filter(Q(rule_code__icontains=search) | Q(rule_name__icontains=search) | Q(scheme__code__icontains=search) | Q(scheme__name__icontains=search))
        if scheme_id:
            queryset = queryset.filter(scheme_id=scheme_id)
        if rule_type:
            queryset = queryset.filter(rule_type=rule_type)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("scheme__code", "priority", "effective_from", "rule_code")

    @staticmethod
    @transaction.atomic
    def create_or_update_rule(attrs: dict, *, instance: StatutoryRule | None = None) -> StatutoryRule:
        rule = instance or StatutoryRule()
        for key, value in attrs.items():
            setattr(rule, key, value)
        try:
            rule.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        rule.save()
        return rule

    @staticmethod
    def resolve_rules(*, entity_id: int | None, scheme: StatutoryScheme, rule_date: date, state_code: str | None = None):
        queryset = StatutoryRule.objects.select_related("scheme").filter(
            scheme=scheme,
            is_active=True,
            effective_from__lte=rule_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=rule_date))
        if entity_id is not None:
            queryset = queryset.filter(Q(entity_id=entity_id) | Q(entity__isnull=True))
        if state_code:
            queryset = queryset.filter(Q(scheme__state_code="") | Q(scheme__state_code=state_code))
        return queryset.order_by("priority", "-effective_from", "rule_code")
