from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from payroll.models import (
    ContractPayrollInputSnapshot,
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    ContractStatutoryProfile,
    ContractTaxDeclaration,
    ContractTaxDeclarationLine,
    EntityPayrollPolicy,
    EntityStatutoryRegistration,
    OneTimePayItem,
    PayrollComponent,
    PayrollPolicyRule,
    PayrollPeriod,
    RecurringPayItem,
    SalaryStructure,
    SalaryStructureLine,
    StatutoryRule,
    StatutoryScheme,
    StatutorySlab,
)
from payroll.services.payroll_setup_service import PayrollSetupService


class PayrollPeriodSerializer(serializers.ModelSerializer):
    run_count = serializers.SerializerMethodField()
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)

    def get_run_count(self, obj):
        return obj.runs.count()

    class Meta:
        model = PayrollPeriod
        fields = [
            "id",
            "entity",
            "entity_name",
            "entityfinid",
            "subentity",
            "subentity_name",
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
            "semantic_code",
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
            "rule_mode",
            "calculation_basis",
            "basis_component",
            "rate",
            "fixed_amount",
            "is_pro_rated",
            "is_override_allowed",
            "is_active",
            "recurrence_frequency",
            "compensation_bucket",
            "ctc_treatment",
            "gross_treatment",
            "rule_json",
        ]


class SalaryStructureSerializer(serializers.ModelSerializer):
    lines = SalaryStructureLineSerializer(many=True, write_only=True, required=False)
    current_version_id = serializers.IntegerField(read_only=True)
    current_version = serializers.SerializerMethodField()
    available_versions = serializers.SerializerMethodField()
    calculation_policy_json = serializers.JSONField(write_only=True, required=False)
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    entityfin_name = serializers.CharField(source="entityfinid.desc", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)

    class Meta:
        model = SalaryStructure
        fields = [
            "id",
            "entity",
            "entity_name",
            "entityfinid",
            "entityfin_name",
            "subentity",
            "subentity_name",
            "code",
            "name",
            "status",
            "notes",
            "is_active",
            "is_template",
            "current_version_id",
            "current_version",
            "available_versions",
            "calculation_policy_json",
            "lines",
        ]

    def get_current_version(self, obj):
        version = obj.current_version
        if not version:
            return None
        return self._serialize_version(version, include_lines=True)

    def get_available_versions(self, obj):
        versions = getattr(obj, "_prefetched_objects_cache", {}).get("versions")
        if versions is None:
            versions = obj.versions.all()
        return [self._serialize_version(version, include_lines=False) for version in versions]

    def _serialize_version(self, version, *, include_lines: bool):
        payload = {
            "id": version.id,
            "version_no": version.version_no,
            "effective_from": version.effective_from,
            "effective_to": version.effective_to,
            "status": version.status,
            "calculation_policy_json": version.calculation_policy_json,
        }
        if include_lines:
            payload["lines"] = SalaryStructureLineSerializer(version.lines.all(), many=True).data
        return payload

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
        calculation_policy_json = validated_data.pop("calculation_policy_json", {})
        structure = SalaryStructure.objects.create(**validated_data)
        if lines:
            PayrollSetupService.create_structure_version(
                structure=structure,
                lines=lines,
                calculation_policy_json=calculation_policy_json,
                approved_by=self.context["request"].user if self.context.get("request") else None,
            )
        return structure

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        calculation_policy_json = validated_data.pop("calculation_policy_json", {})
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines is not None:
            PayrollSetupService.create_structure_version(
                structure=instance,
                lines=lines,
                calculation_policy_json=calculation_policy_json,
                approved_by=self.context["request"].user if self.context.get("request") else None,
            )
        return instance


class ContractPayrollProfileSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    contract_code = serializers.CharField(source="hrms_contract.contract_code", read_only=True)
    contract_status = serializers.CharField(source="hrms_contract.status", read_only=True)
    employee_number = serializers.CharField(source="hrms_contract.employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="hrms_contract.employee.display_name", read_only=True)
    work_email = serializers.CharField(source="hrms_contract.employee.work_email", read_only=True)
    pay_group_code = serializers.CharField(source="hrms_contract.pay_group_code", read_only=True)
    bank_account_label = serializers.SerializerMethodField()

    class Meta:
        model = ContractPayrollProfile
        fields = [
            "id",
            "entity",
            "entity_name",
            "hrms_contract",
            "contract_code",
            "contract_status",
            "employee_number",
            "employee_name",
            "work_email",
            "pay_group_code",
            "pay_frequency",
            "payroll_status",
            "tax_regime",
            "payment_mode",
            "bank_account",
            "bank_account_label",
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
        ]

    def get_bank_account_label(self, obj):
        if not obj.bank_account_id:
            return ""
        return getattr(obj.bank_account, "accountname", "") or getattr(obj.bank_account, "name", "") or ""


class ContractSalaryStructureAssignmentSerializer(serializers.ModelSerializer):
    salary_structure_name = serializers.CharField(source="salary_structure.name", read_only=True)
    salary_structure_code = serializers.CharField(source="salary_structure.code", read_only=True)
    salary_structure_version_no = serializers.IntegerField(source="salary_structure_version.version_no", read_only=True)

    class Meta:
        model = ContractSalaryStructureAssignment
        fields = [
            "id",
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_name",
            "salary_structure_code",
            "salary_structure_version",
            "salary_structure_version_no",
            "effective_from",
            "effective_to",
            "assignment_status",
            "ctc_amount",
            "gross_amount",
            "metadata",
            "is_active",
        ]
        extra_kwargs = {
            "contract_payroll_profile": {"required": False},
        }


class ContractTaxDeclarationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractTaxDeclarationLine
        fields = [
            "id",
            "declaration",
            "section_code",
            "declaration_category",
            "declaration_code",
            "description",
            "declared_amount",
            "approved_amount",
            "evidence_required",
            "evidence_status",
            "metadata",
            "is_active",
        ]
        extra_kwargs = {
            "declaration": {"required": False},
        }


class ContractTaxDeclarationSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    contract_code = serializers.CharField(source="contract_payroll_profile.hrms_contract.contract_code", read_only=True)
    employee_number = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.display_name", read_only=True)
    financial_year_name = serializers.CharField(source="financial_year.desc", read_only=True)
    lines = ContractTaxDeclarationLineSerializer(many=True, read_only=True)

    class Meta:
        model = ContractTaxDeclaration
        fields = [
            "id",
            "entity",
            "entity_name",
            "contract_payroll_profile",
            "contract_code",
            "employee_number",
            "employee_name",
            "financial_year",
            "financial_year_name",
            "tax_regime",
            "declaration_status",
            "approval_status",
            "declared_annual_income",
            "annual_other_income",
            "previous_employer_income",
            "previous_employer_tds",
            "standard_deduction_amount",
            "professional_tax_declared",
            "annual_gross_projection",
            "annual_exemption_total",
            "annual_deduction_total",
            "projected_taxable_income",
            "projected_annual_tax",
            "projected_monthly_tds",
            "tax_already_deducted",
            "balance_tax",
            "metadata",
            "requested_by",
            "approved_by",
            "rejected_by",
            "cancelled_by",
            "locked_by",
            "requested_at",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancelled_at",
            "locked_at",
            "is_active",
            "lines",
        ]


class ContractPayrollInputSnapshotSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    contract_code = serializers.CharField(source="contract_payroll_profile.hrms_contract.contract_code", read_only=True)
    employee_number = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.display_name", read_only=True)
    payroll_period_name = serializers.CharField(source="payroll_period.code", read_only=True)

    class Meta:
        model = ContractPayrollInputSnapshot
        fields = [
            "id",
            "entity",
            "entity_name",
            "contract_payroll_profile",
            "contract_code",
            "employee_number",
            "employee_name",
            "payroll_period",
            "payroll_period_name",
            "input_type",
            "input_json",
            "source",
            "effective_from",
            "effective_to",
            "is_active",
            "metadata",
        ]


class PayrollPolicyRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPolicyRule
        fields = [
            "id",
            "policy",
            "rule_type",
            "rule_key",
            "rule_value_json",
            "effective_from",
            "effective_to",
            "is_active",
            "metadata",
        ]
        extra_kwargs = {
            "policy": {"required": False},
        }


class RecurringPayItemSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    contract_code = serializers.CharField(source="contract_payroll_profile.hrms_contract.contract_code", read_only=True)
    employee_number = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.display_name", read_only=True)
    payroll_component_code = serializers.CharField(source="payroll_component.code", read_only=True)
    payroll_component_name = serializers.CharField(source="payroll_component.name", read_only=True)

    class Meta:
        model = RecurringPayItem
        fields = [
            "id",
            "entity",
            "entity_name",
            "contract_payroll_profile",
            "contract_code",
            "employee_number",
            "employee_name",
            "payroll_component",
            "payroll_component_code",
            "payroll_component_name",
            "item_type",
            "amount",
            "percentage",
            "formula_override",
            "recurrence_frequency",
            "effective_from",
            "effective_to",
            "priority",
            "remarks",
            "metadata",
            "is_active",
        ]


class OneTimePayItemSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    contract_code = serializers.CharField(source="contract_payroll_profile.hrms_contract.contract_code", read_only=True)
    employee_number = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.display_name", read_only=True)
    payroll_component_code = serializers.CharField(source="payroll_component.code", read_only=True)
    payroll_component_name = serializers.CharField(source="payroll_component.name", read_only=True)
    payroll_period_name = serializers.CharField(source="payroll_period.code", read_only=True)

    class Meta:
        model = OneTimePayItem
        fields = [
            "id",
            "entity",
            "entity_name",
            "contract_payroll_profile",
            "contract_code",
            "employee_number",
            "employee_name",
            "payroll_component",
            "payroll_component_code",
            "payroll_component_name",
            "item_type",
            "payroll_period",
            "payroll_period_name",
            "requested_date",
            "effective_date",
            "amount",
            "quantity",
            "remarks",
            "approval_status",
            "source_type",
            "metadata",
            "is_active",
        ]


class StatutorySchemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutoryScheme
        fields = [
            "id",
            "code",
            "name",
            "scheme_type",
            "country_code",
            "state_code",
            "description",
            "is_system",
            "is_active",
            "metadata",
        ]


class StatutorySlabSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutorySlab
        fields = [
            "id",
            "rule",
            "slab_from",
            "slab_to",
            "amount",
            "percentage",
            "formula",
            "metadata",
            "is_active",
        ]
        extra_kwargs = {"rule": {"required": False}}


class StatutoryRuleSerializer(serializers.ModelSerializer):
    scheme_code = serializers.CharField(source="scheme.code", read_only=True)
    scheme_name = serializers.CharField(source="scheme.name", read_only=True)
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    slabs = StatutorySlabSerializer(many=True, read_only=True)

    class Meta:
        model = StatutoryRule
        fields = [
            "id",
            "entity",
            "entity_name",
            "scheme",
            "scheme_code",
            "scheme_name",
            "rule_code",
            "rule_name",
            "rule_type",
            "effective_from",
            "effective_to",
            "rule_json",
            "applicability_json",
            "priority",
            "is_system",
            "is_active",
            "metadata",
            "slabs",
        ]


class EntityStatutoryRegistrationSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    scheme_code = serializers.CharField(source="scheme.code", read_only=True)
    scheme_name = serializers.CharField(source="scheme.name", read_only=True)

    class Meta:
        model = EntityStatutoryRegistration
        fields = [
            "id",
            "entity",
            "entity_name",
            "scheme",
            "scheme_code",
            "scheme_name",
            "registration_number",
            "registration_state",
            "effective_from",
            "effective_to",
            "is_active",
            "metadata",
        ]


class ContractStatutoryProfileSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="contract_payroll_profile.hrms_contract.contract_code", read_only=True)
    employee_number = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="contract_payroll_profile.hrms_contract.employee.display_name", read_only=True)
    scheme_code = serializers.CharField(source="scheme.code", read_only=True)
    scheme_name = serializers.CharField(source="scheme.name", read_only=True)

    class Meta:
        model = ContractStatutoryProfile
        fields = [
            "id",
            "contract_payroll_profile",
            "contract_code",
            "employee_number",
            "employee_name",
            "scheme",
            "scheme_code",
            "scheme_name",
            "is_applicable",
            "override_rule_json",
            "effective_from",
            "effective_to",
            "is_active",
            "metadata",
        ]


class EntityPayrollPolicySerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    rules = PayrollPolicyRuleSerializer(many=True, read_only=True)

    class Meta:
        model = EntityPayrollPolicy
        validators = []
        fields = [
            "id",
            "entity",
            "entity_name",
            "code",
            "name",
            "description",
            "pay_frequency",
            "payroll_month_start_day",
            "payroll_month_end_day",
            "attendance_cutoff_day",
            "salary_disbursement_day",
            "rounding_mode",
            "net_pay_rounding",
            "component_rounding",
            "lop_calculation_method",
            "arrear_calculation_method",
            "negative_salary_policy",
            "payslip_publish_policy",
            "payroll_lock_policy",
            "approval_required",
            "effective_from",
            "effective_to",
            "is_default",
            "is_active",
            "metadata",
            "rules",
        ]


class PayrollRuntimeReadinessPreviewRequestSerializer(serializers.Serializer):
    entity = serializers.IntegerField(required=True)
    payroll_date = serializers.DateField(required=True)
    contract_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
