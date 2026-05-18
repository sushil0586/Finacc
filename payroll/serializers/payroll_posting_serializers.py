from __future__ import annotations

from rest_framework import serializers


class PayrollPostingIssueSerializer(serializers.Serializer):
    severity = serializers.CharField()
    code = serializers.CharField()
    message = serializers.CharField()
    source = serializers.CharField()
    component_code = serializers.CharField(required=False, allow_blank=True, default="")


class PayrollPostingJournalRowSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    account_id = serializers.IntegerField()
    account_name = serializers.CharField()
    ledger_id = serializers.IntegerField(allow_null=True)
    ledger_name = serializers.CharField(required=False, allow_blank=True, default="")
    entry_side = serializers.ChoiceField(choices=["DEBIT", "CREDIT"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    description = serializers.CharField()
    category = serializers.CharField()
    source_reference = serializers.CharField(required=False, allow_blank=True, default="")
    component_code = serializers.CharField(required=False, allow_blank=True, default="")


class PayrollPostingTotalsSerializer(serializers.Serializer):
    debit_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    credit_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    is_balanced = serializers.BooleanField()
    row_count = serializers.IntegerField()


class PayrollPostingValidationSerializer(serializers.Serializer):
    is_valid = serializers.BooleanField()
    blocking_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    issues = PayrollPostingIssueSerializer(many=True)


class PayrollPostingStatusSerializer(serializers.Serializer):
    source_type = serializers.CharField()
    source_id = serializers.IntegerField()
    status = serializers.CharField()
    posted = serializers.BooleanField()
    can_post = serializers.BooleanField()
    can_reverse = serializers.BooleanField()
    is_reversal = serializers.BooleanField()


class PayrollPostingPreviewSerializer(serializers.Serializer):
    source_type = serializers.CharField()
    source_id = serializers.IntegerField()
    source_number = serializers.CharField()
    status = serializers.CharField()
    posting_date = serializers.DateField()
    journal_rows = PayrollPostingJournalRowSerializer(many=True)
    totals = PayrollPostingTotalsSerializer()
    validation = PayrollPostingValidationSerializer()
    posting_status = PayrollPostingStatusSerializer()
