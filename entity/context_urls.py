from django.urls import path

from entity.context_views import UserEntitiesV2View


app_name = "entity_context_api"

urlpatterns = [
    path("me/entities", UserEntitiesV2View.as_view(), name="entity-context-v2"),
]
