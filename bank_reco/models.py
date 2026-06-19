from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Index, Q, UniqueConstraint

from entity.models import Entity, EntityBankAccountV2, EntityFinancialYear, SubEntity
from helpers.models import TrackingModel
from posting.models import Entry, JournalLine
from vouchers.models.voucher_core import VoucherHeader


ZERO = Decimal("0.00")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _stable_hash(payload: dict[str, object]) -> str:
    stable = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


class BankStatementImport(TrackingModel):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        VALIDATED = "validated", "Validated"
        READY = "ready", "Ready"
        REJECTED = "rejected", "Rejected"
        ARCHIVED = "archived", "Archived"

    class FileType(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"
        PDF = "pdf", "PDF"
        MT940 = "mt940", "MT940"
        CAMT053 = "camt053", "CAMT053"
        JSON = "json", "JSON"

    import_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="bank_statement_imports")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    bank_account = models.ForeignKey(EntityBankAccountV2, on_delete=models.PROTECT, related_name="bank_statement_imports")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    source_file_name = models.CharField(max_length=255, blank=True, default="")
    source_file_type = models.CharField(max_length=20, choices=FileType.choices, default=FileType.CSV, db_index=True)
    source_file_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    parser_key = models.CharField(max_length=50, blank=True, default="csv")
    statement_from = models.DateField(null=True, blank=True, db_index=True)
    statement_to = models.DateField(null=True, blank=True, db_index=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    closing_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    imported_line_count = models.PositiveIntegerField(default=0)
    duplicate_line_count = models.PositiveIntegerField(default=0)
    invalid_line_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    validation_summary = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            UniqueConstraint(
                fields=["entity", "bank_account", "source_file_sha256"],
                condition=~Q(source_file_sha256=""),
                name="uq_bank_statement_import_entity_bank_filehash",
            ),
        ]
        indexes = [
            Index(fields=["entity", "entityfin", "subentity", "bank_account"], name="ix_bank_stmt_import_scope"),
            Index(fields=["entity", "status", "statement_from", "statement_to"], name="ix_bsi_status_period"),
        ]

    def save(self, *args, **kwargs):
        self.import_code = _clean_text(self.import_code).upper() or f"BSI-{uuid.uuid4().hex[:12].upper()}"
        self.source_file_name = _clean_text(self.source_file_name)
        self.source_file_sha256 = _clean_text(self.source_file_sha256).lower()
        self.parser_key = _clean_text(self.parser_key).lower() or "csv"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.import_code} - {self.bank_account_id}"


class BankStatementLine(TrackingModel):
    class ValidationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VALID = "valid", "Valid"
        WARNING = "warning", "Warning"
        INVALID = "invalid", "Invalid"

    class ReconciliationStatus(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        SUGGESTED = "suggested", "Suggested"
        CONFIRMED = "confirmed", "Confirmed"
        PARTIALLY_MATCHED = "partially_matched", "Partially Matched"
        CANCELLED = "cancelled", "Cancelled"

    class ExceptionStatus(models.TextChoices):
        NONE = "none", "None"
        BANK_ERROR = "bank_error", "Bank Error"
        BOOK_ERROR = "book_error", "Book Error"
        IGNORED = "ignored", "Ignored"
        HOLD_FOR_REVIEW = "hold_for_review", "Hold For Review"
        PENDING_CLEARANCE = "pending_clearance", "Pending Clearance"

    statement_import = models.ForeignKey(BankStatementImport, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField()
    txn_date = models.DateField(null=True, blank=True, db_index=True)
    value_date = models.DateField(null=True, blank=True, db_index=True)
    narration = models.CharField(max_length=500, blank=True, default="")
    reference_no = models.CharField(max_length=120, blank=True, default="")
    cheque_no = models.CharField(max_length=80, blank=True, default="")
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, blank=True, default="INR")
    raw_data = models.JSONField(default=dict, blank=True)
    normalized_hash = models.CharField(max_length=64, db_index=True)
    validation_status = models.CharField(max_length=20, choices=ValidationStatus.choices, default=ValidationStatus.PENDING, db_index=True)
    reconciliation_status = models.CharField(max_length=20, choices=ReconciliationStatus.choices, default=ReconciliationStatus.UNMATCHED, db_index=True)
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    exception_status = models.CharField(max_length=30, choices=ExceptionStatus.choices, default=ExceptionStatus.NONE, db_index=True)
    exception_reason = models.TextField(blank=True, default="")
    created_voucher = models.ForeignKey(VoucherHeader, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("line_no", "id")
        constraints = [
            UniqueConstraint(fields=["statement_import", "line_no"], name="uq_bank_stmt_line_import_lineno"),
        ]
        indexes = [
            Index(fields=["statement_import", "reconciliation_status"], name="ix_bank_stmt_line_reco"),
            Index(fields=["statement_import", "exception_status"], name="ix_bank_stmt_line_exc"),
            Index(fields=["txn_date", "reference_no"], name="ix_bank_stmt_line_txn_ref"),
            Index(fields=["statement_import", "validation_status", "txn_date"], name="ix_bsl_stmt_val_txn"),
        ]

    def save(self, *args, **kwargs):
        self.narration = _clean_text(self.narration)
        self.reference_no = _clean_text(self.reference_no)
        self.cheque_no = _clean_text(self.cheque_no)
        self.currency = _clean_text(self.currency).upper() or "INR"
        self.exception_reason = _clean_text(self.exception_reason)
        self.normalized_hash = _clean_text(self.normalized_hash).lower() or _stable_hash(
            {
                "txn_date": self.txn_date,
                "value_date": self.value_date,
                "narration": self.narration,
                "reference_no": self.reference_no,
                "cheque_no": self.cheque_no,
                "debit_amount": str(self.debit_amount),
                "credit_amount": str(self.credit_amount),
                "balance": str(self.balance) if self.balance is not None else None,
                "currency": self.currency,
            }
        )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.statement_import_id}:{self.line_no}"


class BankReconciliationRun(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        VALIDATED = "validated", "Validated"
        MATCHING = "matching", "Matching"
        REVIEW = "review", "Review"
        RECONCILED = "reconciled", "Reconciled"
        LOCKED = "locked", "Locked"

    run_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="bank_reconciliation_runs")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    bank_account = models.ForeignKey(EntityBankAccountV2, on_delete=models.PROTECT, related_name="bank_reconciliation_runs")
    statement_import = models.ForeignKey(BankStatementImport, on_delete=models.PROTECT, related_name="reconciliation_runs")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    as_of_date = models.DateField(null=True, blank=True, db_index=True)
    statement_opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    statement_closing_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    book_opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    book_closing_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    matched_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    unmatched_bank_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    unmatched_book_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    difference_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    statement_line_count = models.PositiveIntegerField(default=0)
    matched_line_count = models.PositiveIntegerField(default=0)
    suggested_line_count = models.PositiveIntegerField(default=0)
    exception_line_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            Index(fields=["entity", "entityfin", "subentity", "bank_account"], name="ix_bank_reco_run_scope"),
            Index(fields=["entity", "status", "as_of_date"], name="ix_bank_reco_run_status"),
            Index(fields=["statement_import", "created_at", "id"], name="ix_brr_stmt_latest"),
        ]

    def save(self, *args, **kwargs):
        self.run_code = _clean_text(self.run_code).upper() or f"BRR-{uuid.uuid4().hex[:12].upper()}"
        self.notes = _clean_text(self.notes)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.run_code} - {self.bank_account_id}"


class BankReconciliationMatch(TrackingModel):
    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        CONFIRMED = "confirmed", "Confirmed"
        PARTIALLY_MATCHED = "partially_matched", "Partially Matched"
        UNMATCHED = "unmatched", "Unmatched"
        CANCELLED = "cancelled", "Cancelled"

    class MatchType(models.TextChoices):
        EXACT = "exact", "Exact"
        SUGGESTED = "suggested", "Suggested"
        POSSIBLE = "possible", "Possible"

    class MatchKind(models.TextChoices):
        ONE_TO_ONE = "one_to_one", "One To One"
        ONE_TO_MANY = "one_to_many", "One To Many"
        MANY_TO_ONE = "many_to_one", "Many To One"
        MANY_TO_MANY = "many_to_many", "Many To Many"
        PARTIAL = "partial", "Partial"
        AUTO = "auto", "Auto"
        MANUAL = "manual", "Manual"

    match_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    run = models.ForeignKey(BankReconciliationRun, on_delete=models.CASCADE, related_name="matches")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUGGESTED, db_index=True)
    match_type = models.CharField(max_length=20, choices=MatchType.choices, default=MatchType.SUGGESTED, db_index=True)
    match_kind = models.CharField(max_length=30, choices=MatchKind.choices, default=MatchKind.AUTO, db_index=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    bank_total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    book_total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    matched_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    difference_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    rule_code = models.CharField(max_length=80, blank=True, default="")
    reason_codes = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    suggested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            Index(fields=["run", "status"], name="ix_bank_reco_match_run_status"),
            Index(fields=["run", "match_kind"], name="ix_bank_reco_match_run_kind"),
        ]

    def save(self, *args, **kwargs):
        self.match_code = _clean_text(self.match_code).upper() or f"BRM-{uuid.uuid4().hex[:12].upper()}"
        self.rule_code = _clean_text(self.rule_code)
        self.notes = _clean_text(self.notes)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.match_code} - {self.run_id}"


class BankReconciliationMatchBankLine(TrackingModel):
    match = models.ForeignKey(BankReconciliationMatch, on_delete=models.CASCADE, related_name="bank_lines")
    statement_line = models.ForeignKey(BankStatementLine, on_delete=models.PROTECT, related_name="+")
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    allocation_order = models.PositiveIntegerField(default=1)
    is_primary = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("allocation_order", "id")
        constraints = [
            UniqueConstraint(fields=["match", "statement_line"], name="uq_bank_reco_match_bankline"),
        ]
        indexes = [
            Index(fields=["match", "allocation_order"], name="ix_brm_bl_order"),
            Index(fields=["statement_line"], name="ix_brm_bl_stmt"),
        ]


class BankReconciliationMatchBookLine(TrackingModel):
    match = models.ForeignKey(BankReconciliationMatch, on_delete=models.CASCADE, related_name="book_lines")
    entry = models.ForeignKey(Entry, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    journal_line = models.ForeignKey(JournalLine, on_delete=models.PROTECT, related_name="+")
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    allocation_order = models.PositiveIntegerField(default=1)
    is_primary = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("allocation_order", "id")
        constraints = [
            UniqueConstraint(fields=["match", "journal_line"], name="uq_bank_reco_match_bookline"),
        ]
        indexes = [
            Index(fields=["match", "allocation_order"], name="ix_brm_jl_order"),
            Index(fields=["journal_line"], name="ix_bank_reco_match_bookline_jl"),
        ]


class BankReconciliationAuditLog(TrackingModel):
    run = models.ForeignKey(BankReconciliationRun, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs")
    statement_import = models.ForeignKey(BankStatementImport, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    match = models.ForeignKey(BankReconciliationMatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=40, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            Index(fields=["run", "action"], name="ix_bank_reco_audit_run_action"),
            Index(fields=["statement_import", "action"], name="ix_br_audit_imp_act"),
            Index(fields=["run", "created_at"], name="ix_bank_reco_audit_run_dt"),
        ]
