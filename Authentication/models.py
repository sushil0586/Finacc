from django.db import models
from helpers.models import TrackingModel
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, UserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.apps import apps
from django.utils import timezone
from django.utils.translation import gettext as _
from django.contrib.auth.hashers import make_password


class MyUserManager(UserManager):
    def _create_user(self, username, email, password, **extra_fields):
        if not email:
            raise ValueError("Email must be set")

        email = self.normalize_email(email).strip().lower()
        username = (username or "").strip()

        GlobalUserModel = apps.get_model(
            self.model._meta.app_label,
            self.model._meta.object_name,
        )
        username = GlobalUserModel.normalize_username(username)

        user = self.model(username=username, email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_user(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TrackingModel):
    username_validator = UnicodeUsernameValidator()

    # Display-only username. Email is the real login field.
    username = models.CharField(
        _("username"),
        max_length=150,
        help_text=_("Display username. Email is used for login."),
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_("first name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100, blank=True)
    email = models.EmailField(_("email address"), blank=False, unique=True, db_index=True)

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Designates whether this user should be treated as active."),
    )
    email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Whether the email address has been verified."),
    )

    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    token_version = models.PositiveIntegerField(default=1)

    # Security / lockout fields
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_password_changed_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = MyUserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        indexes = [
            models.Index(fields=("email", "is_active")),
            models.Index(fields=("email_verified",)),
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.username = (self.username or "").strip()
        self.first_name = (self.first_name or "").strip()
        self.last_name = (self.last_name or "").strip()
        super().save(*args, **kwargs)

    @property
    def token(self):
        from Authentication.services import AuthTokenService
        return AuthTokenService.issue_access_token(self)

    @property
    def is_locked(self):
        return bool(self.locked_until and timezone.now() < self.locked_until)

    def __str__(self):
        return self.email


class AuthSession(TrackingModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_sessions")
    session_key = models.CharField(max_length=64, unique=True)
    jti = models.CharField(max_length=64, unique=True)
    refresh_token_hash = models.CharField(max_length=128, unique=True, null=True, blank=True)

    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(default=timezone.now)

    user_agent = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("-issued_at",)
        indexes = [
            models.Index(fields=("user", "revoked_at")),
            models.Index(fields=("user", "expires_at")),
            models.Index(fields=("user", "last_used_at")),
        ]

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def revoke(self, reason="manual_logout"):
        self.revoked_at = timezone.now()
        self.revoked_reason = reason
        self.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])

    def __str__(self):
        return f"{self.user.email} | {self.session_key}"


class AuthAuditLog(TrackingModel):
    EVENT_CHOICES = [
        ("login_success", "Login Success"),
        ("login_failed", "Login Failed"),
        ("logout", "Logout"),
        ("password_changed", "Password Changed"),
        ("otp_sent", "OTP Sent"),
        ("otp_verified", "OTP Verified"),
        ("email_verified", "Email Verified"),
        ("session_revoked", "Session Revoked"),
        ("account_locked", "Account Locked"),
    ]

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="auth_audit_logs",
    )
    email = models.EmailField(blank=True)
    event = models.CharField(max_length=32, choices=EVENT_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "event", "created_at")),
            models.Index(fields=("email", "created_at")),
        ]

    def __str__(self):
        return f"{self.email or self.user_id} | {self.event}"


class AuthOTP(TrackingModel):
    PURPOSE_CHOICES = [
        ("password_reset", "Password Reset"),
        ("email_verification", "Email Verification"),
    ]

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="auth_otps",
    )
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)

    # Store hashed OTP only, never raw OTP.
    code_hash = models.CharField(max_length=128,null=True, blank=True)

    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("email", "purpose", "expires_at")),
            models.Index(fields=("user", "purpose", "consumed_at")),
        ]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

    @property
    def is_active_otp(self):
        return not self.is_consumed and not self.is_expired

    def mark_consumed(self):
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at", "updated_at"])

    def __str__(self):
        return f"{self.email} | {self.purpose}"