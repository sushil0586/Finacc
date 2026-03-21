from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True,blank=True, null=True,)
    updated_at = models.DateTimeField(auto_now=True,blank=True, null=True,)

    class Meta:
        abstract = True


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        abstract = True


class CustomerAccount(TimeStampedModel, SoftDeleteModel):
    class AccountType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        BUSINESS = "business", "Business"
        ENTERPRISE = "enterprise", "Enterprise"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, unique=True,blank=True, null=True,)

    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BUSINESS,blank=True, null=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,blank=True, null=True,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_customer_accounts",blank=True, null=True,
    )

    billing_email = models.EmailField(blank=True, null=True)
    external_customer_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        unique=True,
        help_text="External billing customer ID, e.g. Stripe customer ID.",
    )
    billing_provider = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Billing provider slug, e.g. stripe.",
    )

    timezone = models.CharField(max_length=64, default="UTC")
    country = models.CharField(max_length=2, blank=True, null=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "customer_accounts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status"]),
            models.Index(fields=["owner"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @property
    def is_billable(self):
        return self.status in {self.Status.ACTIVE, self.Status.SUSPENDED}

    @property
    def is_usable(self):
        return self.status == self.Status.ACTIVE and self.is_active


class SubscriptionPlan(TimeStampedModel, SoftDeleteModel):
    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"
        LIFETIME = "lifetime", "Lifetime"
        CUSTOM = "custom", "Custom"

    class PlanTier(models.TextChoices):
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        PRO = "pro", "Pro"
        BUSINESS = "business", "Business"
        ENTERPRISE = "enterprise", "Enterprise"

    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    tier = models.CharField(
        max_length=20,
        choices=PlanTier.choices,
        default=PlanTier.FREE,blank=True, null=True,
    )
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTHLY,blank=True, null=True,
    )

    price_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="INR",blank=True, null=True,)

    trial_days = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)

    is_public = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    external_price_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        unique=True,
        help_text="External billing price ID, e.g. Stripe price ID.",
    )
    billing_provider = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Billing provider slug, e.g. stripe.",
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "subscription_plans"
        ordering = ["sort_order", "price_amount", "created_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["tier"]),
            models.Index(fields=["is_public"]),
            models.Index(fields=["is_default"]),
        ]

    def __str__(self):
        return f"{self.name} [{self.code}]"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            type(self).objects.exclude(pk=self.pk).update(is_default=False)


class PlanLimit(TimeStampedModel):
    class LimitType(models.TextChoices):
        INTEGER = "integer", "Integer"
        BOOLEAN = "boolean", "Boolean"
        TEXT = "text", "Text"

    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        related_name="limits",
    )

    key = models.CharField(max_length=100)
    label = models.CharField(max_length=150, blank=True)

    limit_type = models.CharField(
        max_length=20,
        choices=LimitType.choices,
        default=LimitType.INTEGER,blank=True, null=True,
    )

    int_value = models.BigIntegerField(blank=True, null=True)
    bool_value = models.BooleanField(blank=True, null=True)
    text_value = models.CharField(max_length=255, blank=True, null=True)

    is_unlimited = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "plan_limits"
        ordering = ["plan_id", "key"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "key"], name="uq_plan_limit_plan_key"),
        ]
        indexes = [
            models.Index(fields=["plan", "key"]),
            models.Index(fields=["key"]),
        ]

    def __str__(self):
        return f"{self.plan.code}:{self.key}"

    @property
    def value(self):
        if self.is_unlimited:
            return None
        if self.limit_type == self.LimitType.INTEGER:
            return self.int_value
        if self.limit_type == self.LimitType.BOOLEAN:
            return self.bool_value
        return self.text_value

    def clean(self):
        value_count = sum([
            self.int_value is not None,
            self.bool_value is not None,
            bool(self.text_value),
        ])

        if self.is_unlimited:
            if value_count > 0:
                raise ValidationError("Unlimited limits cannot also store a concrete value.")
            return

        if self.limit_type == self.LimitType.INTEGER:
            if self.int_value is None:
                raise ValidationError({"int_value": "Required for integer limits."})
            if self.bool_value is not None or self.text_value:
                raise ValidationError("Only int_value may be set for integer limits.")

        elif self.limit_type == self.LimitType.BOOLEAN:
            if self.bool_value is None:
                raise ValidationError({"bool_value": "Required for boolean limits."})
            if self.int_value is not None or self.text_value:
                raise ValidationError("Only bool_value may be set for boolean limits.")

        elif self.limit_type == self.LimitType.TEXT:
            if not self.text_value:
                raise ValidationError({"text_value": "Required for text limits."})
            if self.int_value is not None or self.bool_value is not None:
                raise ValidationError("Only text_value may be set for text limits.")


class CustomerSubscription(TimeStampedModel, SoftDeleteModel):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        PAUSED = "paused", "Paused"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    customer_account = models.ForeignKey(
        CustomerAccount,
        on_delete=models.CASCADE,
        related_name="subscriptions",blank=True, null=True,
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="customer_subscriptions",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TRIALING,blank=True, null=True,  
    )

    started_at = models.DateTimeField(default=timezone.now,blank=True, null=True,)
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    current_period_start = models.DateTimeField(blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)
    canceled_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)

    auto_renew = models.BooleanField(default=True,blank=True, null=True,)
    seats_purchased = models.PositiveIntegerField(default=1,blank=True, null=True,)

    external_subscription_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        unique=True,
        help_text="External billing subscription ID, e.g. Stripe subscription ID.",
    )
    billing_provider = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Billing provider slug, e.g. stripe.",
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "customer_subscriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer_account", "status"]),
            models.Index(fields=["plan"]),
            models.Index(fields=["external_subscription_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_account"],
                condition=Q(
                    is_active=True,
                    status__in=["trialing", "active", "past_due", "paused"],
                    ended_at__isnull=True,
                ),
                name="uq_one_current_subscription_per_account",
            ),
        ]

    def __str__(self):
        return f"{self.customer_account.slug} -> {self.plan.code} ({self.status})"

    @property
    def is_current(self):
        now = timezone.now()

        if not self.is_active:
            return False

        if self.status not in {
            self.Status.TRIALING,
            self.Status.ACTIVE,
            self.Status.PAST_DUE,
            self.Status.PAUSED,
        }:
            return False

        if self.ended_at and self.ended_at <= now:
            return False

        return True

    def clean(self):
        if self.current_period_start and self.current_period_end:
            if self.current_period_end < self.current_period_start:
                raise ValidationError(
                    {"current_period_end": "Cannot be earlier than current_period_start."}
                )

        if self.trial_ends_at and self.trial_ends_at < self.started_at:
            raise ValidationError(
                {"trial_ends_at": "Cannot be earlier than started_at."}
            )

        if self.ended_at and self.ended_at < self.started_at:
            raise ValidationError(
                {"ended_at": "Cannot be earlier than started_at."}
            )

        if self.canceled_at and self.canceled_at < self.started_at:
            raise ValidationError(
                {"canceled_at": "Cannot be earlier than started_at."}
            )


class UserEntityAccess(TimeStampedModel, SoftDeleteModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"
        BILLING = "billing", "Billing"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_accesses",
    )
    customer_account = models.ForeignKey(
        CustomerAccount,
        on_delete=models.CASCADE,
        related_name="user_accesses",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,blank=True, null=True,
    )

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_customer_accesses"
    )
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True, null=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "user_entity_access"
        ordering = ["customer_account_id", "user_id", "role"]
        indexes = [
            models.Index(fields=["user", "customer_account"]),
            models.Index(fields=["customer_account", "role"]),
            models.Index(fields=["expires_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "customer_account"],
                condition=Q(is_active=True),
                name="uq_active_account_membership_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.customer_account.slug} [{self.role}]"

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def clean(self):
        if self.expires_at and self.expires_at <= self.granted_at:
            raise ValidationError(
                {"expires_at": "Must be later than granted_at."}
            )