from __future__ import annotations

from rest_framework import serializers

from sales.models.sales_ar import CustomerAdvanceBalance


class ReceiptOpenAdvanceSerializer(serializers.ModelSerializer):
    advance_balance_id = serializers.IntegerField(read_only=True)
    voucher_id = serializers.IntegerField(source="receipt_voucher_id", read_only=True)
    doc_no = serializers.SerializerMethodField()
    voucher_code = serializers.CharField(source="receipt_voucher.doc_code", read_only=True)
    voucher_date = serializers.DateField(source="receipt_voucher.voucher_date", format="%Y-%m-%d", read_only=True)
    receipt_type = serializers.CharField(source="receipt_voucher.receipt_type", read_only=True)
    balance_amount = serializers.DecimalField(source="outstanding_amount", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CustomerAdvanceBalance
        fields = [
            "id",
            "advance_balance_id",
            "customer",
            "voucher_id",
            "doc_no",
            "voucher_code",
            "voucher_date",
            "receipt_type",
            "original_amount",
            "adjusted_amount",
            "balance_amount",
            "is_open",
        ]

    def get_doc_no(self, obj):
        pv = getattr(obj, "receipt_voucher", None)
        return getattr(pv, "voucher_code", None) or obj.reference_no
