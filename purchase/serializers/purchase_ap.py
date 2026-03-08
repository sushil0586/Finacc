from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from purchase.models.purchase_ap import VendorBillOpenItem, VendorAdvanceBalance, VendorSettlement, VendorSettlementLine


class VendorBillOpenItemSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.accountname", read_only=True)
    doc_type_name = serializers.SerializerMethodField()

    def get_doc_type_name(self, obj):
        try:
            return obj.header.get_doc_type_display()
        except Exception:
            return None

    class Meta:
        model = VendorBillOpenItem
        fields = [
            "id",
            "header",
            "entity",
            "entityfinid",
            "subentity",
            "vendor",
            "vendor_name",
            "doc_type",
            "doc_type_name",
            "bill_date",
            "due_date",
            "purchase_number",
            "supplier_invoice_number",
            "original_amount",
            "gross_amount",
            "tds_deducted",
            "gst_tds_deducted",
            "net_payable_amount",
            "settled_amount",
            "outstanding_amount",
            "is_open",
            "last_settled_at",
            "created_at",
            "updated_at",
        ]


class VendorSettlementLineSerializer(serializers.ModelSerializer):
    open_item_label = serializers.SerializerMethodField()
    purchase_number = serializers.CharField(source="open_item.purchase_number", read_only=True)
    supplier_invoice_number = serializers.CharField(source="open_item.supplier_invoice_number", read_only=True)

    def get_open_item_label(self, obj):
        item = getattr(obj, "open_item", None)
        if not item:
            return None
        return item.purchase_number or item.supplier_invoice_number or f"Open Item {item.id}"

    class Meta:
        model = VendorSettlementLine
        fields = [
            "id",
            "open_item",
            "open_item_label",
            "purchase_number",
            "supplier_invoice_number",
            "amount",
            "applied_amount_signed",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["applied_amount_signed", "created_at", "updated_at"]


class VendorSettlementSerializer(serializers.ModelSerializer):
    lines = VendorSettlementLineSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    settlement_type_name = serializers.CharField(source="get_settlement_type_display", read_only=True)
    vendor_name = serializers.CharField(source="vendor.accountname", read_only=True)
    advance_reference_no = serializers.CharField(source="advance_balance.reference_no", read_only=True)
    advance_original_amount = serializers.DecimalField(source="advance_balance.original_amount", max_digits=14, decimal_places=2, read_only=True)
    advance_balance_outstanding_amount = serializers.DecimalField(source="advance_balance.outstanding_amount", max_digits=14, decimal_places=2, read_only=True)
    source_payment_voucher_id = serializers.IntegerField(source="advance_balance.payment_voucher_id", read_only=True)
    source_payment_voucher_code = serializers.CharField(source="advance_balance.payment_voucher.voucher_code", read_only=True)

    class Meta:
        model = VendorSettlement
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "vendor",
            "vendor_name",
            "settlement_type",
            "settlement_type_name",
            "settlement_date",
            "reference_no",
            "external_voucher_no",
            "remarks",
            "advance_balance",
            "advance_reference_no",
            "advance_original_amount",
            "advance_balance_outstanding_amount",
            "source_payment_voucher_id",
            "source_payment_voucher_code",
            "total_amount",
            "status",
            "status_name",
            "posted_at",
            "posted_by",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["total_amount", "status", "posted_at", "posted_by", "created_at", "updated_at"]


class VendorAdvanceBalanceSerializer(serializers.ModelSerializer):
    advance_balance_id = serializers.IntegerField(source="id", read_only=True)
    vendor_name = serializers.CharField(source="vendor.accountname", read_only=True)
    voucher_id = serializers.IntegerField(source="payment_voucher_id", read_only=True)
    doc_no = serializers.SerializerMethodField()
    voucher_code = serializers.CharField(source="payment_voucher.doc_code", read_only=True)
    voucher_date = serializers.DateField(source="payment_voucher.voucher_date", format="%Y-%m-%d", read_only=True)
    payment_type = serializers.CharField(source="payment_voucher.payment_type", read_only=True)
    balance_amount = serializers.DecimalField(source="outstanding_amount", max_digits=14, decimal_places=2, read_only=True)
    consumption_history = serializers.SerializerMethodField()

    def get_doc_no(self, obj):
        pv = getattr(obj, "payment_voucher", None)
        return getattr(pv, "voucher_code", None) or obj.reference_no

    def get_consumption_history(self, obj):
        rows = []
        settlements = getattr(obj, "settlements", None)
        iterable = settlements.all().order_by("-settlement_date", "-id")[:20] if settlements is not None else []
        for st in iterable:
            lines = getattr(st, "lines", None)
            line_items = []
            if lines is not None:
                for ln in lines.all():
                    line_items.append({
                        "open_item": ln.open_item_id,
                        "purchase_number": getattr(getattr(ln, "open_item", None), "purchase_number", None),
                        "supplier_invoice_number": getattr(getattr(ln, "open_item", None), "supplier_invoice_number", None),
                        "amount": ln.amount,
                        "applied_amount_signed": ln.applied_amount_signed,
                    })
            rows.append({
                "settlement_id": st.id,
                "settlement_type": st.settlement_type,
                "settlement_type_name": st.get_settlement_type_display(),
                "settlement_date": st.settlement_date,
                "reference_no": st.reference_no,
                "status": st.status,
                "status_name": st.get_status_display(),
                "total_amount": st.total_amount,
                "lines": line_items,
            })
        return rows

    class Meta:
        model = VendorAdvanceBalance
        fields = [
            "id",
            "advance_balance_id",
            "entity",
            "entityfinid",
            "subentity",
            "vendor",
            "vendor_name",
            "source_type",
            "credit_date",
            "reference_no",
            "remarks",
            "original_amount",
            "adjusted_amount",
            "outstanding_amount",
            "balance_amount",
            "is_open",
            "last_adjusted_at",
            "payment_voucher",
            "voucher_id",
            "doc_no",
            "voucher_code",
            "voucher_date",
            "payment_type",
            "consumption_history",
            "created_at",
            "updated_at",
        ]


class VendorSettlementCreateLineInputSerializer(serializers.Serializer):
    open_item_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class VendorSettlementCreateInputSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    vendor = serializers.IntegerField(min_value=1)

    settlement_type = serializers.ChoiceField(choices=VendorSettlement.SettlementType.choices, default=VendorSettlement.SettlementType.PAYMENT)
    settlement_date = serializers.DateField()
    reference_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    external_voucher_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, min_value=Decimal("0.01"))
    advance_balance = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    lines = VendorSettlementCreateLineInputSerializer(many=True, required=False)

    def validate(self, attrs):
        lines = attrs.get("lines") or []
        amount = attrs.get("amount")
        if not lines and amount is None:
            raise serializers.ValidationError({"detail": "Provide lines or amount (for FIFO allocation)."})
        return attrs
