from __future__ import annotations

from rest_framework import serializers


class Gstr1SectionTotalsSerializer(serializers.Serializer):
    section = serializers.CharField()
    label = serializers.CharField()
    document_count = serializers.IntegerField()
    taxable_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=18, decimal_places=2)


class Gstr1HsnSummarySerializer(serializers.Serializer):
    hsn_sac_code = serializers.CharField(allow_blank=True, allow_null=True)
    is_service = serializers.BooleanField()
    gst_rate = serializers.DecimalField(max_digits=6, decimal_places=2)
    total_qty = serializers.DecimalField(max_digits=18, decimal_places=3)
    taxable_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    document_count = serializers.IntegerField()


class Gstr1DocumentSummarySerializer(serializers.Serializer):
    doc_type = serializers.IntegerField()
    doc_code = serializers.CharField(allow_blank=True, allow_null=True)
    document_count = serializers.IntegerField()
    cancelled_count = serializers.IntegerField()
    min_doc_no = serializers.IntegerField(allow_null=True)
    max_doc_no = serializers.IntegerField(allow_null=True)


class Gstr1NilExemptSummarySerializer(serializers.Serializer):
    taxability = serializers.IntegerField()
    taxable_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    cgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sgst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    igst_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    cess_amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class Gstr1SummarySerializer(serializers.Serializer):
    sections = Gstr1SectionTotalsSerializer(many=True)
    hsn_summary = Gstr1HsnSummarySerializer(many=True)
    document_summary = Gstr1DocumentSummarySerializer(many=True)
    nil_exempt_summary = Gstr1NilExemptSummarySerializer(many=True)
