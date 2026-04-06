from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .base import TrackingModel
from .purchase_core import PurchaseInvoiceHeader

User = settings.AUTH_USER_MODEL
ZERO2 = Decimal("0.00")


def _purchase_form16a_deductee_upload_to(instance, filename: str) -> str:
    filing = getattr(instance, "filing", None)
    entity_id = getattr(filing, "entity_id", None) or "unknown"
    subentity_id = getattr(filing, "subentity_id", None) or "na"
    filing_id = getattr(instance, "filing_id", None) or "unknown"
    year = timezone.localdate().strftime("%Y")
    month = timezone.localdate().strftime("%m")
    raw_name = (filename or "document.pdf").replace("\\", "/")
    name = os.path.basename(raw_name) or "document.pdf"
    stem, ext = os.path.splitext(name)
    safe_stem = (stem or "document")[:24]
    safe_ext = (ext or ".pdf")[:10]
    safe_name = f"{safe_stem}{safe_ext}"
    template = getattr(
        settings,
        "PURCHASE_FORM16A_DEDUCTEE_UPLOAD_TEMPLATE",
        "purchase/e{entity_id}/s{subentity_id}/r{filing_id}/f16a/d/{deductee_key}/{filename}",
    )
    return template.format(
        entity_id=entity_id,
        subentity_id=subentity_id,
        filing_id=filing_id,
        deductee_key=getattr(instance, "deductee_key", None) or "unknown",
        year=year,
        month=month,
        filename=safe_name,
    )


class PurchaseStatutoryChallan(TrackingModel):
    class TaxType(models.TextChoices):
        IT_TDS = "IT_TDS", "Income-tax TDS"
        GST_TDS = "GST_TDS", "GST-TDS"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        DEPOSITED = 2, "Deposited"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    tax_type = models.CharField(max_length=10, choices=TaxType.choices, db_index=True)
    challan_no = models.CharField(max_length=50, db_index=True)
    challan_date = models.DateField(default=timezone.localdate, db_index=True)
    period_from = models.DateField(null=True, blank=True, db_index=True)
    period_to = models.DateField(null=True, blank=True, db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    interest_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    late_fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    penalty_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    bank_ref_no = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    bsr_code = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    cin_no = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    minor_head_code = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    payment_payload_json = models.JSONField(default=dict, blank=True)
    ack_document = models.FileField(upload_to="purchase/statutory/challan/", null=True, blank=True)

    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    deposited_on = models.DateField(null=True, blank=True, db_index=True)
    deposited_at = models.DateTimeField(null=True, blank=True)
    deposited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_challans_deposited",
    )

    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_challans_created",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "tax_type", "challan_no"),
                name="uq_pur_stat_challan_scope_type_no",
            ),
            models.CheckConstraint(check=Q(amount__gte=0), name="ck_pur_stat_challan_amount_nonneg"),
            models.CheckConstraint(check=Q(interest_amount__gte=0), name="ck_pur_stat_challan_interest_nonneg"),
            models.CheckConstraint(check=Q(late_fee_amount__gte=0), name="ck_pur_stat_challan_latefee_nonneg"),
            models.CheckConstraint(check=Q(penalty_amount__gte=0), name="ck_pur_stat_challan_penalty_nonneg"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "tax_type", "status"], name="ix_pur_stat_challan_scope"),
            models.Index(fields=["entity", "entityfinid", "challan_date"], name="ix_pur_stat_challan_date"),
        ]

    def __str__(self) -> str:
        return f"{self.tax_type}:{self.challan_no}"

    @property
    def total_deposit_amount(self) -> Decimal:
        return ZERO2 + (self.amount or ZERO2) + (self.interest_amount or ZERO2) + (self.late_fee_amount or ZERO2) + (
            self.penalty_amount or ZERO2
        )


class PurchaseStatutoryChallanLine(TrackingModel):
    challan = models.ForeignKey(PurchaseStatutoryChallan, on_delete=models.CASCADE, related_name="lines")
    header = models.ForeignKey(PurchaseInvoiceHeader, on_delete=models.PROTECT, related_name="statutory_challan_lines")
    section = models.ForeignKey(
        "withholding.WithholdingSection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_challan_lines",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("challan", "header"), name="uq_pur_stat_challan_line_challan_header"),
            models.CheckConstraint(check=Q(amount__gt=0), name="ck_pur_stat_challan_line_amount_pos"),
        ]
        indexes = [
            models.Index(fields=["challan"], name="ix_pur_stcl_challan"),
            models.Index(fields=["header"], name="ix_pur_stcl_header"),
        ]

    def __str__(self) -> str:
        return f"ChallanLine({self.challan_id}, {self.header_id}, {self.amount})"


class PurchaseStatutoryReturn(TrackingModel):
    class TaxType(models.TextChoices):
        IT_TDS = "IT_TDS", "Income-tax TDS"
        GST_TDS = "GST_TDS", "GST-TDS"

    class Status(models.IntegerChoices):
        DRAFT = 1, "Draft"
        FILED = 2, "Filed"
        REVISED = 3, "Revised"
        CANCELLED = 9, "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    tax_type = models.CharField(max_length=10, choices=TaxType.choices, db_index=True)
    return_code = models.CharField(max_length=30, db_index=True)  # e.g. 26Q / 27Q / GSTR7
    period_from = models.DateField(db_index=True)
    period_to = models.DateField(db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    interest_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    late_fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    penalty_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    status = models.IntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    filed_on = models.DateField(null=True, blank=True, db_index=True)
    filed_at = models.DateTimeField(null=True, blank=True)
    filed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_returns_filed",
    )
    ack_no = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    arn_no = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    filed_payload_json = models.JSONField(default=dict, blank=True)
    ack_document = models.FileField(upload_to="purchase/statutory/return/", null=True, blank=True)
    original_return = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="revisions",
    )
    revision_no = models.PositiveIntegerField(default=0)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_returns_created",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "tax_type", "return_code", "period_from", "period_to"),
                condition=Q(original_return__isnull=True, subentity__isnull=False) & ~Q(status=9),
                name="uq_pur_stret_orig_sub_scope",
            ),
            models.UniqueConstraint(
                fields=("entity", "entityfinid", "tax_type", "return_code", "period_from", "period_to"),
                condition=Q(original_return__isnull=True, subentity__isnull=True) & ~Q(status=9),
                name="uq_pur_stret_orig_nsub_scope",
            ),
            models.CheckConstraint(check=Q(amount__gte=0), name="ck_pur_stat_return_amount_nonneg"),
            models.CheckConstraint(check=Q(interest_amount__gte=0), name="ck_pur_stat_return_interest_nonneg"),
            models.CheckConstraint(check=Q(late_fee_amount__gte=0), name="ck_pur_stat_return_latefee_nonneg"),
            models.CheckConstraint(check=Q(penalty_amount__gte=0), name="ck_pur_stat_return_penalty_nonneg"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "tax_type", "status"], name="ix_pur_stat_return_scope"),
            models.Index(fields=["entity", "entityfinid", "period_from", "period_to"], name="ix_pur_stat_return_period"),
        ]

    def __str__(self) -> str:
        return f"{self.tax_type}:{self.return_code}:{self.period_from}-{self.period_to}"

    @property
    def total_liability_amount(self) -> Decimal:
        return ZERO2 + (self.amount or ZERO2) + (self.interest_amount or ZERO2) + (self.late_fee_amount or ZERO2) + (
            self.penalty_amount or ZERO2
        )


class PurchaseStatutoryReturnLine(TrackingModel):
    class DeducteeResidency(models.TextChoices):
        RESIDENT = "RESIDENT", "Resident"
        NON_RESIDENT = "NON_RESIDENT", "Non-Resident"

    filing = models.ForeignKey(PurchaseStatutoryReturn, on_delete=models.CASCADE, related_name="lines")
    header = models.ForeignKey(PurchaseInvoiceHeader, on_delete=models.PROTECT, related_name="statutory_return_lines")
    challan = models.ForeignKey(
        PurchaseStatutoryChallan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="return_lines",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    section_snapshot_code = models.CharField(max_length=16, null=True, blank=True, db_index=True)
    section_snapshot_desc = models.CharField(max_length=255, null=True, blank=True)
    deductee_residency_snapshot = models.CharField(
        max_length=20,
        choices=DeducteeResidency.choices,
        null=True,
        blank=True,
        db_index=True,
    )
    deductee_country_snapshot = models.ForeignKey(
        "geography.Country",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_return_lines",
    )
    deductee_country_code_snapshot = models.CharField(max_length=10, null=True, blank=True, db_index=True)
    deductee_country_name_snapshot = models.CharField(max_length=255, null=True, blank=True)
    deductee_tax_id_snapshot = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    deductee_pan_snapshot = models.CharField(max_length=16, null=True, blank=True, db_index=True)
    deductee_gstin_snapshot = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    cin_snapshot = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("filing", "header"), name="uq_pur_stat_return_line_filing_header"),
            models.CheckConstraint(check=Q(amount__gt=0), name="ck_pur_stat_return_line_amount_pos"),
        ]
        indexes = [
            models.Index(fields=["filing"], name="ix_pur_stat_return_line_filing"),
            models.Index(fields=["header"], name="ix_pur_stat_return_line_header"),
        ]

    def __str__(self) -> str:
        return f"ReturnLine({self.filing_id}, {self.header_id}, {self.amount})"


class PurchaseStatutoryForm16AOfficialDocument(TrackingModel):
    filing = models.ForeignKey(
        PurchaseStatutoryReturn,
        on_delete=models.CASCADE,
        related_name="form16a_official_documents",
    )
    issue_no = models.PositiveIntegerField(db_index=True)
    source = models.CharField(max_length=20, default="TRACES")
    certificate_no = models.CharField(max_length=100, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    document = models.FileField(upload_to="purchase/statutory/form16a/", max_length=255)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_form16a_uploaded",
    )
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("filing", "issue_no"),
                name="uq_pur_form16a_official_filing_issue",
            ),
        ]
        indexes = [
            models.Index(fields=["filing", "issue_no"], name="ix_pur_form16a_filing_issue"),
        ]

    def __str__(self) -> str:
        return f"Form16AOfficial({self.filing_id}, issue={self.issue_no})"


class PurchaseStatutoryForm16ACertificateDocument(TrackingModel):
    filing = models.ForeignKey(
        PurchaseStatutoryReturn,
        on_delete=models.CASCADE,
        related_name="form16a_certificate_documents",
    )
    return_line = models.OneToOneField(
        PurchaseStatutoryReturnLine,
        on_delete=models.CASCADE,
        related_name="form16a_certificate_document",
    )
    source = models.CharField(max_length=20, default="TRACES")
    certificate_no = models.CharField(max_length=100, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    document = models.FileField(upload_to="purchase/statutory/form16a/certificates/", max_length=255)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_form16a_certificate_uploaded",
    )
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("filing", "return_line"),
                name="uq_pur_form16a_certificate_filing_line",
            ),
        ]
        indexes = [
            models.Index(fields=["filing"], name="ix_pur_form16a_cert_filing"),
            models.Index(fields=["return_line"], name="ix_pur_form16a_cert_line"),
        ]

    def __str__(self) -> str:
        return f"Form16ACertificate({self.filing_id}, line={self.return_line_id})"


class PurchaseStatutoryForm16ADeducteeDocument(TrackingModel):
    filing = models.ForeignKey(
        PurchaseStatutoryReturn,
        on_delete=models.CASCADE,
        related_name="form16a_deductee_documents",
    )
    deductee_key = models.CharField(max_length=40, db_index=True)
    deductee_pan = models.CharField(max_length=16, null=True, blank=True, db_index=True)
    deductee_tax_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    deductee_gstin = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    source = models.CharField(max_length=20, default="TRACES")
    certificate_no = models.CharField(max_length=100, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    line_ids_json = models.JSONField(default=list, blank=True)
    document = models.FileField(upload_to=_purchase_form16a_deductee_upload_to, max_length=255)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_statutory_form16a_deductee_uploaded",
    )
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("filing", "deductee_key"),
                name="uq_pur_form16a_deductee_filing_key",
            ),
        ]
        indexes = [
            models.Index(fields=["filing"], name="ix_pur_form16a_deductee_filing"),
            models.Index(fields=["deductee_key"], name="ix_pur_form16a_deductee_key"),
        ]

    def __str__(self) -> str:
        return f"Form16ADeductee({self.filing_id}, {self.deductee_key})"
