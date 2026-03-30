from __future__ import annotations

from rest_framework import serializers

from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger


class EntityGstTdsConfigSerializer(serializers.ModelSerializer):
    def validate_threshold_amount(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("threshold_amount cannot be negative.")
        return value

    class Meta:
        model = EntityGstTdsConfig
        fields = [
            "id",
            "entity",
            "subentity",
            "enabled",
            "threshold_amount",
            "enforce_pos_rule",
        ]
        read_only_fields = ["id", "entity", "subentity"]


class GstTdsContractLedgerSerializer(serializers.ModelSerializer):
    vendor_name = serializers.SerializerMethodField()

    class Meta:
        model = GstTdsContractLedger
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "vendor",
            "vendor_name",
            "contract_ref",
            "cumulative_taxable",
            "cumulative_tds",
            "updated_at",
        ]
        read_only_fields = fields

    def get_vendor_name(self, obj) -> str:
        vendor = getattr(obj, "vendor", None)
        return str(getattr(vendor, "accountname", "") or "")
