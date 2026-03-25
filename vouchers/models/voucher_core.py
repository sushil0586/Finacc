from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from financial.models import Ledger, account

from .base import TrackingModel

ZERO2 = Decimal("0.00")
User = settings.AUTH_USER_MODEL


class VoucherHeader(TrackingModel):
    class VoucherType(models.TextChoices):
        JOURNAL = "JOURNAL", "Journal"
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        CONFIRMED = 2, "Confirmed"
        POSTED = 3, "Posted"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    voucher_date = models.DateField(default=timezone.localdate, db_index=True)
    doc_code = models.CharField(max_length=10, default="JV")
    doc_no = models.PositiveIntegerField(null=True, blank=True)
    voucher_code = models.CharField(max_length=50, null=True, blank=True)

    voucher_type = models.CharField(max_length=20, choices=VoucherType.choices, default=VoucherType.JOURNAL, db_index=True)
    cash_bank_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voucher_cash_bank_accounts",
    )
    cash_bank_ledger = models.ForeignKey(
        Ledger,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voucher_cash_bank_ledgers",
    )
    reference_number = models.CharField(max_length=100, null=True, blank=True)
    narration = models.TextField(null=True, blank=True)

    instrument_bank_name = models.CharField(max_length=100, null=True, blank=True)
    instrument_no = models.CharField(max_length=50, null=True, blank=True)
    instrument_date = models.DateField(null=True, blank=True)

    total_debit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_vouchers")
    approved_at = models.DateTimeField(null=True, blank=True)
    workflow_payload = models.JSONField(default=dict, blank=True)

    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_vouchers",
        related_query_name="cancelled_voucher",
    )
    cancel_reason = models.CharField(max_length=255, null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_vouchers")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "doc_code", "doc_no"),
                condition=Q(subentity__isnull=False, doc_no__isnull=False),
                name="uq_voucher_scope_docno_sub",
            ),
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "doc_code", "doc_no"),
                condition=Q(subentity__isnull=True, doc_no__isnull=False),
                name="uq_voucher_scope_docno_root",
            ),
            models.CheckConstraint(name="ck_voucher_dr_nonneg", check=Q(total_debit_amount__gte=0)),
            models.CheckConstraint(name="ck_voucher_cr_nonneg", check=Q(total_credit_amount__gte=0)),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "voucher_date"], name="ix_voucher_ent_fin_date"),
            models.Index(fields=["entity", "entityfinid", "voucher_type"], name="ix_voucher_ent_fin_type"),
            models.Index(fields=["entity", "entityfinid", "status"], name="ix_voucher_ent_fin_status"),
        ]

    def __str__(self):
        return self.voucher_code or f"{self.doc_code}-{self.doc_no}"


class VoucherLine(TrackingModel):
    class SystemLineRole(models.TextChoices):
        BUSINESS = "BUSINESS", "Business"
        CASH_OFFSET = "CASH_OFFSET", "Cash Offset"
        BANK_OFFSET = "BANK_OFFSET", "Bank Offset"

    header = models.ForeignKey(VoucherHeader, related_name="lines", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField(default=1)
    account = models.ForeignKey(account, on_delete=models.PROTECT, related_name="voucher_lines")
    ledger = models.ForeignKey(
        Ledger,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voucher_lines_ledgers",
    )
    narration = models.CharField(max_length=255, null=True, blank=True)
    dr_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cr_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    is_system_generated = models.BooleanField(default=False, db_index=True)
    system_line_role = models.CharField(
        max_length=20,
        choices=SystemLineRole.choices,
        default=SystemLineRole.BUSINESS,
        db_index=True,
    )
    generated_from_line = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_lines",
    )
    pair_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("header", "line_no"), name="uq_voucher_line_header_lineno"),
            models.CheckConstraint(name="ck_voucher_line_dr_nonneg", check=Q(dr_amount__gte=0)),
            models.CheckConstraint(name="ck_voucher_line_cr_nonneg", check=Q(cr_amount__gte=0)),
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_voucher_line_header"),
            models.Index(fields=["account"], name="ix_voucher_line_account"),
            models.Index(fields=["header", "is_system_generated"], name="ix_voucher_line_hdr_sys"),
        ]

    def __str__(self):
        return f"{self.header_id}:{self.line_no} Dr={self.dr_amount} Cr={self.cr_amount}"
