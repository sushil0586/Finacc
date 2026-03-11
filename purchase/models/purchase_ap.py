from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from .base import TrackingModel
from .purchase_core import PurchaseInvoiceHeader

User = settings.AUTH_USER_MODEL
ZERO2 = Decimal("0.00")


class VendorBillOpenItem(TrackingModel):
    """
    AP open-item tracker for posted purchase documents.
    One item per purchase header.
    Amounts are signed:
      - Invoice / Debit Note => positive payable
      - Credit Note => negative payable
    """

    header = models.OneToOneField(
        PurchaseInvoiceHeader,
        on_delete=models.CASCADE,
        related_name="ap_open_item",
    )

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    vendor = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    vendor_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    doc_type = models.IntegerField(db_index=True)
    bill_date = models.DateField(db_index=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    purchase_number = models.CharField(max_length=50, null=True, blank=True)
    supplier_invoice_number = models.CharField(max_length=50, null=True, blank=True)

    original_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    tds_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    gst_tds_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    net_payable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    settled_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    outstanding_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, db_index=True)

    is_open = models.BooleanField(default=True, db_index=True)
    last_settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "vendor", "is_open"], name="ix_pur_ap_open_scope"),
            models.Index(fields=["entity", "entityfinid", "vendor_ledger", "is_open"], name="ix_pur_ap_open_vscope"),
            models.Index(fields=["entity", "entityfinid", "bill_date"], name="ix_pur_ap_open_billdt"),
            models.Index(fields=["entity", "entityfinid", "due_date"], name="ix_pur_ap_open_duedt"),
        ]

    def __str__(self) -> str:
        return f"APOpenItem({self.header_id}, outstanding={self.outstanding_amount})"


class VendorSettlement(TrackingModel):
    class SettlementType(models.TextChoices):
        PAYMENT = "payment", "Payment"
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
    vendor = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    vendor_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    advance_balance = models.ForeignKey(
        "purchase.VendorAdvanceBalance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="settlements",
    )

    settlement_type = models.CharField(max_length=30, choices=SettlementType.choices, default=SettlementType.PAYMENT)
    settlement_date = models.DateField(db_index=True)
    reference_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    external_voucher_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="posted_vendor_settlements")

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "vendor", "status"], name="ix_pur_settle_scope"),
            models.Index(fields=["entity", "entityfinid", "vendor_ledger", "status"], name="ix_pur_settle_vscope"),
            models.Index(fields=["entity", "entityfinid", "settlement_date"], name="ix_pur_settle_date"),
        ]

    def __str__(self) -> str:
        return f"VendorSettlement({self.id}, {self.settlement_type}, {self.total_amount})"


class VendorAdvanceBalance(TrackingModel):
    class SourceType(models.TextChoices):
        PAYMENT_ADVANCE = "payment_advance", "Payment Advance"
        ON_ACCOUNT = "on_account", "On Account"
        MANUAL = "manual", "Manual"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    vendor = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)
    vendor_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    source_type = models.CharField(max_length=30, choices=SourceType.choices, default=SourceType.PAYMENT_ADVANCE, db_index=True)
    credit_date = models.DateField(db_index=True)
    reference_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    original_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    adjusted_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    outstanding_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2, db_index=True)
    is_open = models.BooleanField(default=True, db_index=True)
    last_adjusted_at = models.DateTimeField(null=True, blank=True)

    payment_voucher = models.OneToOneField(
        "payments.PaymentVoucherHeader",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_advance_balance",
    )

    class Meta:
        indexes = [
            models.Index(fields=["entity", "entityfinid", "vendor", "is_open"], name="ix_pur_adv_scope"),
            models.Index(fields=["entity", "entityfinid", "vendor_ledger", "is_open"], name="ix_pur_adv_vscope"),
            models.Index(fields=["entity", "entityfinid", "credit_date"], name="ix_pur_adv_creditdt"),
        ]

    def __str__(self) -> str:
        return f"VendorAdvanceBalance({self.id}, outstanding={self.outstanding_amount})"


class VendorSettlementLine(TrackingModel):
    settlement = models.ForeignKey(VendorSettlement, on_delete=models.CASCADE, related_name="lines")
    open_item = models.ForeignKey(VendorBillOpenItem, on_delete=models.PROTECT, related_name="settlement_lines")

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)  # absolute requested amount
    applied_amount_signed = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    note = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("settlement", "open_item"), name="uq_pur_settleline_settlement_openitem"),
        ]
        indexes = [
            models.Index(fields=["settlement"], name="ix_pur_settleline_settlement"),
            models.Index(fields=["open_item"], name="ix_pur_settleline_openitem"),
        ]

    def __str__(self) -> str:
        return f"VendorSettlementLine({self.settlement_id}, {self.open_item_id}, {self.amount})"
