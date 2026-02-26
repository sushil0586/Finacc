from __future__ import annotations

from django.contrib import admin
from django.db.models import Sum, Count, Q
from django.utils.html import format_html
from django.urls import reverse
from django.db.models.functions import Coalesce
from django.db.models import DecimalField

from .models import (
    StaticAccount,
    EntityStaticAccountMap,
    PostingBatch,
    Entry,
    JournalLine,
    InventoryMove,
)


# -------------------------
# Helpers (Admin)
# -------------------------
def link_to(obj, admin_view_name: str, label: str):
    """
    Create a clickable link to a change page.
    """
    url = reverse(f"admin:{admin_view_name}_change", args=[obj.pk])
    return format_html('<a href="{}">{}</a>', url, label)


class ReadOnlyAdminMixin:
    """
    Prevent edits for ledger rows to avoid breaking audit.
    Allow viewing only.
    """
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # allow view, but block edits
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# -------------------------
# Static accounts admin
# -------------------------
@admin.register(StaticAccount)
class StaticAccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "group", "is_required", "is_active", "created_at", "updated_at")
    list_filter = ("group", "is_required", "is_active")
    search_fields = ("code", "name")
    ordering = ("group", "code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(EntityStaticAccountMap)
class EntityStaticAccountMapAdmin(admin.ModelAdmin):
    list_display = ("entity", "static_account", "account", "is_active", "effective_from", "created_at")
    list_filter = ("entity", "is_active", "static_account__group")
    search_fields = ("static_account__code", "static_account__name", "account__accountname")
    ordering = ("entity", "static_account__group", "static_account__code")
    readonly_fields = ("created_at", "updated_at")


# -------------------------
# Inlines for Entry detail view
# -------------------------
class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    fields = (
        "posting_date",
        "drcr",
        "amount",
        "account",
        "accounthead",
        "detail_id",
        "description",
        "posting_batch",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class InventoryMoveInline(admin.TabularInline):
    model = InventoryMove
    extra = 0
    fields = (
        "posting_date",
        "move_type",
        "product",
        "qty",
        "base_qty",
        "uom",
        "base_uom",
        "unit_cost",
        "ext_cost",
        "location",
        "detail_id",
        "cost_source",
        "posting_batch",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# -------------------------
# PostingBatch admin (informative)
# -------------------------
@admin.register(PostingBatch)
class PostingBatchAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_filter = ("entity", "txn_type", "is_active", "revision")
    search_fields = ("voucher_no", "txn_id", "id")
    ordering = ("-created_at",)

    list_display = (
        "id",
        "entity",
        "txn_type",
        "txn_id",
        "voucher_no",
        "revision",
        "is_active",
        "created_at",
        "jl_count",
        "im_count",
        "dr_total",
        "cr_total",
        "is_balanced",
        "entry_link",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # annotate counts & totals
        return qs.annotate(
            jl_cnt=Count("journal_lines", distinct=True),
            im_cnt=Count("inventory_moves_posting", distinct=True),
            dr_sum=Sum("journal_lines__amount", filter=Q(journal_lines__drcr=True)),
            cr_sum=Sum("journal_lines__amount", filter=Q(journal_lines__drcr=False)),
        )

    @admin.display(ordering="jl_cnt", description="JL")
    def jl_count(self, obj):
        return obj.jl_cnt or 0

    @admin.display(ordering="im_cnt", description="IM")
    def im_count(self, obj):
        return obj.im_cnt or 0

    @admin.display(ordering="dr_sum", description="DR Total")
    def dr_total(self, obj):
        return obj.dr_sum or 0

    @admin.display(ordering="cr_sum", description="CR Total")
    def cr_total(self, obj):
        return obj.cr_sum or 0

    @admin.display(boolean=True, description="Balanced")
    def is_balanced(self, obj):
        dr = obj.dr_sum or 0
        cr = obj.cr_sum or 0
        return dr == cr

    @admin.display(description="Entry")
    def entry_link(self, obj):
        entry = obj.entries.order_by("-id").first()
        if not entry:
            return "-"
        return link_to(entry, "posting_entry", f"Entry#{entry.id}")


# -------------------------
# Entry admin (informative)
# -------------------------
@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    date_hierarchy = "posting_date"
    list_filter = ("entity", "txn_type", "status")
    search_fields = ("voucher_no", "txn_id", "id", "posting_batch__id")
    ordering = ("-posting_date", "-id")

    list_display = (
        "id",
        "entity",
        "txn_type",
        "txn_id",
        "voucher_no",
        "posting_date",
        "status",
        "posted_at",
        "jl_count",
        "im_count",
        "dr_total",
        "cr_total",
        "is_balanced",
        "batch_link",
    )

    inlines = [JournalLineInline, InventoryMoveInline]

    readonly_fields = (
        "entity",
        "entityfin",
        "subentity",
        "txn_type",
        "txn_id",
        "voucher_no",
        "voucher_date",
        "posting_date",
        "status",
        "posted_at",
        "posted_by",
        "posting_batch",
        "narration",
        "created_at",
        "created_by",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        return qs.annotate(
            jl_cnt=Count("posting_journal_lines", distinct=True),
            im_cnt=Count("posting_inventory_moves", distinct=True),

            dr_sum=Coalesce(
                Sum(
                    "posting_journal_lines__amount",
                    filter=Q(posting_journal_lines__drcr=True)
                ),
                0,
                output_field=DecimalField()
            ),

            cr_sum=Coalesce(
                Sum(
                    "posting_journal_lines__amount",
                    filter=Q(posting_journal_lines__drcr=False)
                ),
                0,
                output_field=DecimalField()
            ),
        )

    @admin.display(ordering="jl_cnt", description="JL")
    def jl_count(self, obj):
        return obj.jl_cnt or 0

    @admin.display(ordering="im_cnt", description="IM")
    def im_count(self, obj):
        return obj.im_cnt or 0

    @admin.display(ordering="dr_sum", description="DR Total")
    def dr_total(self, obj):
        return obj.dr_sum or 0

    @admin.display(ordering="cr_sum", description="CR Total")
    def cr_total(self, obj):
        return obj.cr_sum or 0

    @admin.display(boolean=True, description="Balanced")
    def is_balanced(self, obj):
        dr = obj.dr_sum or 0
        cr = obj.cr_sum or 0
        return dr == cr

    @admin.display(description="Batch")
    def batch_link(self, obj):
        if not obj.posting_batch_id:
            return "-"
        return link_to(obj.posting_batch, "posting_postingbatch", str(obj.posting_batch_id)[:8])


# -------------------------
# JournalLine / InventoryMove (read-only list)
# -------------------------
@admin.register(JournalLine)
class JournalLineAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    date_hierarchy = "posting_date"
    list_filter = ("entity", "txn_type", "drcr")
    search_fields = ("voucher_no", "txn_id", "entry_id", "posting_batch__id")
    ordering = ("-posting_date", "-id")

    list_display = (
        "id",
        "entity",
        "posting_date",
        "txn_type",
        "txn_id",
        "voucher_no",
        "detail_id",
        "drcr",
        "amount",
        "account",
        "accounthead",
        "entry_link",
        "batch_link",
    )

    readonly_fields = [f.name for f in JournalLine._meta.fields]

    @admin.display(description="Entry")
    def entry_link(self, obj):
        return link_to(obj.entry, "posting_entry", f"Entry#{obj.entry_id}")

    @admin.display(description="Batch")
    def batch_link(self, obj):
        return link_to(obj.posting_batch, "posting_postingbatch", str(obj.posting_batch_id)[:8])


@admin.register(InventoryMove)
class InventoryMoveAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    date_hierarchy = "posting_date"
    list_filter = ("entity", "txn_type", "move_type", "cost_source")
    search_fields = ("voucher_no", "txn_id", "entry_id", "posting_batch__id", "product__name")
    ordering = ("-posting_date", "-id")

    list_display = (
        "id",
        "entity",
        "posting_date",
        "txn_type",
        "txn_id",
        "voucher_no",
        "detail_id",
        "move_type",
        "product",
        "qty",
        "base_qty",
        "uom",
        "unit_cost",
        "ext_cost",
        "location",
        "entry_link",
        "batch_link",
    )

    readonly_fields = [f.name for f in InventoryMove._meta.fields]

    @admin.display(description="Entry")
    def entry_link(self, obj):
        return link_to(obj.entry, "posting_entry", f"Entry#{obj.entry_id}")

    @admin.display(description="Batch")
    def batch_link(self, obj):
        return link_to(obj.posting_batch, "posting_postingbatch", str(obj.posting_batch_id)[:8])
