from __future__ import annotations

from django.contrib import admin
from django.db.models import Sum, Count, Q
from django.utils.html import format_html
from django.urls import reverse
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
from django.forms import ModelForm
from django.core.exceptions import ValidationError



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
class EntityStaticAccountMapInline(admin.TabularInline):
    model = EntityStaticAccountMap
    extra = 0
    fields = (
        "entity",
        "sub_entity",
        "account",
        "ledger",
        "effective_from",
        "is_active",
    )
    readonly_fields = ("effective_from",)
    autocomplete_fields = ("entity", "sub_entity", "account", "ledger")
    show_change_link = True


@admin.register(StaticAccount)
class StaticAccountAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "group",
        "sort_order",
        "is_required",
        "is_active",
        "usage_count",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "group",
        "is_required",
        "is_active",
    )
    search_fields = (
        "code",
        "name",
        "description",
    )
    ordering = (
        "group",
        "sort_order",
        "code",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    inlines = (EntityStaticAccountMapInline,)

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "code",
                "name",
                "group",
                "sort_order",
            )
        }),
        ("Behavior", {
            "fields": (
                "is_required",
                "is_active",
            )
        }),
        ("Description", {
            "fields": (
                "description",
            )
        }),
        ("System Information", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_usage_count=Count("entity_maps"))

    def usage_count(self, obj):
        return obj._usage_count
    usage_count.short_description = "Usage Count"

    def has_delete_permission(self, request, obj=None):
        # Prevent accidental deletion of static master roles
        return False


class EntityStaticAccountMapAdminForm(ModelForm):
    class Meta:
        model = EntityStaticAccountMap
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        entity = cleaned_data.get("entity")
        static_account = cleaned_data.get("static_account")
        is_active = cleaned_data.get("is_active")
        account_obj = cleaned_data.get("account")
        ledger = cleaned_data.get("ledger")

        if not account_obj and not ledger:
            raise ValidationError("Either account or ledger must be selected.")

        # Respect current DB constraint:
        # only one active mapping per entity + static_account
        if entity and static_account and is_active:
            qs = EntityStaticAccountMap.objects.filter(
                entity=entity,
                static_account=static_account,
                is_active=True,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    "An active mapping already exists for this entity and static account."
                )

        return cleaned_data


@admin.register(EntityStaticAccountMap)
class EntityStaticAccountMapAdmin(admin.ModelAdmin):
    form = EntityStaticAccountMapAdminForm

    list_display = (
        "entity",
        "sub_entity",
        "static_account",
        "static_group",
        "account",
        "ledger",
        "is_active",
        "effective_from",
        "createdby",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "entity",
        "sub_entity",
        "is_active",
        "static_account__group",
        "static_account__is_required",
    )
    search_fields = (
        "entity__name",
        "sub_entity__name",
        "static_account__code",
        "static_account__name",
        "account__accountname",
        "ledger__name",
    )
    ordering = (
        "entity",
        "sub_entity",
        "static_account__group",
        "static_account__sort_order",
        "static_account__code",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "createdby",
    )
    autocomplete_fields = (
        "entity",
        "sub_entity",
        "static_account",
        "account",
        "ledger",
    )
    list_select_related = (
        "entity",
        "sub_entity",
        "static_account",
        "account",
        "ledger",
        "createdby",
    )

    fieldsets = (
        ("Mapping Scope", {
            "fields": (
                "entity",
                "sub_entity",
                "static_account",
            )
        }),
        ("Mapped Target", {
            "fields": (
                "account",
                "ledger",
            )
        }),
        ("Status", {
            "fields": (
                "is_active",
                "effective_from",
            )
        }),
        ("Audit", {
            "fields": (
                "createdby",
                "created_at",
                "updated_at",
            )
        }),
    )

    actions = ("mark_selected_inactive",)

    def static_group(self, obj):
        return obj.static_account.get_group_display()
    static_group.short_description = "Group"
    static_group.admin_order_field = "static_account__group"

    def save_model(self, request, obj, form, change):
        if not obj.createdby:
            obj.createdby = request.user

        # Respect current uniqueness rule:
        # one active mapping per entity + static_account
        if obj.is_active:
            qs = EntityStaticAccountMap.objects.filter(
                entity=obj.entity,
                static_account=obj.static_account,
                is_active=True,
            )
            if obj.pk:
                qs = qs.exclude(pk=obj.pk)

            # Auto-deactivate previous active mapping
            for old in qs:
                old.is_active = False
                old.save(update_fields=["is_active", "updated_at"])

        super().save_model(request, obj, form, change)

    @admin.action(description="Mark selected mappings as inactive")
    def mark_selected_inactive(self, request, queryset):
        queryset.update(is_active=False)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj:
            # Prevent changing identity fields after creation
            ro.extend(["entity", "sub_entity", "static_account"])
        return ro


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
        "ledger",
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
        "ledger",
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
