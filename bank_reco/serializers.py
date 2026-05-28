from __future__ import annotations

from rest_framework import serializers

from entity.models import EntityBankAccountV2, EntityFinancialYear, SubEntity

from .models import BankReconciliationMatch, BankReconciliationRun, BankStatementImport, BankStatementLine


class BankRecoScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField(required=False, allow_null=True)
    import_id = serializers.IntegerField(required=False, allow_null=True)
    run_id = serializers.IntegerField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    amount = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    status = serializers.ChoiceField(
        choices=[
            BankStatementLine.ReconciliationStatus.UNMATCHED,
            BankStatementLine.ReconciliationStatus.SUGGESTED,
            BankStatementLine.ReconciliationStatus.CONFIRMED,
            BankStatementLine.ReconciliationStatus.PARTIALLY_MATCHED,
            BankStatementLine.ReconciliationStatus.CANCELLED,
            BankReconciliationMatch.Status.SUGGESTED,
            BankReconciliationMatch.Status.CONFIRMED,
            BankReconciliationMatch.Status.PARTIALLY_MATCHED,
            BankReconciliationMatch.Status.UNMATCHED,
            BankReconciliationMatch.Status.CANCELLED,
        ],
        required=False,
        allow_null=True,
    )
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    action = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BankRecoRunReportScopeSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    bank_account = serializers.IntegerField(required=False, allow_null=True)
    action = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BankStatementImportCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField()
    file = serializers.FileField()
    source_file_type = serializers.ChoiceField(choices=((BankStatementImport.FileType.CSV, "CSV"), (BankStatementImport.FileType.XLSX, "XLSX")))
    parser_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    delimiter = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=",")
    statement_from = serializers.DateField(required=False, allow_null=True)
    statement_to = serializers.DateField(required=False, allow_null=True)
    opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    metadata = serializers.JSONField(required=False, default=dict)
    column_map = serializers.JSONField(required=False, default=dict)


class BankStatementImportPreviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bank_account = serializers.IntegerField()
    file = serializers.FileField()
    source_file_type = serializers.ChoiceField(choices=((BankStatementImport.FileType.CSV, "CSV"), (BankStatementImport.FileType.XLSX, "XLSX")))
    delimiter = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=",")
    column_map = serializers.JSONField(required=False, default=dict)


class BankStatementImportPreviewResponseSerializer(serializers.Serializer):
    headers = serializers.ListField(child=serializers.CharField())
    resolved_delimiter = serializers.CharField(allow_blank=True)
    suggested_column_map = serializers.JSONField()
    mapping_warnings = serializers.ListField(child=serializers.CharField())
    mapping_errors = serializers.ListField(child=serializers.CharField())
    sample_rows = serializers.ListField(child=serializers.DictField())
    normalized_preview_rows = serializers.ListField(child=serializers.DictField())
    detected_file_type = serializers.CharField()


class BankStatementImportListSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.SerializerMethodField()

    class Meta:
        model = BankStatementImport
        fields = [
            "id",
            "import_code",
            "status",
            "source_file_name",
            "source_file_type",
            "statement_from",
            "statement_to",
            "opening_balance",
            "closing_balance",
            "imported_line_count",
            "duplicate_line_count",
            "invalid_line_count",
            "warning_count",
            "created_at",
            "validated_at",
            "bank_account_name",
        ]

    def get_bank_account_name(self, obj):
        return f"{obj.bank_account.bank_name} - {obj.bank_account.account_number[-4:]}"


class BankStatementImportDetailSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.SerializerMethodField()
    bank_account = serializers.SerializerMethodField()
    declared_account_number = serializers.SerializerMethodField()

    class Meta:
        model = BankStatementImport
        fields = [
            "id",
            "import_code",
            "status",
            "source_file_name",
            "source_file_type",
            "statement_from",
            "statement_to",
            "opening_balance",
            "closing_balance",
            "imported_line_count",
            "duplicate_line_count",
            "invalid_line_count",
            "warning_count",
            "created_at",
            "validated_at",
            "bank_account_name",
            "bank_account",
            "validation_summary",
            "declared_account_number",
        ]

    def get_bank_account_name(self, obj):
        return f"{obj.bank_account.bank_name} - {obj.bank_account.account_number[-4:]}"

    def get_bank_account(self, obj):
        return {
            "id": obj.bank_account_id,
            "bank_name": obj.bank_account.bank_name,
            "account_number_masked": f"***{obj.bank_account.account_number[-4:]}",
        }

    def get_declared_account_number(self, obj):
        return (obj.metadata or {}).get("statement_account_number")


class BankStatementImportUpdateSerializer(serializers.Serializer):
    statement_from = serializers.DateField(required=False, allow_null=True)
    statement_to = serializers.DateField(required=False, allow_null=True)
    opening_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    closing_balance = serializers.DecimalField(required=False, allow_null=True, max_digits=14, decimal_places=2)
    declared_account_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BankStatementImportArchiveSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class BankStatementLineListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatementLine
        fields = [
            "id",
            "line_no",
            "txn_date",
            "value_date",
            "narration",
            "reference_no",
            "cheque_no",
            "debit_amount",
            "credit_amount",
            "balance",
            "currency",
            "validation_status",
            "reconciliation_status",
            "validation_errors",
            "validation_warnings",
            "raw_data",
        ]


class BankStatementImportValidationResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatementImport
        fields = [
            "id",
            "import_code",
            "status",
            "duplicate_line_count",
            "invalid_line_count",
            "warning_count",
            "validation_summary",
            "validated_at",
        ]


class AutoMatchResponseSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    run_code = serializers.CharField()
    matches = serializers.ListField(child=serializers.DictField())


class MatchRequestSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    bank_line_id = serializers.IntegerField()
    journal_line_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GroupMatchRequestSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    bank_line_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    journal_line_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class UnmatchRequestSerializer(serializers.Serializer):
    match_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class VoucherAllocationSerializer(serializers.Serializer):
    counterpart_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class VoucherCreationRequestSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    bank_line_id = serializers.IntegerField()
    voucher_kind = serializers.ChoiceField(
        choices=[
            "bank_charges",
            "interest_received",
            "direct_customer_receipt",
            "direct_vendor_payment",
            "bank_transfer",
            "loan_emi",
            "gst_payment",
            "tds_payment",
            "tcs_payment",
            "cheque_bounce",
            "reversal_adjustment",
        ]
    )
    counterpart_account_id = serializers.IntegerField()
    allocations = VoucherAllocationSerializer(many=True, required=False)
    voucher_date = serializers.DateField(required=False, allow_null=True)
    reference_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    instrument_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    instrument_date = serializers.DateField(required=False, allow_null=True)


class ExceptionActionRequestSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    bank_line_id = serializers.IntegerField()
    action = serializers.ChoiceField(
        choices=[
            "mark_as_bank_error",
            "mark_as_book_error",
            "ignore",
            "hold_for_review",
            "mark_as_pending_clearance",
            "clear_exception",
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class RunActionRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[
            "mark_review",
            "mark_reconciled",
            "lock_run",
            "unlock_run",
        ]
    )
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class MatchCandidateResponseSerializer(serializers.Serializer):
    match_id = serializers.IntegerField(required=False)
    status = serializers.CharField()
    match_type = serializers.CharField()
    match_kind = serializers.CharField(required=False)
    confidence_score = serializers.CharField()
    matched_amount = serializers.CharField(required=False)
    difference_amount = serializers.CharField(required=False)
    reason_codes = serializers.ListField(child=serializers.CharField())
    statement_line_id = serializers.IntegerField(required=False)
    journal_line_id = serializers.IntegerField(required=False)
    bank_line_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    journal_line_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class WorkspaceBankLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    line_no = serializers.IntegerField()
    txn_date = serializers.DateField(allow_null=True)
    value_date = serializers.DateField(allow_null=True)
    narration = serializers.CharField()
    reference_no = serializers.CharField()
    cheque_no = serializers.CharField()
    debit_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    credit_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    status = serializers.CharField()
    exception_status = serializers.CharField(required=False)
    exception_reason = serializers.CharField(required=False, allow_blank=True)
    statement_import_id = serializers.IntegerField(required=False)
    statement_import_code = serializers.CharField(required=False, allow_blank=True)
    is_opening_item = serializers.BooleanField(required=False)
    created_voucher_id = serializers.IntegerField(required=False, allow_null=True)


class WorkspaceBookLineSerializer(serializers.Serializer):
    journal_line_id = serializers.IntegerField()
    entry_id = serializers.IntegerField()
    voucher_no = serializers.CharField(allow_blank=True, allow_null=True)
    posting_date = serializers.DateField(allow_null=True)
    drcr = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    description = serializers.CharField(allow_blank=True, allow_null=True)
    reference = serializers.CharField(allow_blank=True, allow_null=True)
    is_opening_item = serializers.BooleanField(required=False)


class AuditTrailRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    action = serializers.CharField()
    object_type = serializers.CharField()
    object_id = serializers.CharField()
    actor = serializers.CharField(allow_blank=True)
    payload = serializers.JSONField()


class BrsReportSerializer(serializers.Serializer):
    balance_as_per_books = serializers.DecimalField(max_digits=14, decimal_places=2)
    add_cheques_issued_not_presented = serializers.DecimalField(max_digits=14, decimal_places=2)
    less_cheques_deposited_not_cleared = serializers.DecimalField(max_digits=14, decimal_places=2)
    add_direct_bank_entries = serializers.DecimalField(max_digits=14, decimal_places=2)
    less_direct_bank_entries = serializers.DecimalField(max_digits=14, decimal_places=2)
    add_errors = serializers.DecimalField(max_digits=14, decimal_places=2)
    less_errors = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_clearance_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    balance_as_per_bank_statement = serializers.DecimalField(max_digits=14, decimal_places=2)
    difference_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    sections = serializers.JSONField(required=False)
    export_rows = serializers.JSONField(required=False)
    supporting_rows = serializers.JSONField()


def resolve_scope_models(validated_data: dict) -> tuple[EntityFinancialYear | None, SubEntity | None, EntityBankAccountV2 | None]:
    entityfin = None
    subentity = None
    bank_account = None
    if validated_data.get("entityfinid"):
        entityfin = EntityFinancialYear.objects.filter(pk=validated_data["entityfinid"]).first()
    if validated_data.get("subentity"):
        subentity = SubEntity.objects.filter(pk=validated_data["subentity"]).first()
    if validated_data.get("bank_account"):
        bank_account = EntityBankAccountV2.objects.filter(pk=validated_data["bank_account"]).first()
    return entityfin, subentity, bank_account
