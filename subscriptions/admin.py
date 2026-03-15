from django.contrib import admin

from .models import CustomerAccount, CustomerSubscription, PlanLimit, SubscriptionPlan, UserEntityAccess


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "primary_user", "status", "isactive")
    search_fields = ("name", "primary_user__email", "primary_user__username")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "is_default", "isactive")
    search_fields = ("code", "name")


@admin.register(PlanLimit)
class PlanLimitAdmin(admin.ModelAdmin):
    list_display = ("id", "plan", "code", "value", "isactive")
    search_fields = ("plan__code", "code")


@admin.register(CustomerSubscription)
class CustomerSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_account", "plan", "status", "starts_at", "ends_at", "isactive")
    search_fields = ("customer_account__name", "plan__code")


@admin.register(UserEntityAccess)
class UserEntityAccessAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "entity", "customer_account", "source", "is_owner", "isactive")
    search_fields = ("user__email", "entity__entityname", "customer_account__name")

