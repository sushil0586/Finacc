from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from entity.models import Entity, EntityBankAccountV2, EntityFinancialYear, SubEntity
from helpers.models import TrackingModel
from posting.models import Entry, JournalLine

ZERO = Decimal("0.00")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return ZERO


def _hash_row(payload: dict[str, object]) -> str:
    stable = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()


class BankReconciliationSession(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IMPORTED = "imported", "Imported"
        MATCHING = "matching", "Matching"
        NEEDS_REVIEW = "needs_review", "Needs Review"
        RECONCILED = "reconciled", "Reconciled"
        LOCKED = "locked", "Locked"

    session_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="bank_reconciliation_sessions")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    bank_account = models.ForeignKey(EntityBankAccountV2, on_delete=models.PROTECT, related_name="bank_reconciliation_sessions")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    statement_label = models.CharField(max_length=255, blank=True, default="")
    source_name = models.CharField(max_length=255, blank=True, default="")
    source_format = models.CharField(max_length=20, blank=True, default="manual")

    date_from = models.DateField(null=True, blank=True, db_index=True)
    date_to = models.DateField(null=True, blank=True, db_index=True)

    statement_opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    statement_closing_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    book_opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    book_closing_balance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    matched_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    unmatched_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    difference_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    imported_row_count = models.PositiveIntegerField(default=0)
    matched_row_count = models.PositiveIntegerField(default=0)
    reviewed_row_count = models.PositiveIntegerField(default=0)
    exception_row_count = models.PositiveIntegerField(default=0)

    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["entity", "status"]),
            models.Index(fields=["entity", "entityfin", "bank_account"]),
            models.Index(fields=["date_from", "date_to"]),
        ]

    def save(self, *args, **kwargs):
        self.session_code = _clean_text(self.session_code).upper() or f"BR-{uuid.uuid4().hex[:12].upper()}"
        self.statement_label = _clean_text(self.statement_label)
        self.source_name = _clean_text(self.source_name)
        self.source_format = _clean_text(self.source_format).lower() or "manual"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session_code} - {self.entity_id}"


class BankStatementBatch(TrackingModel):
    class SourceFormat(models.TextChoices):
        MANUAL = "manual", "Manual"
        CSV = "csv", "CSV"
        EXCEL = "excel", "Excel"
        JSON = "json", "JSON"

    batch_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    session = models.ForeignKey(BankReconciliationSession, on_delete=models.CASCADE, related_name="batches")
    source_name = models.CharField(max_length=255, blank=True, default="")
    source_format = models.CharField(max_length=20, choices=SourceFormat.choices, default=SourceFormat.MANUAL)
    raw_payload = models.JSONField(default=list, blank=True)
    imported_row_count = models.PositiveIntegerField(default=0)
    duplicate_row_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    importedby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["session", "source_format"]),
            models.Index(fields=["batch_code"]),
        ]

    def save(self, *args, **kwargs):
        self.batch_code = _clean_text(self.batch_code).upper() or f"BB-{uuid.uuid4().hex[:12].upper()}"
        self.source_name = _clean_text(self.source_name)
        self.notes = _clean_text(self.notes)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.batch_code} - {self.session_id}"


class BankStatementLine(TrackingModel):
    class MatchStatus(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        SUGGESTED = "suggested", "Suggested"
        MATCHED = "matched", "Matched"
        IGNORED = "ignored", "Ignored"
        EXCEPTION = "exception", "Exception"

    batch = models.ForeignKey(BankStatementBatch, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField()
    transaction_date = models.DateField(null=True, blank=True, db_index=True)
    value_date = models.DateField(null=True, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    reference_number = models.CharField(max_length=120, blank=True, default="")
    counterparty = models.CharField(max_length=255, blank=True, default="")
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    balance_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, blank=True, default="INR")
    external_id = models.CharField(max_length=120, blank=True, default="")
    row_hash = models.CharField(max_length=40, db_index=True)
    match_status = models.CharField(max_length=20, choices=MatchStatus.choices, default=MatchStatus.UNMATCHED, db_index=True)
    suggested_match_score = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("line_no", "id")
        constraints = [
            models.UniqueConstraint(fields=["batch", "line_no"], name="uq_bank_statement_line_batch_line_no"),
            models.UniqueConstraint(fields=["batch", "row_hash"], name="uq_bank_statement_line_batch_row_hash"),
        ]
        indexes = [
            models.Index(fields=["batch", "match_status"]),
            models.Index(fields=["transaction_date", "reference_number"]),
        ]

    def save(self, *args, **kwargs):
        self.description = _clean_text(self.description)
        self.reference_number = _clean_text(self.reference_number)
        self.counterparty = _clean_text(self.counterparty)
        self.currency = _clean_text(self.currency).upper() or "INR"
        self.external_id = _clean_text(self.external_id)
        self.row_hash = _clean_text(self.row_hash).lower() or _hash_row(
            {
                "line_no": self.line_no,
                "transaction_date": self.transaction_date,
                "value_date": self.value_date,
                "description": self.description,
                "reference_number": self.reference_number,
                "counterparty": self.counterparty,
                "debit_amount": str(self.debit_amount),
                "credit_amount": str(self.credit_amount),
                "balance_amount": str(self.balance_amount) if self.balance_amount is not None else None,
                "currency": self.currency,
                "external_id": self.external_id,
            }
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.batch_id}:{self.line_no}"


class BankReconciliationRule(TrackingModel):
    class RuleType(models.TextChoices):
        EXACT = "exact", "Exact Match"
        REFERENCE = "reference", "Reference Contains"
        DATE_WINDOW = "date_window", "Date Window"
        AMOUNT_TOLERANCE = "amount_tolerance", "Amount Tolerance"
        COUNTERPARTY = "counterparty", "Counterparty Contains"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="bank_reconciliation_rules")
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=30, choices=RuleType.choices, default=RuleType.EXACT, db_index=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True, db_index=True)
    amount_tolerance = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    date_window_days = models.PositiveIntegerField(default=0)
    configuration = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("priority", "id")
        constraints = [
            models.UniqueConstraint(fields=["entity", "name"], name="uq_bank_reconciliation_rule_entity_name"),
        ]
        indexes = [
            models.Index(fields=["entity", "rule_type", "is_active"]),
            models.Index(fields=["entity", "priority"]),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.name}"


class BankStatementImportProfile(TrackingModel):
    class SourceFormat(models.TextChoices):
        CSV = "csv", "CSV"
        EXCEL = "excel", "Excel"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="bank_statement_import_profiles")
    bank_account = models.ForeignKey(EntityBankAccountV2, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    name = models.CharField(max_length=255)
    source_format = models.CharField(max_length=20, choices=SourceFormat.choices, default=SourceFormat.CSV, db_index=True)
    delimiter = models.CharField(max_length=5, default=",")
    date_format = models.CharField(max_length=40, blank=True, default="")
    column_mapping = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(fields=["entity", "name"], name="uq_bank_statement_import_profile_entity_name"),
        ]
        indexes = [
            models.Index(fields=["entity", "source_format", "is_active"]),
            models.Index(fields=["entity", "bank_account"]),
        ]

    def save(self, *args, **kwargs):
        self.name = _clean_text(self.name)
        self.delimiter = _clean_text(self.delimiter) or ","
        self.date_format = _clean_text(self.date_format)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.entity_id}:{self.name}"


class BankReconciliationMatch(TrackingModel):
    class MatchKind(models.TextChoices):
        EXACT = "exact", "Exact"
        MANUAL = "manual", "Manual"
        RULE = "rule", "Rule"
        SPLIT = "split", "Split"

    session = models.ForeignKey(BankReconciliationSession, on_delete=models.CASCADE, related_name="matches")
    statement_line = models.OneToOneField(BankStatementLine, on_delete=models.CASCADE, related_name="match", null=True, blank=True)
    entry = models.ForeignKey(Entry, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    journal_line = models.ForeignKey(JournalLine, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    match_kind = models.CharField(max_length=20, choices=MatchKind.choices, default=MatchKind.EXACT)
    matched_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    difference_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True, default="")
    matchedby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    matched_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-matched_at", "-id")
        indexes = [
            models.Index(fields=["session", "match_kind"]),
            models.Index(fields=["entry"]),
            models.Index(fields=["journal_line"]),
        ]

    def save(self, *args, **kwargs):
        self.notes = _clean_text(self.notes)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session_id}:{self.match_kind}"


class BankReconciliationMatchAllocation(TrackingModel):
    match = models.ForeignKey(BankReconciliationMatch, on_delete=models.CASCADE, related_name="allocations")
    journal_line = models.ForeignKey(JournalLine, on_delete=models.PROTECT, related_name="+")
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    allocation_order = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("allocation_order", "id")
        constraints = [
            models.UniqueConstraint(fields=["match", "journal_line"], name="uq_bank_reconciliation_match_allocation_line"),
        ]
        indexes = [
            models.Index(fields=["match", "allocation_order"]),
            models.Index(fields=["journal_line"]),
        ]

    def save(self, *args, **kwargs):
        self.notes = _clean_text(self.notes)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.match_id}:{self.journal_line_id}:{self.allocated_amount}"


class BankReconciliationExceptionItem(TrackingModel):
    class ExceptionType(models.TextChoices):
        BANK_CHARGE = "bank_charge", "Bank Charge"
        BOUNCED_CHEQUE = "bounced_cheque", "Bounced Cheque"
        INTEREST = "interest", "Interest"
        UNKNOWN = "unknown", "Unknown"
        DUPLICATE = "duplicate", "Duplicate"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        IGNORED = "ignored", "Ignored"

    session = models.ForeignKey(BankReconciliationSession, on_delete=models.CASCADE, related_name="exceptions")
    statement_line = models.OneToOneField(BankStatementLine, on_delete=models.CASCADE, related_name="exception_item")
    exception_type = models.CharField(max_length=30, choices=ExceptionType.choices, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolvedby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["session", "exception_type", "status"]),
        ]

    def save(self, *args, **kwargs):
        self.notes = _clean_text(self.notes)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session_id}:{self.exception_type}"


class BankReconciliationAuditLog(TrackingModel):
    session = models.ForeignKey(BankReconciliationSession, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["session", "action"]),
        ]

    def __str__(self):
        return f"{self.session_id}:{self.action}"
