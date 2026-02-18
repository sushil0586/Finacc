from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


User = settings.AUTH_USER_MODEL


class TrackingModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DocumentType(TrackingModel):
    """
    Generic document type master (works across modules):
      - Purchase Invoice, Purchase CN, Sales Invoice, Receipt Voucher, etc.
    doc_key is stable key used in code and APIs.
    """
    module = models.CharField(max_length=50,null=True, blank=True)          # e.g. "purchase", "sales", "accounts"
    name = models.CharField(max_length=255,null=True, blank=True)           # e.g. "Purchase Tax Invoice"
    doc_key = models.CharField(max_length=50,null=True, blank=True)         # e.g. "PURCHASE_TAX_INVOICE"
    default_code = models.CharField(max_length=20,null=True, blank=True)    # e.g. "PINV"

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("module", "doc_key"), name="uq_doc_type_module_key"),
        ]
        indexes = [
            models.Index(fields=["module", "doc_key"], name="ix_doc_type_module_key"),
        ]

    def __str__(self):
        return f"{self.module}:{self.doc_key}"


class DocumentNumberSeries(TrackingModel):
    """
    Per-tenant settings + counter.
    Thread-safe increments must happen in a transaction with select_for_update().
    """

    RESET_CHOICES = [
        ("none", "Do not reset"),
        ("monthly", "Reset every month"),
        ("yearly", "Reset every year"),
    ]

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)

    # Visible series code (can be overridden per customer)
    doc_code = models.CharField(max_length=20)  # e.g. PINV/PCN/PDN

    prefix = models.CharField(max_length=20, default="", blank=True)
    suffix = models.CharField(max_length=20, default="", blank=True)

    starting_number = models.PositiveIntegerField(default=1)
    current_number = models.PositiveIntegerField(default=1)
    number_padding = models.PositiveSmallIntegerField(default=0)

    include_year = models.BooleanField(default=False)
    include_month = models.BooleanField(default=False)
    separator = models.CharField(max_length=5, default="-")

    reset_frequency = models.CharField(max_length=10, choices=RESET_CHOICES, default="none")
    last_reset_date = models.DateField(null=True, blank=True)

    # Optional custom formatting
    custom_format = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Placeholders: {prefix},{year},{month},{number},{suffix},{doc_code}",
    )

    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "doc_type", "doc_code"),
                name="uq_doc_series_scope_type_code",
            ),
            models.CheckConstraint(name="ck_doc_series_start_gte_1", condition=Q(starting_number__gte=1)),
            models.CheckConstraint(name="ck_doc_series_current_gte_1", condition=Q(current_number__gte=1)),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_doc_series_scope"),
            models.Index(fields=["doc_type", "doc_code"], name="ix_doc_series_type_code"),
        ]

    def __str__(self):
        return f"Series({self.entity_id},{self.entityfinid_id},{self.subentity_id}) {self.doc_type_id}/{self.doc_code}"
