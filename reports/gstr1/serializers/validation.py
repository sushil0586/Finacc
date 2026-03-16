from __future__ import annotations

from rest_framework import serializers


class Gstr1ValidationWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    severity = serializers.CharField()
    invoice_id = serializers.IntegerField(required=False)
    invoice_number = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    field = serializers.CharField(required=False, allow_null=True, allow_blank=True)
