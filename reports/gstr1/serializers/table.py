from __future__ import annotations

from rest_framework import serializers


class Gstr1TableCoverageSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField(allow_blank=True, required=False)


class Gstr1TableEnvelopeSerializer(serializers.Serializer):
    table_code = serializers.CharField()
    table_label = serializers.CharField()
    count = serializers.IntegerField()
    rows = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    coverage = Gstr1TableCoverageSerializer()
