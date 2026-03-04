from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .base import TrackingModel
from .purchase_core import PurchaseInvoiceHeader

User = settings.AUTH_USER_MODEL
ZERO2 = Decimal("0.00")


class PurchaseStatutoryChallan(TrackingModel):
    class TaxType(models.TextChoices):
        IT_TDS = "IT_TDS", "Income-tax TDS"
        GST_TDS = "GST_TDS", "GST-TDS"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        DEPOSITED = 2, "Deposited"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    tax_type = models.CharField(max_length=10, choices=TaxType.choices, db_index=True)
    challan_no = models.CharField(max_length=50, db_index=True)
    challan_date = models.DateField(default=timezone.localdate, db_index=True)
    period_from = models.DateField(null=True, blank=True, db_index=True)
    period_to = models.DateField(null=True, blank=True, db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    bank_ref_no = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    bsr_code = models.CharField(max_length=20, null=True, blank=True, db_index=True)

    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    deposited_on = models.DateField(null=True, blank=True, db_index=True)
    deposited_at = models.DateTimeField(null=True, blank=True)
    deposited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_challans_deposited",
    )

    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_challans_created",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "tax_type", "challan_no"),
                name="uq_pur_stat_challan_scope_type_no",
            ),
            models.CheckConstraint(check=Q(amount__gte=0), name="ck_pur_stat_challan_amount_nonneg"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "tax_type", "status"], name="ix_pur_stat_challan_scope"),
            models.Index(fields=["entity", "entityfinid", "challan_date"], name="ix_pur_stat_challan_date"),
        ]

    def __str__(self) -> str:
        return f"{self.tax_type}:{self.challan_no}"


class PurchaseStatutoryChallanLine(TrackingModel):
    challan = models.ForeignKey(PurchaseStatutoryChallan, on_delete=models.CASCADE, related_name="lines")
    header = models.ForeignKey(PurchaseInvoiceHeader, on_delete=models.PROTECT, related_name="statutory_challan_lines")
    section = models.ForeignKey(
        "withholding.WithholdingSection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_challan_lines",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("challan", "header"), name="uq_pur_stat_challan_line_challan_header"),
            models.CheckConstraint(check=Q(amount__gt=0), name="ck_pur_stat_challan_line_amount_pos"),
        ]
        indexes = [
            models.Index(fields=["challan"], name="ix_pur_stcl_challan"),
            models.Index(fields=["header"], name="ix_pur_stcl_header"),
        ]

    def __str__(self) -> str:
        return f"ChallanLine({self.challan_id}, {self.header_id}, {self.amount})"


class PurchaseStatutoryReturn(TrackingModel):
    class TaxType(models.TextChoices):
        IT_TDS = "IT_TDS", "Income-tax TDS"
        GST_TDS = "GST_TDS", "GST-TDS"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        FILED = 2, "Filed"
        REVISED = 3, "Revised"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    tax_type = models.CharField(max_length=10, choices=TaxType.choices, db_index=True)
    return_code = models.CharField(max_length=30, db_index=True)  # e.g. 26Q / 27Q / GSTR7
    period_from = models.DateField(db_index=True)
    period_to = models.DateField(db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    filed_on = models.DateField(null=True, blank=True, db_index=True)
    filed_at = models.DateTimeField(null=True, blank=True)
    filed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_returns_filed",
    )
    ack_no = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_returns_created",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(amount__gte=0), name="ck_pur_stat_return_amount_nonneg"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "tax_type", "status"], name="ix_pur_stat_return_scope"),
            models.Index(fields=["entity", "entityfinid", "period_from", "period_to"], name="ix_pur_stat_return_period"),
        ]

    def __str__(self) -> str:
        return f"{self.tax_type}:{self.return_code}:{self.period_from}-{self.period_to}"


class PurchaseStatutoryReturnLine(TrackingModel):
    filing = models.ForeignKey(PurchaseStatutoryReturn, on_delete=models.CASCADE, related_name="lines")
    header = models.ForeignKey(PurchaseInvoiceHeader, on_delete=models.PROTECT, related_name="statutory_return_lines")
    challan = models.ForeignKey(
        PurchaseStatutoryChallan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="return_lines",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("filing", "header"), name="uq_pur_stat_return_line_filing_header"),
            models.CheckConstraint(check=Q(amount__gt=0), name="ck_pur_stat_return_line_amount_pos"),
        ]
        indexes = [
            models.Index(fields=["filing"], name="ix_pur_stat_return_line_filing"),
            models.Index(fields=["header"], name="ix_pur_stat_return_line_header"),
        ]

    def __str__(self) -> str:
        return f"ReturnLine({self.filing_id}, {self.header_id}, {self.amount})"
