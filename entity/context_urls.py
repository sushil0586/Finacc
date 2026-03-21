from django.urls import path

from entity.context_views import (
    UserEntitiesV2View,
    UserEntityContextGetView,
    UserEntityContextPatchView,
    UserEntityFinancialYearsView,
    UserEntitySubentitiesView,
)


app_name = "entity_context_api"

urlpatterns = [
    path("me/entities", UserEntitiesV2View.as_view(), name="entity-context-v2"),
    path("me/entities/<int:entity_id>/financial-years", UserEntityFinancialYearsView.as_view(), name="entity-context-financial-years"),
    path("me/entities/<int:entity_id>/subentities", UserEntitySubentitiesView.as_view(), name="entity-context-subentities"),
    path("me/entities/<int:entity_id>/context", UserEntityContextPatchView.as_view(), name="entity-context-patch"),
    path("me/context", UserEntityContextGetView.as_view(), name="entity-context-get"),
]
