from __future__ import annotations

from django.db import models

from helpers.models import TrackingModel


class ImportProfile(TrackingModel):
    class Module(models.TextChoices):
        SALES = "sales", "Sales"
        PURCHASE = "purchase", "Purchase"

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, related_name="invoice_import_profiles")
    created_by = models.ForeignKey("Authentication.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    module = models.CharField(max_length=20, choices=Module.choices, db_index=True)
    name = models.CharField(max_length=100)
    source_system = models.CharField(max_length=100, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    is_default = models.BooleanField(default=False, db_index=True)
    mapping = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "module", "is_default"], name="ix_invimp_profile_default"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["entity", "module", "name"], name="uq_invimp_profile_entity_module_name"),
        ]

    def __str__(self) -> str:
        return f"ImportProfile<{self.id}> {self.module} {self.name}"


class ImportJob(TrackingModel):
    class Module(models.TextChoices):
        SALES = "sales", "Sales"
        PURCHASE = "purchase", "Purchase"

    class Mode(models.TextChoices):
        OUTSTANDING_ONLY = "outstanding_only", "Outstanding only"
        FULL_HISTORY = "full_history", "Full history"

    class DetailLevel(models.TextChoices):
        HEADER_ONLY = "header_only", "Header only"
        HEADER_PLUS_LINES = "header_plus_lines", "Header + lines"

    class ComplianceMode(models.TextChoices):
        PASSIVE = "passive", "Passive"
        LIVE = "live", "Live"

    class WithholdingMode(models.TextChoices):
        PRESERVE_LEGACY = "preserve_legacy", "Preserve legacy"
        RECOMPUTE_FINACC = "recompute_finacc", "Recompute Finacc"

    class FileFormat(models.TextChoices):
        XLSX = "xlsx", "XLSX"
        CSV = "csv", "CSV"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VALIDATED = "validated", "Validated"
        FAILED = "failed", "Failed"
        COMMITTED = "committed", "Committed"
        PARTIAL = "partial", "Partial"

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, related_name="invoice_import_jobs")
    created_by = models.ForeignKey("Authentication.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    profile = models.ForeignKey("invoice_import.ImportProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")

    module = models.CharField(max_length=20, choices=Module.choices, db_index=True)
    mode = models.CharField(max_length=30, choices=Mode.choices, db_index=True)
    detail_level = models.CharField(max_length=30, choices=DetailLevel.choices, default=DetailLevel.HEADER_ONLY)
    compliance_mode = models.CharField(max_length=20, choices=ComplianceMode.choices, default=ComplianceMode.PASSIVE)
    withholding_mode = models.CharField(max_length=30, choices=WithholdingMode.choices, default=WithholdingMode.PRESERVE_LEGACY)
    file_format = models.CharField(max_length=10, choices=FileFormat.choices, default=FileFormat.XLSX)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    stock_replay = models.BooleanField(default=False)
    input_filename = models.CharField(max_length=255, blank=True, default="")
    source_system = models.CharField(max_length=100, blank=True, default="")

    summary = models.JSONField(default=dict, blank=True)
    reconciliation_summary = models.JSONField(default=dict, blank=True)
    profile_snapshot = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    review_required = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey("Authentication.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["entity", "module", "status"], name="ix_invimp_job_scope"),
            models.Index(fields=["entity", "module", "created_at"], name="ix_invimp_job_recent"),
        ]

    def __str__(self) -> str:
        return f"ImportJob<{self.id}> {self.module} {self.mode} {self.status}"


class ImportRow(TrackingModel):
    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        ERROR = "error", "Error"
        IMPORTED = "imported", "Imported"
        SKIPPED = "skipped", "Skipped"

    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    row_no = models.PositiveIntegerField()
    group_key = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VALID, db_index=True)

    raw_payload = models.JSONField(default=dict, blank=True)
    normalized_payload = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)

    committed_object_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["job", "status"], name="ix_invimp_row_job_status"),
            models.Index(fields=["job", "group_key"], name="ix_invimp_row_job_group"),
            models.Index(fields=["job", "status", "row_no"], name="ix_invimp_row_status_ord"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["job", "row_no"], name="uq_invimp_row_job_rowno"),
        ]

    def __str__(self) -> str:
        return f"ImportRow<{self.id}> {self.group_key} {self.status}"
