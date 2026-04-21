from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

from catalog.models import Product, ProductBarcode, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, Godown, SubEntity


class RetailConfig(models.Model):
    class BillingMode(models.TextChoices):
        INVOICE_PER_TICKET = "invoice_per_ticket", "Invoice Per Ticket"
        DAILY_SUMMARY = "daily_summary", "Daily Summary"
        WEEKLY_SUMMARY = "weekly_summary", "Weekly Summary"
        MANUAL_SUMMARY = "manual_summary", "Manual Summary"

    class PostingMode(models.TextChoices):
        REAL_TIME = "real_time", "Real Time"
        ON_CLOSE = "on_close", "On Close"
        MANUAL = "manual", "Manual"

    class CustomerMode(models.TextChoices):
        WALK_IN_ONLY = "walk_in_only", "Walk-In Only"
        CUSTOMER_OPTIONAL = "customer_optional", "Customer Optional"
        CUSTOMER_REQUIRED = "customer_required", "Customer Required"

    class WalkInCaptureMode(models.TextChoices):
        NONE = "none", "None"
        OPTIONAL = "optional", "Optional"
        RECOMMENDED = "recommended", "Recommended"
        REQUIRED_FOR_INVOICE = "required_for_invoice", "Required For Invoice"

    class AutoCreateCustomerMode(models.TextChoices):
        NEVER = "never", "Never"
        MANUAL_ONLY = "manual_only", "Manual Only"
        WHEN_MOBILE_PRESENT = "when_mobile_present", "When Mobile Present"
        WHEN_GSTIN_PRESENT = "when_gstin_present", "When GSTIN Present"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="retail_configs")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="retail_configs")
    billing_mode = models.CharField(max_length=30, choices=BillingMode.choices, default=BillingMode.INVOICE_PER_TICKET)
    posting_mode = models.CharField(max_length=20, choices=PostingMode.choices, default=PostingMode.REAL_TIME)
    customer_mode = models.CharField(max_length=30, choices=CustomerMode.choices, default=CustomerMode.CUSTOMER_OPTIONAL)
    walk_in_capture_mode = models.CharField(max_length=30, choices=WalkInCaptureMode.choices, default=WalkInCaptureMode.OPTIONAL)
    auto_create_customer_mode = models.CharField(max_length=30, choices=AutoCreateCustomerMode.choices, default=AutoCreateCustomerMode.NEVER)
    default_walk_in_customer = models.ForeignKey("financial.account", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    default_location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    allow_negative_stock = models.BooleanField(default=False)
    allow_hold_resume = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_retail_config_entity_subentity"),
        ]

    def __str__(self) -> str:
        return f"RetailConfig(entity={self.entity_id}, subentity={self.subentity_id})"


class RetailTicket(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        HELD = "HELD", "Held"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class ExecutionStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        READY = "READY", "Ready"
        GENERATED = "GENERATED", "Generated"
        POSTED = "POSTED", "Posted"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    ticket_no = models.CharField(max_length=50, blank=True, db_index=True)
    bill_date = models.DateField(default=timezone.localdate, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    customer = models.ForeignKey("financial.account", on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    customer_email = models.CharField(max_length=120, blank=True, default="")
    customer_gstin = models.CharField(max_length=30, blank=True, default="")
    address1 = models.CharField(max_length=255, blank=True, default="")
    address2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state_code = models.CharField(max_length=20, blank=True, default="")
    pincode = models.CharField(max_length=12, blank=True, default="")

    narration = models.CharField(max_length=500, blank=True, default="")
    line_count = models.PositiveIntegerField(default=0)
    total_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    total_free_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    total_issue_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    gross_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    discount_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    taxable_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    billing_mode_snapshot = models.CharField(max_length=30, choices=RetailConfig.BillingMode.choices, default=RetailConfig.BillingMode.INVOICE_PER_TICKET)
    posting_mode_snapshot = models.CharField(max_length=20, choices=RetailConfig.PostingMode.choices, default=RetailConfig.PostingMode.REAL_TIME)
    billing_execution_status = models.CharField(max_length=20, choices=ExecutionStatus.choices, default=ExecutionStatus.PENDING, db_index=True)
    posting_execution_status = models.CharField(max_length=20, choices=ExecutionStatus.choices, default=ExecutionStatus.PENDING, db_index=True)
    billing_reference = models.CharField(max_length=80, blank=True, default="")
    posting_reference = models.CharField(max_length=80, blank=True, default="")
    session = models.ForeignKey("retail.RetailSession", on_delete=models.PROTECT, null=True, blank=True, related_name="tickets")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completed_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-bill_date", "-id"]
        indexes = [
            models.Index(fields=["entity", "bill_date"], name="ix_retail_ticket_entity_date"),
            models.Index(fields=["entity", "ticket_no"], name="ix_retail_ticket_entity_no"),
        ]

    def __str__(self) -> str:
        return self.ticket_no or f"Retail Ticket #{self.pk or 'new'}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.ticket_no:
            self.ticket_no = f"RT-{self.entity_id}-{self.pk}"
            super().save(update_fields=["ticket_no"])


class RetailSession(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    session_code = models.CharField(max_length=50, blank=True, db_index=True)
    session_date = models.DateField(default=timezone.localdate, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    opening_note = models.CharField(max_length=200, blank=True, default="")
    closing_note = models.CharField(max_length=200, blank=True, default="")
    opened_at = models.DateTimeField(default=timezone.now, db_index=True)
    opened_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-opened_at", "-id"]
        indexes = [
            models.Index(fields=["entity", "session_date"], name="ix_retail_session_entity_date"),
        ]

    def __str__(self) -> str:
        return self.session_code or f"Retail Session #{self.pk or 'new'}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.session_code:
            self.session_code = f"RS-{self.entity_id}-{self.pk}"
            super().save(update_fields=["session_code"])


class RetailCloseBatch(models.Model):
    class TriggerMode(models.TextChoices):
        SESSION_CLOSE = "SESSION_CLOSE", "Session Close"

    session = models.OneToOneField("retail.RetailSession", on_delete=models.PROTECT, related_name="close_batch")
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    batch_code = models.CharField(max_length=50, blank=True, db_index=True)
    trigger_mode = models.CharField(max_length=20, choices=TriggerMode.choices, default=TriggerMode.SESSION_CLOSE)
    session_date = models.DateField(default=timezone.localdate, db_index=True)
    completed_ticket_count = models.PositiveIntegerField(default=0)
    billing_ready_count = models.PositiveIntegerField(default=0)
    billing_pending_count = models.PositiveIntegerField(default=0)
    posting_ready_count = models.PositiveIntegerField(default=0)
    posting_pending_count = models.PositiveIntegerField(default=0)
    gross_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    taxable_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["entity", "session_date"], name="ix_rtl_clsbch_ent_dt"),
        ]

    def __str__(self) -> str:
        return self.batch_code or f"Retail Close Batch #{self.pk or 'new'}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.batch_code:
            self.batch_code = f"RCB-{self.entity_id}-{self.pk}"
            super().save(update_fields=["batch_code"])


class RetailCloseBatchTicket(models.Model):
    batch = models.ForeignKey("retail.RetailCloseBatch", on_delete=models.CASCADE, related_name="ticket_links")
    ticket = models.ForeignKey("retail.RetailTicket", on_delete=models.PROTECT, related_name="close_batch_links")
    billing_status_snapshot = models.CharField(max_length=20, choices=RetailTicket.ExecutionStatus.choices, default=RetailTicket.ExecutionStatus.PENDING)
    posting_status_snapshot = models.CharField(max_length=20, choices=RetailTicket.ExecutionStatus.choices, default=RetailTicket.ExecutionStatus.PENDING)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["ticket_id"]
        constraints = [
            models.UniqueConstraint(fields=("batch", "ticket"), name="uq_retail_close_batch_ticket"),
        ]

    def __str__(self) -> str:
        return f"RetailCloseBatchTicket(batch={self.batch_id}, ticket={self.ticket_id})"


class RetailTicketLine(models.Model):
    class LineSource(models.TextChoices):
        SCAN = "SCAN", "Scan"
        MANUAL = "MANUAL", "Manual"

    ticket = models.ForeignKey(RetailTicket, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField(default=1)
    line_source = models.CharField(max_length=10, choices=LineSource.choices, default=LineSource.SCAN)

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    barcode = models.ForeignKey(ProductBarcode, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    scanned_barcode = models.CharField(max_length=50, blank=True, default="")
    product_desc_snapshot = models.CharField(max_length=255, blank=True, default="")
    product_hsn_snapshot = models.CharField(max_length=30, blank=True, default="")
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    uom_code_snapshot = models.CharField(max_length=20, blank=True, default="")
    pack_size_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    free_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    stock_issue_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    rate = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    gross_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    discount_percent = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("0.0000"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    taxable_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    promotion_id_snapshot = models.IntegerField(null=True, blank=True)
    promotion_code_snapshot = models.CharField(max_length=50, blank=True, default="")
    gst_snapshot = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["line_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=("ticket", "line_no"), name="uq_retail_ticket_line_no"),
        ]

    def __str__(self) -> str:
        return f"RetailTicketLine(ticket={self.ticket_id}, line={self.line_no})"
