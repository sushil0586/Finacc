from rest_framework import serializers


class FinancialReportScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    group_by = serializers.ChoiceField(
        choices=("ledger", "accounthead", "accounttype"),
        required=False,
        allow_null=True,
    )
    include_zero_balances = serializers.BooleanField(required=False)
    include_inactive_ledgers = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)
    sort_by = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.ChoiceField(choices=("asc", "desc"), required=False, allow_null=True)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)
    export = serializers.ChoiceField(choices=("excel", "pdf", "csv"), required=False, allow_null=True)


class LedgerBookScopeSerializer(FinancialReportScopeSerializer):
    ledger = serializers.IntegerField()
