# purchase/api/serializers/purchase_charge.py
from __future__ import annotations

from decimal import Decimal
from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP


from purchase.models.purchase_addons import PurchaseChargeLine,PurchaseChargeType
ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")
DEC2 = Decimal("0.01")
DEC4 = Decimal("0.0001")

def q2(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC2, rounding=ROUND_HALF_UP)


class PurchaseChargeLineSerializer(serializers.ModelSerializer):
    charge_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    charge_type_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    itc_block_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    charge_type_name = serializers.CharField(source="get_charge_type_display", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)

    class Meta:
        model = PurchaseChargeLine
        fields = [
            "id",
            "line_no",

            "charge_type",
            "charge_type_id",
            "charge_type_name",
            "description",

            "taxability",
            "taxability_name",

            "is_service",
            "hsn_sac_code",
            "is_rate_inclusive_of_tax",

            # inputs
            "taxable_value",
            "gst_rate",
            "itc_eligible",
            "itc_block_reason",

            # computed (server)
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "total_value",
        ]
        read_only_fields = [
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "total_value",
        ]

    def validate(self, attrs):
        # Basic sanity only; real regime split validation happens in service (needs header.tax_regime)
        taxable = q2(attrs.get("taxable_value", ZERO2) or ZERO2)
        gst_rate = q2(attrs.get("gst_rate", ZERO2) or ZERO2)
        taxability = attrs.get("taxability", None) or getattr(self.instance, "taxability", None)

        if taxable < ZERO2:
            raise serializers.ValidationError({"taxable_value": "Must be >= 0."})
        if gst_rate < ZERO2 or gst_rate > Decimal("100.00"):
            raise serializers.ValidationError({"gst_rate": "Must be between 0 and 100."})

        # If non-taxable, enforce gst_rate = 0 (keep consistent with model constraint too)
        if taxability and str(taxability) != str(PurchaseChargeLine.Taxability.TAXABLE):
            if gst_rate > ZERO2:
                raise serializers.ValidationError({"gst_rate": "Must be 0 for non-taxable charges."})

        # HSN/SAC required if GST is applied on taxable value
        hsn = (attrs.get("hsn_sac_code") or "").strip()
        if gst_rate > ZERO2 and taxable > ZERO2 and not hsn:
            raise serializers.ValidationError({"hsn_sac_code": "HSN/SAC is required when GST is applied."})

        return attrs
    


class PurchaseChargeTypeSerializer(serializers.ModelSerializer):
    base_category_name = serializers.CharField(source="get_base_category_display", read_only=True)

    class Meta:
        model = PurchaseChargeType
        fields = [
            "id",
            "entity",
            "code",
            "name",
            "base_category",
            "base_category_name",
            "is_active",
            "is_service",
            "hsn_sac_code_default",
            "gst_rate_default",
            "itc_eligible_default",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_code(self, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise serializers.ValidationError("Code is required.")
        return v
