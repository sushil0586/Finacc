from rest_framework import serializers


def _parse_ledger_ids(value):
    if value in (None, "", []):
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = str(value).split(",")

    parsed = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        parsed.append(int(text))
    return parsed


class FinancialReportScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    financial_year = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    as_on_date = serializers.DateField(required=False, allow_null=True)
    hide_zero_rows = serializers.BooleanField(required=False)
    view_type = serializers.ChoiceField(
        choices=("summary", "detailed"),
        required=False,
        allow_null=True,
    )
    scope_mode = serializers.ChoiceField(
        choices=("financial_year", "month", "quarter", "year", "custom", "as_of"),
        required=False,
        allow_null=True,
    )
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
    account_group = serializers.ChoiceField(
        choices=("ledger", "accounthead", "accounttype"),
        required=False,
        allow_null=True,
    )
    group_by = serializers.ChoiceField(
        choices=("ledger", "accounthead", "accounttype"),
        required=False,
        allow_null=True,
    )
    ledger_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    period_by = serializers.ChoiceField(
        choices=("month", "quarter", "year"),
        required=False,
        allow_null=True,
    )
    stock_valuation_mode = serializers.ChoiceField(
        choices=("auto", "gl", "valuation", "none"),
        required=False,
        allow_null=True,
    )
    stock_valuation_method = serializers.ChoiceField(
        choices=("fifo", "lifo", "mwa", "wac", "latest"),
        required=False,
        allow_null=True,
    )
    include_zero_balance = serializers.BooleanField(required=False)
    include_zero_balances = serializers.BooleanField(required=False)
    include_opening = serializers.BooleanField(required=False)
    include_movement = serializers.BooleanField(required=False)
    include_closing = serializers.BooleanField(required=False)
    posted_only = serializers.BooleanField(required=False)
    include_inactive_ledgers = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)
    sort_by = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.ChoiceField(choices=("asc", "desc"), required=False, allow_null=True)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)
    export = serializers.ChoiceField(choices=("excel", "pdf", "csv"), required=False, allow_null=True)
    orientation = serializers.ChoiceField(choices=("portrait", "landscape"), required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("financial_year") and not attrs.get("entityfinid"):
            attrs["entityfinid"] = attrs["financial_year"]
        if attrs.get("entityfinid") and not attrs.get("financial_year"):
            attrs["financial_year"] = attrs["entityfinid"]
        if attrs.get("as_on_date") and not attrs.get("as_of_date"):
            attrs["as_of_date"] = attrs["as_on_date"]
        if attrs.get("as_of_date") and not attrs.get("as_on_date"):
            attrs["as_on_date"] = attrs["as_of_date"]

        if attrs.get("account_group") and not attrs.get("group_by"):
            attrs["group_by"] = attrs["account_group"]
        if attrs.get("group_by") and not attrs.get("account_group"):
            attrs["account_group"] = attrs["group_by"]

        if "include_zero_balance" in attrs and "include_zero_balances" not in attrs:
            attrs["include_zero_balances"] = attrs["include_zero_balance"]
        if "include_zero_balances" in attrs and "include_zero_balance" not in attrs:
            attrs["include_zero_balance"] = attrs["include_zero_balances"]
        if "hide_zero_rows" in attrs and "include_zero_balance" not in attrs:
            attrs["include_zero_balance"] = not attrs["hide_zero_rows"]
            attrs["include_zero_balances"] = not attrs["hide_zero_rows"]
        if "include_zero_balance" not in attrs and "include_zero_balances" not in attrs:
            attrs["include_zero_balance"] = False
            attrs["include_zero_balances"] = False
        if "hide_zero_rows" not in attrs:
            attrs["hide_zero_rows"] = not attrs["include_zero_balance"]

        ledger_ids = _parse_ledger_ids(attrs.get("ledger_ids"))
        attrs["ledger_ids"] = ledger_ids

        if "posted_only" not in attrs:
            attrs["posted_only"] = True
        if "view_type" not in attrs or attrs.get("view_type") is None:
            attrs["view_type"] = "summary"

        if "include_opening" not in attrs:
            attrs["include_opening"] = True
        if "include_movement" not in attrs:
            attrs["include_movement"] = True
        if "include_closing" not in attrs:
            attrs["include_closing"] = True

        return attrs


class LedgerBookScopeSerializer(FinancialReportScopeSerializer):
    ledger = serializers.IntegerField()
    voucher_type = serializers.CharField(required=False, allow_blank=True)
