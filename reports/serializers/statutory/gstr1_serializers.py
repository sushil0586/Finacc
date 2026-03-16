from __future__ import annotations

from rest_framework import serializers


class Gstr1RowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    invoice_date = serializers.DateField(allow_null=True)
    posting_date = serializers.DateField(allow_null=True)
    doc_type = serializers.IntegerField()
    doc_type_name = serializers.CharField()
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    customer_name = serializers.CharField(allow_blank=True, allow_null=True)
    customer_gstin = serializers.CharField(allow_blank=True, allow_null=True)
    place_of_supply = serializers.CharField(allow_blank=True, allow_null=True)
    supply_category = serializers.IntegerField()
    supply_category_name = serializers.CharField(allow_blank=True, allow_null=True)
    taxability = serializers.IntegerField()
    taxability_name = serializers.CharField(allow_blank=True, allow_null=True)
    tax_regime = serializers.IntegerField()
    tax_regime_name = serializers.CharField(allow_blank=True, allow_null=True)
    section = serializers.CharField(allow_blank=True, allow_null=True)
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)
    status = serializers.IntegerField()
    status_name = serializers.CharField()
    affects_totals = serializers.BooleanField()
    drilldown = serializers.DictField()


class Gstr1TotalsSerializer(serializers.Serializer):
    document_count = serializers.IntegerField()
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)


class Gstr1SectionSummarySerializer(serializers.Serializer):
    section = serializers.CharField()
    document_count = serializers.IntegerField()
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)
