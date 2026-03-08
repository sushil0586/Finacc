from django.contrib import admin

from .models import (
    DataAccessPolicy,
    Menu,
    MenuPermission,
    Permission,
    Role,
    RoleDataAccessPolicy,
    RolePermission,
    UserRoleAssignment,
)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "module", "resource", "action", "scope_type", "isactive")
    search_fields = ("code", "name", "module", "resource", "action")
    list_filter = ("scope_type", "is_system_defined", "isactive")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "entity", "role_level", "priority", "is_system_role", "isactive")
    search_fields = ("name", "code", "entity__entityname")
    list_filter = ("role_level", "is_system_role", "is_assignable", "isactive")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "effect", "isactive")
    search_fields = ("role__name", "permission__code")
    list_filter = ("effect", "isactive")


@admin.register(DataAccessPolicy)
class DataAccessPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "entity", "policy_type", "scope_mode", "is_system_defined", "isactive")
    search_fields = ("name", "code", "entity__entityname")
    list_filter = ("policy_type", "scope_mode", "is_system_defined", "isactive")


@admin.register(RoleDataAccessPolicy)
class RoleDataAccessPolicyAdmin(admin.ModelAdmin):
    list_display = ("role", "policy", "isactive")
    search_fields = ("role__name", "policy__name")


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "entity", "role", "subentity", "is_primary", "effective_from", "effective_to", "isactive")
    search_fields = ("user__email", "entity__entityname", "role__name", "subentity__subentityname")
    list_filter = ("is_primary", "isactive", "entity")


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent", "menu_type", "sort_order", "depth", "isactive")
    search_fields = ("name", "code", "route_path", "route_name")
    list_filter = ("menu_type", "is_system_menu", "isactive")


@admin.register(MenuPermission)
class MenuPermissionAdmin(admin.ModelAdmin):
    list_display = ("menu", "permission", "relation_type", "isactive")
    search_fields = ("menu__name", "permission__code")
    list_filter = ("relation_type", "isactive")

