from __future__ import annotations

from rest_framework import serializers

from payroll.models import (
    GlobalPayrollComponent,
    GlobalPayrollComponentGroup,
    GlobalSalaryStructureTemplate,
    GlobalSalaryStructureTemplateLine,
)


class GlobalPayrollComponentGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalPayrollComponentGroup
        fields = [
            "id",
            "code",
            "name",
            "description",
            "group_type",
            "sort_order",
            "is_system",
            "is_active",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class GlobalPayrollComponentSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    group_code = serializers.CharField(source="group.code", read_only=True)

    class Meta:
        model = GlobalPayrollComponent
        fields = [
            "id",
            "group",
            "group_name",
            "group_code",
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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "group_name", "group_code"]


class GlobalSalaryStructureTemplateLineSerializer(serializers.ModelSerializer):
    template = serializers.UUIDField(read_only=True)
    component_code = serializers.CharField(source="component.code", read_only=True)
    component_name = serializers.CharField(source="component.name", read_only=True)
    component_group_name = serializers.CharField(source="component.group.name", read_only=True)

    class Meta:
        model = GlobalSalaryStructureTemplateLine
        fields = [
            "id",
            "template",
            "component",
            "component_code",
            "component_name",
            "component_group_name",
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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "component_code", "component_name", "component_group_name"]
        extra_kwargs = {}


class GlobalSalaryStructureTemplateSerializer(serializers.ModelSerializer):
    lines = GlobalSalaryStructureTemplateLineSerializer(many=True, read_only=True)
    active_line_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = GlobalSalaryStructureTemplate
        fields = [
            "id",
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
            "active_line_count",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "active_line_count", "lines"]


class EntityAdoptionPreviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)


class EntitySalaryTemplateAdoptionSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    entityfinid = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    structure_name_override = serializers.CharField(max_length=120, required=False, allow_blank=True)
    structure_code_override = serializers.CharField(max_length=40, required=False, allow_blank=True)
    effective_from = serializers.DateField()
    dry_run = serializers.BooleanField(required=False, default=False)
