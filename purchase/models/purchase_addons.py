from __future__ import annotations
from django.db import models
from django.db.models import Q
from .base import TrackingModel
from purchase.models.purchase_core import PurchaseInvoiceHeader
from django.conf import settings
User = settings.AUTH_USER_MODEL
from decimal import Decimal

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


class PurchaseChargeLine(TrackingModel):
    """
    Header-level charges: freight, packing, insurance, other charges.
    Can be taxable/non-taxable and can carry GST if needed.
    """
    header = models.ForeignKey(PurchaseInvoiceHeader, related_name="charges", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField()

    description = models.CharField(max_length=200)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO2)
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("header", "line_no"), name="uq_purchase_charge_header_lineno"),
            models.CheckConstraint(
                name="ck_purchase_charge_nonneg",
                check=(Q(taxable_value__gte=0) & Q(gst_rate__gte=0) & Q(gst_rate__lte=100) &
                       Q(cgst_amount__gte=0) & Q(sgst_amount__gte=0) & Q(igst_amount__gte=0) &
                       Q(total_value__gte=0)),
            ),
        ]
        indexes = [
            models.Index(fields=["header"], name="ix_purchase_charge_header"),
        ]
        

class PurchaseAttachment(TrackingModel):
    """
    Vendor bill PDF/image attachments for audit and future OCR.
    """
    header = models.ForeignKey(PurchaseInvoiceHeader, related_name="attachments", on_delete=models.CASCADE)
    file = models.FileField(upload_to="purchase/attachments/%Y/%m/")
    original_name = models.CharField(max_length=255, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)

    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["header"], name="ix_purchase_attachment_header"),
        ]

    def __str__(self):
        return self.original_name or f"Attachment({self.id})"
