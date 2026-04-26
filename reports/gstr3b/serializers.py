from __future__ import annotations

from rest_framework import serializers


class Gstr3bTaxBucketSerializer(serializers.Serializer):
    taxable_value = serializers.DecimalField(max_digits=24, decimal_places=2)
    cgst = serializers.DecimalField(max_digits=24, decimal_places=2)
    sgst = serializers.DecimalField(max_digits=24, decimal_places=2)
    igst = serializers.DecimalField(max_digits=24, decimal_places=2)
    cess = serializers.DecimalField(max_digits=24, decimal_places=2)
    total_tax = serializers.DecimalField(max_digits=24, decimal_places=2)


class Gstr3bTaxableOnlySerializer(serializers.Serializer):
    taxable_value = serializers.DecimalField(max_digits=24, decimal_places=2)


class Gstr3bNamedTaxBucketSerializer(serializers.Serializer):
    label = serializers.CharField()
    taxable_value = serializers.DecimalField(max_digits=24, decimal_places=2)
    cgst = serializers.DecimalField(max_digits=24, decimal_places=2)
    sgst = serializers.DecimalField(max_digits=24, decimal_places=2)
    igst = serializers.DecimalField(max_digits=24, decimal_places=2)
    cess = serializers.DecimalField(max_digits=24, decimal_places=2)
    total_tax = serializers.DecimalField(max_digits=24, decimal_places=2)


class Gstr3bNamedTaxableOnlySerializer(serializers.Serializer):
    label = serializers.CharField()
    taxable_value = serializers.DecimalField(max_digits=24, decimal_places=2)


class Gstr3bSection31Serializer(serializers.Serializer):
    outward_taxable_supplies = Gstr3bTaxBucketSerializer()
    outward_zero_rated_supplies = Gstr3bTaxBucketSerializer()
    outward_nil_exempt_non_gst = Gstr3bTaxableOnlySerializer()
    inward_supplies_reverse_charge = Gstr3bTaxBucketSerializer()
    non_gst_outward_supplies = Gstr3bTaxableOnlySerializer()
    rows = Gstr3bNamedTaxBucketSerializer(many=True, required=False)


class Gstr3bSection4Serializer(serializers.Serializer):
    itc_available = Gstr3bTaxBucketSerializer()
    itc_reversed = Gstr3bTaxBucketSerializer()
    net_itc = Gstr3bTaxBucketSerializer()
    rows = Gstr3bNamedTaxBucketSerializer(many=True, required=False)


class Gstr3bSection51Serializer(serializers.Serializer):
    inward_exempt_nil_non_gst = Gstr3bTaxableOnlySerializer()
    rows = Gstr3bNamedTaxableOnlySerializer(many=True, required=False)


class Gstr3bTotalsSerializer(serializers.Serializer):
    tax_payable = Gstr3bTaxBucketSerializer()
    net_itc = Gstr3bTaxBucketSerializer()
    net_cash_tax_payable = Gstr3bTaxBucketSerializer()


class Gstr3bSection32Serializer(serializers.Serializer):
    interstate_supplies_to_unregistered = Gstr3bTaxBucketSerializer()
    interstate_supplies_to_composition = Gstr3bTaxBucketSerializer()
    interstate_supplies_to_uin_holders = Gstr3bTaxBucketSerializer()
    rows = Gstr3bNamedTaxBucketSerializer(many=True, required=False)


class Gstr3bSection61Serializer(serializers.Serializer):
    tax_payable = Gstr3bTaxBucketSerializer()
    tax_paid_cash = Gstr3bTaxBucketSerializer()
    tax_paid_itc = Gstr3bTaxBucketSerializer()
    balance_payable = Gstr3bTaxBucketSerializer()
    rows = Gstr3bNamedTaxBucketSerializer(many=True, required=False)


class Gstr3bSummarySerializer(serializers.Serializer):
    section_3_1 = Gstr3bSection31Serializer()
    section_3_2 = Gstr3bSection32Serializer()
    section_4 = Gstr3bSection4Serializer()
    section_5_1 = Gstr3bSection51Serializer()
    section_6_1 = Gstr3bSection61Serializer()
    totals = Gstr3bTotalsSerializer()


class Gstr3bValidationSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["info", "warning", "error"])
    message = serializers.CharField()
