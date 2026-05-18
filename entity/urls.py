from django.urls import path
from entity.approval_policy_views import (
    EntityApprovalPolicyDetailAPIView,
    EntityApprovalPolicyListCreateAPIView,
    EntityApprovalPolicyMetaAPIView,
)
from entity.approval_request_views import (
    ApprovalRequestApproveAPIView,
    ApprovalRequestCancelAPIView,
    ApprovalRequestDetailAPIView,
    ApprovalRequestListAPIView,
    ApprovalRequestLockAPIView,
    ApprovalRequestRejectAPIView,
)
from entity.context_views import (
    UserEntitiesV2View,
    UserEntityContextGetView,
    UserEntityContextPatchView,
    UserEntityFinancialYearsView,
    UserEntitySubentitiesView,
)
from entity.onboarding_views import (
    EntityOnboardingCreateAPIView,
    EntityOnboardingDetailAPIView,
    EntityOnboardingMetaAPIView,
    EntityOnboardingSubmitAPIView,
    OnboardingCityOptionsAPIView,
    OnboardingCountryOptionsAPIView,
    OnboardingDistrictOptionsAPIView,
    OnboardingGstLookupAPIView,
    OnboardingStateOptionsAPIView,
    RegisterAndEntityOnboardingCreateAPIView,
)
from entity.employment_views import (
    EntityEmploymentHierarchyAPIView,
    EntityEmploymentManagerListAPIView,
    EntityEmploymentMetaAPIView,
    EntityEmploymentProfileDetailAPIView,
    EntityEmploymentProfileListCreateAPIView,
)
from entity.notification_views import (
    UserNotificationListAPIView,
    UserNotificationMarkAllReadAPIView,
    UserNotificationMarkReadAPIView,
    UserNotificationUnreadCountAPIView,
)
from entity.org_unit_views import (
    EntityOrgUnitDetailAPIView,
    EntityOrgUnitListCreateAPIView,
    EntityOrgUnitMetaAPIView,
)


app_name = "entity"

urlpatterns = [
    path("me/entities", UserEntitiesV2View.as_view(), name="entity-context-v2"),
    path("me/entities/<int:entity_id>/financial-years", UserEntityFinancialYearsView.as_view(), name="entity-context-financial-years"),
    path("me/entities/<int:entity_id>/subentities", UserEntitySubentitiesView.as_view(), name="entity-context-subentities"),
    path("me/entities/<int:entity_id>/context", UserEntityContextPatchView.as_view(), name="entity-context-patch"),
    path("me/context", UserEntityContextGetView.as_view(), name="entity-context-get"),
    path("onboarding/submit/", EntityOnboardingSubmitAPIView.as_view(), name="entity-onboarding-submit"),
    path("onboarding/create/", EntityOnboardingCreateAPIView.as_view(), name="entity-onboarding-create"),
    path("onboarding/entity/<int:pk>/", EntityOnboardingDetailAPIView.as_view(), name="entity-onboarding-detail"),
    path("onboarding/register/", RegisterAndEntityOnboardingCreateAPIView.as_view(), name="entity-onboarding-register"),
    path("onboarding/meta/", EntityOnboardingMetaAPIView.as_view(), name="entity-onboarding-meta"),
    path("onboarding/options/countries/", OnboardingCountryOptionsAPIView.as_view(), name="entity-onboarding-countries"),
    path("onboarding/options/states/", OnboardingStateOptionsAPIView.as_view(), name="entity-onboarding-states"),
    path("onboarding/options/districts/", OnboardingDistrictOptionsAPIView.as_view(), name="entity-onboarding-districts"),
    path("onboarding/options/cities/", OnboardingCityOptionsAPIView.as_view(), name="entity-onboarding-cities"),
    path("onboarding/gst-lookup/", OnboardingGstLookupAPIView.as_view(), name="entity-onboarding-gst-lookup"),
    path("org-units/meta/", EntityOrgUnitMetaAPIView.as_view(), name="entity-org-unit-meta"),
    path("org-units/", EntityOrgUnitListCreateAPIView.as_view(), name="entity-org-unit-list"),
    path("org-units/<int:pk>/", EntityOrgUnitDetailAPIView.as_view(), name="entity-org-unit-detail"),
    path("approval-policies/meta/", EntityApprovalPolicyMetaAPIView.as_view(), name="entity-approval-policy-meta"),
    path("approval-policies/", EntityApprovalPolicyListCreateAPIView.as_view(), name="entity-approval-policy-list"),
    path("approval-policies/<int:pk>/", EntityApprovalPolicyDetailAPIView.as_view(), name="entity-approval-policy-detail"),
    path("approval-requests/", ApprovalRequestListAPIView.as_view(), name="entity-approval-request-list"),
    path("approval-requests/<int:pk>/", ApprovalRequestDetailAPIView.as_view(), name="entity-approval-request-detail"),
    path("approval-requests/<int:pk>/approve/", ApprovalRequestApproveAPIView.as_view(), name="entity-approval-request-approve"),
    path("approval-requests/<int:pk>/reject/", ApprovalRequestRejectAPIView.as_view(), name="entity-approval-request-reject"),
    path("approval-requests/<int:pk>/cancel/", ApprovalRequestCancelAPIView.as_view(), name="entity-approval-request-cancel"),
    path("approval-requests/<int:pk>/lock/", ApprovalRequestLockAPIView.as_view(), name="entity-approval-request-lock"),
    path("notifications/", UserNotificationListAPIView.as_view(), name="entity-notification-list"),
    path("notifications/unread-count/", UserNotificationUnreadCountAPIView.as_view(), name="entity-notification-unread-count"),
    path("notifications/mark-all-read/", UserNotificationMarkAllReadAPIView.as_view(), name="entity-notification-mark-all-read"),
    path("notifications/<int:pk>/mark-read/", UserNotificationMarkReadAPIView.as_view(), name="entity-notification-mark-read"),
    path("employment/meta/", EntityEmploymentMetaAPIView.as_view(), name="entity-employment-meta"),
    path("employment/managers/", EntityEmploymentManagerListAPIView.as_view(), name="entity-employment-managers"),
    path("employment/hierarchy/", EntityEmploymentHierarchyAPIView.as_view(), name="entity-employment-hierarchy"),
    path("employment/", EntityEmploymentProfileListCreateAPIView.as_view(), name="entity-employment-list"),
    path("employment/<int:pk>/", EntityEmploymentProfileDetailAPIView.as_view(), name="entity-employment-detail"),
]
