from django.contrib import admin
from django.db.models import Count

from .models import CustomerAccount, CustomerSubscription, PlanLimit, SubscriptionPlan, UserEntityAccess
from .services import SubscriptionLimitCodes, SubscriptionService


class PlanLimitInline(admin.TabularInline):
    model = PlanLimit
    extra = 0
    fields = (
        "key",
        "label",
        "limit_type",
        "int_value",
        "bool_value",
        "text_value",
        "is_unlimited",
    )
    readonly_fields = ()
    show_change_link = True


class CustomerSubscriptionInline(admin.TabularInline):
    model = CustomerSubscription
    extra = 0
    fields = (
        "plan",
        "status",
        "started_at",
        "trial_ends_at",
        "current_period_start",
        "current_period_end",
        "ended_at",
        "auto_renew",
        "is_active",
    )
    readonly_fields = ()
    show_change_link = True


class UserEntityAccessInline(admin.TabularInline):
    model = UserEntityAccess
    extra = 0
    fields = (
        "user",
        "role",
        "granted_by",
        "granted_at",
        "expires_at",
        "is_active",
    )
    readonly_fields = ()
    autocomplete_fields = ("user", "granted_by")
    show_change_link = True


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "owner",
        "account_type",
        "status",
        "active_subscription_plan",
        "active_subscription_status",
        "member_count",
        "billing_provider",
        "external_customer_id",
        "is_active",
        "created_at",
    )
    list_filter = (
        "account_type",
        "status",
        "is_active",
        "billing_provider",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "id",
        "name",
        "slug",
        "owner__email",
        "owner__username",
        "billing_email",
        "external_customer_id",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "member_count",
        "subscription_count",
        "current_subscription_summary",
        "feature_summary",
        "usage_summary",
    )
    autocomplete_fields = ("owner",)
    ordering = ("-created_at",)
    inlines = [CustomerSubscriptionInline, UserEntityAccessInline]

    fieldsets = (
        (
            "Account",
            {
                "fields": (
                    "name",
                    "slug",
                    "owner",
                    "account_type",
                    "status",
                    "is_active",
                )
            },
        ),
        (
            "Billing",
            {
                "fields": (
                    "billing_email",
                    "billing_provider",
                    "external_customer_id",
                )
            },
        ),
        (
            "Locale",
            {
                "fields": (
                    "timezone",
                    "country",
                )
            },
        ),
        (
            "Insights",
            {
                "fields": (
                    "member_count",
                    "subscription_count",
                    "current_subscription_summary",
                    "feature_summary",
                    "usage_summary",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("owner").prefetch_related("subscriptions", "user_accesses")

    @admin.display(ordering="created_at", description="Members")
    def member_count(self, obj):
        return obj.user_accesses.filter(is_active=True).count()

    @admin.display(description="Subscriptions")
    def subscription_count(self, obj):
        return obj.subscriptions.count()

    @admin.display(description="Current plan")
    def active_subscription_plan(self, obj):
        subscription = (
            obj.subscriptions.filter(
                is_active=True,
                ended_at__isnull=True,
                status__in=[
                    CustomerSubscription.Status.TRIALING,
                    CustomerSubscription.Status.ACTIVE,
                    CustomerSubscription.Status.PAST_DUE,
                    CustomerSubscription.Status.PAUSED,
                ],
            )
            .select_related("plan")
            .order_by("-started_at", "-id")
            .first()
        )
        return subscription.plan.code if subscription and subscription.plan else "-"

    @admin.display(description="Subscription status")
    def active_subscription_status(self, obj):
        subscription = (
            obj.subscriptions.filter(
                is_active=True,
                ended_at__isnull=True,
                status__in=[
                    CustomerSubscription.Status.TRIALING,
                    CustomerSubscription.Status.ACTIVE,
                    CustomerSubscription.Status.PAST_DUE,
                    CustomerSubscription.Status.PAUSED,
                ],
            )
            .order_by("-started_at", "-id")
            .first()
        )
        return subscription.status if subscription else "-"

    @admin.display(description="Current subscription")
    def current_subscription_summary(self, obj):
        subscription = (
            obj.subscriptions.filter(
                is_active=True,
                ended_at__isnull=True,
                status__in=[
                    CustomerSubscription.Status.TRIALING,
                    CustomerSubscription.Status.ACTIVE,
                    CustomerSubscription.Status.PAST_DUE,
                    CustomerSubscription.Status.PAUSED,
                ],
            )
            .select_related("plan")
            .order_by("-started_at", "-id")
            .first()
        )
        if not subscription:
            return "No active/current subscription"
        return (
            f"Plan={subscription.plan.name} | "
            f"Status={subscription.status} | "
            f"Started={subscription.started_at} | "
            f"Period End={subscription.current_period_end or '-'}"
        )

    @admin.display(description="Features")
    def feature_summary(self, obj):
        try:
            flags = SubscriptionService.get_feature_flags(customer_account=obj)
        except Exception:
            return "-"
        enabled = [key.replace("feature_", "").replace("_", " ").title() for key, value in flags.items() if value]
        return ", ".join(enabled) if enabled else "No features enabled"

    @admin.display(description="Usage snapshot")
    def usage_summary(self, obj):
        try:
            snapshot = SubscriptionService.build_subscription_snapshot(customer_account=obj)
        except Exception:
            return "-"
        usage = snapshot.get("usage", {})
        return (
            f"Entities {usage.get('entities_used', 0)}/{snapshot.get('limits', {}).get(SubscriptionLimitCodes.MAX_ENTITIES, '∞')} | "
            f"Users {usage.get('account_users_used', 0)}/{snapshot.get('limits', {}).get(SubscriptionLimitCodes.MAX_ENTITY_USERS, '∞')}"
        )


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "name",
        "tier",
        "billing_interval",
        "price_amount",
        "currency",
        "trial_days",
        "is_default",
        "is_public",
        "billing_provider",
        "limit_count",
        "limit_summary",
        "feature_summary",
        "subscriber_count",
        "is_active",
    )
    list_filter = (
        "tier",
        "billing_interval",
        "is_default",
        "is_public",
        "is_active",
        "billing_provider",
        "created_at",
    )
    search_fields = (
        "code",
        "name",
        "description",
        "external_price_id",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "limit_count",
        "subscriber_count",
        "feature_summary",
        "limit_summary",
    )
    ordering = ("sort_order", "price_amount", "created_at")
    inlines = [PlanLimitInline]

    fieldsets = (
        (
            "Plan",
            {
                "fields": (
                    "name",
                    "code",
                    "description",
                    "tier",
                    "billing_interval",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "price_amount",
                    "currency",
                    "trial_days",
                    "sort_order",
                )
            },
        ),
        (
            "Visibility",
            {
                "fields": (
                    "is_public",
                    "is_default",
                    "is_active",
                )
            },
        ),
        (
            "Billing Integration",
            {
                "fields": (
                    "billing_provider",
                    "external_price_id",
                )
            },
        ),
        (
            "Insights",
            {
                "fields": (
                    "limit_count",
                    "limit_summary",
                    "feature_summary",
                    "subscriber_count",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("limits", "customer_subscriptions")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        SubscriptionService.ensure_plan_limit_catalog(plan=obj)

    @admin.display(description="Limits")
    def limit_count(self, obj):
        return obj.limits.count()

    @admin.display(description="Limit summary")
    def limit_summary(self, obj):
        limits = {limit.key: limit for limit in obj.limits.all()}
        max_entities = limits.get(SubscriptionLimitCodes.MAX_ENTITIES)
        max_users = limits.get(SubscriptionLimitCodes.MAX_ENTITY_USERS)
        entity_value = "Unlimited" if max_entities and max_entities.is_unlimited else (max_entities.value if max_entities else "-")
        user_value = "Unlimited" if max_users and max_users.is_unlimited else (max_users.value if max_users else "-")
        return f"Entities={entity_value} | Users={user_value}"

    @admin.display(description="Feature summary")
    def feature_summary(self, obj):
        enabled = []
        for limit in obj.limits.all():
            if limit.key.startswith("feature_") and bool(limit.value):
                enabled.append(limit.key.replace("feature_", "").replace("_", " ").title())
        return ", ".join(sorted(enabled)) if enabled else "No enabled features"

    @admin.display(description="Subscribers")
    def subscriber_count(self, obj):
        return obj.customer_subscriptions.filter(is_active=True).count()


@admin.register(PlanLimit)
class PlanLimitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "plan",
        "key",
        "label",
        "limit_type",
        "resolved_value",
        "is_unlimited",
        "plan_code",
        "created_at",
    )
    list_filter = (
        "limit_type",
        "is_unlimited",
        "plan__tier",
        "plan__billing_interval",
    )
    search_fields = (
        "plan__code",
        "plan__name",
        "key",
        "label",
    )
    readonly_fields = (
        "resolved_value",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("plan",)
    ordering = ("plan__code", "key")

    fieldsets = (
        (
            "Limit",
            {
                "fields": (
                    "plan",
                    "key",
                    "label",
                    "limit_type",
                    "is_unlimited",
                )
            },
        ),
        (
            "Values",
            {
                "fields": (
                    "int_value",
                    "bool_value",
                    "text_value",
                    "resolved_value",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Value")
    def resolved_value(self, obj):
        return "Unlimited" if obj.is_unlimited else obj.value

    @admin.display(ordering="plan__code", description="Plan code")
    def plan_code(self, obj):
        return obj.plan.code


@admin.register(CustomerSubscription)
class CustomerSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_account",
        "plan",
        "status",
        "started_at",
        "trial_ends_at",
        "current_period_start",
        "current_period_end",
        "ended_at",
        "auto_renew",
        "seats_purchased",
        "billing_provider",
        "external_subscription_id",
        "is_current_display",
        "limits_snapshot",
        "is_active",
    )
    list_filter = (
        "status",
        "auto_renew",
        "is_active",
        "billing_provider",
        "plan__tier",
        "plan__billing_interval",
        "created_at",
    )
    search_fields = (
        "customer_account__name",
        "customer_account__slug",
        "plan__code",
        "plan__name",
        "external_subscription_id",
    )
    readonly_fields = (
        "is_current_display",
        "limits_snapshot",
        "features_snapshot",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("customer_account", "plan")
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Subscription",
            {
                "fields": (
                    "customer_account",
                    "plan",
                    "status",
                    "is_active",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "started_at",
                    "trial_ends_at",
                    "current_period_start",
                    "current_period_end",
                    "canceled_at",
                    "ended_at",
                    "auto_renew",
                    "is_current_display",
                )
            },
        ),
        (
            "Commercial",
            {
                "fields": (
                    "seats_purchased",
                    "limits_snapshot",
                    "features_snapshot",
                )
            },
        ),
        (
            "Billing Integration",
            {
                "fields": (
                    "billing_provider",
                    "external_subscription_id",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("customer_account", "plan")

    @admin.display(boolean=True, description="Is current")
    def is_current_display(self, obj):
        return obj.is_current

    @admin.display(description="Limits snapshot")
    def limits_snapshot(self, obj):
        try:
            limits = SubscriptionService.get_all_plan_limits(customer_account=obj.customer_account)
        except Exception:
            return "-"
        return (
            f"Entities={limits.get(SubscriptionLimitCodes.MAX_ENTITIES, '-')}, "
            f"Users={limits.get(SubscriptionLimitCodes.MAX_ENTITY_USERS, '-')}"
        )

    @admin.display(description="Features snapshot")
    def features_snapshot(self, obj):
        try:
            flags = SubscriptionService.get_feature_flags(customer_account=obj.customer_account)
        except Exception:
            return "-"
        enabled = [key.replace("feature_", "").replace("_", " ").title() for key, value in flags.items() if value]
        return ", ".join(enabled) if enabled else "No features enabled"


@admin.register(UserEntityAccess)
class UserEntityAccessAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "customer_account",
        "role",
        "granted_by",
        "granted_at",
        "expires_at",
        "is_expired_display",
        "is_active",
        "created_at",
    )
    list_filter = (
        "role",
        "is_active",
        "customer_account__status",
        "granted_at",
        "expires_at",
        "created_at",
    )
    search_fields = (
        "user__email",
        "user__username",
        "customer_account__name",
        "customer_account__slug",
        "granted_by__email",
        "granted_by__username",
    )
    readonly_fields = (
        "is_expired_display",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("user", "customer_account", "granted_by")
    ordering = ("customer_account_id", "user_id", "role")

    fieldsets = (
        (
            "Access",
            {
                "fields": (
                    "user",
                    "customer_account",
                    "role",
                    "is_active",
                )
            },
        ),
        (
            "Grant",
            {
                "fields": (
                    "granted_by",
                    "granted_at",
                    "expires_at",
                    "is_expired_display",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "customer_account", "granted_by")

    @admin.display(boolean=True, description="Expired")
    def is_expired_display(self, obj):
        return obj.is_expired
