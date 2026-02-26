from __future__ import annotations

import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q, Index, UniqueConstraint, CheckConstraint
from django.utils import timezone
from financial.models import account, accountHead
from catalog.models import Product,UnitOfMeasure

User = settings.AUTH_USER_MODEL

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


class TxnType(models.TextChoices):
    SALES = "S", "Sales"
    PURCHASE = "P", "Purchase"
    JOURNAL = "J", "Journal"
    SALES_RETURN = "SR", "Sales Return"
    PURCHASE_RETURN = "PR", "Purchase Return"
    PURCHASE_CREDIT_NOTE = "PCN", "Purchase Credit Note"
    PURCHASE_DEBIT_NOTE = "PDN", "Purchase Debit Note"
    JOURNAL_CASH = "C", "Journal (Cash)"
    JOURNAL_BANK = "B", "Journal (Bank)"
    RECEIPT = "RV", "Receipt Voucher"
    PAYMENT = "PV", "Payment Voucher"


class EntryStatus(models.IntegerChoices):
    DRAFT = 1, "Draft"
    POSTED = 2, "Posted"
    REVERSED = 9, "Reversed"


class StaticAccountGroup(models.TextChoices):
    CASH_BANK = "CASH_BANK", "Cash/Bank"
    ROUND_OFF = "ROUND_OFF", "Round-off"
    GST_OUTPUT = "GST_OUTPUT", "GST Output"
    GST_INPUT = "GST_INPUT", "GST Input"
    RCM_PAYABLE = "RCM_PAYABLE", "RCM Payable"
    TDS = "TDS", "TDS"
    TCS = "TCS", "TCS"
    PURCHASE = "PURCHASE", "Purchase Defaults"
    SALES = "SALES", "Sales Defaults"
    OTHER = "OTHER", "Other"


class StaticAccount(models.Model):
    """
    Global master list of functional ledger roles needed by Finacc.
    You add new codes later without schema changes.
    """
    code = models.CharField(max_length=80, unique=True, db_index=True)  # e.g. CASH_IN_HAND, OUTPUT_IGST
    name = models.CharField(max_length=255)
    group = models.CharField(max_length=30, choices=StaticAccountGroup.choices,
                             default=StaticAccountGroup.OTHER, db_index=True)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.CharField(max_length=500, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class EntityStaticAccountMap(models.Model):
    """
    Per-entity mapping: StaticAccount -> actual ledger account.
    Use is_active to replace mappings over time without deleting.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE,related_name="posting_static_account_maps",)
    static_account = models.ForeignKey(StaticAccount, on_delete=models.PROTECT,related_name="entity_maps",)
    account = models.ForeignKey(account, on_delete=models.PROTECT, related_name="+",)

    is_active = models.BooleanField(default=True, db_index=True)
    effective_from = models.DateField(null=True, blank=True)  # optional for future use

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["entity", "static_account"],
                condition=Q(is_active=True),
                name="uq_esam_entity_static_active",
            ),
        ]
        indexes = [
            Index(fields=["entity", "static_account"], name="ix_esam_entity_static"),
            Index(fields=["entity", "account"], name="ix_esam_entity_account"),
            Index(fields=["static_account"], name="ix_esam_static"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id} {self.static_account.code} -> {self.account_id}"


class PostingBatch(models.Model):
    """
    One atomic posting run for a given source transaction.
    Ensures idempotency + audit trail and safe re-post.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, null=True, blank=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True)

    txn_type = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    txn_id = models.IntegerField(db_index=True)
    voucher_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    revision = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    note = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        indexes = [
            Index(fields=["entity", "txn_type", "txn_id"], name="ix_pb_locator"),
            Index(fields=["entity", "entityfin", "subentity", "txn_type", "txn_id"], name="ix_pb_locator_scope"),
            Index(fields=["entity", "voucher_no"], name="ix_pb_vno"),
            Index(fields=["is_active", "created_at"], name="ix_pb_active_time"),
        ]
        constraints = [
            UniqueConstraint(
                fields=["entity", "entityfin", "subentity", "txn_type", "txn_id"],
                condition=Q(is_active=True),
                name="uq_pb_one_active_per_txn",
            )
        ]

    def __str__(self) -> str:
        return f"{self.txn_type}#{self.txn_id} rev={self.revision} active={self.is_active}"


class Entry(models.Model):
    """
    Ledger posting header for reporting and grouping.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, related_name="+",)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, null=True, blank=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True)

    txn_type = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    txn_id = models.IntegerField(db_index=True)
    voucher_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    voucher_date = models.DateField(null=True, blank=True, db_index=True)  # UI date
    posting_date = models.DateField(db_index=True)                         # accounting date

    status = models.IntegerField(choices=EntryStatus.choices, default=EntryStatus.DRAFT, db_index=True)

    posted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="posting_entries_posted")

    posting_batch = models.ForeignKey(PostingBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="entries")

    narration = models.CharField(max_length=500, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="posting_entries_created")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["entity", "entityfin", "subentity", "txn_type", "txn_id"],
                name="uq_entry_one_per_txn_scope",
            )
        ]
        indexes = [
            Index(fields=["entity", "posting_date"], name="ix_entry_entity_postdate"),
            Index(fields=["entity", "txn_type", "txn_id"], name="ix_entry_txn"),
            Index(fields=["entity", "voucher_no"], name="ix_entry_vno"),
            Index(fields=["status", "posted_at"], name="ix_entry_status_time"),
        ]

    def __str__(self) -> str:
        return f"Entry {self.txn_type}#{self.txn_id} {self.posting_date}"


class JournalLine(models.Model):
    """
    One row = one debit OR one credit.
    """
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE,  related_name="posting_journal_lines",)
    posting_batch = models.ForeignKey(PostingBatch, on_delete=models.CASCADE, related_name="journal_lines")

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE,related_name="+",)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, null=True, blank=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True)

    txn_type = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    txn_id = models.IntegerField(db_index=True)
    detail_id = models.IntegerField(null=True, blank=True, db_index=True)
    voucher_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    # XOR: exactly one must be set
    account = models.ForeignKey(account, on_delete=models.PROTECT, null=True, blank=True,  related_name="+",)
    accounthead = models.ForeignKey(accountHead, on_delete=models.PROTECT, null=True, blank=True,  related_name="+",)

    # True=Debit, False=Credit
    drcr = models.BooleanField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    description = models.CharField(max_length=500, null=True, blank=True)

    posting_date = models.DateField(db_index=True)
    posted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",)

    class Meta:
        constraints = [
            CheckConstraint(name="ck_jl_amount_gt_zero", condition=Q(amount__gt=0)),
            CheckConstraint(
                name="ck_jl_account_xor_head",
                condition=(
                    (Q(account__isnull=False) & Q(accounthead__isnull=True)) |
                    (Q(account__isnull=True) & Q(accounthead__isnull=False))
                ),
            ),
        ]
        indexes = [
            Index(fields=["entity", "txn_type", "txn_id"], name="ix_jl_locator"),
            Index(fields=["entity", "txn_type", "txn_id", "detail_id"], name="ix_jl_locator_line"),
            Index(fields=["entity", "posting_date"], name="ix_jl_entity_postdate"),
            Index(fields=["account"], name="ix_jl_posting_account"),
            Index(fields=["accounthead"], name="ix_jl_head"),
            Index(fields=["posting_batch"], name="ix_jl_batch"),
        ]

    def __str__(self) -> str:
        side = "Dr" if self.drcr else "Cr"
        target = self.account_id or self.accounthead_id
        return f"{side} {self.amount} -> {target} ({self.txn_type}#{self.txn_id})"


class InventoryMove(models.Model):
    """
    Inventory movement row.
    qty sign: +IN / -OUT
    base_qty always in product stock/base UOM.
    """
    class MoveType(models.TextChoices):
        IN_ = "IN", "IN"
        OUT = "OUT", "OUT"
        ADJ = "ADJ", "Adjustment"
        REV = "REV", "Reversal"

    class CostSource(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        FIFO = "FIFO", "FIFO"
        AVG = "AVG", "Average"
        MANUAL = "MANUAL", "Manual"

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="posting_inventory_moves",)
    posting_batch = models.ForeignKey(PostingBatch, on_delete=models.CASCADE, related_name="inventory_moves_posting")

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, related_name="+",)
    entityfin = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, null=True, blank=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True)

    txn_type = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    txn_id = models.IntegerField(db_index=True)
    detail_id = models.IntegerField(null=True, blank=True, db_index=True)
    voucher_no = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    product = models.ForeignKey(Product, on_delete=models.PROTECT,  related_name="+",)

    # Optional: switch to FK if you have Godown model
    location = models.ForeignKey("entity.Godown", on_delete=models.PROTECT, null=True, blank=True)

    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="inv_moves_uom")
    base_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="inv_moves_base_uom")

    qty = models.DecimalField(max_digits=18, decimal_places=4)  # entered qty (+/-)
    uom_factor = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))
    base_qty = models.DecimalField(max_digits=18, decimal_places=4, default=ZERO4)

    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO4)  # ALWAYS 4dp
    ext_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)   # abs(base_qty)*unit_cost

    cost_source = models.CharField(max_length=20, choices=CostSource.choices,
                                   default=CostSource.PURCHASE, db_index=True)
    cost_meta = models.JSONField(null=True, blank=True)

    move_type = models.CharField(max_length=10, choices=MoveType.choices, db_index=True)

    posting_date = models.DateField(db_index=True)
    posted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",)

    class Meta:
        constraints = [
            CheckConstraint(name="ck_im_qty_nonzero", condition=~Q(qty=0)),
            CheckConstraint(name="ck_im_cost_nonneg", condition=Q(unit_cost__gte=0) & Q(ext_cost__gte=0)),
        ]
        indexes = [
            Index(fields=["entity", "txn_type", "txn_id"], name="ix_im_locator"),
            Index(fields=["entity", "txn_type", "txn_id", "detail_id"], name="ix_im_locator_line"),
            Index(fields=["entity", "product", "posting_date"], name="ix_im_p_entity_product_date"),
            Index(fields=["posting_batch"], name="ix_im_batch"),
            Index(fields=["location", "product", "posting_date"], name="ix_im_loc_product_date"),
        ]

    def __str__(self) -> str:
        direction = "IN" if self.qty > 0 else "OUT"
        return f"{direction} {self.qty} ({self.txn_type}#{self.txn_id})"
