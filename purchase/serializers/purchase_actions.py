from rest_framework import serializers


class ItcBlockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ItcClaimSerializer(serializers.Serializer):
    period = serializers.RegexField(
        regex=r"^\d{4}-\d{2}$",
        max_length=7,
        error_messages={"invalid": "period must be YYYY-MM (e.g., 2026-02)"},
    )


class Match2BSerializer(serializers.Serializer):
    match_status = serializers.IntegerField()
