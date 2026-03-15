from django.conf import settings
from django.db import models
from django.utils import timezone

from helpers.models import TrackingModel


class CustomerAccount(TrackingModel):
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_CLOSED, "Closed"),
    )

    name = models.CharField(max_length=150)
    primary_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_account",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name", "id")

    def __str__(self):
        return self.name


class SubscriptionPlan(TrackingModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name", "id")

    def __str__(self):
        return self.name


class PlanLimit(TrackingModel):
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="limits")
    code = models.CharField(max_length=100)
    value = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("plan", "code")
        constraints = [
            models.UniqueConstraint(fields=("plan", "code"), name="subscriptions_plan_limit_unique"),
        ]

    def __str__(self):
        return f"{self.plan.code}:{self.code}"


class CustomerSubscription(TrackingModel):
    STATUS_TRIAL = "trial"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_TRIAL, "Trial"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past Due"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    )

    customer_account = models.ForeignKey(
        CustomerAccount,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="customer_subscriptions",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIAL)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-starts_at", "-id")

    def __str__(self):
        return f"{self.customer_account} - {self.plan}"

    @property
    def is_current(self):
        if self.status not in {self.STATUS_TRIAL, self.STATUS_ACTIVE}:
            return False
        if self.ends_at and self.ends_at <= timezone.now():
            return False
        return self.isactive


class UserEntityAccess(TrackingModel):
    SOURCE_SIGNUP = "signup"
    SOURCE_ENTITY_CREATE = "entity_create"
    SOURCE_INVITE = "invite"
    SOURCE_CHOICES = (
        (SOURCE_SIGNUP, "Signup"),
        (SOURCE_ENTITY_CREATE, "Entity Create"),
        (SOURCE_INVITE, "Invite"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entity_access_rows",
    )
    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.CASCADE,
        related_name="user_access_rows",
    )
    customer_account = models.ForeignKey(
        CustomerAccount,
        on_delete=models.CASCADE,
        related_name="entity_access_rows",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_entity_access_rows",
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_INVITE)
    is_owner = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("entity_id", "user_id")
        constraints = [
            models.UniqueConstraint(fields=("user", "entity"), name="subscriptions_user_entity_access_unique"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.entity_id}"

