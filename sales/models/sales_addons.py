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


class SalesAdvanceAdjustment(TrackingModel):
    """
    Captures advance receipts and later adjustments for GSTR-1 table 11.
    """

    class EntryType(models.TextChoices):
        ADVANCE_RECEIPT = "ADVANCE_RECEIPT", "Advance Receipt"
        ADVANCE_ADJUSTMENT = "ADVANCE_ADJUSTMENT", "Advance Adjustment"

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.CASCADE,
        related_name="sales_advance_adjustments",
        db_index=True,
    )
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.CASCADE,
        related_name="sales_advance_adjustments",
        db_index=True,
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sales_advance_adjustments",
        db_index=True,
    )
    voucher_date = models.DateField()
    voucher_number = models.CharField(max_length=50, blank=True, default="")
    customer = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_advance_adjustments",
    )
    customer_name = models.CharField(max_length=255, blank=True, default="")
    customer_gstin = models.CharField(max_length=15, blank=True, default="")
    place_of_supply_state_code = models.CharField(max_length=2, blank=True, default="")
    entry_type = models.CharField(max_length=20, choices=EntryType.choices, default=EntryType.ADVANCE_RECEIPT)
    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    cgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    cess_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    linked_invoice = models.ForeignKey(
        SalesInvoiceHeader,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advance_adjustments",
    )
    original_entry = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="amendments",
    )
    is_amendment = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "sales_advance_adjustment"
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "voucher_date"], name="ix_sales_adv_scope_date"),
            models.Index(fields=["entity", "entityfinid", "is_amendment"], name="ix_sales_adv_scope_amd"),
        ]
        constraints = [
            models.CheckConstraint(
                name="ck_sales_adv_nonneg",
                check=(
                    Q(taxable_value__gte=0)
                    & Q(cgst_amount__gte=0)
                    & Q(sgst_amount__gte=0)
                    & Q(igst_amount__gte=0)
                    & Q(cess_amount__gte=0)
                ),
            ),
            # One active (non-amendment) advance-receipt row per voucher.
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "voucher_number", "entry_type"],
                condition=Q(is_amendment=False, entry_type="ADVANCE_RECEIPT"),
                name="uq_sales_adv_receipt_active_per_voucher",
            ),
            # One active (non-amendment) adjustment row per voucher+invoice.
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "voucher_number", "entry_type", "linked_invoice"],
                condition=Q(
                    is_amendment=False,
                    entry_type="ADVANCE_ADJUSTMENT",
                    linked_invoice__isnull=False,
                ),
                name="uq_sales_adv_adjust_active_per_invoice",
            ),
            # If linked invoice is unavailable, allow only one active fallback row.
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "voucher_number", "entry_type"],
                condition=Q(
                    is_amendment=False,
                    entry_type="ADVANCE_ADJUSTMENT",
                    linked_invoice__isnull=True,
                ),
                name="uq_sales_adv_adjust_active_without_invoice",
            ),
        ]


class SalesEcommerceSupply(TrackingModel):
    """
    Captures ECO-wise supplies for GSTR-1 tables 14/14A/15/15A.
    """

    class SupplySplit(models.TextChoices):
        B2B = "B2B", "B2B"
        B2C = "B2C", "B2C"

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.CASCADE,
        related_name="sales_ecommerce_supplies",
        db_index=True,
    )
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.CASCADE,
        related_name="sales_ecommerce_supplies",
        db_index=True,
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sales_ecommerce_supplies",
        db_index=True,
    )
    header = models.ForeignKey(
        SalesInvoiceHeader,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ecommerce_rows",
    )
    invoice_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=50, blank=True, default="")
    operator_gstin = models.CharField(max_length=15, blank=True, default="")
    supplier_eco_gstin = models.CharField(max_length=15, blank=True, default="")
    supply_split = models.CharField(max_length=3, choices=SupplySplit.choices, default=SupplySplit.B2C)
    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    cgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    cess_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO2)
    original_row = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="amendments",
    )
    is_amendment = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "sales_ecommerce_supply"
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "operator_gstin"], name="ix_sales_eco_scope_op"),
            models.Index(fields=["entity", "entityfinid", "supplier_eco_gstin"], name="ix_sales_eco_scope_sup"),
            models.Index(fields=["entity", "entityfinid", "is_amendment"], name="ix_sales_eco_scope_amd"),
        ]
        constraints = [
            models.CheckConstraint(
                name="ck_sales_eco_nonneg",
                check=(
                    Q(taxable_value__gte=0)
                    & Q(cgst_amount__gte=0)
                    & Q(sgst_amount__gte=0)
                    & Q(igst_amount__gte=0)
                    & Q(cess_amount__gte=0)
                ),
            )
        ]
