from django.urls import include, path


urlpatterns = [
    path("api/auth/", include(("Authentication.urls", "Authentication_api"), namespace="Authentication_api")),
    path("api/entity/", include(("entity.context_urls", "entity_context_api"), namespace="entity_context_api")),
    path("api/rbac/", include(("rbac.urls", "rbac_api"), namespace="rbac_api")),
]
