from django.urls import path
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
    OnboardingCityOptionsAPIView,
    OnboardingCountryOptionsAPIView,
    OnboardingDistrictOptionsAPIView,
    OnboardingGstLookupAPIView,
    OnboardingStateOptionsAPIView,
    RegisterAndEntityOnboardingCreateAPIView,
)


app_name = "entity"

urlpatterns = [
    path("me/entities", UserEntitiesV2View.as_view(), name="entity-context-v2"),
    path("me/entities/<int:entity_id>/financial-years", UserEntityFinancialYearsView.as_view(), name="entity-context-financial-years"),
    path("me/entities/<int:entity_id>/subentities", UserEntitySubentitiesView.as_view(), name="entity-context-subentities"),
    path("me/entities/<int:entity_id>/context", UserEntityContextPatchView.as_view(), name="entity-context-patch"),
    path("me/context", UserEntityContextGetView.as_view(), name="entity-context-get"),
    path("onboarding/create/", EntityOnboardingCreateAPIView.as_view(), name="entity-onboarding-create"),
    path("onboarding/entity/<int:pk>/", EntityOnboardingDetailAPIView.as_view(), name="entity-onboarding-detail"),
    path("onboarding/register/", RegisterAndEntityOnboardingCreateAPIView.as_view(), name="entity-onboarding-register"),
    path("onboarding/meta/", EntityOnboardingMetaAPIView.as_view(), name="entity-onboarding-meta"),
    path("onboarding/options/countries/", OnboardingCountryOptionsAPIView.as_view(), name="entity-onboarding-countries"),
    path("onboarding/options/states/", OnboardingStateOptionsAPIView.as_view(), name="entity-onboarding-states"),
    path("onboarding/options/districts/", OnboardingDistrictOptionsAPIView.as_view(), name="entity-onboarding-districts"),
    path("onboarding/options/cities/", OnboardingCityOptionsAPIView.as_view(), name="entity-onboarding-cities"),
    path("onboarding/gst-lookup/", OnboardingGstLookupAPIView.as_view(), name="entity-onboarding-gst-lookup"),
]
