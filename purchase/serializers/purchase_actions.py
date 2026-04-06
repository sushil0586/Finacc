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


class ItcReviewSerializer(serializers.Serializer):
    target_status = serializers.ChoiceField(choices=PurchaseInvoiceHeader.ItcClaimStatus.choices)
    claim_period = serializers.RegexField(
        regex=r"^\d{4}-\d{2}$",
        max_length=7,
        required=False,
        allow_blank=True,
        allow_null=True,
        error_messages={"invalid": "claim_period must be YYYY-MM (e.g., 2026-04)"},
    )
    block_reason = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)
    review_comment = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    def validate_claim_period(self, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        try:
            month = int(value[5:7])
        except Exception:
            raise serializers.ValidationError("claim_period must be YYYY-MM (e.g., 2026-04)")
        if month < 1 or month > 12:
            raise serializers.ValidationError("claim_period month must be between 01 and 12")
        return value

    def validate(self, attrs):
        status_value = int(attrs.get("target_status"))
        block_reason = (attrs.get("block_reason") or "").strip()
        claim_period = attrs.get("claim_period")
        if status_value == int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED) and not claim_period:
            raise serializers.ValidationError({"claim_period": "Claim period is required when marking ITC as claimed."})
        if status_value in {
            int(PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED),
            int(PurchaseInvoiceHeader.ItcClaimStatus.REVERSED),
        } and not block_reason:
            raise serializers.ValidationError({"block_reason": "Reason is required when blocking or reversing ITC."})
        return attrs
