from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

try:
    # Django 3.1+
    from django.db.models import JSONField
except ImportError:  # pragma: no cover
    from django.contrib.postgres.fields import JSONField  # old Django

User = settings.AUTH_USER_MODEL

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

    # -------------------------
    # Identity / numbering
    # -------------------------
    doc_type = models.PositiveSmallIntegerField(choices=DocType.choices, default=DocType.TAX_INVOICE)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT)

    bill_date = models.DateField(default=timezone.localdate)
    posting_date = models.DateField(null=True, blank=True)  # derived (default bill_date)

    doc_code = models.CharField(max_length=20)  # e.g. "SINV"
    doc_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    invoice_number = models.CharField(max_length=50, null=True, blank=True,db_index=True)


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
    customer_name = models.CharField(max_length=255)
    customer_gstin = models.CharField(max_length=20, blank=True, default="")
    customer_state_code = models.CharField(max_length=2, blank=True, default="")  # GST state code

    # -------------------------
    # Seller snapshot (optional but recommended)
    # -------------------------
    seller_gstin = models.CharField(max_length=20, blank=True, default="")
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

    ship_to_address1 = models.CharField(max_length=255, blank=True, default="")
    ship_to_address2 = models.CharField(max_length=255, blank=True, default="")
    ship_to_city = models.CharField(max_length=100, blank=True, default="")
    ship_to_state_code = models.CharField(max_length=2, blank=True, default="")
    ship_to_pincode = models.CharField(max_length=10, blank=True, default="")

    # Place of supply
    place_of_supply_state_code = models.CharField(max_length=2, blank=True, default="")

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

    # -------------------------
    # Commercial fields
    # -------------------------
    reference = models.CharField(max_length=255, blank=True, default="")
    remarks = models.TextField(blank=True, default="")

    # -------------------------
    # Audit / lifecycle
    # -------------------------
    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    posted_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)

    confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_confirmed")
    posted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_posted")
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_cancelled")

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
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "bill_date"], name="ix_sales_hdr_billdt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "posting_date"], name="ix_sales_hdr_postdt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "due_date"], name="ix_sales_hdr_duedt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "doc_type", "doc_code", "doc_no"], name="ix_sales_hdr_nav"),
            models.Index(fields=["entity", "entityfinid", "subentity", "status"], name="ix_sales_hdr_status"),
            models.Index(fields=["entity", "entityfinid", "subentity", "customer"], name="ix_sales_hdr_customer"),
            models.Index(fields=["entity", "entityfinid", "subentity", "gst_compliance_mode"], name="ix_sales_hdr_gstmode"),
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


# -------------------------
# E-Invoice Details (IRP / IRN)
# -------------------------
class SalesEInvoiceDetails(EntityScopedModel):
    """
    Stores IRP data + payload snapshots + cancellation/audit info.
    One row per SalesInvoiceHeader.
    """
    class EinvoiceStatus(models.IntegerChoices):
        NOT_APPLICABLE = 0, "Not Applicable"
        PENDING = 1, "Pending"
        GENERATED = 2, "Generated"
        CANCELLED = 3, "Cancelled"
        FAILED = 9, "Failed"

    header = models.OneToOneField(SalesInvoiceHeader, on_delete=models.CASCADE, related_name="einvoice")

    status = models.PositiveSmallIntegerField(choices=EinvoiceStatus.choices, default=EinvoiceStatus.NOT_APPLICABLE)

    irn = models.CharField(max_length=100, blank=True, default="")
    ack_no = models.CharField(max_length=50, blank=True, default="")
    ack_date = models.DateTimeField(null=True, blank=True)

    # Signed content
    signed_invoice = models.TextField(blank=True, default="")
    signed_qr_code = models.TextField(blank=True, default="")

    generated_at = models.DateTimeField(null=True, blank=True)

    # Cancellation (statutory)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason_code = models.CharField(max_length=10, blank=True, default="")
    cancel_remarks = models.CharField(max_length=255, blank=True, default="")

    # Payload snapshots (debugging)
    request_payload = JSONField(null=True, blank=True)
    response_payload = JSONField(null=True, blank=True)
    last_error = JSONField(null=True, blank=True)

    class Meta:
        db_table = "sales_einvoice_details"
        indexes = [
            models.Index(fields=["header"], name="ix_sales_einv_hdr"),
            models.Index(fields=["entity", "entityfinid", "subentity", "status"], name="ix_sales_einv_status"),
            models.Index(fields=["entity", "entityfinid", "subentity", "irn"], name="ix_sales_einv_irn"),
        ]


# -------------------------
# E-Way Bill Details
# -------------------------
class SalesEWayBillDetails(EntityScopedModel):
    """
    Stores EWB Part-A/Part-B like fields + payload snapshots + cancel/update audit.
    One row per SalesInvoiceHeader.
    """
    class EwayStatus(models.IntegerChoices):
        NOT_APPLICABLE = 0, "Not Applicable"
        PENDING = 1, "Pending"
        GENERATED = 2, "Generated"
        CANCELLED = 3, "Cancelled"
        FAILED = 9, "Failed"

    class TransportMode(models.IntegerChoices):
        ROAD = 1, "Road"
        RAIL = 2, "Rail"
        AIR = 3, "Air"
        SHIP = 4, "Ship"

    class VehicleType(models.IntegerChoices):
        REGULAR = 1, "Regular"
        ODC = 2, "ODC"

    header = models.OneToOneField(SalesInvoiceHeader, on_delete=models.CASCADE, related_name="eway")

    status = models.PositiveSmallIntegerField(choices=EwayStatus.choices, default=EwayStatus.NOT_APPLICABLE)

    # If generated via IRP response
    generated_via_irp = models.BooleanField(default=False)

    eway_bill_no = models.CharField(max_length=50, blank=True, default="")
    eway_bill_date = models.DateTimeField(null=True, blank=True)
    valid_upto = models.DateTimeField(null=True, blank=True)

    # Part-A essentials
    transporter_id = models.CharField(max_length=20, blank=True, default="")   # GSTIN/TRANSIN
    transporter_name = models.CharField(max_length=255, blank=True, default="")
    transport_mode = models.PositiveSmallIntegerField(choices=TransportMode.choices, null=True, blank=True)
    distance_km = models.PositiveIntegerField(null=True, blank=True)

    transport_doc_no = models.CharField(max_length=50, blank=True, default="")
    transport_doc_date = models.DateField(null=True, blank=True)

    from_place = models.CharField(max_length=100, blank=True, default="")
    from_pincode = models.CharField(max_length=10, blank=True, default="")

    # Part-B (vehicle)
    vehicle_no = models.CharField(max_length=20, blank=True, default="")
    vehicle_type = models.PositiveSmallIntegerField(choices=VehicleType.choices, null=True, blank=True)

    # Cancellation / updates
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason_code = models.CharField(max_length=10, blank=True, default="")
    cancel_remarks = models.CharField(max_length=255, blank=True, default="")

    last_vehicle_update_at = models.DateTimeField(null=True, blank=True)

    # validity tracking
    original_valid_upto = models.DateTimeField(null=True, blank=True)
    current_valid_upto = models.DateTimeField(null=True, blank=True)

    # extension tracking (latest)
    extension_count = models.PositiveIntegerField(default=0)
    last_extension_at = models.DateTimeField(null=True, blank=True)
    last_extension_reason_code = models.CharField(max_length=10, blank=True, default="")
    last_extension_remarks = models.CharField(max_length=255, blank=True, default="")
    last_extension_from_place = models.CharField(max_length=100, blank=True, default="")
    last_extension_from_pincode = models.CharField(max_length=10, blank=True, default="")

    last_transporter_update_at = models.DateTimeField(null=True, blank=True)

    # Payload snapshots (debugging)
    request_payload = JSONField(null=True, blank=True)
    response_payload = JSONField(null=True, blank=True)
    last_error = JSONField(null=True, blank=True)

    class Meta:
        db_table = "sales_eway_details"
        indexes = [
            models.Index(fields=["header"], name="ix_sales_eway_hdr"),
            models.Index(fields=["entity", "entityfinid", "subentity", "status"], name="ix_sales_eway_status"),
            models.Index(fields=["entity", "entityfinid", "subentity", "eway_bill_no"], name="ix_sales_eway_no"),
        ]


class SalesEWayEvent(EntityScopedModel):
    class EventType(models.IntegerChoices):
        GENERATE = 1, "Generate"
        EXTEND = 2, "Extend Validity"
        VEHICLE_UPDATE = 3, "Vehicle Update"
        TRANSPORTER_UPDATE = 4, "Transporter Update"
        CANCEL = 5, "Cancel"

    eway = models.ForeignKey("sales.SalesEWayBillDetails", on_delete=models.CASCADE, related_name="events")
    event_type = models.PositiveSmallIntegerField(choices=EventType.choices)

    event_at = models.DateTimeField(default=timezone.now)

    # common identifiers for quick search/debug
    eway_bill_no = models.CharField(max_length=50, blank=True, default="")
    reference_no = models.CharField(max_length=50, blank=True, default="")  # if provider returns one

    is_success = models.BooleanField(default=False)
    error_code = models.CharField(max_length=50, blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    request_payload = JSONField(null=True, blank=True)
    response_payload = JSONField(null=True, blank=True)

    class Meta:
        db_table = "sales_eway_event"
        indexes = [
            models.Index(fields=["eway", "event_at"], name="ix_sales_eway_ev_eway_dt"),
            models.Index(fields=["entity", "entityfinid", "subentity", "event_type"], name="ix_sales_eway_ev_type"),
            models.Index(fields=["entity", "entityfinid", "subentity", "eway_bill_no"], name="ix_sales_eway_ev_no"),
        ]

