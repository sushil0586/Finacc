# admin.py
from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from .models import Language, LocalizedStringKey, LocalizedStringValue
from .admin_resources import (
    LanguageResource,
    LocalizedStringKeyResource,
    LocalizedStringValueResource,
)


@admin.register(Language)
class LanguageAdmin(ImportExportModelAdmin):
    resource_class = LanguageResource
    list_display = ("code", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")


@admin.register(LocalizedStringKey)
class LocalizedStringKeyAdmin(ImportExportModelAdmin):
    resource_class = LocalizedStringKeyResource
    list_display = ("key", "module", "is_active", "is_system", "updated_at")
    list_filter = ("module", "is_active", "is_system")
    search_fields = ("key", "description", "default_text")
    ordering = ("module", "key")


@admin.register(LocalizedStringValue)
class LocalizedStringValueAdmin(ImportExportModelAdmin):
    resource_class = LocalizedStringValueResource
    list_display = ("string_key", "language", "entity_id", "is_approved", "updated_at")
    list_filter = ("language", "is_approved")
    search_fields = ("string_key__key", "text")
    ordering = ("-updated_at",)

    # Optional: make it safer for env migrations
    list_select_related = ("string_key", "language")
