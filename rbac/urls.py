from django.urls import path

from . import views


app_name = "rbac_api"

urlpatterns = [
    path("health", views.RBACHealthView.as_view(), name="health"),
    path("permissions", views.PermissionListView.as_view(), name="permissions"),
    path("roles", views.RoleListView.as_view(), name="roles"),
    path("menus", views.MenuTreeView.as_view(), name="menus"),
    path("me/roles", views.UserRolesView.as_view(), name="me-roles"),
    path("me/permissions", views.UserPermissionsView.as_view(), name="me-permissions"),
    path("me/menus", views.UserMenusView.as_view(), name="me-menus"),
]
