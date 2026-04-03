from purchase.models.purchase_core import PurchaseInvoiceHeader
from rest_framework import serializers


class ItcBlockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ItcUnblockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)


class ItcClaimSerializer(serializers.Serializer):
    period = serializers.RegexField(
        regex=r"^\d{4}-\d{2}$",
        max_length=7,
        error_messages={"invalid": "period must be YYYY-MM (e.g., 2026-02)"},
    )

    def validate_period(self, value: str) -> str:
        try:
            month = int(value[5:7])
        except Exception:
            raise serializers.ValidationError("period must be YYYY-MM (e.g., 2026-02)")
        if month < 1 or month > 12:
            raise serializers.ValidationError("period month must be between 01 and 12")
        return value


class Match2BSerializer(serializers.Serializer):
    match_status = serializers.ChoiceField(choices=PurchaseInvoiceHeader.Gstr2bMatchStatus.choices)
