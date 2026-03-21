from django.contrib import admin
from import_export.admin import ImportExportMixin

from Authentication.models import User, AuthSession, AuthAuditLog, AuthOTP


@admin.register(User)
class UserAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "last_login",
        "created_at",
    )
    search_fields = (
        "id",
        "username",
        "email",
        "first_name",
        "last_name",
    )
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
        "last_login",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login",
    )

    fieldsets = (
        (
            "Core",
            {
                "fields": (
                    "username",
                    "email",
                    "password",
                )
            },
        ),
        (
            "Profile",
            {
                "fields": (
                    "first_name",
                    "last_name",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "session_key",
        "issued_at",
        "expires_at",
        "refresh_expires_at",
        "revoked_at",
        "ip_address",
    )
    search_fields = (
        "id",
        "user__email",
        "user__username",
        "session_key",
        "jti",
        "ip_address",
    )
    list_filter = (
        "revoked_at",
        "issued_at",
        "expires_at",
    )
    autocomplete_fields = ("user",)
    ordering = ("-issued_at",)
    readonly_fields = ()

    fieldsets = (
        (
            "Session",
            {
                "fields": (
                    "user",
                    "session_key",
                    "jti",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "issued_at",
                    "expires_at",
                    "refresh_expires_at",
                    "revoked_at",
                )
            },
        ),
        (
            "Request Info",
            {
                "fields": (
                    "ip_address",
                    "user_agent",
                )
            },
        ),
    )


@admin.register(AuthAuditLog)
class AuthAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "event",
        "email",
        "user",
        "ip_address",
    )
    search_fields = (
        "id",
        "email",
        "user__email",
        "user__username",
        "event",
        "ip_address",
    )
    list_filter = (
        "event",
        "created_at",
    )
    autocomplete_fields = ("user",)
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Audit",
            {
                "fields": (
                    "event",
                    "email",
                    "user",
                )
            },
        ),
        (
            "Context",
            {
                "fields": (
                    "ip_address",
                    "user_agent",
                )
            },
        ),
        (
            "Timestamp",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )

    readonly_fields = ("created_at",)


@admin.register(AuthOTP)
class AuthOTPAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "purpose",
        "code_hash",
        "expires_at",
        "consumed_at",
        "attempts",
    )
    search_fields = (
        "id",
        "email",
        "code_hash",
    )
    list_filter = (
        "purpose",
        "consumed_at",
        "expires_at",
    )
    ordering = ("-expires_at",)

    fieldsets = (
        (
            "OTP",
            {
                "fields": (
                    "email",
                    "purpose",
                    "code_hash",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "expires_at",
                    "consumed_at",
                    "attempts",
                )
            },
        ),
    )