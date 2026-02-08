from __future__ import annotations

from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone

from purchase.models.purchase_config import PurchaseSettings, PurchaseLockPeriod, PurchaseChoiceOverride

from purchase.models.purchase_core import (
    PurchaseInvoiceHeader,
    PurchaseInvoiceLine,
    PurchaseTaxSummary,
    DocType,
    Status,
)
from purchase.services.purchase_invoice_service import PurchaseInvoiceService
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions
from purchase.services.purchase_note_factory import PurchaseNoteFactory


# ----------------------------
# Inlines
# ----------------------------

class PurchaseInvoiceLineInline(admin.TabularInline):
    model = PurchaseInvoiceLine
    extra = 0
    show_change_link = True

    autocomplete_fields = ["product", "uom"]  # works if Product/UOM admin has search_fields set
    fields = (
        "line_no",
        "product",
        "product_desc",
        "is_service",
        "hsn_sac",
        "uom",
        "qty",
        "rate",
        "taxability",
        "taxable_value",
        "gst_rate",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "line_total",
        "is_itc_eligible",
        "itc_block_reason",
    )
    ordering = ("line_no", "id")


class PurchaseTaxSummaryInline(admin.TabularInline):
    model = PurchaseTaxSummary
    extra = 0
    can_delete = False
    show_change_link = False

    # Completely read-only in admin (you rebuild from lines)
    readonly_fields = (
        "taxability", "hsn_sac", "is_service", "gst_rate", "is_reverse_charge",
        "taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount",
        "total_value", "itc_eligible_tax", "itc_ineligible_tax",
    )
    fields = readonly_fields
    ordering = ("gst_rate", "taxability", "hsn_sac")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ----------------------------
# Header Admin
# ----------------------------

@admin.register(PurchaseInvoiceHeader)
class PurchaseInvoiceHeaderAdmin(admin.ModelAdmin):
    inlines = [PurchaseInvoiceLineInline, PurchaseTaxSummaryInline]

    list_display = (
        "id",
        "doc_badge",
        "doc_no",
        "bill_date",
        "status_badge",
        "vendor_display",
        "vendor_gstin",
        "regime_display",
        "rcm_display",
        "itc_display",
        "grand_total",
        "entity",
        "entityfinid",
        "subentity",
    )
    list_select_related = (
        "vendor", "vendor_state", "supplier_state", "place_of_supply_state",
        "entity", "entityfinid", "subentity", "ref_document",
    )
    list_filter = (
        "doc_type",
        "status",
        "supply_category",
        "default_taxability",
        "tax_regime",
        "is_reverse_charge",
        "is_itc_eligible",
        "gstr2b_match_status",
        "itc_claim_status",
        "entity",
        "entityfinid",
        "subentity",
    )
    search_fields = (
        "purchase_number",
        "supplier_invoice_number",
        "vendor_name",
        "vendor_gstin",
        "doc_code",
    )
    date_hierarchy = "bill_date"
    ordering = ("-bill_date", "-id")

    raw_id_fields = (
    "vendor",
    "vendor_state",
    "supplier_state",
    "place_of_supply_state",
    "ref_document",
    "entity",
    "entityfinid",
    "subentity",
)

    # Make admin safer (no accidental deletes on posted docs)
    actions = [
        "action_rebuild_tax_summary",
        "action_confirm",
        "action_post",
        "action_cancel",
        "action_create_credit_note",
        "action_create_debit_note",
    ]

    # ---------- Field layout ----------
    fieldsets = (
        ("Document", {
            "fields": (
                ("doc_type", "status"),
                ("bill_date", "doc_code", "doc_no", "purchase_number"),
                ("supplier_invoice_number", "supplier_invoice_date"),
                ("ref_document",),
            )
        }),
        ("Vendor (Snapshot)", {
            "fields": (
                ("vendor",),
                ("vendor_name", "vendor_gstin"),
                ("vendor_state",),
            )
        }),
        ("Supply & Tax Settings", {
            "fields": (
                ("supply_category", "default_taxability"),
                ("supplier_state", "place_of_supply_state"),
                ("tax_regime", "is_igst"),
                ("is_reverse_charge",),
            )
        }),
        ("ITC & GSTR-2B", {
            "fields": (
                ("is_itc_eligible", "itc_claim_status"),
                ("itc_claim_period", "itc_claimed_at"),
                ("itc_block_reason",),
                ("gstr2b_match_status",),
            )
        }),
        ("Totals", {
            "fields": (
                ("total_taxable", "total_gst"),
                ("total_cgst", "total_sgst", "total_igst", "total_cess"),
                ("round_off", "grand_total"),
            )
        }),
        ("SaaS Scope", {
            "fields": (
                ("entity", "entityfinid"),
                ("subentity",),
                ("created_by",),
            )
        }),
    )

    readonly_fields = (
        # These are computed from lines; keep readonly so admin users don't break consistency
        "total_taxable",
        "total_cgst",
        "total_sgst",
        "total_igst",
        "total_cess",
        "total_gst",
        "grand_total",
        "created_by",
    )

    # ----------------------------
    # Visual helpers in list
    # ----------------------------
    @admin.display(description="Doc")
    def doc_badge(self, obj: PurchaseInvoiceHeader):
        t = obj.get_doc_type_display()
        color = "#0d6efd" if obj.doc_type == DocType.TAX_INVOICE else "#6f42c1"
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;background:{};color:white;font-weight:600;">{}</span>',
            color, t
        )

    @admin.display(description="Status")
    def status_badge(self, obj: PurchaseInvoiceHeader):
        label = obj.get_status_display()
        if obj.status == Status.DRAFT:
            color = "#6c757d"
        elif obj.status == Status.CONFIRMED:
            color = "#0dcaf0"
        elif obj.status == Status.POSTED:
            color = "#198754"
        else:
            color = "#dc3545"
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;background:{};color:white;font-weight:600;">{}</span>',
            color, label
        )

    @admin.display(description="Vendor")
    def vendor_display(self, obj: PurchaseInvoiceHeader):
        # show snapshot first, fallback to FK string
        return obj.vendor_name or (str(obj.vendor) if obj.vendor_id else "-")

    @admin.display(description="Regime")
    def regime_display(self, obj: PurchaseInvoiceHeader):
        txt = obj.get_tax_regime_display()
        return txt

    @admin.display(description="RCM")
    def rcm_display(self, obj: PurchaseInvoiceHeader):
        return "Yes" if obj.is_reverse_charge else "No"

    @admin.display(description="ITC")
    def itc_display(self, obj: PurchaseInvoiceHeader):
        # quick consolidated ITC view
        elig = "Eligible" if obj.is_itc_eligible else "Not Eligible"
        claim = obj.get_itc_claim_status_display() if hasattr(obj, "get_itc_claim_status_display") else str(obj.itc_claim_status)
        return f"{elig} | {claim}"

    # ----------------------------
    # Admin protections / auto logic
    # ----------------------------
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.status in (Status.POSTED, Status.CANCELLED):
            # lock nearly everything on posted/cancelled
            ro.extend([
                "doc_type", "bill_date", "doc_code", "doc_no", "purchase_number",
                "supplier_invoice_number", "supplier_invoice_date",
                "ref_document",
                "vendor", "vendor_name", "vendor_gstin", "vendor_state",
                "supply_category", "default_taxability",
                "supplier_state", "place_of_supply_state",
                "tax_regime", "is_igst",
                "is_reverse_charge",
                "is_itc_eligible", "itc_claim_status", "itc_claim_period", "itc_claimed_at", "itc_block_reason",
                "gstr2b_match_status",
                "round_off",
                "entity", "entityfinid", "subentity",
            ])
        return tuple(dict.fromkeys(ro))  # remove duplicates

    def save_model(self, request, obj: PurchaseInvoiceHeader, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user

        # Allow save first so obj has id
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """
        After lines saved in inlines:
          - refresh vendor snapshot
          - derive regime (tax_regime / is_igst)
          - recompute totals from DB lines
          - rebuild tax summary
        """
        super().save_related(request, form, formsets, change)

        obj: PurchaseInvoiceHeader = form.instance

        # Lock recalculation for posted/cancelled
        if obj.status in (Status.POSTED, Status.CANCELLED):
            return

        # Re-derive / recalc based on saved lines
        with transaction.atomic():
            # vendor snapshot
            attrs = {"vendor": obj.vendor, "vendor_name": obj.vendor_name, "vendor_gstin": obj.vendor_gstin, "vendor_state": obj.vendor_state}
            PurchaseInvoiceService.apply_vendor_snapshot(attrs, instance=obj)

            obj.vendor_name = attrs.get("vendor_name")
            obj.vendor_gstin = attrs.get("vendor_gstin")
            obj.vendor_state = attrs.get("vendor_state")

            # derive regime
            derived = PurchaseInvoiceService.derive_tax_regime({}, instance=obj)
            obj.tax_regime = derived.tax_regime
            obj.is_igst = derived.is_igst

            # recompute totals from DB lines
            db_lines = list(obj.lines.all().values(
                "taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount"
            ))
            totals = PurchaseInvoiceService.compute_totals(db_lines)
            obj.total_taxable = totals["total_taxable"]
            obj.total_cgst = totals["total_cgst"]
            obj.total_sgst = totals["total_sgst"]
            obj.total_igst = totals["total_igst"]
            obj.total_cess = totals["total_cess"]
            obj.total_gst = totals["total_gst"]
            obj.grand_total = totals["grand_total_base"] + (obj.round_off or 0)

            obj.save()

            # tax summary
            PurchaseInvoiceService.rebuild_tax_summary(obj)

    # ----------------------------
    # Admin Actions
    # ----------------------------

    @admin.action(description="Rebuild Tax Summary (selected)")
    def action_rebuild_tax_summary(self, request, queryset):
        count = 0
        for obj in queryset:
            PurchaseInvoiceService.rebuild_tax_summary(obj)
            count += 1
        self.message_user(request, f"Rebuilt tax summary for {count} document(s).", level=messages.SUCCESS)

    @admin.action(description="Confirm (Draft → Confirmed)")
    def action_confirm(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            try:
                PurchaseInvoiceActions.confirm(obj.pk)
                ok += 1
            except Exception as e:
                fail += 1
                self.message_user(request, f"[{obj.pk}] confirm failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Confirmed {ok} document(s).", level=messages.SUCCESS)
        if fail == 0 and ok == 0:
            self.message_user(request, "Nothing confirmed.", level=messages.WARNING)

    @admin.action(description="Post (Confirmed → Posted)")
    def action_post(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            try:
                PurchaseInvoiceActions.post(obj.pk)
                ok += 1
            except Exception as e:
                fail += 1
                self.message_user(request, f"[{obj.pk}] post failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Posted {ok} document(s).", level=messages.SUCCESS)

    @admin.action(description="Cancel (Draft/Confirmed → Cancelled)")
    def action_cancel(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            try:
                PurchaseInvoiceActions.cancel(obj.pk)
                ok += 1
            except Exception as e:
                fail += 1
                self.message_user(request, f"[{obj.pk}] cancel failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Cancelled {ok} document(s).", level=messages.SUCCESS)

    @admin.action(description="Create Credit Note from Invoice (selected Tax Invoices)")
    def action_create_credit_note(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            try:
                res = PurchaseNoteFactory.create_note_from_invoice(
                    invoice_id=obj.pk,
                    note_type=DocType.CREDIT_NOTE,
                    created_by_id=request.user.id,
                )
                ok += 1
                self.message_user(request, f"CN created: {res.header} (from invoice {obj.pk})", level=messages.SUCCESS)
            except Exception as e:
                fail += 1
                self.message_user(request, f"[{obj.pk}] CN failed: {e}", level=messages.ERROR)
        if ok == 0 and fail == 0:
            self.message_user(request, "No action performed.", level=messages.WARNING)

    @admin.action(description="Create Debit Note from Invoice (selected Tax Invoices)")
    def action_create_debit_note(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            try:
                res = PurchaseNoteFactory.create_note_from_invoice(
                    invoice_id=obj.pk,
                    note_type=DocType.DEBIT_NOTE,
                    created_by_id=request.user.id,
                )
                ok += 1
                self.message_user(request, f"DN created: {res.header} (from invoice {obj.pk})", level=messages.SUCCESS)
            except Exception as e:
                fail += 1
                self.message_user(request, f"[{obj.pk}] DN failed: {e}", level=messages.ERROR)
        if ok == 0 and fail == 0:
            self.message_user(request, "No action performed.", level=messages.WARNING)


# ----------------------------
# Optional: Line Admin (quick debug)
# ----------------------------

@admin.register(PurchaseInvoiceLine)
class PurchaseInvoiceLineAdmin(admin.ModelAdmin):
    list_display = (
        "id", "header", "line_no", "product", "qty", "rate", "taxable_value",
        "cgst_amount", "sgst_amount", "igst_amount", "line_total",
        "is_itc_eligible",
    )
    list_select_related = ("header", "product", "uom")
    list_filter = ("taxability", "is_service", "is_itc_eligible")
    search_fields = ("product_desc", "hsn_sac", "header__purchase_number", "header__supplier_invoice_number")
    ordering = ("-id",)


# ----------------------------
# Optional: Tax Summary Admin (read-only debug)
# ----------------------------

@admin.register(PurchaseTaxSummary)
class PurchaseTaxSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "id", "header", "taxability", "hsn_sac", "is_service", "gst_rate",
        "is_reverse_charge", "taxable_value", "cgst_amount", "sgst_amount", "igst_amount",
        "itc_eligible_tax", "itc_ineligible_tax",
    )
    list_select_related = ("header",)
    list_filter = ("taxability", "is_service", "is_reverse_charge", "gst_rate")
    search_fields = ("header__purchase_number", "header__supplier_invoice_number", "hsn_sac")
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    



@admin.register(PurchaseSettings)
class PurchaseSettingsAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "default_workflow_action", "default_doc_code_invoice", "enable_round_off")
    list_filter = ("default_workflow_action", "enable_round_off", "auto_derive_tax_regime")
    search_fields = ("entity__name", "subentity__name", "default_doc_code_invoice")


@admin.register(PurchaseLockPeriod)
class PurchaseLockPeriodAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "lock_date", "reason")
    list_filter = ("entity", "subentity")
    search_fields = ("reason",)


@admin.register(PurchaseChoiceOverride)
class PurchaseChoiceOverrideAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "choice_group", "choice_key", "is_enabled", "override_label")
    list_filter = ("choice_group", "is_enabled", "entity")
    search_fields = ("choice_group", "choice_key", "override_label")

