from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class SalesEInvoiceStatus(models.IntegerChoices):
    NOT_APPLICABLE = 0, "Not Applicable"
    PENDING = 1, "Pending"
    GENERATED = 2, "Generated"
    CANCELLED = 3, "Cancelled"
    FAILED = 9, "Failed"


class SalesEWayStatus(models.IntegerChoices):
    NOT_APPLICABLE = 0, "Not Applicable"
    PENDING = 1, "Pending"
    GENERATED = 2, "Generated"
    CANCELLED = 3, "Cancelled"
    FAILED = 9, "Failed"


class NICEnvironment(models.IntegerChoices):
    SANDBOX = 1, "Sandbox"
    PRODUCTION = 2, "Production"


class SalesEInvoice(models.Model):
    """
    One-to-one compliance artifact for SalesInvoiceHeader (IRP / e-Invoice).
    Stores IRN/Ack and signed payloads + audit fields.
    """
    invoice = models.OneToOneField(
        "sales.SalesInvoiceHeader",
        on_delete=models.CASCADE,
        related_name="einvoice_artifact",          # ✅ changed
        related_query_name="einvoice_artifact",    # ✅ changed
        db_index=True,
    )

    status = models.PositiveSmallIntegerField(
        choices=SalesEInvoiceStatus.choices,
        default=SalesEInvoiceStatus.PENDING,
        db_index=True,
    )

    # ---- IRP response data ----
    irn = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    ack_no = models.CharField(max_length=64, null=True, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)

    signed_invoice = models.TextField(null=True, blank=True)     # large JSON string (signed)
    signed_qr_code = models.TextField(null=True, blank=True)     # base64/text

    # Optional fields often returned / needed later
    ewb_no = models.CharField(max_length=32, null=True, blank=True)  # IRP may generate EWB too
    ewb_date = models.DateTimeField(null=True, blank=True)
    ewb_valid_upto = models.DateTimeField(null=True, blank=True)

    # ---- request/response snapshots (debug/audit) ----
    last_request_json = models.JSONField(null=True, blank=True)
    last_response_json = models.JSONField(null=True, blank=True)

    # ---- failure info ----
    last_error_code = models.CharField(max_length=64, null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)

    # ---- idempotency / tracing ----
    attempt_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    # ---- audit ----
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_einvoice_created"
    )
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_einvoice_updated"
    )

    class Meta:
        db_table = "sales_einvoice"
        indexes = [
            models.Index(fields=["status"], name="idx_sales_einv_status"),
            models.Index(fields=["irn"], name="idx_sales_einv_irn"),
            models.Index(fields=["created_at"], name="idx_sales_einv_created"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["invoice"], name="uq_sales_einv_invoice"),
        ]

    def __str__(self) -> str:
        return f"SalesEInvoice(invoice_id={self.invoice_id}, status={self.status}, irn={self.irn})"


class SalesEInvoiceCancel(models.Model):
    """
    Stores cancellation history (IRN cancellation is time-bound).
    Keep separate rows for audit and for multiple attempts.
    """
    einvoice = models.ForeignKey(
        SalesEInvoice, on_delete=models.CASCADE, related_name="cancellations", db_index=True
    )

    cancel_reason_code = models.CharField(max_length=8)  # NIC uses reason codes (string/int)
    cancel_remarks = models.CharField(max_length=255, null=True, blank=True)

    cancelled_at = models.DateTimeField(default=timezone.now)
    irp_cancel_date = models.DateTimeField(null=True, blank=True)

    last_request_json = models.JSONField(null=True, blank=True)
    last_response_json = models.JSONField(null=True, blank=True)

    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_einvoice_cancel_created"
    )

    class Meta:
        db_table = "sales_einvoice_cancel"
        indexes = [
            models.Index(fields=["cancelled_at"], name="idx_sales_einv_can_dt"),
            models.Index(fields=["einvoice"], name="idx_sales_einv_can_einv"),
        ]

    def __str__(self) -> str:
        return f"SalesEInvoiceCancel(einvoice_id={self.einvoice_id}, at={self.cancelled_at})"


class SalesEWayBill(models.Model):
    """
    E-Way Bill compliance artifact.
    If you generate EWB from IRP, you can store it here too (and optionally mirror in SalesEInvoice).
    """
    invoice = models.OneToOneField(
        "sales.SalesInvoiceHeader",
        on_delete=models.CASCADE,
        related_name="eway_artifact",              # ✅ changed
        related_query_name="eway_artifact",        # ✅ changed
        db_index=True,
    )

    status = models.PositiveSmallIntegerField(
        choices=SalesEWayStatus.choices,
        default=SalesEWayStatus.PENDING,
        db_index=True,
    )

    ewb_no = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    ewb_date = models.DateTimeField(null=True, blank=True)
    valid_upto = models.DateTimeField(null=True, blank=True)

    # Transport details (some are mandatory for EWB)
    transporter_id = models.CharField(max_length=32, null=True, blank=True)
    transporter_name = models.CharField(max_length=128, null=True, blank=True)
    transport_mode = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-Road,2-Rail,3-Air,4-Ship
    distance_km = models.PositiveIntegerField(null=True, blank=True)

    vehicle_no = models.CharField(max_length=32, null=True, blank=True)
    vehicle_type = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-Regular, 2-ODC
    doc_no = models.CharField(max_length=32, null=True, blank=True)
    doc_date = models.DateField(null=True, blank=True)

    # ---- request/response snapshots ----
    last_request_json = models.JSONField(null=True, blank=True)
    last_response_json = models.JSONField(null=True, blank=True)

    last_error_code = models.CharField(max_length=64, null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)

    attempt_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_eway_created"
    )
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_eway_updated"
    )

    class Meta:
        db_table = "sales_ewaybill"
        indexes = [
            models.Index(fields=["status"], name="idx_sales_eway_status"),
            models.Index(fields=["ewb_no"], name="idx_sales_eway_no"),
            models.Index(fields=["created_at"], name="idx_sales_eway_created"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["invoice"], name="uq_sales_eway_invoice"),
        ]

    def __str__(self) -> str:
        return f"SalesEWayBill(invoice_id={self.invoice_id}, status={self.status}, ewb_no={self.ewb_no})"


class SalesEWayBillCancel(models.Model):
    """
    Cancellation audit trail for EWB.
    """
    eway = models.ForeignKey(
        SalesEWayBill, on_delete=models.CASCADE, related_name="cancellations", db_index=True
    )

    cancel_reason_code = models.CharField(max_length=8)
    cancel_remarks = models.CharField(max_length=255, null=True, blank=True)

    cancelled_at = models.DateTimeField(default=timezone.now)
    portal_cancel_date = models.DateTimeField(null=True, blank=True)

    last_request_json = models.JSONField(null=True, blank=True)
    last_response_json = models.JSONField(null=True, blank=True)

    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_eway_cancel_created"
    )

    class Meta:
        db_table = "sales_ewaybill_cancel"
        indexes = [
            models.Index(fields=["cancelled_at"], name="idx_sales_eway_can_dt"),
            models.Index(fields=["eway"], name="idx_sales_eway_can_eway"),
        ]

    def __str__(self) -> str:
        return f"SalesEWayBillCancel(eway_id={self.eway_id}, at={self.cancelled_at})"


class SalesNICCredential(models.Model):
    """
    Entity-level NIC credential mapping (environment-aware).
    Keep this separate and admin-managed like your PayrollComponentGlobal approach.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", null=True, blank=True, on_delete=models.CASCADE, db_index=True)

    environment = models.PositiveSmallIntegerField(choices=NICEnvironment.choices, default=NICEnvironment.SANDBOX)

    # Depending on your gateway choice, you may store:
    # - ASP credentials (GSP/ASP)
    # - NIC direct credentials
    # We'll keep generic fields. Secrets should ideally be encrypted at rest.
    username = models.CharField(max_length=128)
    password = models.CharField(max_length=256)
    client_id = models.CharField(max_length=128, null=True, blank=True)
    client_secret = models.CharField(max_length=256, null=True, blank=True)
    gstin = models.CharField(max_length=15, db_index=True)

    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_nic_credential"
        indexes = [
            models.Index(fields=["entity", "subentity"], name="idx_sales_nic_scope"),
            models.Index(fields=["gstin"], name="idx_sales_nic_gstin"),
            models.Index(fields=["is_active"], name="idx_sales_nic_active"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "environment"],
                name="uq_sales_nic_scope_env",
            )
        ]

    def __str__(self) -> str:
        return f"SalesNICCredential(entity_id={self.entity_id}, subentity_id={self.subentity_id}, env={self.environment})"