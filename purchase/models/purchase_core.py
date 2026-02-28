from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from geography.models import State
from financial.models import account
from catalog.models import Product,UnitOfMeasure

User = settings.AUTH_USER_MODEL

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


class PurchaseInvoiceHeader(models.Model):
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
    posting_date = models.DateField(null=True, blank=True, db_index=True)

    # ✅ NEW: terms for due date derivation
    credit_days = models.PositiveSmallIntegerField(null=True, blank=True)

    # ✅ NEW: due date for AP aging & overdue reports
    due_date = models.DateField(null=True, blank=True, db_index=True)
    doc_code = models.CharField(max_length=10, default="PINV")
    doc_no = models.PositiveIntegerField(null=True, blank=True)
    purchase_number = models.CharField(max_length=50, null=True, blank=True)

    supplier_invoice_number = models.CharField(max_length=50, null=True, blank=True)
    supplier_invoice_date = models.DateField(null=True, blank=True)

    ref_document = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_notes"
    )

    vendor = models.ForeignKey(
       account, on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_documents"
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
    itc_claim_period = models.CharField(max_length=7, null=True, blank=True)  # "YYYY-MM"
    itc_claimed_at = models.DateTimeField(null=True, blank=True)
    itc_block_reason = models.CharField(max_length=200, null=True, blank=True)

    # ✅ default pricing behavior for UI (line can still override)
    is_rate_inclusive_of_tax_default = models.BooleanField(default=False)
    withholding_enabled = models.BooleanField(default=False, db_index=True)

    tds_section = models.ForeignKey(
        "withholding.WithholdingSection",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="purchase_headers",
        limit_choices_to={"tax_type": 1},  # TDS
    )
    tds_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    tds_base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tds_reason = models.CharField(max_length=255, null=True, blank=True)

    # totals (computed, persisted)
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
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, null=True, blank=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="created_purchase_documents")

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "doc_type", "doc_code", "doc_no"),
                name="uq_purchase_doc_entity_fin_type_code_no",
            ),
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
            models.Index(fields=["entity", "entityfinid", "vendor"], name="ix_pur_ent_fin_vendor"),
            models.Index(fields=["entity", "entityfinid", "doc_code", "doc_no"], name="ix_pur_docno_lookup"),
            models.Index(fields=["entity", "entityfinid", "vendor", "due_date"], name="ix_pur_ap_due"),
        ]

    def __str__(self):
        return self.purchase_number or f"{self.doc_code}-{self.doc_no}"


# ✅ Safe aliases AFTER the model exists
DocType = PurchaseInvoiceHeader.DocType
Status = PurchaseInvoiceHeader.Status
Taxability = PurchaseInvoiceHeader.Taxability
TaxRegime = PurchaseInvoiceHeader.TaxRegime
Gstr2bMatchStatus = PurchaseInvoiceHeader.Gstr2bMatchStatus
ItcClaimStatus = PurchaseInvoiceHeader.ItcClaimStatus


class PurchaseInvoiceLine(models.Model):
    class DiscountType(models.TextChoices):
        NONE = "N", "None"
        PERCENT = "P", "Percent"
        AMOUNT = "A", "Amount"

    header = models.ForeignKey(PurchaseInvoiceHeader, related_name="lines", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField()

    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    product_desc = models.CharField(max_length=500, null=True, blank=True)
    is_service = models.BooleanField(default=False)
    hsn_sac = models.CharField(max_length=10, null=True, blank=True)

    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True)

    # ✅ quantities
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO4)        # billable qty
    free_qty = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO4)   # free qty (inventory only)

    # ✅ pricing
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)       # as entered (inclusive or exclusive)
    is_rate_inclusive_of_tax = models.BooleanField(default=False)

    # ✅ discount (client can send; server recomputes and persists final values)
    discount_type = models.CharField(max_length=1, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)   # 0..100
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)  # absolute

    taxability = models.IntegerField(
        choices=PurchaseInvoiceHeader.Taxability.choices,
        default=PurchaseInvoiceHeader.Taxability.TAXABLE
    )

    # ✅ computed monetary base (server authoritative)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    # GST
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    cgst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    sgst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    igst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)

    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    # ✅ cess support (percent + amount). You already had amount; percent makes it complete.
    cess_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    cess_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    # ITC line-level
    is_itc_eligible = models.BooleanField(default=True)
    itc_block_reason = models.CharField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("header", "line_no"), name="uq_purchase_line_header_lineno"),
            # safe sanity checks
            models.CheckConstraint(name="ck_pur_qty_nonneg", check=Q(qty__gte=0)),
            models.CheckConstraint(name="ck_pur_freeqty_nonneg", check=Q(free_qty__gte=0)),
            models.CheckConstraint(name="ck_pur_rate_nonneg", check=Q(rate__gte=0)),
            models.CheckConstraint(name="ck_pur_disc_pct_range", check=Q(discount_percent__gte=0) & Q(discount_percent__lte=100)),
            models.CheckConstraint(name="ck_pur_disc_amt_nonneg", check=Q(discount_amount__gte=0)),
            models.CheckConstraint(name="ck_pur_gst_rate_range", check=Q(gst_rate__gte=0) & Q(gst_rate__lte=100)),
            models.CheckConstraint(name="ck_pur_cess_rate_range", check=Q(cess_percent__gte=0) & Q(cess_percent__lte=100)),
        ]
        indexes = [
            models.Index(fields=["header", "product"], name="ix_pur_line_header_product"),
            models.Index(fields=["header", "hsn_sac"], name="ix_pur_line_header_hsn"),
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
        indexes = [
            models.Index(fields=["header"], name="ix_pur_taxsum_header"),
        ]

    def __str__(self):
        return f"TaxSummary({self.header_id}, {self.hsn_sac}, {self.gst_rate})"
