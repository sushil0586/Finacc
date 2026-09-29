from __future__ import annotations

from rest_framework import serializers


class CfoControlTowerScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True, write_only=True)
    date_to = serializers.DateField(required=False, allow_null=True, write_only=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bucket = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=500)
    scenario = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    threshold_amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)
    threshold_percent = serializers.DecimalField(required=False, allow_null=True, max_digits=7, decimal_places=2, min_value=0)
    risk_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    revenue_change_percent = serializers.DecimalField(required=False, allow_null=True, max_digits=7, decimal_places=2)
    purchase_change_percent = serializers.DecimalField(required=False, allow_null=True, max_digits=7, decimal_places=2)
    collection_delay_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    vendor_delay_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    expense_increase_amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)
    one_time_cash_inflow = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)
    one_time_cash_outflow = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("date_from") and not attrs.get("from_date"):
            attrs["from_date"] = attrs["date_from"]
        if attrs.get("date_to") and not attrs.get("to_date"):
            attrs["to_date"] = attrs["date_to"]
        if attrs.get("from_date") and attrs.get("to_date") and attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class CashFlowForecastAdjustmentSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    scenario = serializers.ChoiceField(choices=("base", "conservative", "optimistic"), required=False, default="base")
    adjustment_date = serializers.DateField()
    direction = serializers.ChoiceField(choices=("inflow", "outflow"))
    category = serializers.CharField(required=False, allow_blank=True, max_length=80)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class MonthCloseActionSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("from_date") and attrs.get("to_date") and attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class BudgetLineSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    category = serializers.ChoiceField(choices=("revenue", "purchase_expense", "gross_snapshot", "statutory_payable"))
    budget_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class BudgetVarianceReviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    status = serializers.ChoiceField(choices=("open", "explained", "accepted", "action_required"))
    explanation = serializers.CharField(required=False, allow_blank=True)
    action_owner = serializers.CharField(required=False, allow_blank=True, max_length=120)
    due_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class CfoRiskReviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    item_key = serializers.CharField(max_length=180)
    risk_type = serializers.CharField(max_length=60)
    source_type = serializers.CharField(max_length=60)
    source_id = serializers.CharField(required=False, allow_blank=True, max_length=80)
    status = serializers.ChoiceField(choices=("open", "acknowledged", "resolved", "dismissed"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ManagementPackSnapshotSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    title = serializers.CharField(required=False, allow_blank=True, max_length=180)
    status = serializers.ChoiceField(choices=("draft", "published"), required=False, default="draft")
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class EvidenceItemSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    evidence_type = serializers.ChoiceField(
        choices=("management_pack", "reconciliation", "variance_review", "risk_review", "close_evidence", "other"),
        required=False,
        default="other",
    )
    title = serializers.CharField(max_length=180)
    description = serializers.CharField(required=False, allow_blank=True)
    source_type = serializers.CharField(required=False, allow_blank=True, max_length=60)
    source_id = serializers.CharField(required=False, allow_blank=True, max_length=80)
    source_route = serializers.CharField(required=False, allow_blank=True, max_length=180)
    status = serializers.ChoiceField(choices=("open", "reviewed", "rejected", "archived"), required=False, default="open")
    owner = serializers.CharField(required=False, allow_blank=True, max_length=120)
    due_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class EvidenceReviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=("open", "reviewed", "rejected", "archived"))
    description = serializers.CharField(required=False, allow_blank=True)


class InsightSignalReviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    signal_key = serializers.CharField(max_length=180)
    signal_type = serializers.CharField(max_length=60)
    severity = serializers.ChoiceField(choices=("low", "medium", "high", "critical"))
    status = serializers.ChoiceField(choices=("open", "acknowledged", "resolved", "dismissed"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class ScenarioPlanSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    title = serializers.CharField(required=False, allow_blank=True, max_length=180)
    status = serializers.ChoiceField(choices=("draft", "approved"), required=False, default="draft")
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    revenue_change_percent = serializers.DecimalField(required=False, allow_null=True, max_digits=7, decimal_places=2)
    purchase_change_percent = serializers.DecimalField(required=False, allow_null=True, max_digits=7, decimal_places=2)
    collection_delay_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    vendor_delay_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    expense_increase_amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)
    one_time_cash_inflow = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)
    one_time_cash_outflow = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2, min_value=0)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["from_date"] > attrs["to_date"]:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs
