from django.contrib import admin
from django.db.models import Count

from .models import (
    DataAccessPolicy,
    Menu,
    MenuPermission,
    Permission,
    RBACAuditLog,
    Role,
    RoleDataAccessPolicy,
    RolePermission,
    UserRoleAssignment,
)


class ActivationAdminMixin:
    actions = ("mark_active", "mark_inactive")

    @admin.action(description="Mark selected rows active")
    def mark_active(self, request, queryset):
        queryset.update(isactive=True)

    @admin.action(description="Mark selected rows inactive")
    def mark_inactive(self, request, queryset):
        queryset.update(isactive=False)


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ("permission",)
    fields = ("permission", "effect", "isactive")


class RoleDataAccessPolicyInline(admin.TabularInline):
    model = RoleDataAccessPolicy
    extra = 0
    autocomplete_fields = ("policy",)
    fields = ("policy", "isactive")


class UserRoleAssignmentInline(admin.TabularInline):
    model = UserRoleAssignment
    extra = 0
    autocomplete_fields = ("subentity",)
    raw_id_fields = ("user", "assigned_by")
    fields = (
        "user",
        "subentity",
        "is_primary",
        "effective_from",
        "effective_to",
        "assigned_by",
        "isactive",
    )


class MenuPermissionInline(admin.TabularInline):
    model = MenuPermission
    extra = 0
    autocomplete_fields = ("permission",)
    fields = ("permission", "relation_type", "isactive")


@admin.register(Permission)
class PermissionAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "module",
        "resource",
        "action",
        "scope_type",
        "is_system_defined",
        "isactive",
    )
    search_fields = ("code", "name", "module", "resource", "action", "description")
    list_filter = ("scope_type", "module", "is_system_defined", "isactive")
    list_editable = ("isactive",)
    ordering = ("module", "resource", "action", "name")
    fieldsets = (
        (
            "Permission",
            {
                "fields": (
                    "code",
                    "name",
                    "description",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "module",
                    "resource",
                    "action",
                    "scope_type",
                )
            },
        ),
        (
            "Behavior",
            {
                "fields": (
                    "is_system_defined",
                    "metadata",
                    "isactive",
                )
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "entity",
        "role_level",
        "priority",
        "is_system_role",
        "is_assignable",
        "permission_count",
        "assignment_count",
        "isactive",
    )
    search_fields = ("name", "code", "description", "entity__entityname")
    list_filter = ("role_level", "entity", "is_system_role", "is_assignable", "isactive")
    list_editable = ("priority", "isactive")
    autocomplete_fields = ("entity",)
    raw_id_fields = ("createdby",)
    list_select_related = ("entity", "createdby")
    inlines = (RolePermissionInline, RoleDataAccessPolicyInline, UserRoleAssignmentInline)
    fieldsets = (
        (
            "Role",
            {
                "fields": (
                    "entity",
                    "name",
                    "code",
                    "description",
                )
            },
        ),
        (
            "Behavior",
            {
                "fields": (
                    "role_level",
                    "is_system_role",
                    "is_assignable",
                    "priority",
                    "isactive",
                )
            },
        ),
        (
            "Advanced",
            {
                "classes": ("collapse",),
                "fields": (
                    "metadata",
                    "createdby",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("entity", "createdby")
            .annotate(
                _permission_count=Count("role_permissions", distinct=True),
                _assignment_count=Count("user_assignments", distinct=True),
            )
        )

    @admin.display(ordering="_permission_count", description="Permissions")
    def permission_count(self, obj):
        return getattr(obj, "_permission_count", 0)

    @admin.display(ordering="_assignment_count", description="Assignments")
    def assignment_count(self, obj):
        return getattr(obj, "_assignment_count", 0)

    def save_model(self, request, obj, form, change):
        if not obj.createdby_id:
            obj.createdby = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(RolePermission)
class RolePermissionAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = ("role", "permission", "effect", "isactive")
    search_fields = ("role__name", "role__code", "permission__code", "permission__name")
    list_filter = ("effect", "isactive", "role__entity")
    autocomplete_fields = ("role", "permission")
    list_select_related = ("role", "permission")


@admin.register(DataAccessPolicy)
class DataAccessPolicyAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "entity", "policy_type", "scope_mode", "is_system_defined", "isactive")
    search_fields = ("name", "code", "entity__entityname")
    list_filter = ("policy_type", "scope_mode", "is_system_defined", "isactive", "entity")
    autocomplete_fields = ("entity",)
    list_select_related = ("entity",)
    fieldsets = (
        (
            "Policy",
            {
                "fields": (
                    "entity",
                    "name",
                    "code",
                    "policy_type",
                    "scope_mode",
                )
            },
        ),
        (
            "Behavior",
            {
                "fields": (
                    "is_system_defined",
                    "configuration",
                    "isactive",
                )
            },
        ),
    )


@admin.register(RoleDataAccessPolicy)
class RoleDataAccessPolicyAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = ("role", "policy", "isactive")
    search_fields = ("role__name", "role__code", "policy__name", "policy__code")
    list_filter = ("isactive", "role__entity", "policy__policy_type")
    autocomplete_fields = ("role", "policy")
    list_select_related = ("role", "policy")


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = (
        "user_display",
        "entity",
        "role",
        "subentity",
        "is_primary",
        "effective_from",
        "effective_to",
        "isactive",
    )
    search_fields = (
        "user__email",
        "user__username",
        "user__first_name",
        "user__last_name",
        "entity__entityname",
        "role__name",
        "role__code",
        "subentity__subentityname",
    )
    list_filter = ("is_primary", "isactive", "entity", "role")
    autocomplete_fields = ("entity", "role", "subentity")
    raw_id_fields = ("user", "assigned_by")
    list_select_related = ("user", "entity", "role", "subentity", "assigned_by")
    fieldsets = (
        (
            "Assignment",
            {
                "fields": (
                    "user",
                    "entity",
                    "role",
                    "subentity",
                )
            },
        ),
        (
            "Timing",
            {
                "fields": (
                    "effective_from",
                    "effective_to",
                )
            },
        ),
        (
            "Behavior",
            {
                "fields": (
                    "is_primary",
                    "scope_data",
                    "assigned_by",
                    "isactive",
                )
            },
        ),
    )

    @admin.display(description="User")
    def user_display(self, obj):
        full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full_name or obj.user.email or obj.user.username

    def save_model(self, request, obj, form, change):
        if not obj.assigned_by_id:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Menu)
class MenuAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = ("indented_name", "code", "parent", "menu_type", "route_name", "sort_order", "depth", "isactive")
    search_fields = ("name", "code", "route_path", "route_name")
    list_filter = ("menu_type", "is_system_menu", "isactive", "depth")
    autocomplete_fields = ("parent",)
    list_editable = ("sort_order", "isactive")
    inlines = (MenuPermissionInline,)
    readonly_fields = ("depth",)
    fieldsets = (
        (
            "Menu",
            {
                "fields": (
                    "parent",
                    "name",
                    "code",
                    "menu_type",
                )
            },
        ),
        (
            "Navigation",
            {
                "fields": (
                    "route_path",
                    "route_name",
                    "icon",
                    "sort_order",
                    "depth",
                )
            },
        ),
        (
            "Behavior",
            {
                "fields": (
                    "is_system_menu",
                    "metadata",
                    "isactive",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("parent").order_by("depth", "parent_id", "sort_order", "name")

    @admin.display(description="Menu")
    def indented_name(self, obj):
        return f"{'|-- ' * obj.depth}{obj.name}"


@admin.register(MenuPermission)
class MenuPermissionAdmin(ActivationAdminMixin, admin.ModelAdmin):
    list_display = ("menu", "permission", "relation_type", "isactive")
    search_fields = ("menu__name", "menu__code", "permission__code", "permission__name")
    list_filter = ("relation_type", "isactive", "menu__menu_type")
    autocomplete_fields = ("menu", "permission")
    list_select_related = ("menu", "permission")


@admin.register(RBACAuditLog)
class RBACAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "object_type", "object_id", "entity", "action", "actor", "message")
    search_fields = ("object_type", "message", "actor__email", "entity__entityname")
    list_filter = ("object_type", "action", "entity")
    list_select_related = ("actor", "entity")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
