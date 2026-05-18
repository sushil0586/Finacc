from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import EntityPayrollPolicy, PayrollPolicyRule


class PayrollPolicyRuleService:
    @staticmethod
    def list_rules(*, policy: EntityPayrollPolicy, rule_type: str | None = None, is_active: bool | None = None):
        queryset = PayrollPolicyRule.objects.filter(policy=policy)
        if rule_type:
            queryset = queryset.filter(rule_type=rule_type)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("rule_type", "rule_key", "effective_from", "id")

    @staticmethod
    @transaction.atomic
    def create_or_update_rule(attrs: dict, *, instance: PayrollPolicyRule | None = None) -> PayrollPolicyRule:
        rule = instance or PayrollPolicyRule()
        for key, value in attrs.items():
            setattr(rule, key, value)
        try:
            rule.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        rule.save()
        return rule

    @staticmethod
    def resolve_active_rules(*, policy: EntityPayrollPolicy, rule_date: date):
        return PayrollPolicyRule.objects.filter(
            policy=policy,
            is_active=True,
            effective_from__lte=rule_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=rule_date)).order_by("rule_type", "rule_key", "-effective_from")
