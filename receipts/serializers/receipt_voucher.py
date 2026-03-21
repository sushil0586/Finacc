from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from receipts.models import (
    ReceiptVoucherHeader,
    ReceiptVoucherAllocation,
    ReceiptVoucherAdjustment,
    ReceiptVoucherAdvanceAdjustment,
)
from receipts.services.receipt_voucher_nav_service import ReceiptVoucherNavService
from receipts.services.receipt_voucher_service import ReceiptVoucherService


class ReceiptVoucherAllocationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    open_item_label = serializers.SerializerMethodField(read_only=True)
    invoice_number = serializers.CharField(source="open_item.invoice_number", read_only=True)
    customer_reference_number = serializers.CharField(source="open_item.customer_reference_number", read_only=True)

    class Meta:
        model = ReceiptVoucherAllocation
        fields = [
            "id",
            "open_item",
            "open_item_label",
            "invoice_number",
            "customer_reference_number",
            "settled_amount",
            "is_full_settlement",
            "is_advance_adjustment",
        ]

    def get_open_item_label(self, obj):
        item = getattr(obj, "open_item", None)
        if not item:
            return None
        invoice_number = getattr(item, "invoice_number", None) or getattr(item, "purchase_number", None)
        customer_ref = getattr(item, "customer_reference_number", None) or getattr(item, "supplier_invoice_number", None)
        return invoice_number or customer_ref or f"Open Item {item.id}"


class ReceiptVoucherAdjustmentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ReceiptVoucherAdjustment
        fields = [
            "id",
            "allocation",
            "adj_type",
            "ledger_account",
            "amount",
            "settlement_effect",
            "remarks",
        ]


class ReceiptVoucherAdvanceAdjustmentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    advance_balance_id = serializers.IntegerField(required=False)
    doc_no = serializers.SerializerMethodField(read_only=True)
    voucher_id = serializers.IntegerField(source="advance_balance.receipt_voucher_id", read_only=True)
    voucher_code = serializers.CharField(source="advance_balance.receipt_voucher.doc_code", read_only=True)
    voucher_date = serializers.DateField(source="advance_balance.receipt_voucher.voucher_date", format="%Y-%m-%d", read_only=True)
    receipt_type = serializers.CharField(source="advance_balance.receipt_voucher.receipt_type", read_only=True)
    balance_amount = serializers.DecimalField(source="advance_balance.outstanding_amount", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ReceiptVoucherAdvanceAdjustment
        fields = [
            "id",
            "advance_balance_id",
            "voucher_id",
            "doc_no",
            "voucher_code",
            "voucher_date",
            "receipt_type",
            "allocation",
            "open_item",
            "adjusted_amount",
            "balance_amount",
            "remarks",
        ]

    def get_doc_no(self, obj):
        pv = getattr(getattr(obj, "advance_balance", None), "receipt_voucher", None)
        return getattr(pv, "voucher_code", None) or getattr(getattr(obj, "advance_balance", None), "reference_no", None)


class ReceiptVoucherHeaderSerializer(serializers.ModelSerializer):
    voucher_date = serializers.DateField(format="%Y-%m-%d")
    instrument_date = serializers.DateField(format="%Y-%m-%d", required=False, allow_null=True)
    approved_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    cancelled_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    allocations = ReceiptVoucherAllocationSerializer(many=True, required=False)
    adjustments = ReceiptVoucherAdjustmentSerializer(many=True, required=False)
    advance_adjustments = ReceiptVoucherAdvanceAdjustmentSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    receipt_type_name = serializers.CharField(source="get_receipt_type_display", read_only=True)
    supply_type_name = serializers.CharField(source="get_supply_type_display", read_only=True)
    preview_doc_no = serializers.SerializerMethodField()
    preview_voucher_code = serializers.SerializerMethodField()
    advance_balance_id = serializers.SerializerMethodField()
    approval_state = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()
    approval_status_name = serializers.SerializerMethodField()
    navigation = serializers.SerializerMethodField()
    number_navigation = serializers.SerializerMethodField()
    received_in_name = serializers.CharField(source="received_in.effective_accounting_name", read_only=True)
    received_in_accountcode = serializers.IntegerField(source="received_in.effective_accounting_code", read_only=True)
    received_in_ledger_id = serializers.IntegerField(read_only=True)
    received_in_partytype = serializers.CharField(source="received_in.commercial_profile.partytype", read_only=True)
    received_from_name = serializers.CharField(source="received_from.effective_accounting_name", read_only=True)
    received_from_accountcode = serializers.IntegerField(source="received_from.effective_accounting_code", read_only=True)
    received_from_ledger_id = serializers.IntegerField(read_only=True)
    received_from_partytype = serializers.CharField(source="received_from.commercial_profile.partytype", read_only=True)
    receipt_mode_name = serializers.CharField(source="receipt_mode.paymentmode", read_only=True)
    advance_consumed_amount = serializers.SerializerMethodField()
    total_settlement_support_amount = serializers.SerializerMethodField()
    allocated_amount = serializers.SerializerMethodField()
    settlement_balance_amount = serializers.SerializerMethodField()
    ap_settlement_summary = serializers.SerializerMethodField()

    @staticmethod
    def _workflow_state(payload):
        data = payload if isinstance(payload, dict) else {}
        state = data.get("_approval_state")
        if not isinstance(state, dict):
            state = {"status": "DRAFT"}
        return state

    def get_approval_state(self, obj):
        return self._workflow_state(getattr(obj, "workflow_payload", None))

    def get_advance_balance_id(self, obj):
        rel = getattr(obj, "customer_advance_balance", None)
        return getattr(rel, "id", None)

    def get_approval_status(self, obj):
        return self.get_approval_state(obj).get("status") or "DRAFT"

    def get_approval_status_name(self, obj):
        mapping = {
            "DRAFT": "Draft",
            "SUBMITTED": "Submitted",
            "APPROVED": "Approved",
            "REJECTED": "Rejected",
        }
        status = str(self.get_approval_status(obj)).upper()
        return mapping.get(status, status.title())

    def get_advance_consumed_amount(self, obj):
        total = Decimal("0.00")
        for row in getattr(obj, "advance_adjustments", []).all() if hasattr(getattr(obj, "advance_adjustments", None), "all") else []:
            total += Decimal(getattr(row, "adjusted_amount", 0) or 0)
        return total

    def get_navigation(self, obj):
        if self.context.get("skip_navigation", False):
            return None
        return ReceiptVoucherNavService.get_prev_next_for_instance(obj)

    def get_number_navigation(self, obj):
        if self.context.get("skip_navigation", False):
            return None
        return ReceiptVoucherNavService.get_number_navigation(obj)

    def get_total_settlement_support_amount(self, obj):
        return Decimal(getattr(obj, "settlement_effective_amount", 0) or 0) + Decimal(self.get_advance_consumed_amount(obj) or 0)

    def get_allocated_amount(self, obj):
        total = Decimal("0.00")
        for row in getattr(obj, "allocations", []).all() if hasattr(getattr(obj, "allocations", None), "all") else []:
            total += Decimal(getattr(row, "settled_amount", 0) or 0)
        return total

    def get_settlement_balance_amount(self, obj):
        return Decimal(self.get_total_settlement_support_amount(obj) or 0) - Decimal(self.get_allocated_amount(obj) or 0)

    def get_ap_settlement_summary(self, obj):
        if not getattr(obj, "ap_settlement_id", None):
            return None
        settlement = getattr(obj, "ap_settlement", None)
        if not settlement:
            return {"id": obj.ap_settlement_id}
        return {
            "id": settlement.id,
            "status": settlement.status,
            "status_name": getattr(settlement, "get_status_display", lambda: None)(),
            "total_settled_amount": settlement.total_amount,
        }

    class Meta:
        model = ReceiptVoucherHeader
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "voucher_date",
            "doc_code",
            "doc_no",
            "voucher_code",
            "currency_code",
            "base_currency_code",
            "exchange_rate",
            "preview_doc_no",
            "preview_voucher_code",
            "advance_balance_id",
            "receipt_type",
            "receipt_type_name",
            "supply_type",
            "supply_type_name",
            "received_in",
            "received_in_name",
            "received_in_accountcode",
            "received_in_ledger_id",
            "received_in_partytype",
            "received_from",
            "received_from_name",
            "received_from_accountcode",
            "received_from_ledger_id",
            "received_from_partytype",
            "receipt_mode",
            "receipt_mode_name",
            "cash_received_amount",
            "total_adjustment_amount",
            "settlement_effective_amount",
            "settlement_effective_amount_base_currency",
            "advance_consumed_amount",
            "total_settlement_support_amount",
            "allocated_amount",
            "settlement_balance_amount",
            "reference_number",
            "narration",
            "instrument_bank_name",
            "instrument_no",
            "instrument_date",
            "place_of_supply_state",
            "customer_gstin",
            "advance_taxable_value",
            "advance_cgst",
            "advance_sgst",
            "advance_igst",
            "advance_cess",
            "status",
            "status_name",
            "approval_state",
            "approval_status",
            "approval_status_name",
            "navigation",
            "number_navigation",
            "approved_by",
            "approved_at",
            "workflow_payload",
            "is_cancelled",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
            "created_by",
            "ap_settlement",
            "ap_settlement_summary",
            "allocations",
            "advance_adjustments",
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
            module="receipts",
            default_code=obj.doc_code,
            is_active=True,
        ).first()
        if not dt:
            raise serializers.ValidationError(f"DocumentType not found for receipt doc_code={obj.doc_code}")
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
            int(ReceiptVoucherHeader.Status.POSTED),
            int(ReceiptVoucherHeader.Status.CANCELLED),
        ):
            raise serializers.ValidationError("Cannot edit a POSTED or CANCELLED receipt voucher.")
        return attrs

    def create(self, validated_data):
        try:
            return ReceiptVoucherService.create_voucher(validated_data)
        except ValueError as e:
            payload = e.args[0] if e.args else str(e)
            if isinstance(payload, dict):
                raise serializers.ValidationError(payload)
            raise serializers.ValidationError({"non_field_errors": [str(payload)]})

    def update(self, instance, validated_data):
        try:
            return ReceiptVoucherService.update_voucher(instance, validated_data)
        except ValueError as e:
            payload = e.args[0] if e.args else str(e)
            if isinstance(payload, dict):
                raise serializers.ValidationError(payload)
            raise serializers.ValidationError({"non_field_errors": [str(payload)]})


class ReceiptVoucherListSerializer(serializers.ModelSerializer):
    voucher_date = serializers.DateField(format="%Y-%m-%d")
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    receipt_type_name = serializers.CharField(source="get_receipt_type_display", read_only=True)
    approval_status = serializers.SerializerMethodField()
    approval_status_name = serializers.SerializerMethodField()
    advance_balance_id = serializers.SerializerMethodField()
    received_from_name = serializers.CharField(source="received_from.effective_accounting_name", read_only=True)
    received_from_accountcode = serializers.IntegerField(source="received_from.effective_accounting_code", read_only=True)
    received_from_ledger_id = serializers.IntegerField(read_only=True)
    received_from_partytype = serializers.CharField(source="received_from.commercial_profile.partytype", read_only=True)
    receipt_mode_name = serializers.CharField(source="receipt_mode.paymentmode", read_only=True)
    advance_consumed_amount = serializers.SerializerMethodField()
    total_settlement_support_amount = serializers.SerializerMethodField()

    @staticmethod
    def _workflow_state(payload):
        data = payload if isinstance(payload, dict) else {}
        state = data.get("_approval_state")
        if not isinstance(state, dict):
            state = {"status": "DRAFT"}
        return state

    def get_approval_status(self, obj):
        return self._workflow_state(getattr(obj, "workflow_payload", None)).get("status") or "DRAFT"

    def get_approval_status_name(self, obj):
        mapping = {
            "DRAFT": "Draft",
            "SUBMITTED": "Submitted",
            "APPROVED": "Approved",
            "REJECTED": "Rejected",
        }
        status = str(self.get_approval_status(obj)).upper()
        return mapping.get(status, status.title())

    def get_advance_balance_id(self, obj):
        rel = getattr(obj, "customer_advance_balance", None)
        return getattr(rel, "id", None)

    def get_advance_consumed_amount(self, obj):
        total = Decimal("0.00")
        for row in getattr(obj, "advance_adjustments", []).all() if hasattr(getattr(obj, "advance_adjustments", None), "all") else []:
            total += Decimal(getattr(row, "adjusted_amount", 0) or 0)
        return total

    def get_total_settlement_support_amount(self, obj):
        return Decimal(getattr(obj, "settlement_effective_amount", 0) or 0) + Decimal(self.get_advance_consumed_amount(obj) or 0)

    class Meta:
        model = ReceiptVoucherHeader
        fields = [
            "id",
            "voucher_date",
            "doc_code",
            "doc_no",
            "voucher_code",
            "advance_balance_id",
            "status",
            "status_name",
            "approval_status",
            "approval_status_name",
            "receipt_type",
            "receipt_type_name",
            "received_from",
            "received_from_name",
            "received_from_accountcode",
            "received_from_ledger_id",
            "received_from_partytype",
            "receipt_mode_name",
            "cash_received_amount",
            "total_adjustment_amount",
            "settlement_effective_amount",
            "settlement_effective_amount_base_currency",
            "advance_consumed_amount",
            "total_settlement_support_amount",
            "reference_number",
            "entity",
            "entityfinid",
            "subentity",
            "created_at",
            "updated_at",
        ]
