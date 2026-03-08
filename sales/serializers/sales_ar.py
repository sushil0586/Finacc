from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from sales.models.sales_ar import CustomerBillOpenItem, CustomerAdvanceBalance, CustomerSettlement, CustomerSettlementLine


class CustomerBillOpenItemSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.accountname", read_only=True)
    doc_type_name = serializers.SerializerMethodField()

    def get_doc_type_name(self, obj):
        try:
            return obj.header.get_doc_type_display()
        except Exception:
            return None

    class Meta:
        model = CustomerBillOpenItem
        fields = [
            "id",
            "header",
            "entity",
            "entityfinid",
            "subentity",
            "customer",
            "customer_name",
            "doc_type",
            "doc_type_name",
            "bill_date",
            "due_date",
            "invoice_number",
            "customer_reference_number",
            "original_amount",
            "gross_amount",
            "tds_collected",
            "gst_tds_collected",
            "net_receivable_amount",
            "settled_amount",
            "outstanding_amount",
            "is_open",
            "last_settled_at",
            "created_at",
            "updated_at",
        ]


class CustomerSettlementLineSerializer(serializers.ModelSerializer):
    open_item_label = serializers.SerializerMethodField()
    invoice_number = serializers.CharField(source="open_item.invoice_number", read_only=True)
    customer_reference_number = serializers.CharField(source="open_item.customer_reference_number", read_only=True)

    def get_open_item_label(self, obj):
        item = getattr(obj, "open_item", None)
        if not item:
            return None
        return item.invoice_number or item.customer_reference_number or f"Open Item {item.id}"

    class Meta:
        model = CustomerSettlementLine
        fields = [
            "id",
            "open_item",
            "open_item_label",
            "invoice_number",
            "customer_reference_number",
            "amount",
            "applied_amount_signed",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["applied_amount_signed", "created_at", "updated_at"]


class CustomerSettlementSerializer(serializers.ModelSerializer):
    lines = CustomerSettlementLineSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    settlement_type_name = serializers.CharField(source="get_settlement_type_display", read_only=True)
    customer_name = serializers.CharField(source="customer.accountname", read_only=True)
    advance_reference_no = serializers.CharField(source="advance_balance.reference_no", read_only=True)
    advance_original_amount = serializers.DecimalField(source="advance_balance.original_amount", max_digits=14, decimal_places=2, read_only=True)
    advance_balance_outstanding_amount = serializers.DecimalField(source="advance_balance.outstanding_amount", max_digits=14, decimal_places=2, read_only=True)
    source_receipt_voucher_id = serializers.IntegerField(source="advance_balance.receipt_voucher_id", read_only=True)
    source_receipt_voucher_code = serializers.CharField(source="advance_balance.receipt_voucher.voucher_code", read_only=True)

    class Meta:
        model = CustomerSettlement
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "customer",
            "customer_name",
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
            "source_receipt_voucher_id",
            "source_receipt_voucher_code",
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


class CustomerAdvanceBalanceSerializer(serializers.ModelSerializer):
    advance_balance_id = serializers.IntegerField(source="id", read_only=True)
    customer_name = serializers.CharField(source="customer.accountname", read_only=True)
    voucher_id = serializers.IntegerField(source="receipt_voucher_id", read_only=True)
    doc_no = serializers.SerializerMethodField()
    voucher_code = serializers.CharField(source="receipt_voucher.doc_code", read_only=True)
    voucher_date = serializers.DateField(source="receipt_voucher.voucher_date", format="%Y-%m-%d", read_only=True)
    receipt_type = serializers.CharField(source="receipt_voucher.receipt_type", read_only=True)
    balance_amount = serializers.DecimalField(source="outstanding_amount", max_digits=14, decimal_places=2, read_only=True)
    consumption_history = serializers.SerializerMethodField()

    def get_doc_no(self, obj):
        pv = getattr(obj, "receipt_voucher", None)
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
                        "invoice_number": getattr(getattr(ln, "open_item", None), "invoice_number", None),
                        "customer_reference_number": getattr(getattr(ln, "open_item", None), "customer_reference_number", None),
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
        model = CustomerAdvanceBalance
        fields = [
            "id",
            "advance_balance_id",
            "entity",
            "entityfinid",
            "subentity",
            "customer",
            "customer_name",
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
            "receipt_voucher",
            "voucher_id",
            "doc_no",
            "voucher_code",
            "voucher_date",
            "receipt_type",
            "consumption_history",
            "created_at",
            "updated_at",
        ]


class CustomerSettlementCreateLineInputSerializer(serializers.Serializer):
    open_item_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CustomerSettlementCreateInputSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    customer = serializers.IntegerField(min_value=1)

    settlement_type = serializers.ChoiceField(choices=CustomerSettlement.SettlementType.choices, default=CustomerSettlement.SettlementType.RECEIPT)
    settlement_date = serializers.DateField()
    reference_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    external_voucher_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, min_value=Decimal("0.01"))
    advance_balance = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    lines = CustomerSettlementCreateLineInputSerializer(many=True, required=False)

    def validate(self, attrs):
        lines = attrs.get("lines") or []
        amount = attrs.get("amount")
        if not lines and amount is None:
            raise serializers.ValidationError({"detail": "Provide lines or amount (for FIFO allocation)."})
        return attrs
