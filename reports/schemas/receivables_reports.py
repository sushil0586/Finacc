from rest_framework import serializers


class ReceivableReportScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)

    customer = serializers.IntegerField(required=False, allow_null=True)
    customer_group = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    region = serializers.IntegerField(required=False, allow_null=True)
    territory = serializers.IntegerField(required=False, allow_null=True)
    salesperson = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    overdue_only = serializers.BooleanField(required=False)
    credit_limit_exceeded = serializers.BooleanField(required=False)
    exception_only = serializers.BooleanField(required=False)
    outstanding_gt = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_by = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_order = serializers.ChoiceField(choices=("asc", "desc"), required=False, allow_null=True)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)


class ReceivableAgingScopeSerializer(ReceivableReportScopeSerializer):
    view = serializers.ChoiceField(choices=("summary", "invoice"), required=False, allow_null=True)


class CollectionsHistoryScopeSerializer(ReceivableReportScopeSerializer):
    settlement_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
