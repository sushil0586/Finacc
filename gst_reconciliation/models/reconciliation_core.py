from __future__ import annotations

from django.db import models

from core.models.base import EntityScopedModel, TrackingModel


class GstReconciliationRun(EntityScopedModel):
    class ReconciliationType(models.TextChoices):
        GSTR2B_PURCHASE = "GSTR2B_PURCHASE", "GSTR-2B vs Purchase Register"
        GSTR1_SALES = "GSTR1_SALES", "GSTR-1 vs Sales Register"
        GSTR3B_BOOKS = "GSTR3B_BOOKS", "GSTR-3B vs Books"

    class PeriodType(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        YEARLY = "YEARLY", "Yearly"

    class SourceMode(models.TextChoices):
        BOOKS_VS_IMPORTED = "BOOKS_VS_IMPORTED", "Books vs Imported"
        BOOKS_ONLY = "BOOKS_ONLY", "Books Only"
        IMPORTED_ONLY = "IMPORTED_ONLY", "Imported Only"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IMPORTED = "IMPORTED", "Imported"
        MATCHING = "MATCHING", "Matching"
        READY_FOR_REVIEW = "READY_FOR_REVIEW", "Ready For Review"
        IN_REVIEW = "IN_REVIEW", "In Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CLOSED = "CLOSED", "Closed"
        FAILED = "FAILED", "Failed"

    gst_registration_gstin = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    reconciliation_type = models.CharField(max_length=32, choices=ReconciliationType.choices, db_index=True)
    period_type = models.CharField(max_length=16, choices=PeriodType.choices, default=PeriodType.MONTHLY)
    period_from = models.DateField(null=True, blank=True)
    period_to = models.DateField(null=True, blank=True)
    return_period = models.CharField(max_length=7, db_index=True)
    revision_no = models.PositiveIntegerField(default=1)
    source_mode = models.CharField(max_length=20, choices=SourceMode.choices, default=SourceMode.BOOKS_VS_IMPORTED)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT, db_index=True)
    match_strategy_code = models.CharField(max_length=64, default="default")
    tolerance_config_json = models.JSONField(default=dict, blank=True)
    imported_return = models.ForeignKey(
        "gst_reconciliation.GstImportedReturn",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reconciliation_runs",
    )
    source_reference = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    summary_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(null=True, blank=True)
    review_comment = models.TextField(null=True, blank=True)
    approval_comment = models.TextField(null=True, blank=True)
    close_comment = models.TextField(null=True, blank=True)

    submitted_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_runs_submitted",
    )
    reviewed_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_runs_reviewed",
    )
    approved_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_runs_approved",
    )
    closed_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_runs_closed",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(EntityScopedModel.Meta):
        ordering = ("-created_at", "-id")
        indexes = EntityScopedModel.Meta.indexes + [
            models.Index(
                fields=["entity", "entityfinid", "subentity", "reconciliation_type", "return_period"],
                name="ix_gst_run_scope_type_period",
            ),
            models.Index(
                fields=["entity", "reconciliation_type", "return_period", "status", "created_at"],
                name="ix_gst_run_ent_type_st_ct",
            ),
            models.Index(fields=["status", "reconciliation_type", "return_period"], name="ix_gst_run_status_type_period"),
            models.Index(
                fields=["gst_registration_gstin", "reconciliation_type", "return_period"],
                name="ix_gst_run_gstin_type_period",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "entity",
                    "entityfinid",
                    "subentity",
                    "gst_registration_gstin",
                    "reconciliation_type",
                    "return_period",
                    "revision_no",
                    "is_active",
                ],
                name="uq_gst_run_scope_type_period_revision",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reconciliation_type} {self.return_period} #{self.id}"


class GstReconciliationItem(EntityScopedModel):
    class ItemType(models.TextChoices):
        INVOICE = "INVOICE", "Invoice"
        CREDIT_NOTE = "CREDIT_NOTE", "Credit Note"
        DEBIT_NOTE = "DEBIT_NOTE", "Debit Note"
        SECTION_BUCKET = "SECTION_BUCKET", "Section Bucket"
        SUMMARY_BUCKET = "SUMMARY_BUCKET", "Summary Bucket"

    class Direction(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        SALES = "SALES", "Sales"
        OUTPUT = "OUTPUT", "Output"
        INPUT = "INPUT", "Input"

    class MatchStatus(models.TextChoices):
        NOT_CHECKED = "NOT_CHECKED", "Not Checked"
        MATCHED = "MATCHED", "Matched"
        PARTIAL = "PARTIAL", "Partial"
        MISMATCHED = "MISMATCHED", "Mismatched"
        MISSING_IN_BOOKS = "MISSING_IN_BOOKS", "Missing In Books"
        MISSING_IN_RETURN = "MISSING_IN_RETURN", "Missing In Return"
        DUPLICATE = "DUPLICATE", "Duplicate"
        IGNORED = "IGNORED", "Ignored"
        MANUALLY_RESOLVED = "MANUALLY_RESOLVED", "Manually Resolved"

    class ResolutionStatus(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        ASSIGNED = "ASSIGNED", "Assigned"
        AUTO_MATCHED = "AUTO_MATCHED", "Auto Matched"
        MANUAL_MATCHED = "MANUAL_MATCHED", "Manual Matched"
        PARTIAL_MATCH = "PARTIAL_MATCH", "Partial Match"
        MISMATCH = "MISMATCH", "Mismatch"
        ACCEPTED_MISMATCH = "ACCEPTED_MISMATCH", "Accepted Mismatch"
        IGNORED = "IGNORED", "Ignored"
        REOPENED = "REOPENED", "Reopened"
        RESOLVED = "RESOLVED", "Resolved"

    run = models.ForeignKey(
        GstReconciliationRun,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.INVOICE)
    direction = models.CharField(max_length=16, choices=Direction.choices, default=Direction.PURCHASE)
    match_key = models.CharField(max_length=255, db_index=True)
    source_document_type = models.CharField(max_length=64)
    source_document_id = models.CharField(max_length=64)
    linked_document_type = models.CharField(max_length=64, null=True, blank=True)
    linked_document_id = models.CharField(max_length=64, null=True, blank=True)
    gstin = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    counterparty_gstin = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    invoice_number = models.CharField(max_length=50, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    doc_type_code = models.CharField(max_length=20, null=True, blank=True)
    taxable_value_books = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cgst_books = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst_books = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst_books = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cess_books = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    taxable_value_imported = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cgst_imported = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst_imported = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst_imported = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cess_imported = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    match_status = models.CharField(max_length=24, choices=MatchStatus.choices, default=MatchStatus.NOT_CHECKED, db_index=True)
    resolution_status = models.CharField(
        max_length=24,
        choices=ResolutionStatus.choices,
        default=ResolutionStatus.PENDING_REVIEW,
        db_index=True,
    )
    mismatch_count = models.PositiveIntegerField(default=0)
    match_confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    mismatch_summary = models.JSONField(default=list, blank=True)
    assigned_reviewer = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_items_assigned",
    )
    assigned_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_items_assigned_by",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.TextField(null=True, blank=True)
    resolution_note = models.TextField(null=True, blank=True)
    accepted_mismatch_at = models.DateTimeField(null=True, blank=True)
    accepted_mismatch_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_items_accepted_mismatch",
    )
    resolved_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_items_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "Authentication.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gst_recon_items_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta(EntityScopedModel.Meta):
        indexes = EntityScopedModel.Meta.indexes + [
            models.Index(fields=["run", "match_status"], name="ix_gst_item_run_status"),
            models.Index(fields=["run", "resolution_status"], name="ix_gst_item_run_resolution"),
            models.Index(fields=["run", "match_key"], name="ix_gst_item_run_key"),
            models.Index(fields=["run", "item_type"], name="ix_gst_item_run_type"),
            models.Index(fields=["gstin", "counterparty_gstin"], name="ix_gst_item_gstin_pair"),
            models.Index(
                fields=["run", "assigned_reviewer", "resolution_status", "updated_at"],
                name="ix_gst_item_queue",
            ),
            models.Index(
                fields=["run", "counterparty_gstin", "resolution_status"],
                name="ix_gst_item_run_party_res",
            ),
            models.Index(
                fields=["run", "match_confidence_score"],
                name="ix_gst_item_run_conf",
            ),
            models.Index(
                fields=["run", "resolution_status", "updated_at"],
                name="ix_gst_item_run_res_upd",
            ),
            models.Index(
                fields=["run", "match_status", "updated_at"],
                name="ix_gst_item_run_stat_upd",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "source_document_type", "source_document_id"],
                name="uq_gst_item_run_source_doc",
            ),
        ]

    def __str__(self) -> str:
        return f"Run {self.run_id} | {self.match_status} | {self.match_key}"


class GstMismatchReason(TrackingModel):
    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    item = models.ForeignKey(
        GstReconciliationItem,
        on_delete=models.CASCADE,
        related_name="mismatch_reasons",
    )
    code = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.WARNING)
    message = models.TextField()
    details_json = models.JSONField(default=dict, blank=True)

    class Meta(TrackingModel.Meta):
        indexes = [
            models.Index(fields=["item", "severity"], name="ix_gst_reason_item_severity"),
            models.Index(fields=["code", "severity"], name="ix_gst_reason_code_severity"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["item", "code"], name="uq_gst_reason_item_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.severity})"
