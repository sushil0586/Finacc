from __future__ import annotations

from rest_framework import serializers

from receipts.models import ReceiptMode


class ReceiptModeSerializer(serializers.ModelSerializer):
    paymentmodeid = serializers.IntegerField(source="id", read_only=True)
    paymentmodename = serializers.CharField(source="paymentmode", read_only=True)

    class Meta:
        model = ReceiptMode
        fields = [
            "paymentmodeid",
            "paymentmodename",
            "paymentmodecode",
            "iscash",
        ]
