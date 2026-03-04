from __future__ import annotations

from rest_framework import serializers

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from payments.models import (
    PaymentVoucherHeader,
    PaymentVoucherAllocation,
    PaymentVoucherAdjustment,
)
from payments.services.payment_voucher_service import PaymentVoucherService


class PaymentVoucherAllocationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = PaymentVoucherAllocation
        fields = [
            "id",
            "open_item",
            "settled_amount",
            "is_full_settlement",
            "is_advance_adjustment",
        ]


class PaymentVoucherAdjustmentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = PaymentVoucherAdjustment
        fields = [
            "id",
            "allocation",
            "adj_type",
            "ledger_account",
            "amount",
            "settlement_effect",
            "remarks",
        ]


class PaymentVoucherHeaderSerializer(serializers.ModelSerializer):
    allocations = PaymentVoucherAllocationSerializer(many=True, required=False)
    adjustments = PaymentVoucherAdjustmentSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    payment_type_name = serializers.CharField(source="get_payment_type_display", read_only=True)
    supply_type_name = serializers.CharField(source="get_supply_type_display", read_only=True)
    preview_doc_no = serializers.SerializerMethodField()
    preview_voucher_code = serializers.SerializerMethodField()

    class Meta:
        model = PaymentVoucherHeader
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "voucher_date",
            "doc_code",
            "doc_no",
            "voucher_code",
            "preview_doc_no",
            "preview_voucher_code",
            "payment_type",
            "payment_type_name",
            "supply_type",
            "supply_type_name",
            "paid_from",
            "paid_to",
            "payment_mode",
            "cash_paid_amount",
            "total_adjustment_amount",
            "settlement_effective_amount",
            "reference_number",
            "narration",
            "instrument_bank_name",
            "instrument_no",
            "instrument_date",
            "place_of_supply_state",
            "vendor_gstin",
            "advance_taxable_value",
            "advance_cgst",
            "advance_sgst",
            "advance_igst",
            "advance_cess",
            "status",
            "status_name",
            "approved_by",
            "approved_at",
            "is_cancelled",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
            "created_by",
            "ap_settlement",
            "allocations",
            "adjustments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "doc_no",
            "voucher_code",
            "total_adjustment_amount",
            "settlement_effective_amount",
            "status",
            "approved_by",
            "approved_at",
            "is_cancelled",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
            "ap_settlement",
            "created_at",
            "updated_at",
        ]

    def _get_document_type_id(self, obj) -> int:
        dt = DocumentType.objects.filter(
            module="payments",
            default_code=obj.doc_code,
            is_active=True,
        ).first()
        if not dt:
            raise serializers.ValidationError(f"DocumentType not found for payment doc_code={obj.doc_code}")
        return dt.id

    def get_preview_doc_no(self, obj):
        if obj.doc_no:
            return obj.doc_no
        if self.context.get("skip_preview_numbers", False):
            return None
        try:
            dt_id = self._get_document_type_id(obj)
            res = DocumentNumberService.peek_preview(
                entity_id=obj.entity_id,
                entityfinid_id=obj.entityfinid_id,
                subentity_id=obj.subentity_id,
                doc_type_id=dt_id,
                doc_code=obj.doc_code,
                on_date=obj.voucher_date,
            )
            return res.doc_no
        except Exception:
            return None

    def get_preview_voucher_code(self, obj):
        if obj.voucher_code:
            return obj.voucher_code
        if self.context.get("skip_preview_numbers", False):
            return None
        try:
            dt_id = self._get_document_type_id(obj)
            res = DocumentNumberService.peek_preview(
                entity_id=obj.entity_id,
                entityfinid_id=obj.entityfinid_id,
                subentity_id=obj.subentity_id,
                doc_type_id=dt_id,
                doc_code=obj.doc_code,
                on_date=obj.voucher_date,
            )
            return res.display_no
        except Exception:
            return None

    def validate(self, attrs):
        inst = getattr(self, "instance", None)
        if inst and int(inst.status) in (
            int(PaymentVoucherHeader.Status.POSTED),
            int(PaymentVoucherHeader.Status.CANCELLED),
        ):
            raise serializers.ValidationError("Cannot edit a POSTED or CANCELLED payment voucher.")
        return attrs

    def create(self, validated_data):
        try:
            return PaymentVoucherService.create_voucher(validated_data)
        except ValueError as e:
            payload = e.args[0] if e.args else str(e)
            if isinstance(payload, dict):
                raise serializers.ValidationError(payload)
            raise serializers.ValidationError({"non_field_errors": [str(payload)]})

    def update(self, instance, validated_data):
        try:
            return PaymentVoucherService.update_voucher(instance, validated_data)
        except ValueError as e:
            payload = e.args[0] if e.args else str(e)
            if isinstance(payload, dict):
                raise serializers.ValidationError(payload)
            raise serializers.ValidationError({"non_field_errors": [str(payload)]})


class PaymentVoucherListSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    payment_type_name = serializers.CharField(source="get_payment_type_display", read_only=True)

    class Meta:
        model = PaymentVoucherHeader
        fields = [
            "id",
            "voucher_date",
            "doc_code",
            "doc_no",
            "voucher_code",
            "status",
            "status_name",
            "payment_type",
            "payment_type_name",
            "paid_to",
            "cash_paid_amount",
            "total_adjustment_amount",
            "settlement_effective_amount",
            "reference_number",
            "entity",
            "entityfinid",
            "subentity",
            "created_at",
            "updated_at",
        ]
