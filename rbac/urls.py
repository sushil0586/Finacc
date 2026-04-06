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
    path("admin/bootstrap", views.RBACAdminBootstrapView.as_view(), name="admin-bootstrap"),
    path("admin/users", views.EntityUserOptionsView.as_view(), name="admin-users"),
    path("admin/users/create-and-assign", views.CreateUserWithAssignmentView.as_view(), name="admin-users-create-and-assign"),
    path("admin/access-preview", views.EffectiveAccessPreviewView.as_view(), name="admin-access-preview"),
    path("admin/audit-logs", views.AuditLogListView.as_view(), name="admin-audit-logs"),
    path("admin/templates", views.RoleTemplatesView.as_view(), name="admin-templates"),
    path("admin/permissions", views.PermissionAdminListCreateView.as_view(), name="admin-permissions"),
    path("admin/permissions/<int:pk>", views.PermissionAdminDetailView.as_view(), name="admin-permission-detail"),
    path("admin/roles", views.RoleAdminListCreateView.as_view(), name="admin-roles"),
    path("admin/roles/<int:pk>", views.RoleAdminDetailView.as_view(), name="admin-role-detail"),
    path("admin/roles/<int:pk>/permissions", views.RolePermissionsStateView.as_view(), name="admin-role-permissions"),
    path("admin/roles/<int:pk>/clone", views.RoleCloneView.as_view(), name="admin-role-clone"),
    path("admin/roles/<int:pk>/apply-template", views.RoleTemplateApplyView.as_view(), name="admin-role-apply-template"),
    path("admin/menus", views.MenuAdminListCreateView.as_view(), name="admin-menus"),
    path("admin/menu-tree", views.MenuAdminTreeView.as_view(), name="admin-menu-tree"),
    path("admin/menus/<int:pk>", views.MenuAdminDetailView.as_view(), name="admin-menu-detail"),
    path("admin/menus/<int:pk>/permissions", views.MenuPermissionsStateView.as_view(), name="admin-menu-permissions"),
    path("admin/assignments", views.UserRoleAssignmentAdminListCreateView.as_view(), name="admin-assignments"),
    path("admin/assignments/<int:pk>", views.UserRoleAssignmentAdminDetailView.as_view(), name="admin-assignment-detail"),
    path("admin/assignments/bulk", views.BulkAssignmentView.as_view(), name="admin-assignments-bulk"),
]
