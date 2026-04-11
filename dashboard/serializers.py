from __future__ import annotations

from rest_framework import serializers


class DashboardHomeScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True, write_only=True)
    date_to = serializers.DateField(required=False, allow_null=True, write_only=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("date_from") and not attrs.get("from_date"):
            attrs["from_date"] = attrs["date_from"]
        if attrs.get("date_to") and not attrs.get("to_date"):
            attrs["to_date"] = attrs["date_to"]
        if attrs.get("from_date") and not attrs.get("date_from"):
            attrs["date_from"] = attrs["from_date"]
        if attrs.get("to_date") and not attrs.get("date_to"):
            attrs["date_to"] = attrs["to_date"]
        return attrs

