from __future__ import annotations

from rest_framework import serializers


class Gstr9ValidationWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["info", "warning", "error"])
    message = serializers.CharField()
    table_code = serializers.CharField(required=False, allow_blank=True)
    field = serializers.CharField(required=False, allow_blank=True)

