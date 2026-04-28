from __future__ import annotations

from rest_framework import serializers


class Gstr9TableCoverageSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()


class Gstr9TableRowSerializer(serializers.Serializer):
    line_no = serializers.CharField(required=False, allow_blank=True)
    particulars = serializers.CharField(required=False, allow_blank=True)
    taxable_value = serializers.DecimalField(max_digits=24, decimal_places=2, required=False)
    cgst = serializers.DecimalField(max_digits=24, decimal_places=2, required=False)
    sgst = serializers.DecimalField(max_digits=24, decimal_places=2, required=False)
    igst = serializers.DecimalField(max_digits=24, decimal_places=2, required=False)
    cess = serializers.DecimalField(max_digits=24, decimal_places=2, required=False)
    total_tax = serializers.DecimalField(max_digits=24, decimal_places=2, required=False)


class Gstr9TableEnvelopeSerializer(serializers.Serializer):
    table_code = serializers.CharField()
    table_label = serializers.CharField()
    count = serializers.IntegerField()
    rows = Gstr9TableRowSerializer(many=True)
    coverage = Gstr9TableCoverageSerializer()
