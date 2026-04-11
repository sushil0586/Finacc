from rest_framework import serializers


class PayableReportScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    view = serializers.ChoiceField(choices=("summary", "detailed"), required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True, write_only=True)
    date_to = serializers.DateField(required=False, allow_null=True, write_only=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)

    vendor = serializers.IntegerField(required=False, allow_null=True)
    vendor_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    vendor_group = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    region = serializers.IntegerField(required=False, allow_null=True)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gst_registered = serializers.BooleanField(required=False, allow_null=True, default=None)
    msme = serializers.BooleanField(required=False, allow_null=True, default=None)
    voucher_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    aging_basis = serializers.ChoiceField(choices=("due_date", "bill_date"), required=False, allow_null=True)

    overdue_only = serializers.BooleanField(required=False)
    credit_limit_exceeded = serializers.BooleanField(required=False)
    reconcile_gl = serializers.BooleanField(required=False)
    include_zero_balance = serializers.BooleanField(required=False)
    include_credit_balances = serializers.BooleanField(required=False)
    include_advances_separately = serializers.BooleanField(required=False)
    show_settled = serializers.BooleanField(required=False)
    show_overdue_only = serializers.BooleanField(required=False)
    show_not_due = serializers.BooleanField(required=False)
    outstanding_gt = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    include_trace = serializers.BooleanField(required=False, default=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_by = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_order = serializers.ChoiceField(choices=("asc", "desc"), required=False, allow_null=True)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        from_date = attrs.get("from_date")
        to_date = attrs.get("to_date")
        errors = {}
        if date_from and from_date and date_from != from_date:
            errors["date_from"] = ["date_from must match from_date when both are provided."]
        if date_to and to_date and date_to != to_date:
            errors["date_to"] = ["date_to must match to_date when both are provided."]
        if errors:
            raise serializers.ValidationError(errors)
        if date_from and not from_date:
            attrs["from_date"] = date_from
        if date_to and not to_date:
            attrs["to_date"] = date_to

        vendor_ids = attrs.get("vendor_ids")
        if isinstance(vendor_ids, str):
            parsed_vendor_ids = []
            for token in vendor_ids.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    parsed_vendor_ids.append(int(token))
                except (TypeError, ValueError):
                    continue
            attrs["vendor_ids"] = parsed_vendor_ids
        elif vendor_ids in (None, ""):
            attrs["vendor_ids"] = []

        voucher_type = attrs.get("voucher_type")
        if isinstance(voucher_type, str):
            attrs["voucher_type"] = [token.strip() for token in voucher_type.split(",") if token.strip()]
        elif voucher_type in (None, ""):
            attrs["voucher_type"] = []
        return attrs


class PayableAgingScopeSerializer(PayableReportScopeSerializer):
    view = serializers.ChoiceField(choices=("summary", "invoice"), required=False, allow_null=True)


class PayableControlScopeSerializer(PayableReportScopeSerializer):
    pass


class PayableExceptionScopeSerializer(PayableControlScopeSerializer):
    min_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    overdue_days_gt = serializers.IntegerField(required=False, min_value=0)
    stale_days_gt = serializers.IntegerField(required=False, min_value=1)
    include_negative_balances = serializers.BooleanField(required=False, default=True)
    include_old_advances = serializers.BooleanField(required=False, default=True)
    include_stale_vendors = serializers.BooleanField(required=False, default=True)


class PayableCloseValidationScopeSerializer(PayableControlScopeSerializer):
    include_samples = serializers.BooleanField(required=False)


class PayableVendorLedgerScopeSerializer(PayableReportScopeSerializer):
    vendor = serializers.IntegerField()
    include_opening = serializers.BooleanField(required=False, default=True)
    include_running_balance = serializers.BooleanField(required=False, default=True)
    include_settlement_drilldowns = serializers.BooleanField(required=False, default=True)
    include_related_reports = serializers.BooleanField(required=False, default=True)


class PayableClosePackScopeSerializer(PayableControlScopeSerializer):
    include_overview = serializers.BooleanField(required=False, default=True)
    include_aging = serializers.BooleanField(required=False, default=True)
    include_reconciliation = serializers.BooleanField(required=False, default=True)
    include_validation = serializers.BooleanField(required=False, default=True)
    include_exceptions = serializers.BooleanField(required=False, default=True)
    include_top_vendors = serializers.BooleanField(required=False, default=True)
    expanded_validation = serializers.BooleanField(required=False, default=False)


class PayableSettlementHistoryScopeSerializer(PayableReportScopeSerializer):
    settlement_type = serializers.ChoiceField(
        choices=("payment", "advance_adjustment", "credit_note_adjustment", "debit_note_adjustment", "writeoff", "manual"),
        required=False,
        allow_null=True,
    )
    include_unapplied = serializers.BooleanField(required=False, default=True)


class PayableNoteRegisterScopeSerializer(PayableReportScopeSerializer):
    note_type = serializers.ChoiceField(choices=("credit", "debit"), required=False, allow_null=True)
    status = serializers.IntegerField(required=False, allow_null=True)
