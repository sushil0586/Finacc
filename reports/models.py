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
        ]

    def __str__(self):
        scope = f"{self.entity_id}:{self.entityfinid_id}:{self.subentity_id or 'all'}"
        return f"{self.report_code}:{scope}:filing:{self.id}:{self.status}"
