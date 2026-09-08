from django.contrib import admin

from .models import (
    PlatformAuditEvent,
    PlatformOperationApproval,
    PlatformOperationRequest,
    PlatformPermission,
    PlatformRole,
    PlatformUserRole,
)


@admin.register(PlatformPermission)
class PlatformPermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(PlatformRole)
class PlatformRoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_system", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_system", "is_active")
    filter_horizontal = ("permissions",)


@admin.register(PlatformUserRole)
class PlatformUserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "valid_from", "expires_at", "is_active")
    search_fields = ("user__email", "role__code")
    list_filter = ("role", "is_active")


@admin.register(PlatformAuditEvent)
class PlatformAuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "outcome", "actor", "created_at")
    search_fields = ("event_type", "actor__email", "correlation_id")
    list_filter = ("outcome", "event_type")
    readonly_fields = tuple(field.name for field in PlatformAuditEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformOperationRequest)
class PlatformOperationRequestAdmin(admin.ModelAdmin):
    list_display = ("operation_type", "risk", "status", "requested_by", "created_at")
    search_fields = ("id", "correlation_id", "requested_by__email", "ticket_reference")
    list_filter = ("operation_type", "risk", "status")
    readonly_fields = tuple(field.name for field in PlatformOperationRequest._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformOperationApproval)
class PlatformOperationApprovalAdmin(admin.ModelAdmin):
    list_display = ("operation", "decision", "decided_by", "decided_at")
    search_fields = ("operation__id", "operation__correlation_id", "decided_by__email")
    list_filter = ("decision",)
    readonly_fields = tuple(field.name for field in PlatformOperationApproval._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
