from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from .base import TrackingModel
from .sales_core import SalesInvoiceHeader

User = settings.AUTH_USER_MODEL
ZERO2 = Decimal("0.00")


class CustomerBillOpenItem(TrackingModel):
    """
    AR open-item tracker for posted sales documents.
    One item per sales header.
    Amounts are signed:
      - Invoice / Debit Note => positive receivable
      - Credit Note => negative receivable
    """

    header = models.OneToOneField(
        SalesInvoiceHeader,
        on_delete=models.CASCADE,
        related_name="ap_open_item",
    )

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    customer = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)

    doc_type = models.IntegerField(db_index=True)
    bill_date = models.DateField(db_index=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    invoice_number = models.CharField(max_length=50, null=True, blank=True)
    customer_reference_number = models.CharField(max_length=50, null=True, blank=True)

    original_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    tds_collected = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    gst_tds_collected = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    net_receivable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    settled_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    outstanding_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, db_index=True)

    is_open = models.BooleanField(default=True, db_index=True)
    last_settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "customer", "is_open"], name="ix_sales_ar_open_scope"),
            models.Index(fields=["entity", "entityfinid", "bill_date"], name="ix_sales_ar_open_billdt"),
            models.Index(fields=["entity", "entityfinid", "due_date"], name="ix_sales_ar_open_duedt"),
        ]

    def __str__(self) -> str:
        return f"APOpenItem({self.header_id}, outstanding={self.outstanding_amount})"


class CustomerSettlement(TrackingModel):
    class SettlementType(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        ADVANCE_ADJUSTMENT = "advance_adjustment", "Advance Adjustment"
        CREDIT_NOTE_ADJUSTMENT = "credit_note_adjustment", "Credit Note Adjustment"
        DEBIT_NOTE_ADJUSTMENT = "debit_note_adjustment", "Debit Note Adjustment"
        WRITEOFF = "writeoff", "Writeoff"
        MANUAL = "manual", "Manual"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        POSTED = 2, "Posted"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    customer = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    advance_balance = models.ForeignKey(
        "sales.CustomerAdvanceBalance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="settlements",
    )

    settlement_type = models.CharField(max_length=30, choices=SettlementType.choices, default=SettlementType.RECEIPT)
    settlement_date = models.DateField(db_index=True)
    reference_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    external_voucher_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="posted_customer_settlements")

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "customer", "status"], name="ix_sales_ar_settle_scope"),
            models.Index(fields=["entity", "entityfinid", "settlement_date"], name="ix_sales_ar_settle_date"),
        ]

    def __str__(self) -> str:
        return f"CustomerSettlement({self.id}, {self.settlement_type}, {self.total_amount})"


class CustomerAdvanceBalance(TrackingModel):
    class SourceType(models.TextChoices):
        RECEIPT_ADVANCE = "receipt_advance", "Receipt Advance"
        ON_ACCOUNT = "on_account", "On Account"
        MANUAL = "manual", "Manual"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    customer = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)

    source_type = models.CharField(max_length=30, choices=SourceType.choices, default=SourceType.RECEIPT_ADVANCE, db_index=True)
    credit_date = models.DateField(db_index=True)
    reference_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    original_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    adjusted_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    outstanding_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, db_index=True)
    is_open = models.BooleanField(default=True, db_index=True)
    last_adjusted_at = models.DateTimeField(null=True, blank=True)

    receipt_voucher = models.OneToOneField(
        "receipts.ReceiptVoucherHeader",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_advance_balance",
    )

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "customer", "is_open"], name="ix_sales_ar_adv_scope"),
            models.Index(fields=["entity", "entityfinid", "credit_date"], name="ix_sales_ar_adv_creditdt"),
        ]

    def __str__(self) -> str:
        return f"CustomerAdvanceBalance({self.id}, outstanding={self.outstanding_amount})"


class CustomerSettlementLine(TrackingModel):
    settlement = models.ForeignKey(CustomerSettlement, on_delete=models.CASCADE, related_name="lines")
    open_item = models.ForeignKey(CustomerBillOpenItem, on_delete=models.PROTECT, related_name="settlement_lines")

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)  # absolute requested amount
    applied_amount_signed = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    note = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("settlement", "open_item"), name="uq_sales_ar_settleline_settlement_openitem"),
        ]
        indexes = [
            models.Index(fields=["settlement"], name="ix_sales_stl_settle"),
            models.Index(fields=["open_item"], name="ix_sales_stl_open"),
        ]

    def __str__(self) -> str:
        return f"CustomerSettlementLine({self.settlement_id}, {self.open_item_id}, {self.amount})"
