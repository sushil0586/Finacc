from __future__ import annotations
from django.db import models
from django.db.models import Q
from .base import TrackingModel
from purchase.models.purchase_core import PurchaseInvoiceHeader
from django.conf import settings
User = settings.AUTH_USER_MODEL
from decimal import Decimal
from geography.models import Country, State, District, City

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")




class Gstr2bImportBatch(TrackingModel):
    """
    One GSTR-2B import event (file/batch).
    Store period and metadata; rows in Gstr2bImportRow.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    entityfinid = models.ForeignKey("entity.entityfinancialyear", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.subentity", on_delete=models.PROTECT, null=True, blank=True)

    period = models.CharField(max_length=7)  # "YYYY-MM"
    source = models.CharField(max_length=50, default="gstr2b")  # future: api/manual/etc.
    reference = models.CharField(max_length=100, null=True, blank=True)  # filename or batch id

    imported_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "period", "reference"),
                name="uq_gstr2b_batch_scope_period_ref",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period"], name="ix_gstr2b_batch_scope_period"),
        ]

    def __str__(self):
        return f"GSTR2B Batch({self.entity_id},{self.period})"


class Gstr2bImportRow(TrackingModel):
    """
    Raw rows from GSTR-2B.
    Used for matching with PurchaseInvoiceHeader.
    """
    batch = models.ForeignKey(Gstr2bImportBatch, related_name="rows", on_delete=models.CASCADE)

    supplier_gstin = models.CharField(max_length=15, null=True, blank=True)
    supplier_name = models.CharField(max_length=200, null=True, blank=True)

    supplier_invoice_number = models.CharField(max_length=50, null=True, blank=True)
    supplier_invoice_date = models.DateField(null=True, blank=True)

    doc_type = models.CharField(max_length=20, null=True, blank=True)  # INV/CN/DN as provided by source

    pos_state = models.ForeignKey(State, null=True, blank=True, on_delete=models.PROTECT)
    is_igst = models.BooleanField(default=False)

    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cess = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    # Matching pointers (optional)
    matched_purchase = models.ForeignKey(
        PurchaseInvoiceHeader, null=True, blank=True, on_delete=models.SET_NULL, related_name="gstr2b_matches"
    )
    match_status = models.CharField(max_length=20, default="NOT_CHECKED")  # quick status for import tool UI

    class Meta:
        indexes = [
            models.Index(fields=["batch"], name="ix_gstr2b_row_batch"),
            models.Index(fields=["supplier_gstin", "supplier_invoice_number"], name="ix_gstr2b_row_gstin_invno"),
            models.Index(fields=["matched_purchase"], name="ix_gstr2b_row_matched_purchase"),
        ]
        constraints = [
            models.CheckConstraint(
                name="ck_gstr2b_row_nonneg",
                check=(
                    Q(taxable_value__gte=0) &
                    Q(igst__gte=0) & Q(cgst__gte=0) & Q(sgst__gte=0) & Q(cess__gte=0)
                ),
            )
        ]

    def __str__(self):
        return f"2BRow({self.supplier_gstin},{self.supplier_invoice_number})"