from rest_framework import serializers


class ReportPreferenceSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    report_code = serializers.CharField(max_length=120)
    payload = serializers.JSONField(required=False, default=dict)
