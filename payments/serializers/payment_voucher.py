from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from payments.models import (
    PaymentVoucherHeader,
    PaymentVoucherAllocation,
    PaymentVoucherAdjustment,
    PaymentVoucherAdvanceAdjustment,
)
from payments.services.payment_voucher_nav_service import PaymentVoucherNavService
from payments.services.payment_voucher_service import PaymentVoucherService


class PaymentVoucherAllocationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    open_item_label = serializers.SerializerMethodField(read_only=True)
    purchase_number = serializers.CharField(source="open_item.purchase_number", read_only=True)
    supplier_invoice_number = serializers.CharField(source="open_item.supplier_invoice_number", read_only=True)

    class Meta:
        model = PaymentVoucherAllocation
        fields = [
            "id",
            "open_item",
            "open_item_label",
            "purchase_number",
            "supplier_invoice_number",
            "settled_amount",
            "is_full_settlement",
            "is_advance_adjustment",
        ]

    def get_open_item_label(self, obj):
        item = getattr(obj, "open_item", None)
        if not item:
            return None
        return item.purchase_number or item.supplier_invoice_number or f"Open Item {item.id}"


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


class PaymentVoucherAdvanceAdjustmentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    advance_balance_id = serializers.IntegerField(required=False)
    doc_no = serializers.SerializerMethodField(read_only=True)
    voucher_id = serializers.IntegerField(source="advance_balance.payment_voucher_id", read_only=True)
    voucher_code = serializers.CharField(source="advance_balance.payment_voucher.doc_code", read_only=True)
    voucher_date = serializers.DateField(source="advance_balance.payment_voucher.voucher_date", format="%Y-%m-%d", read_only=True)
    payment_type = serializers.CharField(source="advance_balance.payment_voucher.payment_type", read_only=True)
    balance_amount = serializers.DecimalField(source="advance_balance.outstanding_amount", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PaymentVoucherAdvanceAdjustment
        fields = [
            "id",
            "advance_balance_id",
            "voucher_id",
            "doc_no",
            "voucher_code",
            "voucher_date",
            "payment_type",
            "allocation",
            "open_item",
            "adjusted_amount",
            "balance_amount",
            "remarks",
        ]

    def get_doc_no(self, obj):
        pv = getattr(getattr(obj, "advance_balance", None), "payment_voucher", None)
        return getattr(pv, "voucher_code", None) or getattr(getattr(obj, "advance_balance", None), "reference_no", None)


class PaymentVoucherHeaderSerializer(serializers.ModelSerializer):
    voucher_date = serializers.DateField(format="%Y-%m-%d")
    instrument_date = serializers.DateField(format="%Y-%m-%d", required=False, allow_null=True)
    approved_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    cancelled_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    allocations = PaymentVoucherAllocationSerializer(many=True, required=False)
    adjustments = PaymentVoucherAdjustmentSerializer(many=True, required=False)
    advance_adjustments = PaymentVoucherAdvanceAdjustmentSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    payment_type_name = serializers.CharField(source="get_payment_type_display", read_only=True)
    supply_type_name = serializers.CharField(source="get_supply_type_display", read_only=True)
    preview_doc_no = serializers.SerializerMethodField()
    preview_voucher_code = serializers.SerializerMethodField()
    advance_balance_id = serializers.SerializerMethodField()
    approval_state = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()
    approval_status_name = serializers.SerializerMethodField()
    navigation = serializers.SerializerMethodField()
    number_navigation = serializers.SerializerMethodField()
    paid_from_name = serializers.CharField(source="paid_from.effective_accounting_name", read_only=True)
    paid_from_accountcode = serializers.IntegerField(source="paid_from.effective_accounting_code", read_only=True)
    paid_from_ledger_id = serializers.IntegerField(read_only=True)
    paid_from_partytype = serializers.CharField(source="paid_from.commercial_profile.partytype", read_only=True)
    paid_to_name = serializers.CharField(source="paid_to.effective_accounting_name", read_only=True)
    paid_to_accountcode = serializers.IntegerField(source="paid_to.effective_accounting_code", read_only=True)
    paid_to_ledger_id = serializers.IntegerField(read_only=True)
    paid_to_partytype = serializers.CharField(source="paid_to.commercial_profile.partytype", read_only=True)
    payment_mode_name = serializers.CharField(source="payment_mode.paymentmode", read_only=True)
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
        rel = getattr(obj, "vendor_advance_balance", None)
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
        return PaymentVoucherNavService.get_prev_next_for_instance(obj)

    def get_number_navigation(self, obj):
        if self.context.get("skip_navigation", False):
            return None
        return PaymentVoucherNavService.get_number_navigation(obj)

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
            "currency_code",
            "base_currency_code",
            "exchange_rate",
            "preview_doc_no",
            "preview_voucher_code",
            "advance_balance_id",
            "payment_type",
            "payment_type_name",
            "supply_type",
            "supply_type_name",
            "paid_from",
            "paid_from_name",
            "paid_from_accountcode",
            "paid_from_ledger_id",
            "paid_from_partytype",
            "paid_to",
            "paid_to_name",
            "paid_to_accountcode",
            "paid_to_ledger_id",
            "paid_to_partytype",
            "payment_mode",
            "payment_mode_name",
            "cash_paid_amount",
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
            "vendor_gstin",
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
    voucher_date = serializers.DateField(format="%Y-%m-%d")
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    payment_type_name = serializers.CharField(source="get_payment_type_display", read_only=True)
    approval_status = serializers.SerializerMethodField()
    approval_status_name = serializers.SerializerMethodField()
    advance_balance_id = serializers.SerializerMethodField()
    paid_to_name = serializers.CharField(source="paid_to.effective_accounting_name", read_only=True)
    paid_to_accountcode = serializers.IntegerField(source="paid_to.effective_accounting_code", read_only=True)
    paid_to_ledger_id = serializers.IntegerField(read_only=True)
    paid_to_partytype = serializers.CharField(source="paid_to.commercial_profile.partytype", read_only=True)
    paid_from_name = serializers.CharField(source="paid_from.effective_accounting_name", read_only=True)
    paid_from_accountcode = serializers.IntegerField(source="paid_from.effective_accounting_code", read_only=True)
    paid_from_ledger_id = serializers.IntegerField(read_only=True)
    paid_from_partytype = serializers.CharField(source="paid_from.commercial_profile.partytype", read_only=True)
    payment_mode_name = serializers.CharField(source="payment_mode.paymentmode", read_only=True)
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
        rel = getattr(obj, "vendor_advance_balance", None)
        return getattr(rel, "id", None)

    def get_advance_consumed_amount(self, obj):
        total = Decimal("0.00")
        for row in getattr(obj, "advance_adjustments", []).all() if hasattr(getattr(obj, "advance_adjustments", None), "all") else []:
            total += Decimal(getattr(row, "adjusted_amount", 0) or 0)
        return total

    def get_total_settlement_support_amount(self, obj):
        return Decimal(getattr(obj, "settlement_effective_amount", 0) or 0) + Decimal(self.get_advance_consumed_amount(obj) or 0)

    class Meta:
        model = PaymentVoucherHeader
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
            "payment_type",
            "payment_type_name",
            "paid_from",
            "paid_from_name",
            "paid_from_accountcode",
            "paid_from_ledger_id",
            "paid_from_partytype",
            "paid_to",
            "paid_to_name",
            "paid_to_accountcode",
            "paid_to_ledger_id",
            "paid_to_partytype",
            "payment_mode_name",
            "cash_paid_amount",
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
