from django.db import models
from django.db.models.deletion import CASCADE
from django.conf import settings
from django.db.models import JSONField
from helpers.models import TrackingModel
from Authentication.models import User
from django.utils.translation import gettext as _
from entity.models import Entity,EntityFinancialYear,SubEntity
from financial.models import account
import barcode                      # additional imports
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
import os



class TransactionType(TrackingModel):
    transactiontype = models.CharField(max_length= 255,verbose_name=_('Transaction Type'))
    transactioncode = models.CharField(max_length= 2000,verbose_name=_('Transaction Code'))

    def __str__(self):
        return f'{self.transactiontype}'


class UserReportPreference(TrackingModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_preferences",
    )
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="report_preferences")
    report_code = models.CharField(max_length=120)
    payload = JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("entity_id", "report_code", "-updated_at")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "entity", "report_code"),
                name="reports_user_entity_report_unique",
            )
        ]
        indexes = [
            models.Index(fields=("user", "entity", "report_code")),
            models.Index(fields=("user", "entity", "isactive", "report_code"), name="ix_rpt_pref_active"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.entity_id}:{self.report_code}"


class ReportFreezeSnapshot(TrackingModel):
    report_code = models.CharField(max_length=50, db_index=True)
    entity = models.ForeignKey(Entity, on_delete=CASCADE, related_name="report_freeze_snapshots")
    entityfinid = models.ForeignKey(
        EntityFinancialYear,
        on_delete=CASCADE,
        related_name="report_freeze_snapshots",
    )
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=CASCADE,
        null=True,
        blank=True,
        related_name="report_freeze_snapshots",
    )
    version = models.PositiveIntegerField()
    payload = JSONField(default=dict, blank=True)
    frozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_freeze_snapshots",
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("report_code", "entity", "entityfinid", "subentity", "version"),
                name="reports_freeze_scope_version_unique",
            )
        ]
        indexes = [
            models.Index(fields=("report_code", "entity", "entityfinid", "subentity", "version")),
            models.Index(fields=("report_code", "entity", "entityfinid", "subentity", "created_at"), name="ix_rpt_frz_latest"),
        ]

    def __str__(self):
        scope = f"{self.entity_id}:{self.entityfinid_id}:{self.subentity_id or 'all'}"
        return f"{self.report_code}:{scope}:v{self.version}"


class ReportFilingRun(TrackingModel):
    class Status(models.TextChoices):
        PREPARED = "prepared", "Prepared"
        SUBMITTED = "submitted", "Submitted"
        FAILED = "failed", "Failed"

    report_code = models.CharField(max_length=50, db_index=True)
    entity = models.ForeignKey(Entity, on_delete=CASCADE, related_name="report_filing_runs")
    entityfinid = models.ForeignKey(
        EntityFinancialYear,
        on_delete=CASCADE,
        related_name="report_filing_runs",
    )
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=CASCADE,
        null=True,
        blank=True,
        related_name="report_filing_runs",
    )
    freeze_snapshot = models.ForeignKey(
        ReportFreezeSnapshot,
        on_delete=CASCADE,
        related_name="filing_runs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREPARED)
    payload = JSONField(default=dict, blank=True)
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_report_filing_runs",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_report_filing_runs",
    )
    portal_provider = models.CharField(max_length=40, blank=True, default="")
    prepared_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    portal_reference = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("report_code", "entity", "entityfinid", "subentity", "status")),
            models.Index(fields=("report_code", "entity", "entityfinid", "subentity", "created_at"), name="ix_rpt_filing_scope"),
        ]

    def __str__(self):
        scope = f"{self.entity_id}:{self.entityfinid_id}:{self.subentity_id or 'all'}"
        return f"{self.report_code}:{scope}:filing:{self.id}:{self.status}"


class GstPortalSession(TrackingModel):
    class Status(models.TextChoices):
        OTP_REQUESTED = "otp_requested", "OTP Requested"
        AUTHENTICATED = "authenticated", "Authenticated"
        LOGGED_OUT = "logged_out", "Logged Out"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=40, default="whitebox", db_index=True)
    entity = models.ForeignKey(Entity, on_delete=CASCADE, related_name="gst_portal_sessions")
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=CASCADE,
        null=True,
        blank=True,
        related_name="gst_portal_sessions",
    )
    gstin = models.CharField(max_length=15, db_index=True)
    state_cd = models.CharField(max_length=2, blank=True, default="")
    gst_username = models.CharField(max_length=128, blank=True, default="")
    email = models.EmailField(max_length=254)
    ip_address = models.CharField(max_length=64, blank=True, default="")
    txn = models.CharField(max_length=64, blank=True, default="", db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OTP_REQUESTED, db_index=True)
    last_response = JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_gst_portal_sessions",
    )
    authenticated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authenticated_gst_portal_sessions",
    )
    otp_requested_at = models.DateTimeField(null=True, blank=True)
    authenticated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=("provider", "entity", "gstin", "status")),
            models.Index(fields=("provider", "entity", "subentity", "gstin"), name="ix_gst_portal_session_scope"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.gstin}:{self.email}:{self.status}"

    def save(self, *args, **kwargs):
        self.provider = (self.provider or "whitebox").strip().lower()
        self.gstin = (self.gstin or "").strip().upper()
        self.state_cd = (self.state_cd or "").strip().zfill(2)[:2]
        self.gst_username = (self.gst_username or "").strip()
        self.email = (self.email or "").strip().lower()
        self.ip_address = (self.ip_address or "").strip()
        self.txn = (self.txn or "").strip()
        super().save(*args, **kwargs)


class GstPortalFilingRun(TrackingModel):
    class ReturnType(models.TextChoices):
        GSTR1 = "gstr1", "GSTR-1"
        GSTR3B = "gstr3b", "GSTR-3B"
        GSTR2B = "gstr2b", "GSTR-2B"

    class Status(models.TextChoices):
        PREPARED = "prepared", "Prepared"
        SAVED = "saved", "Saved"
        PROCEEDED = "proceeded", "Proceeded"
        SUMMARY_FETCHED = "summary_fetched", "Summary Fetched"
        OFFSET = "offset", "Offset"
        EVC_REQUESTED = "evc_requested", "EVC Requested"
        FILED = "filed", "Filed"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=40, default="whitebox", db_index=True)
    return_type = models.CharField(max_length=12, choices=ReturnType.choices, db_index=True)
    entity = models.ForeignKey(Entity, on_delete=CASCADE, related_name="gst_portal_filing_runs")
    entityfinid = models.ForeignKey(
        EntityFinancialYear,
        on_delete=CASCADE,
        related_name="gst_portal_filing_runs",
    )
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=CASCADE,
        null=True,
        blank=True,
        related_name="gst_portal_filing_runs",
    )
    gstin = models.CharField(max_length=15, db_index=True)
    state_cd = models.CharField(max_length=2, blank=True, default="")
    ret_period = models.CharField(max_length=6, db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PREPARED, db_index=True)
    stage = models.CharField(max_length=40, blank=True, default="prepared")
    txn = models.CharField(max_length=64, blank=True, default="", db_index=True)
    portal_reference = models.CharField(max_length=120, blank=True, default="")
    scope_payload = JSONField(default=dict, blank=True)
    payload = JSONField(default=dict, blank=True)
    warnings = JSONField(default=list, blank=True)
    portal_response = JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_gst_portal_filing_runs",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_gst_portal_filing_runs",
    )
    prepared_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("provider", "return_type", "entity", "entityfinid", "gstin", "ret_period")),
            models.Index(fields=("return_type", "entity", "entityfinid", "subentity", "status"), name="ix_gst_portal_filing_scope"),
        ]

    def __str__(self):
        scope = f"{self.entity_id}:{self.entityfinid_id}:{self.subentity_id or 'gstin'}"
        return f"{self.return_type}:{scope}:{self.gstin}:{self.ret_period}:{self.status}"

    def save(self, *args, **kwargs):
        self.provider = (self.provider or "whitebox").strip().lower()
        self.return_type = (self.return_type or "").strip().lower()
        self.gstin = (self.gstin or "").strip().upper()
        self.state_cd = (self.state_cd or "").strip().zfill(2)[:2]
        self.ret_period = (self.ret_period or "").strip()
        self.txn = (self.txn or "").strip()
        self.portal_reference = (self.portal_reference or "").strip()
        self.stage = (self.stage or self.status or "").strip()
        super().save(*args, **kwargs)


class GstPortalProfile(TrackingModel):
    provider = models.CharField(max_length=40, default="whitebox", db_index=True)
    entity = models.ForeignKey(Entity, on_delete=CASCADE, related_name="gst_portal_profiles")
    gstin = models.CharField(max_length=15, db_index=True)
    state_cd = models.CharField(max_length=2, blank=True, default="")
    gst_username = models.CharField(max_length=128, blank=True, default="")
    registered_mobile_masked = models.CharField(max_length=32, blank=True, default="")
    registered_email_masked = models.EmailField(max_length=254, blank=True, default="")
    is_verified = models.BooleanField(default=False)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_gst_portal_profiles",
    )

    class Meta:
        ordering = ("entity_id", "gstin", "provider")
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "entity", "gstin"),
                name="reports_gst_portal_profile_unique",
            )
        ]
        indexes = [
            models.Index(fields=("provider", "entity", "gstin", "isactive"), name="ix_gst_portal_profile_scope"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.entity_id}:{self.gstin}"

    def save(self, *args, **kwargs):
        self.provider = (self.provider or "whitebox").strip().lower()
        self.gstin = (self.gstin or "").strip().upper()
        self.state_cd = (self.state_cd or "").strip().zfill(2)[:2]
        self.gst_username = (self.gst_username or "").strip()
        self.registered_mobile_masked = (self.registered_mobile_masked or "").strip()
        self.registered_email_masked = (self.registered_email_masked or "").strip().lower()
        super().save(*args, **kwargs)


def _gst_compliance_task_attachment_upload_to(instance: "GstComplianceTaskAttachment", filename: str) -> str:
    return f"gst/compliance/tasks/{instance.task_id or 'new'}/{filename}"


class GstComplianceTask(TrackingModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In Review"
        BLOCKED = "blocked", "Blocked"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    entity = models.ForeignKey(Entity, on_delete=CASCADE, related_name="gst_compliance_tasks")
    entityfinid = models.ForeignKey(
        EntityFinancialYear,
        on_delete=CASCADE,
        related_name="gst_compliance_tasks",
    )
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=CASCADE,
        null=True,
        blank=True,
        related_name="gst_compliance_tasks",
    )
    gstin = models.CharField(max_length=15, db_index=True)
    return_period = models.CharField(max_length=7, db_index=True)
    return_type = models.CharField(max_length=24, blank=True, default="", db_index=True)
    source = models.CharField(max_length=80, blank=True, default="", db_index=True)
    source_code = models.CharField(max_length=120, blank=True, default="", db_index=True)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN, db_index=True)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.WARNING, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_gst_compliance_tasks",
    )
    due_date = models.DateField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_gst_compliance_tasks",
    )
    closure_note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_gst_compliance_tasks",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_gst_compliance_tasks",
    )

    class Meta:
        ordering = ("status", "due_date", "-updated_at", "-id")
        indexes = [
            models.Index(fields=("entity", "entityfinid", "subentity", "gstin", "return_period", "status"), name="ix_gst_task_scope_status"),
            models.Index(fields=("entity", "owner", "status", "due_date"), name="ix_gst_task_owner_due"),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.gstin}:{self.return_period}:{self.source_code}:{self.status}"

    def save(self, *args, **kwargs):
        self.gstin = (self.gstin or "").strip().upper()
        self.return_period = (self.return_period or "").strip()
        self.return_type = (self.return_type or "").strip().upper()
        self.source = (self.source or "").strip()
        self.source_code = (self.source_code or "").strip()
        self.title = (self.title or "").strip()
        super().save(*args, **kwargs)


class GstComplianceTaskComment(TrackingModel):
    task = models.ForeignKey(GstComplianceTask, on_delete=CASCADE, related_name="comments")
    comment = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gst_compliance_task_comments",
    )

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("task", "created_at"), name="ix_gst_task_comment_task_dt"),
        ]

    def __str__(self):
        return f"{self.task_id}:comment:{self.id}"


class GstComplianceTaskAttachment(TrackingModel):
    task = models.ForeignKey(GstComplianceTask, on_delete=CASCADE, related_name="attachments")
    file = models.FileField(upload_to=_gst_compliance_task_attachment_upload_to, max_length=255)
    original_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gst_compliance_task_attachments",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("task", "created_at"), name="ix_gst_task_attach_task_dt"),
        ]

    def __str__(self):
        return f"{self.task_id}:{self.original_name or self.file.name}"


class GstComplianceTaskAudit(TrackingModel):
    task = models.ForeignKey(GstComplianceTask, on_delete=CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=40, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gst_compliance_task_audit_logs",
    )
    old_data = JSONField(default=dict, blank=True)
    new_data = JSONField(default=dict, blank=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("task", "action", "created_at"), name="ix_gst_task_audit_task_action"),
            models.Index(fields=("actor", "created_at"), name="ix_gst_task_audit_actor_dt"),
        ]

    def __str__(self):
        return f"{self.task_id}:{self.action}:{self.created_at}"
