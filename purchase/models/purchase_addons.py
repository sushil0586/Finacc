from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from .base import TrackingModel
from purchase.models.purchase_core import PurchaseInvoiceHeader

User = settings.AUTH_USER_MODEL

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


def _purchase_attachment_upload_to(instance: "PurchaseAttachment", filename: str) -> str:
    ext = os.path.splitext(filename or "")[1]
    stem = slugify(os.path.splitext(filename or "")[0]) or "attachment"
    safe_stem = stem[:24] or "attachment"
    safe_ext = (ext.lower() or "")[:10]
    template = getattr(
        settings,
        "PURCHASE_ATTACHMENT_UPLOAD_TEMPLATE",
        "purchase/e{entity_id}/s{subentity_id}/i{invoice_id}/{year}/{month}/{filename}",
    )
    header = getattr(instance, "header", None)
    entity_id = getattr(header, "entity_id", None) or "global"
    subentity_id = getattr(header, "subentity_id", None)
    invoice_id = getattr(instance, "header_id", None) or getattr(header, "id", None) or "draft"
    today = getattr(instance, "created_at", None) or getattr(header, "created_at", None)
    year = getattr(today, "strftime", lambda fmt: "0000")("%Y")
    month = getattr(today, "strftime", lambda fmt: "00")("%m")
    safe_name = f"{safe_stem}{safe_ext}"
    return template.format(
        app="purchase",
        feature="attachments",
        entity_id=entity_id,
        subentity_id=subentity_id if subentity_id is not None else "root",
        invoice_id=invoice_id,
        year=year,
        month=month,
        filename=safe_name,
    )


class PurchaseChargeType(TrackingModel):
    """
    Master table for Purchase charge types (for dropdown + defaults).
    Scope: per entity (recommended). You can allow global by entity=NULL if you want later.
    """

    # If you want hard-coded base categories, keep them here.
    class BaseCategory(models.TextChoices):
        FREIGHT = "FREIGHT", "Freight"
        PACKING = "PACKING", "Packing"
        INSURANCE = "INSURANCE", "Insurance"
        OTHER = "OTHER", "Other"

    entity = models.ForeignKey(
        "entity.Entity",  # change to your actual Entity app path
        on_delete=models.CASCADE,
        related_name="purchase_charge_types",
        null=True,
        blank=True,
        db_index=True,
    )

    code = models.CharField(max_length=30)           # e.g. FREIGHT_LOCAL, PACKING_STD
    name = models.CharField(max_length=80)           # display name in UI
    base_category = models.CharField(
        max_length=20, choices=BaseCategory.choices, default=BaseCategory.OTHER
    )

    is_active = models.BooleanField(default=True)

    # Defaults pushed to PurchaseChargeLine when selected
    is_service = models.BooleanField(default=True)
    hsn_sac_code_default = models.CharField(max_length=16, blank=True, default="")
    gst_rate_default = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    itc_eligible_default = models.BooleanField(default=True)

    description = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "code"),
                name="uq_purchase_charge_type_entity_code",
            ),
            models.CheckConstraint(
                name="ck_purchase_charge_type_gst_rate_bounds",
                check=Q(gst_rate_default__gte=0) & Q(gst_rate_default__lte=100),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "is_active"], name="ix_charge_type_entity_active"),
            models.Index(fields=["entity", "base_category"], name="ix_charge_type_entity_cat"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class PurchaseChargeLine(TrackingModel):
    """
    Header-level charges: freight, packing, insurance, other.
    These charges can be taxable or non-taxable and may carry GST.
    Stored as independent lines to support multiple charges & different GST rates.
    """

    class ChargeType(models.TextChoices):
        FREIGHT = "FREIGHT", "Freight"
        PACKING = "PACKING", "Packing"
        INSURANCE = "INSURANCE", "Insurance"
        OTHER = "OTHER", "Other"

    class Taxability(models.TextChoices):
        TAXABLE = "TAXABLE", "Taxable"
        EXEMPT = "EXEMPT", "Exempt"
        NIL = "NIL", "Nil Rated"
        NON_GST = "NON_GST", "Non-GST"

    header = models.ForeignKey(
        PurchaseInvoiceHeader,
        related_name="charges",
        on_delete=models.CASCADE,
        db_index=True,
    )
    line_no = models.PositiveIntegerField()

    charge_type = models.CharField(
        max_length=20,
        choices=ChargeType.choices,
        default=ChargeType.OTHER,
    )
    description = models.CharField(max_length=200, blank=True, default="")

    # Classification for reporting / tax summary
    taxability = models.CharField(
        max_length=20,
        choices=Taxability.choices,
        default=Taxability.TAXABLE,
    )
    is_service = models.BooleanField(default=True)
    hsn_sac_code = models.CharField(max_length=16, blank=True, default="")

    # Pricing behavior
    is_rate_inclusive_of_tax = models.BooleanField(default=False)

    # Amounts (server-computed in service; UI may only send taxable + rate)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)

    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    # ITC controls (posting decides Dr Input GST vs expense if blocked)
    itc_eligible = models.BooleanField(default=True)
    itc_block_reason = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("header", "line_no"),
                name="uq_purchase_charge_header_lineno",
            ),

            # non-negative amounts and gst rate bounds
            models.CheckConstraint(
                name="ck_purchase_charge_nonneg",
                check=(
                    Q(taxable_value__gte=0)
                    & Q(gst_rate__gte=0) & Q(gst_rate__lte=100)
                    & Q(cgst_amount__gte=0) & Q(sgst_amount__gte=0) & Q(igst_amount__gte=0)
                    & Q(total_value__gte=0)
                ),
            ),

          

            # If GST is applied (gst_rate > 0 and taxable_value > 0) -> HSN/SAC must be present
            models.CheckConstraint(
                name="ck_purchase_charge_hsn_required_when_gst",
                check=(
                    Q(gst_rate=0)
                    | Q(taxable_value=0)
                    | ~Q(hsn_sac_code="")
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_purchase_charge_header"),
            models.Index(fields=["header", "charge_type"], name="ix_purchase_charge_hdr_type"),
            models.Index(fields=["header", "taxability", "gst_rate"], name="ix_purchase_charge_hdr_tax"),
        ]

    def __str__(self) -> str:
        return f"Charge({self.header_id}, #{self.line_no}, {self.charge_type})"
        

class PurchaseAttachment(TrackingModel):
    """
    Vendor bill PDF/image attachments for audit and future OCR.
    """
    header = models.ForeignKey(PurchaseInvoiceHeader, related_name="attachments", on_delete=models.CASCADE)
    file = models.FileField(upload_to=_purchase_attachment_upload_to, max_length=255)
    original_name = models.CharField(max_length=255, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)

    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["header"], name="ix_purchase_attachment_header"),
        ]

    def __str__(self):
        return self.original_name or f"Attachment({self.id})"
