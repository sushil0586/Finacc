from __future__ import annotations

from rest_framework import serializers

from payments.models import PaymentMode


class PaymentModeSerializer(serializers.ModelSerializer):
    paymentmodeid = serializers.IntegerField(source="id", read_only=True)
    paymentmodename = serializers.CharField(source="paymentmode", read_only=True)

    class Meta:
        model = PaymentMode
        fields = [
            "paymentmodeid",
            "paymentmodename",
            "paymentmodecode",
            "iscash",
        ]
