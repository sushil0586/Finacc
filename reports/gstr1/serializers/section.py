from __future__ import annotations

from rest_framework import serializers


class Gstr1SectionRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    invoice_date = serializers.DateField()
    posting_date = serializers.DateField(allow_null=True)
    doc_type = serializers.IntegerField()
    doc_type_name = serializers.CharField()
    invoice_number = serializers.CharField(allow_blank=True, allow_null=True)
    customer_name = serializers.CharField(allow_blank=True, allow_null=True)
    customer_gstin = serializers.CharField(allow_blank=True, allow_null=True)
    place_of_supply_state_code = serializers.CharField(allow_blank=True, allow_null=True)
    tax_regime = serializers.IntegerField()
    taxability = serializers.IntegerField()
    supply_category = serializers.IntegerField()
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)
    status = serializers.IntegerField()
    status_name = serializers.CharField()
    drilldown = serializers.DictField()


class Gstr1SectionEnvelopeSerializer(serializers.Serializer):
    section = serializers.CharField()
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = Gstr1SectionRowSerializer(many=True)
