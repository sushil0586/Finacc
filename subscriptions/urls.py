from django.urls import path

from .views import TenantMembershipDetailView, TenantMembershipListCreateView


app_name = "subscriptions_api"


urlpatterns = [
    path("admin/memberships", TenantMembershipListCreateView.as_view(), name="admin-memberships"),
    path("admin/memberships/<int:membership_id>", TenantMembershipDetailView.as_view(), name="admin-membership-detail"),
]
