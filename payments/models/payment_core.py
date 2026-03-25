from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from financial.models import Ledger, account
from geography.models import State

from .base import TrackingModel
from .payment_masters import PaymentMode

ZERO2 = Decimal("0.00")
User = settings.AUTH_USER_MODEL


class PaymentVoucherHeader(TrackingModel):
    class PaymentType(models.TextChoices):
        AGAINST_BILL = "AGAINST_BILL", "Against Bill"
        ADVANCE = "ADVANCE", "Advance Payment"
        ON_ACCOUNT = "ON_ACCOUNT", "On Account"

    class SupplyType(models.TextChoices):
        GOODS = "GOODS", "Goods"
        SERVICES = "SERVICES", "Services"
        MIXED = "MIXED", "Mixed/Unknown"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        CONFIRMED = 2, "Confirmed"
        POSTED = 3, "Posted"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    voucher_date = models.DateField(default=timezone.localdate, db_index=True)
    doc_code = models.CharField(max_length=10, default="PPV")
    doc_no = models.PositiveIntegerField(null=True, blank=True)
    voucher_code = models.CharField(max_length=50, null=True, blank=True)
    currency_code = models.CharField(max_length=3, default="INR", db_index=True)
    base_currency_code = models.CharField(max_length=3, default="INR")
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("1.000000"))

    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.AGAINST_BILL)
    supply_type = models.CharField(max_length=10, choices=SupplyType.choices, default=SupplyType.SERVICES)

    paid_from = models.ForeignKey(account, on_delete=models.PROTECT, related_name="new_pv_paid_from")
    paid_from_ledger = models.ForeignKey(
        Ledger,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_vouchers_paid_from",
        help_text="Additive ledger-native mirror of paid_from for the staged accounting cutover.",
    )
    paid_to = models.ForeignKey(account, on_delete=models.PROTECT, related_name="new_pv_paid_to")
    paid_to_ledger = models.ForeignKey(
        Ledger,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_vouchers_paid_to",
        help_text="Additive ledger-native mirror of paid_to for the staged accounting cutover.",
    )
    payment_mode = models.ForeignKey(PaymentMode, on_delete=models.PROTECT, null=True, blank=True)

    cash_paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_adjustment_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    settlement_effective_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    settlement_effective_amount_base_currency = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    reference_number = models.CharField(max_length=100, null=True, blank=True)
    narration = models.TextField(null=True, blank=True)

    instrument_bank_name = models.CharField(max_length=100, null=True, blank=True)
    instrument_no = models.CharField(max_length=50, null=True, blank=True)
    instrument_date = models.DateField(null=True, blank=True)

    place_of_supply_state = models.ForeignKey(State, null=True, blank=True, on_delete=models.SET_NULL)
    vendor_gstin = models.CharField(max_length=15, null=True, blank=True)

    advance_taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    advance_cgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    advance_sgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    advance_igst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    advance_cess = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="new_pv_approved")
    approved_at = models.DateTimeField(null=True, blank=True)
    workflow_payload = models.JSONField(default=dict, blank=True)

    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_payment_vouchers_cancelled",
        related_query_name="new_payment_voucher_cancelled",
    )
    cancel_reason = models.CharField(max_length=255, null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="new_pv_created")
    ap_settlement = models.OneToOneField(
        "purchase.VendorSettlement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_voucher",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "doc_code", "doc_no"),
                condition=Q(subentity__isnull=False, doc_no__isnull=False),
                name="uq_payment_voucher_scope_docno_sub",
            ),
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "doc_code", "doc_no"),
                condition=Q(subentity__isnull=True, doc_no__isnull=False),
                name="uq_payment_voucher_scope_docno_root",
            ),
            models.CheckConstraint(name="ck_payment_cash_nonneg", check=Q(cash_paid_amount__gte=0)),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "voucher_date"], name="ix_pay_ent_fin_date"),
            models.Index(fields=["entity", "entityfinid", "paid_to"], name="ix_pay_ent_fin_vendor"),
            models.Index(fields=["entity", "entityfinid", "paid_to_ledger"], name="ix_pay_ent_fin_vendor_led"),
            models.Index(fields=["entity", "entityfinid", "status"], name="ix_pay_ent_fin_status"),
        ]

    def __str__(self):
        return self.voucher_code or f"{self.doc_code}-{self.doc_no}"


class PaymentVoucherAllocation(TrackingModel):
    payment_voucher = models.ForeignKey(PaymentVoucherHeader, related_name="allocations", on_delete=models.CASCADE)
    open_item = models.ForeignKey(
        "purchase.VendorBillOpenItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )
    settled_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    is_full_settlement = models.BooleanField(default=False)
    is_advance_adjustment = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(name="ck_payment_alloc_amt_nonneg", check=Q(settled_amount__gte=0)),
            models.UniqueConstraint(fields=("payment_voucher", "open_item"), name="uq_payment_alloc_voucher_openitem"),
        ]
        indexes = [
            models.Index(fields=["payment_voucher"], name="ix_payment_alloc_voucher"),
            models.Index(fields=["open_item"], name="ix_payment_alloc_openitem"),
        ]

    def __str__(self):
        return f"{self.payment_voucher_id} -> {self.open_item_id}: {self.settled_amount}"


class PaymentVoucherAdjustment(TrackingModel):
    class AdjType(models.TextChoices):
        TDS = "TDS", "TDS"
        TCS = "TCS", "TCS"
        DISCOUNT_RCVD = "DISCOUNT_RCVD", "Discount Received"
        BANK_CHARGES = "BANK_CHARGES", "Bank Charges"
        ROUND_OFF = "ROUND_OFF", "Round Off"
        WRITE_OFF = "WRITE_OFF", "Write Off"
        FX_DIFF = "FX_DIFF", "Forex Difference"
        OTHER = "OTHER", "Other"

    class Effect(models.TextChoices):
        PLUS = "PLUS", "Plus"
        MINUS = "MINUS", "Minus"

    payment_voucher = models.ForeignKey(PaymentVoucherHeader, related_name="adjustments", on_delete=models.CASCADE)
    allocation = models.ForeignKey(
        PaymentVoucherAllocation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjustments",
    )
    adj_type = models.CharField(max_length=20, choices=AdjType.choices)
    ledger_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        related_name="new_payment_adjustment_ledgers",
    )
    ledger = models.ForeignKey(
        Ledger,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_adjustments",
        help_text="Additive ledger-native mirror of ledger_account for the staged accounting cutover.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    settlement_effect = models.CharField(max_length=5, choices=Effect.choices, default=Effect.PLUS)
    remarks = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(name="ck_payment_adj_amt_nonneg", check=Q(amount__gte=0)),
        ]

    def __str__(self):
        return f"{self.payment_voucher_id} {self.adj_type} {self.amount} {self.settlement_effect}"


class PaymentVoucherAdvanceAdjustment(TrackingModel):
    payment_voucher = models.ForeignKey(PaymentVoucherHeader, related_name="advance_adjustments", on_delete=models.CASCADE)
    advance_balance = models.ForeignKey(
        "purchase.VendorAdvanceBalance",
        on_delete=models.PROTECT,
        related_name="payment_advance_adjustments",
    )
    allocation = models.ForeignKey(
        PaymentVoucherAllocation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="advance_adjustments",
    )
    open_item = models.ForeignKey(
        "purchase.VendorBillOpenItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_advance_adjustments",
    )
    adjusted_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    ap_settlement = models.OneToOneField(
        "purchase.VendorSettlement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_advance_adjustment",
    )
    remarks = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(name="ck_payment_adv_adj_amt_nonneg", check=Q(adjusted_amount__gte=0)),
        ]
        indexes = [
            models.Index(fields=["payment_voucher"], name="ix_payment_adv_adj_voucher"),
            models.Index(fields=["advance_balance"], name="ix_payment_adv_adj_balance"),
            models.Index(fields=["open_item"], name="ix_payment_adv_adj_openitem"),
        ]

    def __str__(self):
        return f"{self.payment_voucher_id} -> {self.advance_balance_id}: {self.adjusted_amount}"
