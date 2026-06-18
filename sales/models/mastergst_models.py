from __future__ import annotations

from datetime import timedelta
import base64
import hashlib
import ipaddress
from django.conf import settings
from django.db import models
from django.utils import timezone
from cryptography.fernet import Fernet, InvalidToken

User = settings.AUTH_USER_MODEL
ENC_PREFIX = "enc$"


def _fernet() -> Fernet:
    raw = getattr(settings, "SALES_SECRET_ENCRYPTION_KEY", None)
    if raw:
        key = raw.encode("utf-8") if isinstance(raw, str) else raw
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _enc(value: str | None) -> str | None:
    if not value:
        return value
    s = str(value)
    if s.startswith(ENC_PREFIX):
        return s
    token = _fernet().encrypt(s.encode("utf-8")).decode("utf-8")
    return f"{ENC_PREFIX}{token}"


def _dec(value: str | None) -> str | None:
    if not value:
        return value
    s = str(value)
    if not s.startswith(ENC_PREFIX):
        return s
    token = s[len(ENC_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


class MasterGSTEnvironment(models.IntegerChoices):
    SANDBOX = 1, "Sandbox"
    PRODUCTION = 2, "Production"


class MasterGSTServiceScope(models.IntegerChoices):
    EINVOICE = 1, "E-Invoice"
    EWAY = 2, "E-Way"


class SalesMasterGSTCredential(models.Model):
    """
    Keep per entity + environment + scope (EINVOICE/EWAY).
    This allows different client_id/client_secret/gstin for EWAY sandbox.
    """
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)

    environment = models.PositiveSmallIntegerField(
        choices=MasterGSTEnvironment.choices,
        default=MasterGSTEnvironment.SANDBOX,
        db_index=True,
    )

    # ✅ NEW (EINVOICE default)
    service_scope = models.PositiveSmallIntegerField(
        choices=MasterGSTServiceScope.choices,
        default=MasterGSTServiceScope.EINVOICE,
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
                fields=["entity", "environment", "service_scope"],
                name="uq_sales_mgst_entity_env_scope",
            )
        ]

    def __str__(self) -> str:
        return f"MasterGSTCredential(entity={self.entity_id}, env={self.environment}, scope={self.service_scope}, gstin={self.gstin})"

    def get_client_secret(self) -> str:
        return _dec(self.client_secret) or ""

    def get_gst_password(self) -> str:
        return _dec(self.gst_password) or ""

    def get_eway_username(self) -> str:
        # Current credential model uses the GST portal username for both e-invoice
        # and e-way unless a future schema introduces dedicated e-way fields.
        return str(self.gst_username or "").strip()

    def get_eway_password(self) -> str:
        return self.get_gst_password()

    def resolve_ip_address(self) -> str | None:
        ip = str(self.ip_address or "").strip()
        if not ip:
            return None
        try:
            ipaddress.ip_address(ip)
        except ValueError as exc:
            raise ValueError(f"Invalid credential ip_address: {ip}") from exc
        return ip

    def save(self, *args, **kwargs):
        self.client_secret = _enc(self.client_secret)
        self.gst_password = _enc(self.gst_password)
        super().save(*args, **kwargs)


class SalesMasterGSTToken(models.Model):
    """
    Token cache per credential.
    NOTE: Keep this for EINVOICE only (default behavior unchanged).
    """
    credential = models.OneToOneField(
        SalesMasterGSTCredential,
        on_delete=models.CASCADE,
        related_name="token",
        db_index=True,
    )

    auth_token = models.TextField(null=True, blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    eway_auth_token = models.TextField(null=True, blank=True)
    eway_token_expiry = models.DateTimeField(null=True, blank=True)
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
        self.token_expiry = timezone.now() + timedelta(hours=5, minutes=45)

    def get_auth_token(self) -> str:
        return _dec(self.auth_token) or ""

    def get_eway_auth_token(self) -> str:
        return _dec(self.eway_auth_token) or ""

    def save(self, *args, **kwargs):
        self.auth_token = _enc(self.auth_token)
        self.eway_auth_token = _enc(self.eway_auth_token)
        super().save(*args, **kwargs)
