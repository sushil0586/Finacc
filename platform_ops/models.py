import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class PlatformPermission(models.Model):
    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return self.code


class PlatformRole(models.Model):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(
        PlatformPermission,
        related_name="roles",
        blank=True,
    )
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "code")

    def __str__(self):
        return self.name


class PlatformUserRole(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_role_assignments",
    )
    role = models.ForeignKey(
        PlatformRole,
        on_delete=models.PROTECT,
        related_name="user_assignments",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="platform_roles_granted",
    )
    valid_from = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user_id", "role_id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role"),
                condition=Q(is_active=True),
                name="uq_active_platform_user_role",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "is_active", "valid_from", "expires_at"),
                name="ix_platform_role_effective",
            ),
        ]

    def clean(self):
        if self.expires_at and self.expires_at <= self.valid_from:
            raise ValidationError({"expires_at": "Must be later than valid_from."})
        if self.revoked_at and self.is_active:
            raise ValidationError({"is_active": "A revoked assignment cannot remain active."})

    @property
    def is_effective(self):
        now = timezone.now()
        return (
            self.is_active
            and self.revoked_at is None
            and self.valid_from <= now
            and (self.expires_at is None or self.expires_at > now)
            and self.role.is_active
            and self.user.is_active
        )

    def __str__(self):
        return f"{self.user_id} -> {self.role.code}"


class ImmutableAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Platform audit events are immutable.")

    def delete(self):
        raise ValidationError("Platform audit events are immutable.")


class PlatformAuditEvent(models.Model):
    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        DENIED = "denied", "Denied"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="platform_audit_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=120, db_index=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, db_index=True)
    permission_code = models.CharField(max_length=120, blank=True)
    customer_account_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    entity_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("actor", "created_at"), name="ix_platform_audit_actor"),
            models.Index(fields=("event_type", "outcome"), name="ix_platform_audit_event"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Platform audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Platform audit events are immutable.")

    def __str__(self):
        return f"{self.event_type} ({self.outcome})"


class PlatformOperationRequest(models.Model):
    class OperationType(models.TextChoices):
        ONBOARD_CUSTOMER = "onboard_customer", "Onboard customer"
        CUSTOMER_CONTACT_UPDATE = "customer_contact_update", "Update customer contacts"
        CUSTOMER_STATUS_UPDATE = "customer_status_update", "Update customer status"
        ADD_ENTITY_BRANCH = "add_entity_branch", "Add entity branch"
        ADD_ENTITY_FINANCIAL_YEAR = "add_entity_financial_year", "Add entity financial year"
        UPDATE_ENTITY_GST_REGISTRATION = "update_entity_gst_registration", "Update entity GST registration"
        REPAIR_ENTITY_NUMBERING = "repair_entity_numbering", "Repair entity document numbering"
        REPAIR_ENTITY_POSTING_MAPPINGS = "repair_entity_posting_mappings", "Repair required entity posting mappings"
        REPAIR_ENTITY_RBAC_ROLES = "repair_entity_rbac_roles", "Repair missing entity RBAC roles"
        REPAIR_ENTITY_CATALOG_DEFAULTS = "repair_entity_catalog_defaults", "Repair missing entity catalog defaults"
        REPAIR_ENTITY_ASSET_DEFAULTS = "repair_entity_asset_defaults", "Repair missing entity asset defaults"
        REPAIR_ENTITY_TRADE_SETTINGS = "repair_entity_trade_settings", "Repair missing purchase and sales settings"
        CHANGE_SUBSCRIPTION_PLAN = "change_subscription_plan", "Change subscription plan"
        UPDATE_TENANT_MEMBERSHIP = "update_tenant_membership", "Update tenant membership"
        INVITE_TENANT_USER = "invite_tenant_user", "Invite tenant user"
        RESEND_TENANT_INVITATION = "resend_tenant_invitation", "Resend tenant invitation"
        TRANSFER_CUSTOMER_OWNERSHIP = "transfer_customer_ownership", "Transfer customer ownership"
        CHANGE_PLATFORM_ROLE = "change_platform_role", "Change platform operator role"
        REVOKE_PLATFORM_SESSIONS = "revoke_platform_sessions", "Revoke platform operator sessions"

    class Risk(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        VALIDATED = "validated", "Validated"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        RETRY_QUEUED = "retry_queued", "Retry queued"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    correlation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    operation_type = models.CharField(max_length=50, choices=OperationType.choices, db_index=True)
    risk = models.CharField(max_length=20, choices=Risk.choices, default=Risk.MEDIUM)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.VALIDATED, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="platform_operations_requested",
    )
    reason = models.CharField(max_length=500)
    ticket_reference = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=120)
    payload_hash = models.CharField(max_length=64)
    request_snapshot = models.JSONField()
    validation_snapshot = models.JSONField(default=dict)
    result_snapshot = models.JSONField(default=dict, blank=True)
    customer_account_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    entity_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    subscription_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    membership_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    expected_target_version = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=120, blank=True)
    failure_message = models.CharField(max_length=500, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="platform_operations_cancelled",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("requested_by", "idempotency_key"),
                name="uq_platform_operation_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=("operation_type", "status", "created_at"), name="ix_platform_operation_queue"),
        ]


class PlatformProvisioningJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    operation = models.OneToOneField(
        PlatformOperationRequest,
        on_delete=models.PROTECT,
        related_name="provisioning_job",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    current_stage = models.CharField(max_length=80, blank=True)
    completed_stages = models.JSONField(default=list, blank=True)
    stage_results = models.JSONField(default=dict, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)


class PlatformOperationApproval(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    operation = models.ForeignKey(
        PlatformOperationRequest,
        on_delete=models.PROTECT,
        related_name="approvals",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="platform_operation_decisions",
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    comment = models.CharField(max_length=500)
    target_version = models.DateTimeField()
    decided_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        ordering = ("-decided_at",)
        constraints = [
            models.UniqueConstraint(fields=("operation", "decided_by"), name="uq_platform_approval_approver"),
        ]

    def clean(self):
        if self.operation_id and self.decided_by_id == self.operation.requested_by_id:
            raise ValidationError({"decided_by": "The requester cannot approve or reject their own operation."})

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Platform approval decisions are immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Platform approval decisions are immutable.")


class CustomerServiceRequest(models.Model):
    class RequestType(models.TextChoices):
        ACCOUNT_CHANGE = "account_change", "Account change"
        ENTITY_CHANGE = "entity_change", "Entity change"
        SUBSCRIPTION_CHANGE = "subscription_change", "Subscription change"
        USER_ACCESS = "user_access", "User access"
        COMPLIANCE_SETUP = "compliance_setup", "Compliance setup"
        TECHNICAL_SUPPORT = "technical_support", "Technical support"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_REVIEW = "in_review", "In review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"

    customer_account = models.ForeignKey(
        "subscriptions.CustomerAccount",
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.PROTECT,
        related_name="customer_service_requests",
        null=True,
        blank=True,
    )
    request_type = models.CharField(max_length=40, choices=RequestType.choices, db_index=True)
    subject = models.CharField(max_length=180)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_service_requests_submitted",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_service_requests_assigned",
        null=True,
        blank=True,
    )
    operator_note = models.TextField(blank=True)
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("customer_account", "status", "created_at"), name="ix_service_request_customer"),
            models.Index(fields=("status", "priority", "created_at"), name="ix_service_request_queue"),
        ]


class CustomerServiceRequestEvent(models.Model):
    request = models.ForeignKey(CustomerServiceRequest, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_service_request_events")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("created_at", "id")

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Customer request events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Customer request events are immutable.")
