from __future__ import annotations

from rest_framework import serializers


class SalesGstinRowSerializer(serializers.Serializer):
    customer_gstin = serializers.CharField(allow_blank=True, allow_null=True)
    customer_name = serializers.CharField(allow_blank=True, allow_null=True)
    invoice_count = serializers.IntegerField()
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_tax = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)


class SalesGstinSummarySerializer(serializers.Serializer):
    gstin_count = serializers.IntegerField()
    invoice_count = serializers.IntegerField()
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_tax = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)
