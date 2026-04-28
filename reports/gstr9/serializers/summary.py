from __future__ import annotations

from rest_framework import serializers


class Gstr9SummaryTableSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    status = serializers.CharField()


class Gstr9SummarySerializer(serializers.Serializer):
    phase = serializers.IntegerField()
    status = serializers.CharField()
    message = serializers.CharField()
    tables = Gstr9SummaryTableSerializer(many=True)

