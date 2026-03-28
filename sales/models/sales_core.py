from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.core.validators import RegexValidator

User = settings.AUTH_USER_MODEL
GSTIN_VALIDATOR = RegexValidator(
    regex=r"^[0-9A-Z]{15}$",
    message="GSTIN must be 15 uppercase alphanumeric characters.",
)

# ✅ Adjust import to your base class
from core.models.base import EntityScopedModel  # change path to your actual base


# -------------------------
# Sales Invoice Header
# -------------------------
class SalesInvoiceHeader(EntityScopedModel):
    """
    Sales Invoice Header (GST-ready)
    - Supports e-invoice (IRP/IRN), e-way, and combined e-invoice+e-way flows
    - Backend controls status transitions
    - Totals are stored but MUST be computed in service
    - E-Invoice and E-Way details stored in separate OneToOne models
    """

    # -------------------------
    # Enums
    # -------------------------
    class DocType(models.IntegerChoices):
        TAX_INVOICE = 1, "Tax Invoice"
        CREDIT_NOTE = 2, "Credit Note"
        DEBIT_NOTE = 3, "Debit Note"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        CONFIRMED = 2, "Confirmed"
        POSTED = 3, "Posted"
        CANCELLED = 9, "Cancelled"

    class SupplyCategory(models.IntegerChoices):
        DOMESTIC_B2B = 1, "Domestic B2B"
        DOMESTIC_B2C = 2, "Domestic B2C"
        EXPORT_WITH_IGST = 3, "Export with IGST"
        EXPORT_WITHOUT_IGST = 4, "Export without IGST (LUT)"
        SEZ_WITH_IGST = 5, "SEZ with IGST"
        SEZ_WITHOUT_IGST = 6, "SEZ without IGST"
        DEEMED_EXPORT = 7, "Deemed Export"

    class Taxability(models.IntegerChoices):
        TAXABLE = 1, "Taxable"
        EXEMPT = 2, "Exempt"
        NIL_RATED = 3, "Nil-rated"
        NON_GST = 4, "Non-GST"

    class TaxRegime(models.IntegerChoices):
        INTRA_STATE = 1, "Intra-state (CGST+SGST)"
        INTER_STATE = 2, "Inter-state (IGST)"

    class GstComplianceMode(models.IntegerChoices):
        NONE = 0, "None"
        EINVOICE_ONLY = 1, "E-Invoice only"
        EWAY_ONLY = 2, "E-Way only"
        EINVOICE_AND_EWAY = 3, "E-Invoice + E-Way"

    class SettlementStatus(models.IntegerChoices):
        OPEN = 1, "Open"
        PARTIAL = 2, "Partial"
        SETTLED = 3, "Settled"

    # -------------------------
    # Identity / numbering
    # -------------------------
    doc_type = models.PositiveSmallIntegerField(choices=DocType.choices, default=DocType.TAX_INVOICE)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT)

    bill_date = models.DateField(default=timezone.localdate)
    posting_date = models.DateField(null=True, blank=True)  # derived (default bill_date)

    doc_code = models.CharField(max_length=20, blank=True, default="")
    doc_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    invoice_number = models.CharField(max_length=50, null=True, blank=True,db_index=True)
    original_invoice = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustment_documents",
    )


    # -------------------------
    # Customer snapshot
    # -------------------------
    customer = models.ForeignKey(
        "financial.account",  # adjust
        on_delete=models.PROTECT,
        related_name="sales_invoices",
        null=True,
        blank=True,
    )
    # New code should use customer_ledger for accounting identity.
    # customer is retained for compatibility with existing modules and forms.
    customer_ledger = models.ForeignKey(
        "financial.Ledger",
        on_delete=models.PROTECT,
        related_name="sales_invoices_by_ledger",
        null=True,
        blank=True,
    )
    customer_name = models.CharField(max_length=255, blank=True, default="")
    customer_gstin = models.CharField(max_length=15, blank=True, default="", validators=[GSTIN_VALIDATOR])
    customer_state_code = models.CharField(max_length=2, blank=True, default="")  # GST state code

    # -------------------------
    # Seller snapshot (optional but recommended)
    # -------------------------
    seller_gstin = models.CharField(max_length=15, blank=True, default="", validators=[GSTIN_VALIDATOR])
    ecm_gstin = models.CharField(max_length=15, blank=True, default="", validators=[GSTIN_VALIDATOR])
    seller_state_code = models.CharField(max_length=2, blank=True, default="")

    # -------------------------
    # Bill-to / Ship-to snapshot (GST + IRP/EWB needed)
    # -------------------------
    is_bill_to_ship_to_same = models.BooleanField(default=True)

    bill_to_address1 = models.CharField(max_length=255, blank=True, default="")
    bill_to_address2 = models.CharField(max_length=255, blank=True, default="")
    bill_to_city = models.CharField(max_length=100, blank=True, default="")
    bill_to_state_code = models.CharField(max_length=2, blank=True, default="")
    bill_to_pincode = models.CharField(max_length=10, blank=True, default="")

    shipping_detail = models.ForeignKey(
        "financial.ShippingDetails",  # adjust app label
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales_invoices",
        db_index=True,
    )

    # Place of supply
    place_of_supply_state_code = models.CharField(max_length=2, blank=True, default="")
    place_of_supply_pincode = models.CharField(max_length=8, blank=True, default="")

    # -------------------------
    # GST classification / regime
    # -------------------------
    supply_category = models.PositiveSmallIntegerField(choices=SupplyCategory.choices, default=SupplyCategory.DOMESTIC_B2B)
    taxability = models.PositiveSmallIntegerField(choices=Taxability.choices, default=Taxability.TAXABLE)

    tax_regime = models.PositiveSmallIntegerField(choices=TaxRegime.choices, default=TaxRegime.INTRA_STATE)
    is_igst = models.BooleanField(default=False)  # derived: seller_state != POS
    is_reverse_charge = models.BooleanField(default=False)  # usually False for sales, keep for completeness

    # -------------------------
    # Credit terms
    # -------------------------
    credit_days = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)  # derived: bill_date + credit_days (>= bill_date)

    # -------------------------
    # Compliance applicability
    # -------------------------
    gst_compliance_mode = models.PositiveSmallIntegerField(
        choices=GstComplianceMode.choices,
        default=GstComplianceMode.NONE
    )
    is_einvoice_applicable = models.BooleanField(default=False)
    is_eway_applicable = models.BooleanField(default=False)
    einvoice_applicable_manual = models.BooleanField(null=True, blank=True)
    eway_applicable_manual = models.BooleanField(null=True, blank=True)
    compliance_override_reason = models.CharField(max_length=255, blank=True, default="")
    compliance_override_at = models.DateTimeField(null=True, blank=True)
    compliance_override_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales_compliance_overridden",
    )


    withholding_enabled = models.BooleanField(default=False, db_index=True)

    tcs_section = models.ForeignKey(
        "withholding.WithholdingSection",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="sales_headers",
        limit_choices_to={"tax_type": 2},  # TCS
    )
    tcs_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    tcs_base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tcs_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tcs_reason = models.CharField(max_length=255, null=True, blank=True)
    tcs_is_reversal = models.BooleanField(default=False)

    # -------------------------
    # Totals (computed in service)
    # -------------------------
    total_taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_cgst = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_sgst = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_igst = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_cess = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    total_discount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_other_charges = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    round_off = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    settled_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    outstanding_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    settlement_status = models.PositiveSmallIntegerField(
        choices=SettlementStatus.choices,
        default=SettlementStatus.OPEN,
    )

    # -------------------------
    # Commercial fields
    # -------------------------
    reference = models.CharField(max_length=255, blank=True, default="")
    remarks = models.TextField(blank=True, default="")
    custom_fields_json = models.JSONField(default=dict, blank=True)

    # -------------------------
    # Audit / lifecycle
    # -------------------------
    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    posted_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    reversed_at = models.DateTimeField(null=True, blank=True, editable=False)

    confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_confirmed")
    posted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_posted")
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_cancelled")
    reversed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_reversed")
    reverse_reason = models.CharField(max_length=255, blank=True, default="")
    is_posting_reversed = models.BooleanField(default=False)

    class Meta:
        db_table = "sales_invoice_header"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "doc_type", "doc_code", "doc_no"],
                name="uq_sales_hdr_scope_docno",
            ),
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "subentity", "doc_type", "doc_code", "invoice_number"],
                name="uq_sales_hdr_scope_invoiceno",
            ),
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "doc_type", "doc_code", "doc_no"],
                condition=Q(subentity__isnull=True, doc_no__isnull=False),
                name="uq_sales_hdr_root_docno",
            ),
            models.UniqueConstraint(
                fields=["entity", "entityfinid", "doc_type", "doc_code", "invoice_number"],
                condition=Q(subentity__isnull=True, invoice_number__isnull=False) & ~Q(invoice_number=""),
                name="uq_sales_hdr_root_invoiceno",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "bill_date"], name="ix_sales_hdr_billdt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "posting_date"], name="ix_sales_hdr_postdt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "due_date"], name="ix_sales_hdr_duedt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "doc_type", "doc_code", "doc_no"], name="ix_sales_hdr_nav"),
            models.Index(fields=["entity", "entityfinid", "subentity", "status"], name="ix_sales_hdr_status"),
            models.Index(fields=["entity", "entityfinid", "subentity", "customer"], name="ix_sales_hdr_customer"),
            models.Index(fields=["entity", "entityfinid", "subentity", "customer_ledger"], name="ix_sales_hdr_cust_ledger"),
            models.Index(fields=["entity", "entityfinid", "subentity", "gst_compliance_mode"], name="ix_sales_hdr_gstmode"),
            models.Index(fields=["entity", "entityfinid", "subentity", "original_invoice"], name="ix_sales_hdr_original"),
            models.Index(fields=["entity", "entityfinid", "subentity", "settlement_status"], name="ix_sales_hdr_settle"),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.get_status_display()})"


# -------------------------
# Sales Invoice Line
# -------------------------
class SalesInvoiceLine(EntityScopedModel):
    class DiscountType(models.IntegerChoices):
        NONE = 0, "None"
        PERCENT = 1, "Percent"
        AMOUNT = 2, "Amount"

    header = models.ForeignKey(SalesInvoiceHeader, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField(default=1)

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="sales_lines")
    productDesc = models.CharField(max_length=200, blank=True, default="")
    uom = models.ForeignKey("catalog.UnitOfMeasure", on_delete=models.PROTECT, related_name="sales_lines")

    hsn_sac_code = models.CharField(max_length=20, blank=True, default="")
    is_service = models.BooleanField(default=False)

    qty = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal("0.000"))
    free_qty = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal("0.000"))

    rate = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    is_rate_inclusive_of_tax = models.BooleanField(default=False)

    discount_type = models.PositiveSmallIntegerField(choices=DiscountType.choices, default=DiscountType.NONE)
    discount_percent = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("0.0000"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    gst_rate = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    cess_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    cess_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # computed (service)
    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    cgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    sgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    igst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # Optional revenue mapping
    sales_account = models.ForeignKey(
        "financial.account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_invoice_lines",
    )

    class Meta:
        db_table = "sales_invoice_line"
        constraints = [
            models.UniqueConstraint(fields=["header", "line_no"], name="uq_sales_line_hdr_lineno"),
            models.CheckConstraint(
                name="ck_sales_line_nonneg_and_rate",
                check=(
                    Q(qty__gte=0)
                    & Q(free_qty__gte=0)
                    & Q(rate__gte=0)
                    & Q(discount_percent__gte=0)
                    & Q(discount_percent__lte=100)
                    & Q(discount_amount__gte=0)
                    & Q(gst_rate__gte=0)
                    & Q(gst_rate__lte=100)
                    & Q(cess_percent__gte=0)
                    & Q(cess_percent__lte=100)
                    & Q(taxable_value__gte=0)
                    & Q(cgst_amount__gte=0)
                    & Q(sgst_amount__gte=0)
                    & Q(igst_amount__gte=0)
                    & Q(cess_amount__gte=0)
                    & Q(line_total__gte=0)
                ),
            ),
            models.CheckConstraint(
                name="ck_sales_line_hsn_required_when_gst",
                check=(Q(gst_rate=0) | Q(taxable_value=0) | ~Q(hsn_sac_code="")),
            ),
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_sales_line_hdr"),
            models.Index(fields=["entity", "entityfinid", "subentity", "product"], name="ix_sales_line_product"),
            models.Index(fields=["entity", "entityfinid", "subentity", "hsn_sac_code"], name="ix_sales_line_hsn"),
        ]

    def __str__(self) -> str:
        return f"Line {self.line_no} - {self.product_id}"


# -------------------------
# Sales Tax Summary (bucket for printing/reporting)
# -------------------------
class SalesTaxSummary(EntityScopedModel):
    header = models.ForeignKey(SalesInvoiceHeader, on_delete=models.CASCADE, related_name="tax_summaries")

    taxability = models.PositiveSmallIntegerField(choices=SalesInvoiceHeader.Taxability.choices)
    hsn_sac_code = models.CharField(max_length=20, blank=True, default="")
    is_service = models.BooleanField(default=False)

    gst_rate = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    is_reverse_charge = models.BooleanField(default=False)

    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    cgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    sgst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    igst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    cess_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "sales_tax_summary"
        constraints = [
            models.UniqueConstraint(
                fields=["header", "taxability", "hsn_sac_code", "is_service", "gst_rate", "is_reverse_charge"],
                name="uq_sales_taxsum_bucket",
            )
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_sales_taxsum_hdr"),
            models.Index(fields=["entity", "entityfinid", "subentity", "gst_rate"], name="ix_sales_taxsum_rate"),
            models.Index(fields=["entity", "entityfinid", "subentity", "hsn_sac_code"], name="ix_sales_taxsum_hsn"),
        ]


class SalesInvoiceShipToSnapshot(models.Model):
    header = models.OneToOneField(
        "sales.SalesInvoiceHeader",
        on_delete=models.CASCADE,
        related_name="shipto_snapshot",
        primary_key=True,
    )

    # store scope ids for quick filtering (no FK)
    entity_id = models.IntegerField(db_index=True,null=True, blank=True,)
    entityfinid_id = models.IntegerField(db_index=True,null=True, blank=True,)
    subentity_id = models.IntegerField(null=True, blank=True, db_index=True)

    address1 = models.CharField(max_length=255, blank=True, default="")
    address2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state_code = models.CharField(max_length=2, blank=True, default="")
    pincode = models.CharField(max_length=10, blank=True, default="")

    full_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    class Meta:
        db_table = "sales_invoice_shipto_snapshot"
        indexes = [
            models.Index(fields=["entity_id", "entityfinid_id", "subentity_id"], name="ix_sales_shipto_scope"),
        ]

