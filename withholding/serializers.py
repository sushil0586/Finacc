from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from withholding.models import (
    EntityWithholdingConfig,
    GstTcsComputation,
    GstTcsEcoProfile,
    PartyTaxProfile,
    TcsCollection,
    TcsComputation,
    TcsDeposit,
    TcsDepositAllocation,
    TcsQuarterlyReturn,
    WithholdingSection,
    WithholdingTaxType,
)
from withholding.services import (
    CUTOFF_DISABLE_206C_1H,
    ZERO2,
    compute_withholding_preview,
    determine_fy_quarter,
    q2,
)


class WithholdingSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithholdingSection
        fields = [
            "id",
            "tax_type",
            "law_type",
            "sub_type",
            "section_code",
            "description",
            "base_rule",
            "rate_default",
            "threshold_default",
            "requires_pan",
            "higher_rate_no_pan",
            "applicability_json",
            "effective_from",
            "effective_to",
            "is_active",
        ]


class PartyTaxProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyTaxProfile
        fields = [
            "id",
            "party_account",
            "pan",
            "is_pan_available",
            "is_exempt_withholding",
            "lower_deduction_rate",
            "lower_deduction_valid_from",
            "lower_deduction_valid_to",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class EntityWithholdingConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityWithholdingConfig
        fields = [
            "id",
            "entity",
            "entityfin",
            "subentity",
            "enable_tds",
            "enable_tcs",
            "default_tds_section",
            "default_tcs_section",
            "apply_194q",
            "apply_tcs_206c1h",
            "effective_from",
            "rounding_places",
        ]


class TcsComputeRequestSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entityfin_id = serializers.IntegerField()
    subentity_id = serializers.IntegerField(required=False, allow_null=True)
    party_account_id = serializers.IntegerField(required=False, allow_null=True)
    tax_type = serializers.ChoiceField(choices=WithholdingTaxType.choices, default=WithholdingTaxType.TCS)
    section_id = serializers.IntegerField(required=False, allow_null=True)
    document_type = serializers.CharField(required=False, allow_blank=True, default="invoice")
    document_id = serializers.IntegerField(required=False, allow_null=True)
    document_no = serializers.CharField(required=False, allow_blank=True, default="")
    module_name = serializers.CharField(required=False, allow_blank=True, default="sales")
    doc_date = serializers.DateField()
    taxable_total = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    gross_total = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    trigger_basis = serializers.CharField(required=False, allow_blank=True, default="INVOICE")
    override_reason = serializers.CharField(required=False, allow_blank=True, default="")


class TcsComputeConfirmSerializer(TcsComputeRequestSerializer):
    status = serializers.ChoiceField(choices=TcsComputation.Status.choices, required=False, default=TcsComputation.Status.CONFIRMED)


class TcsComputationSerializer(serializers.ModelSerializer):
    section_code = serializers.CharField(source="section.section_code", read_only=True)

    class Meta:
        model = TcsComputation
        fields = [
            "id",
            "module_name",
            "document_type",
            "document_id",
            "document_no",
            "doc_date",
            "entity",
            "entityfin",
            "subentity",
            "party_account",
            "section",
            "section_code",
            "rule_snapshot_json",
            "applicability_status",
            "trigger_basis",
            "taxable_base",
            "excluded_base",
            "tcs_base_amount",
            "rate",
            "tcs_amount",
            "no_pan_applied",
            "lower_rate_applied",
            "override_reason",
            "overridden_by",
            "overridden_at",
            "fiscal_year",
            "quarter",
            "status",
            "computation_json",
            "created_at",
            "updated_at",
        ]


class TcsCollectionSerializer(serializers.ModelSerializer):
    def validate_status(self, value):
        v = (value or "").strip().upper()
        if v == "CLOSED":
            return TcsCollection.Status.ALLOCATED
        return v

    class Meta:
        model = TcsCollection
        fields = [
            "id",
            "computation",
            "collection_date",
            "receipt_voucher_id",
            "amount_received",
            "tcs_collected_amount",
            "collection_reference",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class TcsDepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = TcsDeposit
        fields = [
            "id",
            "entity",
            "financial_year",
            "month",
            "challan_no",
            "challan_date",
            "bsr_code",
            "cin",
            "bank_name",
            "total_deposit_amount",
            "deposited_by",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class TcsDepositAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TcsDepositAllocation
        fields = ["id", "deposit", "collection", "allocated_amount", "created_at"]
        read_only_fields = ["created_at"]


class TcsQuarterlyReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = TcsQuarterlyReturn
        fields = [
            "id",
            "entity",
            "fy",
            "quarter",
            "form_name",
            "return_type",
            "status",
            "ack_no",
            "filed_on",
            "json_snapshot",
            "file_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class GstTcsEcoProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstTcsEcoProfile
        fields = [
            "id",
            "entity",
            "gstin",
            "is_eco",
            "section_code",
            "default_rate",
            "effective_from",
            "effective_to",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class GstTcsComputationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstTcsComputation
        fields = [
            "id",
            "entity",
            "eco_profile",
            "supplier_account",
            "doc_date",
            "document_type",
            "document_id",
            "document_no",
            "taxable_value",
            "gst_tcs_rate",
            "gst_tcs_amount",
            "fy",
            "month",
            "status",
            "snapshot_json",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class GstTcsComputeRequestSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    eco_profile_id = serializers.IntegerField()
    supplier_account_id = serializers.IntegerField()
    doc_date = serializers.DateField()
    document_type = serializers.CharField(required=False, allow_blank=True, default="invoice")
    document_id = serializers.IntegerField(required=False, allow_null=True)
    document_no = serializers.CharField(required=False, allow_blank=True, default="")
    taxable_value = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=ZERO2)
    gst_tcs_rate = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    status = serializers.ChoiceField(choices=GstTcsComputation.Status.choices, required=False, default=GstTcsComputation.Status.DRAFT)

    def validate(self, attrs):
        doc_date = attrs["doc_date"]
        fy, month, _ = determine_fy_quarter(doc_date)
        attrs["fy"] = fy
        attrs["month"] = month
        return attrs


def build_preview_payload(*, req: dict, user=None) -> dict:
    preview = compute_withholding_preview(**req)
    response = {
        "enabled": preview.enabled,
        "reason": preview.reason,
        "section_id": preview.section.id if preview.section else None,
        "section_code": preview.section.section_code if preview.section else None,
        "rate": q2(preview.rate),
        "base_amount": q2(preview.base_amount),
        "amount": q2(preview.amount),
        "section_law_type": getattr(preview.section, "law_type", None),
        "section_sub_type": getattr(preview.section, "sub_type", None),
    }
    section = preview.section
    if section and section.section_code and section.section_code.strip().upper() in {"206C(1H)", "206C1H"}:
        response["policy_warning"] = f"206C(1H) is legacy-only from {CUTOFF_DISABLE_206C_1H.isoformat()}."
    if user:
        response["computed_by"] = user.id
    return response
