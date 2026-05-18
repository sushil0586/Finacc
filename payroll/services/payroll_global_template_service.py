from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Q

from payroll.models import GlobalPayrollComponent, GlobalSalaryStructureTemplate, GlobalSalaryStructureTemplateLine


class GlobalSalaryTemplateService:
    @staticmethod
    def list_templates(*, search: str | None = None, template_type: str | None = None, is_active: bool | None = None):
        queryset = GlobalSalaryStructureTemplate.objects.all().order_by("name")
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        if template_type:
            queryset = queryset.filter(template_type=template_type)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset

    @staticmethod
    def get_template_detail(template_id):
        return GlobalSalaryStructureTemplate.objects.prefetch_related("lines__component", "lines__component__group").get(pk=template_id)

    @staticmethod
    def _validate_template_code(code: str, *, instance: GlobalSalaryStructureTemplate | None = None) -> None:
        queryset = GlobalSalaryStructureTemplate.objects.filter(code=code)
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise ValueError("A global salary template with this code already exists.")

    @staticmethod
    def _validate_line_component(component: GlobalPayrollComponent | None) -> None:
        if component is None:
            raise ValueError("Template line component is required.")

    @staticmethod
    def _validate_line_sequence(template: GlobalSalaryStructureTemplate, sequence: int, *, instance: GlobalSalaryStructureTemplateLine | None = None) -> None:
        queryset = GlobalSalaryStructureTemplateLine.objects.filter(template=template, sequence=sequence, is_active=True)
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise ValueError("An active template line with this sequence already exists.")

    @classmethod
    @transaction.atomic
    def create_or_update_template(cls, payload: dict[str, Any], *, instance: GlobalSalaryStructureTemplate | None = None) -> GlobalSalaryStructureTemplate:
        template = instance or GlobalSalaryStructureTemplate()
        cls._validate_template_code(payload.get("code", template.code), instance=instance)

        for field in (
            "code",
            "name",
            "description",
            "template_type",
            "country_code",
            "state_code",
            "industry_type",
            "pay_frequency",
            "is_default",
            "is_system",
            "is_active",
            "effective_from",
            "effective_to",
            "metadata",
        ):
            if field in payload:
                setattr(template, field, payload[field])
        if not template.country_code:
            template.country_code = "IN"
        if template.state_code is None:
            template.state_code = ""
        if template.metadata is None:
            template.metadata = {}
        template.full_clean()
        template.save()
        return template

    @classmethod
    @transaction.atomic
    def create_or_update_line(
        cls,
        template: GlobalSalaryStructureTemplate,
        payload: dict[str, Any],
        *,
        instance: GlobalSalaryStructureTemplateLine | None = None,
    ) -> GlobalSalaryStructureTemplateLine:
        component = payload.get("component") or getattr(instance, "component", None)
        cls._validate_line_component(component)
        sequence = payload.get("sequence", getattr(instance, "sequence", None))
        if sequence is None:
            raise ValueError("Template line sequence is required.")
        cls._validate_line_sequence(template, sequence, instance=instance)

        line = instance or GlobalSalaryStructureTemplateLine(template=template)
        for field in (
            "component",
            "sequence",
            "calculation_type",
            "formula",
            "rule_json",
            "amount_default",
            "percentage_default",
            "basis_components",
            "min_amount",
            "max_amount",
            "taxable_override",
            "affects_gross_override",
            "affects_net_override",
            "affects_ctc_override",
            "pro_rata",
            "attendance_dependent",
            "lop_dependent",
            "applicability_json",
            "is_active",
            "metadata",
        ):
            if field in payload:
                setattr(line, field, payload[field])
        line.template = template
        if line.formula is None:
            line.formula = ""
        if line.rule_json is None:
            line.rule_json = {}
        if line.basis_components is None:
            line.basis_components = []
        if line.applicability_json is None:
            line.applicability_json = {}
        if line.amount_default is None:
            line.amount_default = Decimal("0.00")
        if line.percentage_default is None:
            line.percentage_default = Decimal("0.00")
        if line.metadata is None:
            line.metadata = {}
        line.full_clean()
        line.save()
        return line
