from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Q

from payroll.models import GlobalPayrollComponent, GlobalPayrollComponentGroup


class GlobalPayrollCatalogService:
    @staticmethod
    def list_component_groups(*, search: str | None = None, is_active: bool | None = None):
        queryset = GlobalPayrollComponentGroup.objects.all().order_by("sort_order", "name")
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset

    @staticmethod
    def list_components(*, search: str | None = None, component_type: str | None = None, is_active: bool | None = None):
        queryset = GlobalPayrollComponent.objects.select_related("group").all().order_by("default_sequence", "code")
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        if component_type:
            queryset = queryset.filter(component_type=component_type)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset

    @staticmethod
    def validate_component_code(code: str, *, instance: GlobalPayrollComponent | None = None) -> None:
        queryset = GlobalPayrollComponent.objects.filter(code=code)
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise ValueError("A global payroll component with this code already exists.")

    @staticmethod
    def validate_effective_dates(effective_from, effective_to) -> None:
        if effective_to and effective_from and effective_to < effective_from:
            raise ValueError("Effective to date cannot be earlier than effective from date.")

    @classmethod
    @transaction.atomic
    def create_or_update_component_group(cls, payload: dict[str, Any], *, instance: GlobalPayrollComponentGroup | None = None) -> GlobalPayrollComponentGroup:
        group = instance or GlobalPayrollComponentGroup()
        for field in (
            "code",
            "name",
            "description",
            "group_type",
            "sort_order",
            "is_system",
            "is_active",
            "metadata",
        ):
            if field in payload:
                setattr(group, field, payload[field])
        group.full_clean()
        group.save()
        return group

    @classmethod
    @transaction.atomic
    def create_or_update_component(cls, payload: dict[str, Any], *, instance: GlobalPayrollComponent | None = None) -> GlobalPayrollComponent:
        component = instance or GlobalPayrollComponent()
        cls.validate_component_code(payload.get("code", component.code), instance=instance)
        cls.validate_effective_dates(payload.get("effective_from", component.effective_from), payload.get("effective_to", component.effective_to))

        for field in (
            "group",
            "code",
            "name",
            "description",
            "component_type",
            "calculation_type",
            "default_sequence",
            "default_formula",
            "default_rule_json",
            "taxable",
            "affects_gross",
            "affects_net",
            "affects_ctc",
            "attendance_dependent",
            "lop_dependent",
            "overtime_dependent",
            "pro_rata",
            "statutory_code",
            "country_code",
            "state_code",
            "effective_from",
            "effective_to",
            "is_system",
            "is_active",
            "metadata",
        ):
            if field in payload:
                setattr(component, field, payload[field])
        if component.default_formula is None:
            component.default_formula = ""
        if component.default_rule_json is None:
            component.default_rule_json = {}
        if not component.statutory_code:
            component.statutory_code = ""
        if not component.country_code:
            component.country_code = "IN"
        if not component.state_code:
            component.state_code = ""
        if component.default_sequence is None:
            component.default_sequence = 100
        if component.metadata is None:
            component.metadata = {}
        component.full_clean()
        component.save()
        return component
