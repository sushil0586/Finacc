from django.urls import path

from .views import (
    SubscriptionAccountCancelView,
    SubscriptionAccountAdminDetailView,
    SubscriptionAccountPlanChangeView,
    CurrentSubscriptionSnapshotView,
    PublicSubscriptionPlanListView,
    SubscriptionPlanAdminDetailView,
    SubscriptionPlanAdminListCreateView,
    TenantMembershipDetailView,
    TenantMembershipListCreateView,
    TenantMembershipPasswordResetView,
    TenantMembershipResendInviteView,
)


app_name = "subscriptions_api"


urlpatterns = [
    path("public/plans", PublicSubscriptionPlanListView.as_view(), name="public-plans"),
    path("me/summary", CurrentSubscriptionSnapshotView.as_view(), name="current-summary"),
    path("admin/accounts/<int:account_id>", SubscriptionAccountAdminDetailView.as_view(), name="admin-account-detail"),
    path("admin/accounts/<int:account_id>/change-plan", SubscriptionAccountPlanChangeView.as_view(), name="admin-account-change-plan"),
    path("admin/accounts/<int:account_id>/cancel", SubscriptionAccountCancelView.as_view(), name="admin-account-cancel"),
    path("admin/plans", SubscriptionPlanAdminListCreateView.as_view(), name="admin-plans"),
    path("admin/plans/<int:plan_id>", SubscriptionPlanAdminDetailView.as_view(), name="admin-plan-detail"),
    path("admin/memberships", TenantMembershipListCreateView.as_view(), name="admin-memberships"),
    path("admin/memberships/<int:membership_id>", TenantMembershipDetailView.as_view(), name="admin-membership-detail"),
    path("admin/memberships/<int:membership_id>/reset-password", TenantMembershipPasswordResetView.as_view(), name="admin-membership-reset-password"),
    path("admin/memberships/<int:membership_id>/resend-invite", TenantMembershipResendInviteView.as_view(), name="admin-membership-resend-invite"),
]
