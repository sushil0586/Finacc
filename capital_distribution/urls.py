from django.urls import path

from .views import (
    DistributionPolicyApproveAPIView,
    DistributionPolicyCompareAPIView,
    DistributionPolicyDetailAPIView,
    DistributionPolicyListCreateAPIView,
    DistributionPolicyRejectAPIView,
    DistributionPolicySeedAPIView,
    DistributionPolicySubmitAPIView,
    DistributionPolicySupersedeAPIView,
    FormationProfileAPIView,
    CapitalDistributionRunDetailAPIView,
    CapitalDistributionRunListCalculateAPIView,
    CapitalDistributionAccountMappingAPIView,
    CapitalDistributionRunSubmitAPIView,
    CapitalDistributionRunApproveAPIView,
    CapitalDistributionRunPostAPIView,
    CapitalDistributionRunReverseAPIView,
    AppropriationStatementAPIView,
)


app_name = "capital_distribution_api"

urlpatterns = [
    path("formation/", FormationProfileAPIView.as_view(), name="formation-profile"),
    path("policies/", DistributionPolicyListCreateAPIView.as_view(), name="policy-list"),
    path("policies/seed/", DistributionPolicySeedAPIView.as_view(), name="policy-seed"),
    path("policies/<int:policy_id>/", DistributionPolicyDetailAPIView.as_view(), name="policy-detail"),
    path("policies/<int:policy_id>/submit/", DistributionPolicySubmitAPIView.as_view(), name="policy-submit"),
    path("policies/<int:policy_id>/approve/", DistributionPolicyApproveAPIView.as_view(), name="policy-approve"),
    path("policies/<int:policy_id>/reject/", DistributionPolicyRejectAPIView.as_view(), name="policy-reject"),
    path("policies/<int:policy_id>/supersede/", DistributionPolicySupersedeAPIView.as_view(), name="policy-supersede"),
    path(
        "policies/<int:policy_id>/compare/<int:other_policy_id>/",
        DistributionPolicyCompareAPIView.as_view(),
        name="policy-compare",
    ),
    path("runs/", CapitalDistributionRunListCalculateAPIView.as_view(), name="run-list-calculate"),
    path("runs/<int:run_id>/", CapitalDistributionRunDetailAPIView.as_view(), name="run-detail"),
    path("account-mappings/", CapitalDistributionAccountMappingAPIView.as_view(), name="account-mappings"),
    path("runs/<int:run_id>/submit/", CapitalDistributionRunSubmitAPIView.as_view(), name="run-submit"),
    path("runs/<int:run_id>/approve/", CapitalDistributionRunApproveAPIView.as_view(), name="run-approve"),
    path("runs/<int:run_id>/post/", CapitalDistributionRunPostAPIView.as_view(), name="run-post"),
    path("runs/<int:run_id>/reverse/", CapitalDistributionRunReverseAPIView.as_view(), name="run-reverse"),
    path("reports/appropriation-statement/", AppropriationStatementAPIView.as_view(), name="appropriation-statement"),
]
