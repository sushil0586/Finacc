from django.db import models
from django.db.models.deletion import CASCADE
from django.conf import settings
from django.db.models import JSONField
from helpers.models import TrackingModel
from Authentication.models import User
from django.utils.translation import gettext as _
from entity.models import Entity,EntityFinancialYear
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



