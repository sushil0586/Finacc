from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q

from core.models.base import TrackingModel
from sales.models.sales_core import SalesInvoiceHeader

ZERO2 = Decimal("0.00")


class SalesChargeType(TrackingModel):
    class BaseCategory(models.TextChoices):
        FREIGHT = "FREIGHT", "Freight"
        PACKING = "PACKING", "Packing"
        INSURANCE = "INSURANCE", "Insurance"
        OTHER = "OTHER", "Other"

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.CASCADE,
        related_name="sales_charge_types",
        null=True,
        blank=True,
        db_index=True,
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=80)
    base_category = models.CharField(max_length=20, choices=BaseCategory.choices, default=BaseCategory.OTHER)
    is_active = models.BooleanField(default=True)

    is_service = models.BooleanField(default=True)
    hsn_sac_code_default = models.CharField(max_length=20, blank=True, default="")
    gst_rate_default = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    description = models.CharField(max_length=200, blank=True, default="")
    revenue_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_charge_type_revenue_accounts",
    )

    class Meta:
        db_table = "sales_charge_type"
        constraints = [
            models.UniqueConstraint(fields=("entity", "code"), name="uq_sales_charge_type_entity_code"),
            models.CheckConstraint(
                name="ck_sales_charge_type_gst_rate_bounds",
                check=Q(gst_rate_default__gte=0) & Q(gst_rate_default__lte=100),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "is_active"], name="ix_schtype_ent_active"),
            models.Index(fields=["entity", "base_category"], name="ix_schtype_ent_cat"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class SalesChargeLine(TrackingModel):
    class ChargeType(models.TextChoices):
        FREIGHT = "FREIGHT", "Freight"
        PACKING = "PACKING", "Packing"
        INSURANCE = "INSURANCE", "Insurance"
        OTHER = "OTHER", "Other"

    header = models.ForeignKey(
        SalesInvoiceHeader,
        related_name="charges",
        on_delete=models.CASCADE,
        db_index=True,
    )
    line_no = models.PositiveIntegerField()

    charge_type = models.CharField(max_length=20, choices=ChargeType.choices, default=ChargeType.OTHER)
    description = models.CharField(max_length=200, blank=True, default="")

    taxability = models.PositiveSmallIntegerField(
        choices=SalesInvoiceHeader.Taxability.choices,
        default=SalesInvoiceHeader.Taxability.TAXABLE,
    )
    is_service = models.BooleanField(default=True)
    hsn_sac_code = models.CharField(max_length=20, blank=True, default="")
    is_rate_inclusive_of_tax = models.BooleanField(default=False)

    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    gst_rate = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO2)
    cgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    total_value = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)

    revenue_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_charge_lines_revenue_accounts",
    )

    class Meta:
        db_table = "sales_charge_line"
        constraints = [
            models.UniqueConstraint(fields=("header", "line_no"), name="uq_sales_charge_header_lineno"),
            models.CheckConstraint(
                name="ck_sales_charge_nonneg",
                check=(
                    Q(taxable_value__gte=0)
                    & Q(gst_rate__gte=0)
                    & Q(gst_rate__lte=100)
                    & Q(cgst_amount__gte=0)
                    & Q(sgst_amount__gte=0)
                    & Q(igst_amount__gte=0)
                    & Q(total_value__gte=0)
                ),
            ),
            models.CheckConstraint(
                name="ck_sales_charge_hsn_required_when_gst",
                check=(Q(gst_rate=0) | Q(taxable_value=0) | ~Q(hsn_sac_code="")),
            ),
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_sales_charge_header"),
            models.Index(fields=["header", "charge_type"], name="ix_sales_charge_hdr_type"),
            models.Index(fields=["header", "taxability", "gst_rate"], name="ix_sales_charge_hdr_tax"),
        ]

    def __str__(self) -> str:
        return f"SalesCharge({self.header_id}, #{self.line_no}, {self.charge_type})"
