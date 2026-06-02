from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models.base import EntityScopedModel


class GstImportedReturn(EntityScopedModel):
    class ReturnType(models.TextChoices):
        GSTR2B = "GSTR2B", "GSTR-2B"
        GSTR1 = "GSTR1", "GSTR-1"
        GSTR3B = "GSTR3B", "GSTR-3B"

    class Source(models.TextChoices):
        JSON_UPLOAD = "JSON_UPLOAD", "JSON Upload"
        EXCEL_UPLOAD = "EXCEL_UPLOAD", "Excel Upload"
        CSV_UPLOAD = "CSV_UPLOAD", "CSV Upload"
        PORTAL_API = "PORTAL_API", "Portal API"
        MANUAL_ENTRY = "MANUAL_ENTRY", "Manual Entry"
        ADAPTER = "ADAPTER", "Adapter"

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        VALIDATED = "VALIDATED", "Validated"
        PARTIAL = "PARTIAL", "Partial"
        FAILED = "FAILED", "Failed"
        CONSUMED = "CONSUMED", "Consumed"

    gst_registration_gstin = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    return_type = models.CharField(max_length=16, choices=ReturnType.choices)
    return_period = models.CharField(max_length=7, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL_ENTRY)
    reference = models.CharField(max_length=255, null=True, blank=True)
    source_reference = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    checksum = models.CharField(max_length=128, null=True, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)
    normalized_payload_json = models.JSONField(default=dict, blank=True)
    validation_summary_json = models.JSONField(default=dict, blank=True)
    imported_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_imported_returns",
    )
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta(EntityScopedModel.Meta):
        indexes = EntityScopedModel.Meta.indexes + [
            models.Index(
                fields=["entity", "entityfinid", "subentity", "return_type", "return_period"],
                name="ix_gst_imp_scope_type_period",
            ),
            models.Index(
                fields=["gst_registration_gstin", "return_type", "return_period"],
                name="ix_gst_imp_gstin_type_period",
            ),
            models.Index(fields=["status", "return_type", "return_period"], name="ix_gst_imp_status_type_period"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "entity",
                    "entityfinid",
                    "subentity",
                    "return_type",
                    "return_period",
                    "source",
                    "source_reference",
                ],
                condition=models.Q(source_reference__isnull=False),
                name="uq_gst_imp_scope_type_period_source_ref",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.return_type} {self.return_period} ({self.entity_id})"


class GstImportedReturnRow(EntityScopedModel):
    imported_return = models.ForeignKey(
        GstImportedReturn,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_no = models.PositiveIntegerField()
    source_section = models.CharField(max_length=50, null=True, blank=True)
    source_row_reference = models.CharField(max_length=100, null=True, blank=True)
    row_hash = models.CharField(max_length=64, db_index=True)
    doc_type_code = models.CharField(max_length=20, null=True, blank=True)
    counterparty_gstin = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    counterparty_gstin_normalized = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    counterparty_name = models.CharField(max_length=255, null=True, blank=True)
    invoice_number = models.CharField(max_length=50, null=True, blank=True)
    invoice_number_normalized = models.CharField(max_length=80, null=True, blank=True, db_index=True)
    invoice_date = models.DateField(null=True, blank=True)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pos_state_name = models.CharField(max_length=100, null=True, blank=True)
    raw_row_json = models.JSONField(default=dict, blank=True)
    normalized_row_json = models.JSONField(default=dict, blank=True)

    class Meta(EntityScopedModel.Meta):
        indexes = EntityScopedModel.Meta.indexes + [
            models.Index(fields=["imported_return", "row_no"], name="ix_gst_imp_row_return_row"),
            models.Index(
                fields=["imported_return", "counterparty_gstin_normalized", "invoice_number_normalized"],
                name="ix_gst_imp_row_match",
            ),
            models.Index(fields=["imported_return", "doc_type_code"], name="ix_gst_imp_row_doctype"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["imported_return", "row_no"], name="uq_gst_imp_row_return_row"),
            models.UniqueConstraint(fields=["imported_return", "row_hash"], name="uq_gst_imp_row_return_hash"),
        ]

    def __str__(self) -> str:
        return f"{self.imported_return_id}:{self.row_no}"

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "imported_return_id",
                "row_no",
                "source_section",
                "source_row_reference",
                "row_hash",
                "doc_type_code",
                "counterparty_gstin",
                "counterparty_gstin_normalized",
                "counterparty_name",
                "invoice_number",
                "invoice_number_normalized",
                "invoice_date",
                "taxable_value",
                "cgst",
                "sgst",
                "igst",
                "cess",
                "total_amount",
                "pos_state_name",
                "raw_row_json",
                "normalized_row_json",
            ).first()
            current = {
                "imported_return_id": self.imported_return_id,
                "row_no": self.row_no,
                "source_section": self.source_section,
                "source_row_reference": self.source_row_reference,
                "row_hash": self.row_hash,
                "doc_type_code": self.doc_type_code,
                "counterparty_gstin": self.counterparty_gstin,
                "counterparty_gstin_normalized": self.counterparty_gstin_normalized,
                "counterparty_name": self.counterparty_name,
                "invoice_number": self.invoice_number,
                "invoice_number_normalized": self.invoice_number_normalized,
                "invoice_date": self.invoice_date,
                "taxable_value": self.taxable_value,
                "cgst": self.cgst,
                "sgst": self.sgst,
                "igst": self.igst,
                "cess": self.cess,
                "total_amount": self.total_amount,
                "pos_state_name": self.pos_state_name,
                "raw_row_json": self.raw_row_json,
                "normalized_row_json": self.normalized_row_json,
            }
            if original and current != original:
                raise ValidationError("Imported GST portal rows are immutable after ingestion.")
        return super().save(*args, **kwargs)
