from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from sales.models.sales_addons import SalesChargeLine, SalesChargeType
from sales.models.sales_core import SalesInvoiceHeader

ZERO2 = Decimal("0.00")


class SalesChargeLineSerializer(serializers.ModelSerializer):
    charge_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    charge_type_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    taxability = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    charge_type_name = serializers.CharField(source="get_charge_type_display", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)

    class Meta:
        model = SalesChargeLine
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
            "taxable_value",
            "gst_rate",
            "revenue_account",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "total_value",
        ]
        read_only_fields = ["cgst_amount", "sgst_amount", "igst_amount", "total_value"]

    @staticmethod
    def _normalize_taxability(raw_value):
        if raw_value in (None, ""):
            return None
        if isinstance(raw_value, int):
            return raw_value

        txt = str(raw_value).strip()
        if not txt:
            return None
        if txt.isdigit():
            return int(txt)

        by_name = {name.upper(): int(value) for name, value in SalesInvoiceHeader.Taxability.__members__.items()}
        if txt.upper() in by_name:
            return by_name[txt.upper()]

        by_label = {str(label).strip().upper(): int(value) for value, label in SalesInvoiceHeader.Taxability.choices}
        if txt.upper() in by_label:
            return by_label[txt.upper()]
        return raw_value

    def validate(self, attrs):
        taxable = Decimal(attrs.get("taxable_value", ZERO2) or ZERO2)
        gst_rate = Decimal(attrs.get("gst_rate", ZERO2) or ZERO2)
        taxability = self._normalize_taxability(attrs.get("taxability", None))
        if taxability is None:
            taxability = getattr(self.instance, "taxability", None)
        attrs["taxability"] = taxability

        if taxable < ZERO2:
            raise serializers.ValidationError({"taxable_value": "Must be >= 0."})
        if gst_rate < ZERO2 or gst_rate > Decimal("100.00"):
            raise serializers.ValidationError({"gst_rate": "Must be between 0 and 100."})

        valid_values = {int(v) for v, _ in SalesInvoiceHeader.Taxability.choices}
        if taxability is not None and int(taxability) not in valid_values:
            allowed = ", ".join([f"{v}:{label}" for v, label in SalesInvoiceHeader.Taxability.choices])
            raise serializers.ValidationError({"taxability": f"Invalid taxability. Use one of {allowed} or enum names like TAXABLE."})

        if taxability is not None and int(taxability) != int(SalesInvoiceHeader.Taxability.TAXABLE):
            if gst_rate > ZERO2:
                raise serializers.ValidationError({"gst_rate": "Must be 0 for non-taxable charges."})

        hsn = (attrs.get("hsn_sac_code") or "").strip()
        if gst_rate > ZERO2 and taxable > ZERO2 and not hsn:
            raise serializers.ValidationError({"hsn_sac_code": "HSN/SAC is required when GST is applied."})

        return attrs


class SalesChargeTypeSerializer(serializers.ModelSerializer):
    base_category_name = serializers.CharField(source="get_base_category_display", read_only=True)

    class Meta:
        model = SalesChargeType
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
            "description",
            "revenue_account",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_code(self, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise serializers.ValidationError("Code is required.")
        return v
