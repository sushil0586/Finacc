from __future__ import annotations

from decimal import Decimal
import re

from django.db.models import Sum
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


def _is_valid_fy_label(value: str) -> bool:
    raw = (value or "").strip()
    m_short = re.match(r"^(\d{4})-(\d{2})$", raw)
    if m_short:
        start = int(m_short.group(1))
        end_2 = int(m_short.group(2))
        end_full = (start // 100) * 100 + end_2
        if end_full < start:
            end_full += 100
        return end_full == (start + 1)
    m_full = re.match(r"^(\d{4})-(\d{4})$", raw)
    if m_full:
        start = int(m_full.group(1))
        end_full = int(m_full.group(2))
        return end_full == (start + 1)
    return False


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
    status = serializers.ChoiceField(
        choices=list(TcsCollection.Status.choices) + [("CLOSED", "Closed")],
        required=False,
    )

    def validate_status(self, value):
        v = (value or "").strip().upper()
        if v == "CLOSED":
            return TcsCollection.Status.ALLOCATED
        return v

    def validate(self, attrs):
        data = super().validate(attrs)
        instance = getattr(self, "instance", None)
        computation = data.get("computation") or getattr(instance, "computation", None)
        collection_date = data.get("collection_date") or getattr(instance, "collection_date", None)
        amount_received = data.get("amount_received")
        if amount_received is None and instance is not None:
            amount_received = instance.amount_received
        tcs_collected_amount = data.get("tcs_collected_amount")
        if tcs_collected_amount is None and instance is not None:
            tcs_collected_amount = instance.tcs_collected_amount

        if computation is None:
            return data

        if computation.status == TcsComputation.Status.REVERSED:
            raise serializers.ValidationError({"computation": "Cannot collect TCS for a reversed computation."})
        if q2(computation.tcs_amount or Decimal("0.00")) <= Decimal("0.00"):
            raise serializers.ValidationError({"computation": "Collection is allowed only when computed TCS amount is greater than 0."})
        if collection_date and computation.doc_date and collection_date < computation.doc_date:
            raise serializers.ValidationError({"collection_date": "Collection date cannot be before computation document date."})

        amount_received = q2(amount_received or Decimal("0.00"))
        tcs_collected_amount = q2(tcs_collected_amount or Decimal("0.00"))
        if tcs_collected_amount <= Decimal("0.00"):
            raise serializers.ValidationError({"tcs_collected_amount": "Collected amount must be greater than 0."})
        if amount_received < tcs_collected_amount:
            raise serializers.ValidationError({"tcs_collected_amount": "TCS collected amount cannot exceed amount received."})

        existing_total = (
            TcsCollection.objects.filter(computation=computation)
            .exclude(pk=getattr(instance, "pk", None))
            .exclude(status=TcsCollection.Status.CANCELLED)
            .aggregate(v=Sum("tcs_collected_amount"))
            .get("v")
            or Decimal("0.00")
        )
        if q2(existing_total + tcs_collected_amount) > q2(computation.tcs_amount):
            raise serializers.ValidationError({"tcs_collected_amount": "Total collections cannot exceed computed TCS amount."})
        return data

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
    def validate(self, attrs):
        data = super().validate(attrs)
        instance = getattr(self, "instance", None)

        entity = data.get("entity") or getattr(instance, "entity", None)
        financial_year = (data.get("financial_year") or getattr(instance, "financial_year", "") or "").strip()
        month = data.get("month")
        if month is None and instance is not None:
            month = instance.month
        challan_no = (data.get("challan_no") or getattr(instance, "challan_no", "") or "").strip()
        total_deposit_amount = data.get("total_deposit_amount")
        if total_deposit_amount is None and instance is not None:
            total_deposit_amount = instance.total_deposit_amount

        if month is not None and (int(month) < 1 or int(month) > 12):
            raise serializers.ValidationError({"month": "Month must be between 1 and 12."})
        if financial_year and not _is_valid_fy_label(financial_year):
            raise serializers.ValidationError({"financial_year": "Financial year must be like 2025-26 (single-year span)."})

        if q2(total_deposit_amount or Decimal("0.00")) <= Decimal("0.00"):
            raise serializers.ValidationError({"total_deposit_amount": "Deposit amount must be greater than 0."})

        if entity is not None and financial_year and challan_no:
            clash_qs = TcsDeposit.objects.filter(
                entity=entity,
                financial_year=financial_year,
                challan_no__iexact=challan_no,
            )
            if instance is not None:
                clash_qs = clash_qs.exclude(pk=instance.pk)
            if clash_qs.exists():
                raise serializers.ValidationError(
                    {"challan_no": "Challan number already exists for this entity and financial year."}
                )
        return data

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
    def validate(self, attrs):
        data = super().validate(attrs)
        instance = getattr(self, "instance", None)
        fy = (data.get("fy") or getattr(instance, "fy", "") or "").strip()
        quarter = (data.get("quarter") or getattr(instance, "quarter", "") or "").strip().upper()
        form_name = (data.get("form_name") or getattr(instance, "form_name", "") or "").strip().upper()
        return_type = data.get("return_type") or getattr(instance, "return_type", TcsQuarterlyReturn.ReturnType.ORIGINAL)
        entity = data.get("entity") or getattr(instance, "entity", None)

        if quarter and quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise serializers.ValidationError({"quarter": "Quarter must be one of Q1, Q2, Q3, Q4."})
        if fy and not _is_valid_fy_label(fy):
            raise serializers.ValidationError({"fy": "FY must be like 2025-26 (single-year span)."})
        if form_name and form_name != "27EQ":
            raise serializers.ValidationError({"form_name": "Only form 27EQ is supported in this endpoint."})
        status_value = data.get("status") or getattr(instance, "status", None)
        ack_no = (data.get("ack_no") if "ack_no" in data else getattr(instance, "ack_no", "")) or ""
        filed_on = data.get("filed_on") if "filed_on" in data else getattr(instance, "filed_on", None)
        if status_value == TcsQuarterlyReturn.Status.FILED:
            if not str(ack_no).strip():
                raise serializers.ValidationError({"ack_no": "ack_no is required when return status is FILED."})
            if filed_on is None:
                raise serializers.ValidationError({"filed_on": "filed_on is required when return status is FILED."})
        if return_type == TcsQuarterlyReturn.ReturnType.ORIGINAL and entity and fy and quarter:
            clash_qs = TcsQuarterlyReturn.objects.filter(
                entity=entity,
                fy=fy,
                quarter=quarter,
                form_name="27EQ",
                return_type=TcsQuarterlyReturn.ReturnType.ORIGINAL,
            )
            if instance is not None:
                clash_qs = clash_qs.exclude(pk=instance.pk)
            if clash_qs.exists():
                raise serializers.ValidationError(
                    {"return_type": "Original 27EQ return already exists for this entity/FY/quarter. Use Correction return."}
                )
        if return_type == TcsQuarterlyReturn.ReturnType.CORRECTION and entity and fy and quarter:
            has_original = TcsQuarterlyReturn.objects.filter(
                entity=entity,
                fy=fy,
                quarter=quarter,
                form_name="27EQ",
                return_type=TcsQuarterlyReturn.ReturnType.ORIGINAL,
            ).exclude(pk=getattr(instance, "pk", None)).exists()
            if not has_original:
                raise serializers.ValidationError({"return_type": "Correction return requires an existing Original return."})
        return data

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
