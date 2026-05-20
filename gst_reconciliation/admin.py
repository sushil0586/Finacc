from __future__ import annotations

from django.contrib import admin

from gst_reconciliation.models import (
    GstImportedReturn,
    GstImportedReturnRow,
    GstMismatchReason,
    GstReconciliationActionLog,
    GstReconciliationItem,
    GstReconciliationRun,
)


class GstMismatchReasonInline(admin.TabularInline):
    model = GstMismatchReason
    extra = 0
    can_delete = False
    fields = ("code", "category", "severity", "message")
    readonly_fields = fields


class GstReconciliationItemInline(admin.TabularInline):
    model = GstReconciliationItem
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("item_type", "match_key", "match_status", "invoice_number", "counterparty_gstin")
    readonly_fields = fields


class GstImportedReturnRowInline(admin.TabularInline):
    model = GstImportedReturnRow
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "row_no",
        "doc_type_code",
        "counterparty_gstin_normalized",
        "invoice_number_normalized",
        "total_amount",
    )
    readonly_fields = fields


@admin.register(GstImportedReturn)
class GstImportedReturnAdmin(admin.ModelAdmin):
    inlines = [GstImportedReturnRowInline]
    list_display = (
        "id",
        "entity",
        "return_type",
        "return_period",
        "gst_registration_gstin",
        "source",
        "status",
        "reference",
        "imported_by",
        "imported_at",
    )
    list_filter = ("return_type", "source", "status", "entity")
    search_fields = ("reference", "source_reference", "gst_registration_gstin", "entity__entityname")
    readonly_fields = ("created_at", "updated_at", "imported_at")
    list_select_related = ("entity", "entityfinid", "subentity", "imported_by")


@admin.register(GstImportedReturnRow)
class GstImportedReturnRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "imported_return",
        "row_no",
        "doc_type_code",
        "counterparty_gstin_normalized",
        "invoice_number_normalized",
        "total_amount",
    )
    list_filter = ("doc_type_code", "entity", "imported_return__return_type")
    search_fields = ("counterparty_gstin_normalized", "invoice_number_normalized", "counterparty_name")
    readonly_fields = ("created_at", "updated_at", "raw_row_json", "normalized_row_json")
    list_select_related = ("imported_return", "entity", "entityfinid", "subentity")


@admin.register(GstReconciliationRun)
class GstReconciliationRunAdmin(admin.ModelAdmin):
    inlines = [GstReconciliationItemInline]
    list_display = (
        "id",
        "entity",
        "reconciliation_type",
        "return_period",
        "gst_registration_gstin",
        "status",
        "source_mode",
        "match_strategy_code",
        "created_at",
    )
    list_filter = ("reconciliation_type", "status", "source_mode", "entity")
    search_fields = ("gst_registration_gstin", "return_period", "source_reference", "entity__entityname")
    readonly_fields = (
        "created_at",
        "updated_at",
        "submitted_at",
        "reviewed_at",
        "approved_at",
        "closed_at",
        "summary_json",
    )
    list_select_related = ("entity", "entityfinid", "subentity", "imported_return")


@admin.register(GstReconciliationItem)
class GstReconciliationItemAdmin(admin.ModelAdmin):
    inlines = [GstMismatchReasonInline]
    list_display = (
        "id",
        "run",
        "item_type",
        "match_status",
        "invoice_number",
        "counterparty_gstin",
        "mismatch_count",
        "match_confidence_score",
    )
    list_filter = ("match_status", "item_type", "direction", "run__reconciliation_type")
    search_fields = ("invoice_number", "match_key", "counterparty_gstin")
    readonly_fields = ("created_at", "updated_at", "mismatch_summary", "metadata_json")
    list_select_related = ("run", "entity", "entityfinid", "subentity")


@admin.register(GstMismatchReason)
class GstMismatchReasonAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "code", "category", "severity", "created_at")
    list_filter = ("severity", "category")
    search_fields = ("code", "message", "item__invoice_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(GstReconciliationActionLog)
class GstReconciliationActionLogAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "action_type", "actor", "from_status", "to_status", "created_at")
    list_filter = ("action_type", "run__reconciliation_type", "entity")
    search_fields = ("comment", "run__id", "actor__email")
    readonly_fields = ("created_at", "updated_at", "details_json")
    list_select_related = ("run", "item", "actor", "entity", "entityfinid", "subentity")
