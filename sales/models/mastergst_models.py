from __future__ import annotations

from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class MasterGSTEnvironment(models.IntegerChoices):
    SANDBOX = 1, "Sandbox"
    PRODUCTION = 2, "Production"


class SalesMasterGSTCredential(models.Model):
    """
    Keep it per entity for now.
    If later you want per subentity/GSTIN, add subentity and gstin uniqueness.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)

    environment = models.PositiveSmallIntegerField(
        choices=MasterGSTEnvironment.choices,
        default=MasterGSTEnvironment.SANDBOX,
        db_index=True,
    )

    gstin = models.CharField(max_length=15, db_index=True)

    client_id = models.CharField(max_length=128)
    client_secret = models.CharField(max_length=256)

    email = models.EmailField()
    gst_username = models.CharField(max_length=128)
    gst_password = models.CharField(max_length=256)

    allow_all_ips = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_mastergst_credential"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "environment"],
                name="uq_sales_mgst_entity_env",
            )
        ]

    def __str__(self) -> str:
        return f"MasterGSTCredential(entity={self.entity_id}, env={self.environment}, gstin={self.gstin})"


class SalesMasterGSTToken(models.Model):
    """
    Token cache per credential.
    """
    credential = models.OneToOneField(
        SalesMasterGSTCredential,
        on_delete=models.CASCADE,
        related_name="token",
        db_index=True,
    )

    auth_token = models.TextField(null=True, blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    sek = models.TextField(null=True, blank=True)
    gsp_client_id = models.CharField(max_length=64, null=True, blank=True)

    last_auth_at = models.DateTimeField(null=True, blank=True)
    last_response_json = models.JSONField(null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_mastergst_token"

    def is_valid(self) -> bool:
        return bool(self.auth_token and self.token_expiry and timezone.now() < self.token_expiry)

    def set_expiry_default(self):
        # conservative expiry; tweak if your sandbox says different
        self.token_expiry = timezone.now() + timedelta(hours=5, minutes=45)