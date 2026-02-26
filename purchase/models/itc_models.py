# purchase/models/itc_models.py
from __future__ import annotations
from decimal import Decimal
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from .base import TrackingModel
from decimal import Decimal

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


from purchase.models import PurchaseInvoiceHeader

User = settings.AUTH_USER_MODEL


class PurchaseItcAction(TrackingModel):
    """
    Audit table for ITC claim status changes.
    This is your truth for 'who/when/why/how much'.
    """

    class ActionType(models.TextChoices):
        CLAIM = "CLAIM", "Claim ITC"
        REVERSE = "REVERSE", "Reverse ITC"
        BLOCK = "BLOCK", "Block ITC"
        UNBLOCK = "UNBLOCK", "Unblock (back to pending)"
        SET_PENDING = "SET_PENDING", "Set Pending"
        ADJUST = "ADJUST", "Adjustment"

    header = models.ForeignKey(PurchaseInvoiceHeader, on_delete=models.CASCADE, related_name="itc_actions")

    action_type = models.CharField(max_length=20, choices=ActionType.choices)

    # Period in which ITC is claimed/reversed in returns (GSTR-3B)
    period = models.CharField(max_length=7, null=True, blank=True)  # "YYYY-MM"

    # Previous/current status snapshot (for easy audits)
    from_status = models.IntegerField(null=True, blank=True)  # PurchaseInvoiceHeader.ItcClaimStatus
    to_status = models.IntegerField(null=True, blank=True)    # PurchaseInvoiceHeader.ItcClaimStatus

    # Amounts impacted (if partial claim/reversal is supported later)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cess = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    reason = models.CharField(max_length=300, null=True, blank=True)
    notes = models.CharField(max_length=1000, null=True, blank=True)

    # Evidence pointers (optional)
    gstr2b_batch = models.ForeignKey("purchase.Gstr2bImportBatch", null=True, blank=True, on_delete=models.SET_NULL)
    attachment = models.ForeignKey("purchase.PurchaseAttachment", null=True, blank=True, on_delete=models.SET_NULL)

    acted_at = models.DateTimeField(default=timezone.now)
    acted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_itc_actions")

    class Meta:
        indexes = [
            models.Index(fields=["header", "acted_at"], name="ix_pur_itc_action_header_date"),
            models.Index(fields=["period"], name="ix_pur_itc_action_period"),
            models.Index(fields=["action_type"], name="ix_pur_itc_action_type"),
        ]
        constraints = [
            models.CheckConstraint(
                name="ck_pur_itc_action_nonneg",
                condition=Q(igst__gte=0) & Q(cgst__gte=0) & Q(sgst__gte=0) & Q(cess__gte=0),
            ),
        ]

    def __str__(self):
        return f"ITC {self.action_type} for {self.header_id} ({self.period})"
