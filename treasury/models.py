from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from helpers.models import TrackingModel

ZERO2 = Decimal("0.00")
User = settings.AUTH_USER_MODEL


class TreasuryPaymentBatch(TrackingModel):
    class SourceType(models.TextChoices):
        VENDOR_PAYABLES = "VENDOR_PAYABLES", "Vendor Payables"
        PAYROLL = "PAYROLL", "Payroll"
        TAX = "TAX", "Tax"
        MISC = "MISC", "Miscellaneous"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        VALIDATED = "VALIDATED", "Validated"
        APPROVED = "APPROVED", "Approved"
        EXPORTED = "EXPORTED", "Exported"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

    class ExportFormat(models.TextChoices):
        GENERIC_CSV = "GENERIC_CSV", "Generic CSV"
        BANK_UPLOAD_PLACEHOLDER = "BANK_UPLOAD_PLACEHOLDER", "Bank Upload Placeholder"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="treasury_payment_batches")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_batches",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_batches",
    )
    source_type = models.CharField(max_length=30, choices=SourceType.choices, default=SourceType.VENDOR_PAYABLES)
    batch_number = models.CharField(max_length=70)
    batch_name = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT)
    payout_date = models.DateField(null=True, blank=True)
    export_format = models.CharField(max_length=40, choices=ExportFormat.choices, default=ExportFormat.GENERIC_CSV)
    total_lines = models.PositiveIntegerField(default=0)
    payable_line_count = models.PositiveIntegerField(default=0)
    invalid_line_count = models.PositiveIntegerField(default=0)
    warning_line_count = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    validation_summary_json = models.JSONField(default=dict, blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    export_reference = models.CharField(max_length=120, blank=True, default="")
    payment_reference = models.CharField(max_length=120, blank=True, default="")
    paid_from = models.ForeignKey(
        "financial.account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_batches_paid_from",
    )
    payment_mode = models.ForeignKey(
        "payments.PaymentMode",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_batches",
    )
    instrument_bank_name = models.CharField(max_length=100, blank=True, default="")
    instrument_no = models.CharField(max_length=50, blank=True, default="")
    instrument_date = models.DateField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    requested_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="requested_treasury_payment_batches")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_treasury_payment_batches")
    exported_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="exported_treasury_payment_batches")
    paid_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="paid_treasury_payment_batches")
    failed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="failed_treasury_payment_batches")
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_treasury_payment_batches")
    approved_at = models.DateTimeField(null=True, blank=True)
    exported_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "batch_number"], name="uq_treasury_payment_batch_number"),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_treas_batch_status"),
            models.Index(fields=["entity", "source_type"], name="ix_treas_batch_source"),
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_treas_batch_scope"),
        ]
        ordering = ["-created_at", "batch_number"]

    def __str__(self) -> str:
        return self.batch_number


class TreasuryPaymentBatchLine(TrackingModel):
    class LineStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VALID = "VALID", "Valid"
        INVALID = "INVALID", "Invalid"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(TreasuryPaymentBatch, on_delete=models.CASCADE, related_name="lines")
    vendor_open_item = models.ForeignKey(
        "purchase.VendorBillOpenItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_batch_lines",
    )
    sequence = models.PositiveIntegerField(default=100)
    party_account = models.ForeignKey(
        "financial.account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_batch_lines",
    )
    party_name = models.CharField(max_length=200, blank=True, default="")
    party_code = models.CharField(max_length=40, blank=True, default="")
    source_doc_type = models.CharField(max_length=40, blank=True, default="")
    source_doc_number = models.CharField(max_length=80, blank=True, default="")
    source_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    account_holder_name = models.CharField(max_length=160, blank=True, default="")
    bank_name = models.CharField(max_length=120, blank=True, default="")
    branch_name = models.CharField(max_length=120, blank=True, default="")
    account_number = models.CharField(max_length=64, blank=True, default="")
    ifsc_code = models.CharField(max_length=20, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    narration = models.CharField(max_length=255, blank=True, default="")
    line_status = models.CharField(max_length=20, choices=LineStatus.choices, default=LineStatus.PENDING)
    has_duplicate_account_warning = models.BooleanField(default=False)
    validation_errors_json = models.JSONField(default=list, blank=True)
    validation_warnings_json = models.JSONField(default=list, blank=True)
    source_snapshot_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "vendor_open_item"],
                condition=Q(vendor_open_item__isnull=False),
                name="uq_treas_batch_line_vendor_item",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "line_status"], name="ix_treas_line_status"),
            models.Index(fields=["vendor_open_item", "line_status"], name="ix_treas_line_vendor_item"),
        ]
        ordering = ["sequence", "created_at", "id"]

    def __str__(self) -> str:
        return f"{self.batch_id}:{self.source_doc_number or self.id}"


class TreasuryPaymentFileExport(TrackingModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(TreasuryPaymentBatch, on_delete=models.CASCADE, related_name="exports")
    export_format = models.CharField(max_length=40, choices=TreasuryPaymentBatch.ExportFormat.choices)
    file_name = models.CharField(max_length=180)
    content_type = models.CharField(max_length=80, default="text/csv")
    row_count = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    file_content = models.TextField(blank=True, default="")
    export_metadata_json = models.JSONField(default=dict, blank=True)
    exported_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="treasury_payment_file_exports")
    exported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["batch", "exported_at"], name="ix_treas_exported")]
        ordering = ["-exported_at", "-created_at"]

    def __str__(self) -> str:
        return self.file_name


class TreasuryPaymentInstrument(TrackingModel):
    class InstrumentType(models.TextChoices):
        CHEQUE = "CHEQUE", "Cheque"
        UPI = "UPI", "UPI"
        NEFT = "NEFT", "NEFT"
        RTGS = "RTGS", "RTGS"
        IMPS = "IMPS", "IMPS"
        CASH = "CASH", "Cash"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        CARD = "CARD", "Card"
        GATEWAY = "GATEWAY", "Payment Gateway"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PREPARED = "PREPARED", "Prepared"
        EXPORTED = "EXPORTED", "Exported"
        SENT_TO_BANK = "SENT_TO_BANK", "Sent To Bank"
        CLEARED = "CLEARED", "Cleared"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        BOUNCED = "BOUNCED", "Bounced"
        STALE = "STALE", "Stale"
        REVERSED = "REVERSED", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(TreasuryPaymentBatch, on_delete=models.CASCADE, related_name="instruments")
    source_account = models.ForeignKey(
        "financial.account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_instruments",
    )
    payment_mode = models.ForeignKey(
        "payments.PaymentMode",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_payment_instruments",
    )
    instrument_type = models.CharField(max_length=30, choices=InstrumentType.choices, default=InstrumentType.OTHER)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PREPARED)
    reference_no = models.CharField(max_length=120, blank=True, default="")
    instrument_no = models.CharField(max_length=50, blank=True, default="")
    instrument_date = models.DateField(null=True, blank=True)
    bank_name = models.CharField(max_length=100, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    status_reason = models.CharField(max_length=255, blank=True, default="")
    cleared_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    cheque_leaf = models.ForeignKey(
        "treasury.TreasuryChequeLeaf",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_instruments",
    )
    reconciliation_match = models.ForeignKey(
        "bank_reco.BankReconciliationMatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treasury_payment_instruments",
    )
    reconciled_bank_line = models.ForeignKey(
        "bank_reco.BankStatementLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treasury_payment_instruments",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "status"], name="ix_treas_instr_batch_status"),
            models.Index(fields=["source_account", "status"], name="ix_treas_instr_source_status"),
            models.Index(fields=["reference_no"], name="ix_treas_instr_reference"),
            models.Index(fields=["reconciliation_match"], name="ix_treas_instr_reco_match"),
        ]
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.batch_id}:{self.reference_no or self.instrument_no or self.id}"


class TreasuryChequeBook(TrackingModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXHAUSTED = "EXHAUSTED", "Exhausted"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="treasury_cheque_books")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_cheque_books",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_cheque_books",
    )
    bank_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        related_name="treasury_cheque_books",
    )
    book_number = models.CharField(max_length=60)
    start_leaf = models.CharField(max_length=30)
    end_leaf = models.CharField(max_length=30)
    total_leaves = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    issued_on = models.DateField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "bank_account", "book_number"], name="uq_treas_cheque_book_bank_book"),
        ]
        indexes = [
            models.Index(fields=["entity", "bank_account", "status"], name="ix_treas_chq_book_bank_status"),
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_treas_chq_book_scope"),
        ]
        ordering = ["bank_account_id", "book_number", "start_leaf"]

    def __str__(self) -> str:
        return f"{self.book_number}: {self.start_leaf}-{self.end_leaf}"


class TreasuryChequeLeaf(TrackingModel):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        RESERVED = "RESERVED", "Reserved"
        ISSUED = "ISSUED", "Issued"
        CLEARED = "CLEARED", "Cleared"
        BOUNCED = "BOUNCED", "Bounced"
        CANCELLED = "CANCELLED", "Cancelled"
        STALE = "STALE", "Stale"
        REISSUED = "REISSUED", "Reissued"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cheque_book = models.ForeignKey(TreasuryChequeBook, on_delete=models.CASCADE, related_name="leaves")
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="treasury_cheque_leaves")
    bank_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        related_name="treasury_cheque_leaves",
    )
    leaf_no = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    reserved_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "bank_account", "leaf_no"], name="uq_treas_cheque_leaf_bank_no"),
        ]
        indexes = [
            models.Index(fields=["entity", "bank_account", "status"], name="ix_treas_chq_leaf_bank_status"),
            models.Index(fields=["leaf_no"], name="ix_treas_chq_leaf_no"),
        ]
        ordering = ["bank_account_id", "leaf_no"]

    def __str__(self) -> str:
        return f"{self.leaf_no} ({self.status})"


class TreasuryCashMovement(TrackingModel):
    class MovementType(models.TextChoices):
        CASH_DEPOSIT = "CASH_DEPOSIT", "Cash Deposit"
        CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
        BANK_TO_BANK = "BANK_TO_BANK", "Bank To Bank"
        CASH_TO_BANK = "CASH_TO_BANK", "Cash To Bank"
        BANK_TO_CASH = "BANK_TO_CASH", "Bank To Cash"

    class Status(models.TextChoices):
        POSTED = "POSTED", "Posted"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="treasury_cash_movements")
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, related_name="treasury_cash_movements")
    subentity = models.ForeignKey(
        "entity.SubEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_cash_movements",
    )
    movement_number = models.CharField(max_length=70)
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    movement_date = models.DateField(default=timezone.localdate, db_index=True)
    source_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        related_name="treasury_cash_movements_source",
    )
    destination_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        related_name="treasury_cash_movements_destination",
    )
    payment_mode = models.ForeignKey(
        "payments.PaymentMode",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_cash_movements",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    reference_no = models.CharField(max_length=120, blank=True, default="")
    instrument_no = models.CharField(max_length=50, blank=True, default="")
    instrument_date = models.DateField(null=True, blank=True)
    bank_name = models.CharField(max_length=100, blank=True, default="")
    narration = models.CharField(max_length=255, blank=True, default="")
    voucher = models.ForeignKey(
        "vouchers.VoucherHeader",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="treasury_cash_movements",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    posted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="posted_treasury_cash_movements")
    posted_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_treasury_cash_movements")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "movement_number"], name="uq_treas_cash_move_number"),
            models.CheckConstraint(name="ck_treas_cash_move_amt_pos", check=Q(amount__gt=0)),
            models.CheckConstraint(
                name="ck_treas_cash_move_accounts_diff",
                check=~Q(source_account=models.F("destination_account")),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "movement_date"], name="ix_treas_cash_scope_dt"),
            models.Index(fields=["entity", "status", "movement_date"], name="ix_treas_cash_status_dt"),
            models.Index(fields=["source_account", "movement_date"], name="ix_treas_cash_src_dt"),
            models.Index(fields=["destination_account", "movement_date"], name="ix_treas_cash_dst_dt"),
            models.Index(fields=["voucher"], name="ix_treas_cash_voucher"),
        ]
        ordering = ["-movement_date", "-created_at", "movement_number"]

    def __str__(self) -> str:
        return self.movement_number


class TreasuryPaymentStatusLog(TrackingModel):
    batch = models.ForeignKey(TreasuryPaymentBatch, on_delete=models.CASCADE, related_name="status_logs")
    old_status = models.CharField(max_length=20, blank=True, default="")
    new_status = models.CharField(max_length=20)
    acted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="treasury_payment_status_logs")
    comment = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["batch", "created_at"], name="ix_treas_log_batch")]
        ordering = ["created_at", "id"]
