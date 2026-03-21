from __future__ import annotations

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import DocumentNumberSeries, DocumentType


class DocumentNumberSeriesInline(admin.TabularInline):
    model = DocumentNumberSeries
    extra = 0
    fields = (
        "entity",
        "entityfinid",
        "subentity",
        "doc_code",
        "current_number",
        "is_active",
    )
    autocomplete_fields = ("entity", "entityfinid", "subentity")
    show_change_link = True


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("module", "name", "doc_key", "default_code", "is_active", "created_at", "updated_at")
    list_filter = ("module", "is_active")
    search_fields = ("module", "name", "doc_key", "default_code")
    ordering = ("module", "doc_key")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50
    inlines = (DocumentNumberSeriesInline,)

    fieldsets = (
        ("Document", {"fields": ("module", "name", "doc_key", "default_code")}),
        ("Status", {"fields": ("is_active",)}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    actions = ("make_active", "make_inactive")

    @admin.action(description="Mark selected document types as Active")
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Updated {updated} record(s) to Active.", level=messages.SUCCESS)

    @admin.action(description="Mark selected document types as Inactive")
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Updated {updated} record(s) to Inactive.", level=messages.WARNING)


@admin.register(DocumentNumberSeries)
class DocumentNumberSeriesAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "entityfinid",
        "subentity",
        "doc_type",
        "doc_code",
        "preview_example",
        "starting_number",
        "current_number",
        "reset_frequency",
        "last_reset_date",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "reset_frequency",
        "include_year",
        "include_month",
        "doc_type",
        "entity",
        "entityfinid",
    )
    search_fields = (
        "entity__entityname",
        "subentity__subentityname",
        "doc_type__module",
        "doc_type__name",
        "doc_type__doc_key",
        "doc_code",
        "prefix",
        "suffix",
    )
    list_select_related = ("entity", "entityfinid", "subentity", "doc_type", "created_by")
    ordering = ("entity_id", "entityfinid_id", "subentity_id", "doc_type_id", "doc_code")
    list_per_page = 50
    readonly_fields = ("created_at", "updated_at", "preview_example")
    actions = ("make_active", "make_inactive", "reset_counter_to_starting", "sync_current_to_starting")
    raw_id_fields = ("entity", "entityfinid", "subentity", "doc_type", "created_by")

    fieldsets = (
        ("Scope", {"fields": ("entity", "entityfinid", "subentity", "doc_type")}),
        ("Series Code", {"fields": ("doc_code", "is_active")}),
        (
            "Format",
            {
                "fields": (
                    ("prefix", "suffix"),
                    ("separator", "number_padding"),
                    ("include_year", "include_month"),
                    "custom_format",
                    "preview_example",
                )
            },
        ),
        ("Counter", {"fields": (("starting_number", "current_number"), ("reset_frequency", "last_reset_date"))}),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj: DocumentNumberSeries, form, change):
        if not obj.created_by_id and getattr(request, "user", None) and request.user.is_authenticated:
            obj.created_by = request.user
        if obj.current_number < obj.starting_number:
            obj.current_number = obj.starting_number
        super().save_model(request, obj, form, change)

    @admin.display(description="Example")
    def preview_example(self, obj: DocumentNumberSeries) -> str:
        today = timezone.localdate()
        year = str(today.year)
        month = f"{today.month:02d}"
        number_str = str(obj.current_number).zfill(obj.number_padding or 0)

        if obj.custom_format:
            try:
                return obj.custom_format.format(
                    prefix=obj.prefix or "",
                    suffix=obj.suffix or "",
                    year=year if obj.include_year else "",
                    month=month if obj.include_month else "",
                    number=number_str,
                    doc_code=obj.doc_code or "",
                )
            except Exception:
                return "Invalid custom_format"

        parts = []
        if obj.prefix:
            parts.append(obj.prefix)
        if obj.doc_code:
            parts.append(obj.doc_code)
        if obj.include_year:
            parts.append(year)
        if obj.include_month:
            parts.append(month)
        parts.append(number_str)
        if obj.suffix:
            parts.append(obj.suffix)
        return (obj.separator or "-").join([p for p in parts if p])

    @admin.action(description="Mark selected series as Active")
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Updated {updated} record(s) to Active.", level=messages.SUCCESS)

    @admin.action(description="Mark selected series as Inactive")
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Updated {updated} record(s) to Inactive.", level=messages.WARNING)

    @admin.action(description="Reset counter to starting number")
    def reset_counter_to_starting(self, request, queryset):
        today = timezone.localdate()
        count = 0
        with transaction.atomic():
            for series in queryset.select_for_update():
                series.current_number = series.starting_number
                series.last_reset_date = today
                series.save(update_fields=["current_number", "last_reset_date", "updated_at"])
                count += 1
        self.message_user(request, f"Reset {count} series counter(s).", level=messages.SUCCESS)

    @admin.action(description="Sync starting_number = current_number")
    def sync_current_to_starting(self, request, queryset):
        count = 0
        with transaction.atomic():
            for series in queryset.select_for_update():
                series.starting_number = series.current_number
                series.save(update_fields=["starting_number", "updated_at"])
                count += 1
        self.message_user(request, f"Synced starting_number for {count} series.", level=messages.SUCCESS)
