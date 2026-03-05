from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement, VendorSettlementLine


class VendorBillOpenItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorBillOpenItem
        fields = [
            "id",
            "header",
            "entity",
            "entityfinid",
            "subentity",
            "vendor",
            "doc_type",
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
    class Meta:
        model = VendorSettlementLine
        fields = [
            "id",
            "open_item",
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

    class Meta:
        model = VendorSettlement
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "vendor",
            "settlement_type",
            "settlement_type_name",
            "settlement_date",
            "reference_no",
            "external_voucher_no",
            "remarks",
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
    lines = VendorSettlementCreateLineInputSerializer(many=True, required=False)

    def validate(self, attrs):
        lines = attrs.get("lines") or []
        amount = attrs.get("amount")
        if not lines and amount is None:
            raise serializers.ValidationError({"detail": "Provide lines or amount (for FIFO allocation)."})
        return attrs
