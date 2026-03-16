from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from payroll.models import (
    PayrollAdjustment,
    PayrollComponent,
    PayrollEmployeeProfile,
    PayrollPeriod,
    SalaryStructure,
    SalaryStructureLine,
)
from payroll.services.payroll_setup_service import PayrollSetupService


class PayrollPeriodSerializer(serializers.ModelSerializer):
    run_count = serializers.SerializerMethodField()

    def get_run_count(self, obj):
        return obj.runs.count()

    class Meta:
        model = PayrollPeriod
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "code",
            "pay_frequency",
            "period_start",
            "period_end",
            "payout_date",
            "status",
            "locked_at",
            "locked_by",
            "submitted_for_close_by",
            "submitted_for_close_at",
            "closed_by",
            "closed_at",
            "close_note",
            "run_count",
        ]
        read_only_fields = [
            "status",
            "locked_at",
            "locked_by",
            "submitted_for_close_by",
            "submitted_for_close_at",
            "closed_by",
            "closed_at",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        PayrollSetupService.validate_period_overlap(instance=instance, attrs=attrs)
        if instance:
            changed_fields = {field for field in attrs if getattr(instance, field) != attrs[field]}
            PayrollSetupService.assert_period_dates_editable(instance, changed_fields)
        return attrs


class PayrollComponentSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="component_type", read_only=True)

    class Meta:
        model = PayrollComponent
        fields = [
            "id",
            "entity",
            "code",
            "name",
            "component_type",
            "category",
            "posting_behavior",
            "is_taxable",
            "is_statutory",
            "affects_net_pay",
            "is_active",
            "default_sequence",
            "description",
            "country_code",
            "state_code",
            "statutory_tag",
        ]


class SalaryStructureLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryStructureLine
        fields = [
            "id",
            "component",
            "sequence",
            "calculation_basis",
            "basis_component",
            "rate",
            "fixed_amount",
            "is_pro_rated",
            "is_override_allowed",
            "is_active",
        ]


class SalaryStructureSerializer(serializers.ModelSerializer):
    lines = SalaryStructureLineSerializer(many=True, write_only=True, required=False)
    current_version_id = serializers.IntegerField(source="current_version_id", read_only=True)
    current_version = serializers.SerializerMethodField()

    class Meta:
        model = SalaryStructure
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "code",
            "name",
            "status",
            "notes",
            "is_active",
            "is_template",
            "current_version_id",
            "current_version",
            "lines",
        ]

    def get_current_version(self, obj):
        version = obj.current_version
        if not version:
            return None
        return {
            "id": version.id,
            "version_no": version.version_no,
            "effective_from": version.effective_from,
            "effective_to": version.effective_to,
            "status": version.status,
            "lines": SalaryStructureLineSerializer(version.lines.all(), many=True).data,
        }

    def validate(self, attrs):
        entity = attrs.get("entity") or getattr(self.instance, "entity", None)
        entityfinid = attrs.get("entityfinid", getattr(self.instance, "entityfinid", None))
        subentity = attrs.get("subentity", getattr(self.instance, "subentity", None))
        if entityfinid and entity and entityfinid.entity_id != entity.id:
            raise serializers.ValidationError({"entityfinid": "Financial year must belong to the selected entity."})
        if subentity and entity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Subentity must belong to the selected entity."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        structure = SalaryStructure.objects.create(**validated_data)
        if lines:
            PayrollSetupService.create_structure_version(
                structure=structure,
                lines=lines,
                approved_by=self.context["request"].user if self.context.get("request") else None,
            )
        return structure

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines is not None:
            PayrollSetupService.create_structure_version(
                structure=instance,
                lines=lines,
                approved_by=self.context["request"].user if self.context.get("request") else None,
            )
        return instance


class PayrollEmployeeProfileSerializer(serializers.ModelSerializer):
    payment_mode = serializers.CharField(required=False, allow_blank=True, write_only=True)
    payment_mode_display = serializers.SerializerMethodField()

    class Meta:
        model = PayrollEmployeeProfile
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "employee_user",
            "employee_code",
            "full_name",
            "work_email",
            "pan",
            "uan",
            "date_of_joining",
            "status",
            "salary_structure",
            "salary_structure_version",
            "ctc_annual",
            "payment_account",
            "payment_mode",
            "payment_mode_display",
            "tax_regime",
            "pay_frequency",
            "effective_from",
            "effective_to",
            "blocked_for_payroll",
            "locked_for_processing",
            "extra_data",
        ]

    def get_payment_mode_display(self, obj):
        return (obj.extra_data or {}).get("payment_mode", "")

    def validate(self, attrs):
        entity = attrs.get("entity") or getattr(self.instance, "entity", None)
        subentity = attrs.get("subentity", getattr(self.instance, "subentity", None))
        structure = attrs.get("salary_structure", getattr(self.instance, "salary_structure", None))
        version = attrs.get("salary_structure_version", getattr(self.instance, "salary_structure_version", None))
        payment_account = attrs.get("payment_account", getattr(self.instance, "payment_account", None))
        if subentity and entity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if structure and entity and structure.entity_id != entity.id:
            raise serializers.ValidationError({"salary_structure": "Salary structure must belong to the selected entity."})
        if version and structure and version.salary_structure_id != structure.id:
            raise serializers.ValidationError({"salary_structure_version": "Version must belong to the selected salary structure."})
        if payment_account and entity and payment_account.entity_id != entity.id:
            raise serializers.ValidationError({"payment_account": "Payment account must belong to the selected entity."})
        return attrs

    def create(self, validated_data):
        payment_mode = validated_data.pop("payment_mode", "")
        if validated_data.get("salary_structure") and not validated_data.get("salary_structure_version"):
            validated_data["salary_structure_version"] = validated_data["salary_structure"].current_version
        if payment_mode:
            validated_data["extra_data"] = {**(validated_data.get("extra_data") or {}), "payment_mode": payment_mode}
        return super().create(validated_data)

    def update(self, instance, validated_data):
        payment_mode = validated_data.pop("payment_mode", None)
        if validated_data.get("salary_structure") and not validated_data.get("salary_structure_version"):
            validated_data["salary_structure_version"] = validated_data["salary_structure"].current_version
        if payment_mode is not None:
            validated_data["extra_data"] = {**(instance.extra_data or {}), **(validated_data.get("extra_data") or {}), "payment_mode": payment_mode}
        return super().update(instance, validated_data)


class PayrollAdjustmentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = PayrollAdjustment
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "employee_profile",
            "payroll_period",
            "component",
            "kind",
            "kind_label",
            "amount",
            "effective_date",
            "status",
            "remarks",
            "source_reference_type",
            "source_reference_id",
            "approved_by",
            "approved_at",
            "approved_run",
            "reversed_adjustment",
        ]
        read_only_fields = ["approved_by", "approved_at", "approved_run"]

    def validate(self, attrs):
        entity = attrs.get("entity") or getattr(self.instance, "entity", None)
        entityfinid = attrs.get("entityfinid") or getattr(self.instance, "entityfinid", None)
        subentity = attrs.get("subentity", getattr(self.instance, "subentity", None))
        employee_profile = attrs.get("employee_profile", getattr(self.instance, "employee_profile", None))
        payroll_period = attrs.get("payroll_period", getattr(self.instance, "payroll_period", None))
        component = attrs.get("component", getattr(self.instance, "component", None))
        if employee_profile and entity and employee_profile.entity_id != entity.id:
            raise serializers.ValidationError({"employee_profile": "Employee profile must belong to the selected entity."})
        if employee_profile and subentity is not None and employee_profile.subentity_id != getattr(subentity, "id", None):
            raise serializers.ValidationError({"employee_profile": "Employee profile must match the selected subentity."})
        if payroll_period and entity and payroll_period.entity_id != entity.id:
            raise serializers.ValidationError({"payroll_period": "Payroll period must belong to the selected entity."})
        if payroll_period and entityfinid and payroll_period.entityfinid_id != entityfinid.id:
            raise serializers.ValidationError({"payroll_period": "Payroll period must belong to the selected financial year."})
        if component and entity and component.entity_id != entity.id:
            raise serializers.ValidationError({"component": "Payroll component must belong to the selected entity."})
        return attrs
