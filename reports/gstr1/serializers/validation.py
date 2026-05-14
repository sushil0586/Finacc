from __future__ import annotations

from rest_framework import serializers


class Gstr1ValidationWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    severity = serializers.CharField()
    invoice_id = serializers.IntegerField(required=False)
    invoice_number = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    field = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    impact = serializers.CharField(required=False, allow_blank=True)
    group_code = serializers.CharField(required=False, allow_blank=True)
    group_label = serializers.CharField(required=False, allow_blank=True)
    action_label = serializers.CharField(required=False, allow_blank=True)
    action_description = serializers.CharField(required=False, allow_blank=True)
    invoice_detail_url = serializers.CharField(required=False, allow_blank=True)
    drilldowns = serializers.JSONField(required=False)


class Gstr1ReadinessStatusSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    tone = serializers.CharField()
    message = serializers.CharField()


class Gstr1ReadinessCountsSerializer(serializers.Serializer):
    total_warnings = serializers.IntegerField()
    blocked_warnings = serializers.IntegerField()
    review_warnings = serializers.IntegerField()
    groups = serializers.IntegerField()


class Gstr1ReadinessSummaryCardSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    value = serializers.JSONField()
    tone = serializers.CharField()


class Gstr1ValidationGroupSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    warning_count = serializers.IntegerField()
    blocked_count = serializers.IntegerField()
    review_count = serializers.IntegerField()
    action_label = serializers.CharField()
    action_description = serializers.CharField()
    warnings = Gstr1ValidationWarningSerializer(many=True)


class Gstr1ExportFlowSerializer(serializers.Serializer):
    primary_format = serializers.CharField()
    secondary_formats = serializers.ListField(child=serializers.CharField())
    recommended_step = serializers.CharField()


class Gstr1ReadinessSerializer(serializers.Serializer):
    status = Gstr1ReadinessStatusSerializer()
    counts = Gstr1ReadinessCountsSerializer()
    summary_cards = Gstr1ReadinessSummaryCardSerializer(many=True)
    validation_groups = Gstr1ValidationGroupSerializer(many=True)
    next_steps = serializers.ListField(child=serializers.CharField())
    export_flow = Gstr1ExportFlowSerializer()
    warnings = Gstr1ValidationWarningSerializer(many=True)
