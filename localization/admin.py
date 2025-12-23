from django.contrib import admin
from .models import Language, LocalizedStringKey, LocalizedStringValue


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")


@admin.register(LocalizedStringKey)
class LocalizedStringKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "module", "is_active", "is_system", "updated_at")
    list_filter = ("module", "is_active", "is_system")
    search_fields = ("key", "description", "default_text")
    ordering = ("module", "key")


@admin.register(LocalizedStringValue)
class LocalizedStringValueAdmin(admin.ModelAdmin):
    list_display = ("string_key", "language", "entity_id", "is_approved", "updated_at")
    list_filter = ("language", "is_approved")
    search_fields = ("string_key__key", "text")
    ordering = ("-updated_at",)
