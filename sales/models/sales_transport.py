from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SalesInvoiceTransportSnapshot(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        EWAY_PREFILL = "eway_prefill", "E-Way Prefill"
        COPIED = "copied", "Copied"

    invoice = models.OneToOneField(
        "sales.SalesInvoiceHeader",
        on_delete=models.CASCADE,
        related_name="transport_snapshot",
        related_query_name="transport_snapshot",
        db_index=True,
    )

    transporter_id = models.CharField(max_length=32, blank=True, default="")
    transporter_name = models.CharField(max_length=128, blank=True, default="")
    transport_mode = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-Road,2-Rail,3-Air,4-Ship
    vehicle_no = models.CharField(max_length=32, blank=True, default="")
    vehicle_type = models.CharField(max_length=1, blank=True, default="")  # R/O
    lr_gr_no = models.CharField(max_length=32, blank=True, default="")
    lr_gr_date = models.DateField(null=True, blank=True)
    distance_km = models.PositiveIntegerField(null=True, blank=True)

    dispatch_through = models.CharField(max_length=64, blank=True, default="")
    driver_name = models.CharField(max_length=128, blank=True, default="")
    driver_mobile = models.CharField(max_length=20, blank=True, default="")
    remarks = models.CharField(max_length=255, blank=True, default="")

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_transport_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_transport_updated",
    )

    class Meta:
        db_table = "sales_invoice_transport_snapshot"
        indexes = [
            models.Index(fields=["transport_mode"], name="idx_sales_trn_mode"),
            models.Index(fields=["vehicle_no"], name="idx_sales_trn_vehicle"),
            models.Index(fields=["lr_gr_no"], name="idx_sales_trn_lrgr"),
            models.Index(fields=["source"], name="idx_sales_trn_source"),
        ]

    def __str__(self) -> str:
        return f"SalesInvoiceTransportSnapshot(invoice_id={self.invoice_id})"
