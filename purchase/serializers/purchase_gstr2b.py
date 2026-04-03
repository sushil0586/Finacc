from __future__ import annotations

from rest_framework import serializers

from financial.gstin import validate_financial_gstin
from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow


class Gstr2bImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gstr2bImportRow
        fields = [
            "id",
            "batch",
            "supplier_gstin",
            "supplier_name",
            "supplier_invoice_number",
            "supplier_invoice_date",
            "doc_type",
            "pos_state",
            "is_igst",
            "taxable_value",
            "igst",
            "cgst",
            "sgst",
            "cess",
            "matched_purchase",
            "match_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "batch", "matched_purchase", "match_status", "created_at", "updated_at"]


class Gstr2bImportRowInputSerializer(serializers.Serializer):
    supplier_gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    supplier_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    supplier_invoice_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    supplier_invoice_date = serializers.DateField(required=False, allow_null=True)
    doc_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pos_state = serializers.IntegerField(required=False, allow_null=True)
    is_igst = serializers.BooleanField(required=False, default=False)
    taxable_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default="0.00")
    igst = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default="0.00")
    cgst = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default="0.00")
    sgst = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default="0.00")
    cess = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default="0.00")

    def validate_supplier_gstin(self, value):
        try:
            return validate_financial_gstin(value)
        except Exception as ex:
            raise serializers.ValidationError(str(ex))


class Gstr2bImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gstr2bImportBatch
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "period",
            "source",
            "reference",
            "imported_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "imported_by", "created_at", "updated_at"]


class Gstr2bImportBatchCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField()
    subentity = serializers.IntegerField(required=False, allow_null=True)
    period = serializers.RegexField(r"^\d{4}-\d{2}$")
    source = serializers.CharField(required=False, allow_blank=True, default="gstr2b")
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    rows = Gstr2bImportRowInputSerializer(many=True)

