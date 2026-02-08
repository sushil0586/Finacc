# purchase/models/purchase_core.py
from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from geography.models import Country, State, District, City
from catalog.models import Product,UnitOfMeasure

from .base import TrackingModel

User = settings.AUTH_USER_MODEL

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


class PurchaseInvoiceHeader(TrackingModel):
    # ---- enums (ALL header enums live here) ----
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
        DOMESTIC = 1, "Domestic"
        IMPORT_GOODS = 2, "Import of Goods"
        IMPORT_SERVICES = 3, "Import of Services"
        SEZ = 4, "SEZ Purchase"

    class Taxability(models.IntegerChoices):
        TAXABLE = 1, "Taxable"
        EXEMPT = 2, "Exempt"
        NIL_RATED = 3, "Nil-rated"
        NON_GST = 4, "Non-GST"

    class TaxRegime(models.IntegerChoices):
        INTRA = 1, "Intra-state (CGST+SGST)"
        INTER = 2, "Inter-state (IGST)"

    class Gstr2bMatchStatus(models.IntegerChoices):
        NA = 0, "Not Applicable"
        NOT_CHECKED = 1, "Not Checked"
        MATCHED = 2, "Matched"
        MISMATCHED = 3, "Mismatched"
        NOT_IN_2B = 4, "Not in 2B"
        PARTIAL = 5, "Partial / Needs Review"

    class ItcClaimStatus(models.IntegerChoices):
        NA = 0, "Not Applicable"
        PENDING = 1, "Pending"
        CLAIMED = 2, "Claimed"
        REVERSED = 3, "Reversed"
        BLOCKED = 4, "Blocked (17(5)/etc)"

    # ---- identity ----
    doc_type = models.IntegerField(choices=DocType.choices, default=DocType.TAX_INVOICE)
    bill_date = models.DateField(default=timezone.now)
    doc_code = models.CharField(max_length=10, default="PINV")
    doc_no = models.PositiveIntegerField(null=True, blank=True)
    purchase_number = models.CharField(max_length=50, null=True, blank=True)

    supplier_invoice_number = models.CharField(max_length=50, null=True, blank=True)
    supplier_invoice_date = models.DateField(null=True, blank=True)

    ref_document = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_notes"
    )

    vendor = models.ForeignKey(
        "financial.account", on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_documents"
    )

    # snapshot fields
    vendor_name = models.CharField(max_length=200, null=True, blank=True)
    vendor_gstin = models.CharField(max_length=15, null=True, blank=True)
    vendor_state = models.ForeignKey(
        State, null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_vendor_state_docs"
    )

    supply_category = models.IntegerField(choices=SupplyCategory.choices, default=SupplyCategory.DOMESTIC)
    default_taxability = models.IntegerField(choices=Taxability.choices, default=Taxability.TAXABLE)

    tax_regime = models.IntegerField(choices=TaxRegime.choices, default=TaxRegime.INTRA)
    is_igst = models.BooleanField(default=False)

    supplier_state = models.ForeignKey(
        State, null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_supplier_state_docs"
    )
    place_of_supply_state = models.ForeignKey(
        State, null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_pos_state_docs"
    )

    # ITC + 2B
    is_reverse_charge = models.BooleanField(default=False)
    is_itc_eligible = models.BooleanField(default=True)
    gstr2b_match_status = models.IntegerField(
        choices=Gstr2bMatchStatus.choices, default=Gstr2bMatchStatus.NOT_CHECKED
    )

    itc_claim_status = models.IntegerField(choices=ItcClaimStatus.choices, default=ItcClaimStatus.PENDING)
    itc_claim_period = models.CharField(max_length=7, null=True, blank=True)
    itc_claimed_at = models.DateTimeField(null=True, blank=True)
    itc_block_reason = models.CharField(max_length=200, null=True, blank=True)

    # totals
    total_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_cgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_sgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_igst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_cess = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_gst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    round_off = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT)

    # SaaS scope
    subentity = models.ForeignKey("entity.subentity", on_delete=models.PROTECT, null=True)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, null=True)
    entityfinid = models.ForeignKey("entity.entityfinancialyear", on_delete=models.PROTECT, null=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="created_purchase_documents")

    class Meta:
        constraints = [
            # ✅ strongly recommended for SaaS numbering safety
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "doc_type", "doc_code", "doc_no"),
                name="uq_purchase_doc_entity_fin_type_code_no",
            ),
            # ✅ CN/DN require reference; defined safely using alias below
            # (see DocType alias after class)
            models.CheckConstraint(
                name="ck_purchase_ref_required_for_notes",
                check=(
                    (Q(doc_type=1) & Q(ref_document__isnull=True)) |
                    (Q(doc_type__in=[2, 3]) & Q(ref_document__isnull=False))
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "bill_date"], name="ix_pur_ent_fin_dt"),
        ]

    def __str__(self):
        return self.purchase_number or f"{self.doc_code}-{self.doc_no}"


# ✅ Safe aliases AFTER the model exists (use these in services/serializers if needed)
DocType = PurchaseInvoiceHeader.DocType
Status = PurchaseInvoiceHeader.Status
Taxability = PurchaseInvoiceHeader.Taxability
TaxRegime = PurchaseInvoiceHeader.TaxRegime
Gstr2bMatchStatus = PurchaseInvoiceHeader.Gstr2bMatchStatus
ItcClaimStatus = PurchaseInvoiceHeader.ItcClaimStatus


class PurchaseInvoiceLine(TrackingModel):
    header = models.ForeignKey(PurchaseInvoiceHeader, related_name="lines", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField()

    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    product_desc = models.CharField(max_length=500, null=True, blank=True)
    is_service = models.BooleanField(default=False)
    hsn_sac = models.CharField(max_length=10, null=True, blank=True)

    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True)
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO4)
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    taxability = models.IntegerField(
        choices=PurchaseInvoiceHeader.Taxability.choices,
        default=PurchaseInvoiceHeader.Taxability.TAXABLE
    )

    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    cgst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    sgst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    igst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)

    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cess_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    is_itc_eligible = models.BooleanField(default=True)
    itc_block_reason = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("header", "line_no"), name="uq_purchase_line_header_lineno"),
        ]

    def __str__(self):
        return f"PurchaseLine({self.header_id}, {self.line_no})"


class PurchaseTaxSummary(models.Model):
    header = models.ForeignKey(PurchaseInvoiceHeader, related_name="tax_summaries", on_delete=models.CASCADE)
    taxability = models.IntegerField(
        choices=PurchaseInvoiceHeader.Taxability.choices,
        default=PurchaseInvoiceHeader.Taxability.TAXABLE
    )
    hsn_sac = models.CharField(max_length=10, null=True, blank=True)
    is_service = models.BooleanField(default=False)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    is_reverse_charge = models.BooleanField(default=False)

    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cess_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    itc_eligible_tax = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    itc_ineligible_tax = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("header", "taxability", "hsn_sac", "is_service", "gst_rate", "is_reverse_charge"),
                name="uq_pur_taxsum_bucket",
            ),
        ]

    def __str__(self):
        return f"TaxSummary({self.header_id}, {self.hsn_sac}, {self.gst_rate})"
