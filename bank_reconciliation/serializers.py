from __future__ import annotations

import ast
import json

from rest_framework import serializers


def _coerce_scalar(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text.replace("'", '"'))
                if isinstance(parsed, list) and parsed:
                    return parsed[0]
            except Exception:
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, list) and parsed:
                        return parsed[0]
                except Exception:
                    return value
    return value


class BankReconciliationScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class BankReconciliationSessionCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField()
    statement_label = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    source_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    source_format = serializers.ChoiceField(choices=("manual", "csv", "excel", "json"), required=False, default="manual")
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    statement_opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    statement_closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    book_opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    book_closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class BankReconciliationSessionUpdateSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.ChoiceField(
        choices=("draft", "imported", "matching", "needs_review", "reconciled", "locked"),
        required=False,
    )


class BankStatementRowSerializer(serializers.Serializer):
    transaction_date = serializers.DateField(required=False, allow_null=True)
    value_date = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    reference_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=120)
    counterparty = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    debit_amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    credit_amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    balance_amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=10)
    external_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=120)
    match_status = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    suggested_match_score = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2)
    metadata = serializers.JSONField(required=False, default=dict)


class BankStatementImportSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField()
    source_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    source_format = serializers.ChoiceField(choices=("manual", "csv", "excel", "json"), required=False, default="json")
    rows = BankStatementRowSerializer(many=True)
    statement_opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    statement_closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    book_opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    book_closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class BankStatementUploadSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField()
    source_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    source_format = serializers.ChoiceField(choices=("csv", "excel"), required=False, default="csv")
    file = serializers.FileField()
    delimiter = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=",", max_length=5)
    profile_id = serializers.IntegerField(required=False, allow_null=True)
    column_mapping = serializers.JSONField(required=False, default=dict)
    statement_opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    statement_closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    book_opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    book_closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_source_format(self, value):
        return _coerce_scalar(value)

    def validate_delimiter(self, value):
        coerced = _coerce_scalar(value)
        return "," if coerced in (None, "") else str(coerced)


class BankStatementPreviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField()
    source_format = serializers.ChoiceField(choices=("csv", "excel"), required=False, default="csv")
    file = serializers.FileField()
    delimiter = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=",", max_length=5)

    def validate_source_format(self, value):
        return _coerce_scalar(value)

    def validate_delimiter(self, value):
        coerced = _coerce_scalar(value)
        return "," if coerced in (None, "") else str(coerced)


class BankStatementImportProfileQuerySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField(required=False, allow_null=True)
    source_format = serializers.ChoiceField(choices=("csv", "excel"), required=False, allow_null=True)


class BankStatementImportProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=255)
    entity_id = serializers.IntegerField(required=False)
    bank_account_id = serializers.IntegerField(required=False, allow_null=True)
    source_format = serializers.ChoiceField(choices=("csv", "excel"), required=False, default="csv")
    delimiter = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=",", max_length=5)
    date_format = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=40)
    column_mapping = serializers.JSONField(required=False, default=dict)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_source_format(self, value):
        return _coerce_scalar(value)

    def validate_delimiter(self, value):
        coerced = _coerce_scalar(value)
        return "," if coerced in (None, "") else str(coerced)


class BankReconciliationLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    line_no = serializers.IntegerField()
    transaction_date = serializers.DateField(allow_null=True)
    value_date = serializers.DateField(allow_null=True)
    description = serializers.CharField()
    reference_number = serializers.CharField()
    counterparty = serializers.CharField()
    debit_amount = serializers.CharField()
    credit_amount = serializers.CharField()
    balance_amount = serializers.CharField(allow_null=True)
    currency = serializers.CharField()
    match_status = serializers.CharField()
    suggested_match_score = serializers.CharField()


class BankReconciliationCandidateSerializer(serializers.Serializer):
    journal_line_id = serializers.IntegerField()
    entry_id = serializers.IntegerField()
    txn_type = serializers.CharField()
    txn_id = serializers.IntegerField()
    voucher_no = serializers.CharField(allow_null=True)
    posting_date = serializers.DateField(allow_null=True)
    amount = serializers.CharField()
    drcr = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    score = serializers.DecimalField(max_digits=5, decimal_places=2)
    reason = serializers.CharField()


class BankReconciliationMatchRequestSerializer(serializers.Serializer):
    statement_line_id = serializers.IntegerField(required=False, allow_null=True)
    journal_line_id = serializers.IntegerField()
    match_kind = serializers.ChoiceField(choices=("manual", "exact", "rule", "split"), required=False, default="manual")
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    confidence = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2)
    metadata = serializers.JSONField(required=False, default=dict)


class BankReconciliationSplitAllocationSerializer(serializers.Serializer):
    journal_line_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BankReconciliationSplitMatchRequestSerializer(serializers.Serializer):
    statement_line_id = serializers.IntegerField()
    allocations = BankReconciliationSplitAllocationSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class BankReconciliationExceptionRequestSerializer(serializers.Serializer):
    statement_line_id = serializers.IntegerField()
    exception_type = serializers.ChoiceField(choices=("bank_charge", "bounced_cheque", "interest", "unknown", "duplicate", "other"))
    amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)


class BankReconciliationSessionLockSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)


class BankReconciliationUnmatchRequestSerializer(serializers.Serializer):
    statement_line_id = serializers.IntegerField()


class BankReconciliationExceptionResolveRequestSerializer(serializers.Serializer):
    exception_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=("resolved", "ignored"), required=False, default="resolved")


class BankReconciliationAutoMatchResponseSerializer(serializers.Serializer):
    matched_count = serializers.IntegerField()
    reviewed_count = serializers.IntegerField()
    unmatched_count = serializers.IntegerField()
    total_lines = serializers.IntegerField()
    candidates_considered = serializers.IntegerField()
    matches = serializers.ListField(child=serializers.DictField())
