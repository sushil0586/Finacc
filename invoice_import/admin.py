from __future__ import annotations

from django.contrib import admin, messages

from invoice_import.models import ImportJob, ImportProfile, ImportRow
from invoice_import.services import commit_job


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "row_no",
        "group_key",
        "status",
        "committed_object_id",
        "errors_preview",
        "warnings_preview",
    )
    readonly_fields = fields
    ordering = ("row_no",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Errors")
    def errors_preview(self, obj: ImportRow) -> str:
        errors = obj.errors or []
        if not errors:
            return "-"
        return " | ".join(f"{item.get('field')}: {item.get('message')}" for item in errors[:3])

    @admin.display(description="Warnings")
    def warnings_preview(self, obj: ImportRow) -> str:
        warnings = obj.warnings or []
        if not warnings:
            return "-"
        return " | ".join(str(item) for item in warnings[:3])


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    inlines = [ImportRowInline]
    actions = ["commit_selected_jobs"]

    list_display = (
        "id",
        "entity",
        "module",
        "mode",
        "detail_level",
        "status",
        "stock_replay",
        "compliance_mode",
        "withholding_mode",
        "source_system",
        "created_by",
        "created_at",
    )
    list_filter = (
        "module",
        "mode",
        "detail_level",
        "status",
        "stock_replay",
        "compliance_mode",
        "withholding_mode",
        "entity",
    )
    search_fields = ("id", "input_filename", "source_system", "entity__entityname", "created_by__username")
    readonly_fields = (
        "entity",
        "created_by",
        "module",
        "mode",
        "detail_level",
        "compliance_mode",
        "withholding_mode",
        "stock_replay",
        "file_format",
        "status",
        "input_filename",
        "source_system",
        "summary",
        "reconciliation_summary",
        "options",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at", "-id")
    list_select_related = ("entity", "created_by")

    def has_add_permission(self, request):
        return False

    @admin.action(description="Commit selected validated import jobs")
    def commit_selected_jobs(self, request, queryset):
        committed = 0
        skipped = 0
        for job in queryset.order_by("id"):
            if job.status not in {ImportJob.Status.VALIDATED, ImportJob.Status.PARTIAL, ImportJob.Status.COMMITTED}:
                skipped += 1
                continue
            try:
                commit_job(job=job, user=request.user)
                committed += 1
            except Exception as exc:  # pragma: no cover - admin safety path
                skipped += 1
                self.message_user(
                    request,
                    f"Job {job.id} could not be committed: {exc}",
                    level=messages.ERROR,
                )
        if committed:
            self.message_user(request, f"Committed {committed} import job(s).", level=messages.SUCCESS)
        if skipped:
            self.message_user(request, f"Skipped {skipped} job(s).", level=messages.WARNING)


@admin.register(ImportProfile)
class ImportProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "module",
        "name",
        "source_system",
        "is_default",
        "created_by",
        "created_at",
    )
    list_filter = ("module", "is_default", "entity")
    search_fields = ("name", "source_system", "entity__entityname")
    readonly_fields = ("created_by", "created_at", "updated_at")
    list_select_related = ("entity", "created_by")
    ordering = ("module", "name", "id")


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "row_no",
        "group_key",
        "status",
        "committed_object_id",
        "created_at",
    )
    list_filter = ("status", "job__module", "job__mode", "job__entity")
    search_fields = ("group_key", "job__id", "job__entity__entityname")
    readonly_fields = (
        "job",
        "row_no",
        "group_key",
        "status",
        "raw_payload",
        "normalized_payload",
        "errors",
        "warnings",
        "committed_object_id",
        "created_at",
        "updated_at",
    )
    list_select_related = ("job", "job__entity")
    ordering = ("job_id", "row_no")

    def has_add_permission(self, request):
        return False
