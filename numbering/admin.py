from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone
from .models import DocumentSequenceSettings,DocumentType


@admin.register(DocumentType)
class DocTypeAdmin(admin.ModelAdmin):
    list_display  = ("doccode", "docname", "entity", "direction", "is_return",
                     "affects_stock", "supports_einvoice", "supports_ewaybill", "is_active")
    list_filter   = ("entity", "direction", "is_return", "affects_stock", "supports_einvoice", "supports_ewaybill", "is_active")
    search_fields = ("doccode", "docname")
    ordering      = ("entity", "doccode")

@admin.register(DocumentSequenceSettings)
class DocumentSequenceSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "entity", "entityfinid", "subentity", "doctype", "series_key",
        "current_number", "next_integer", "reset_frequency", "last_reset_key",
        "preview_next_display",
    )
    list_filter  = ("entity", "entityfinid", "doctype", "subentity", "series_key", "reset_frequency")
    search_fields = ("prefix", "suffix", "series_key")
    readonly_fields = ("last_reset_date", "last_reset_key", "preview_next_display")

    fieldsets = (
        ("Scope",    {"fields": ("entity", "entityfinid", "subentity", "doctype", "series_key")}),
        ("Counters", {"fields": ("starting_number", "current_number", "next_integer")}),
        ("Format",   {"fields": ("prefix", "suffix", "number_padding", "include_year",
                                 "include_month", "separator", "custom_format")}),
        ("Reset",    {"fields": ("reset_frequency", "last_reset_key", "last_reset_date")}),
        ("Preview",  {"fields": ("preview_next_display",)}),
    )

    actions = ["action_preview_next", "action_force_reset", "action_bump_current", "action_bump_integer"]

    def preview_next_display(self, obj):
        if not obj.pk:
            return "-"
        seq = obj.current_number
        display = obj.render_number(seq)
        return format_html("<code>{}</code>", display)
    preview_next_display.short_description = "Next display #"

    @admin.action(description="Preview next numbers")
    def action_preview_next(self, request, queryset):
        for s in queryset:
            code = getattr(s.doctype, "code", s.doctype_id)
            msg = f"[{s.id}] {s.entity_id}/{s.entityfinid_id} {code} | next_integer={s.next_integer} | next_display={s.render_number(s.current_number)}"
            self.message_user(request, msg, level=messages.INFO)

    @admin.action(description="Apply reset policy now")
    def action_force_reset(self, request, queryset):
        updated = 0
        for s in queryset.select_for_update():
            if s._maybe_reset():
                s.save(update_fields=["current_number", "last_reset_key", "last_reset_date"])
                updated += 1
        self.message_user(request, f"Applied reset on {updated} row(s).", level=messages.SUCCESS)

    @admin.action(description="Bump display counter (+1)")
    def action_bump_current(self, request, queryset):
        for s in queryset.select_for_update():
            s.current_number += 1
            s.save(update_fields=["current_number"])
        self.message_user(request, "Bumped current_number.", level=messages.SUCCESS)

    @admin.action(description="Bump integer counter (+1)")
    def action_bump_integer(self, request, queryset):
        for s in queryset.select_for_update():
            s.next_integer += 1
            s.save(update_fields=["next_integer"])
        self.message_user(request, "Bumped next_integer.", level=messages.SUCCESS)
