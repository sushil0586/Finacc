from __future__ import annotations

from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone

from sales.models.sales_settings import SalesSettings, SalesLockPeriod, SalesChoiceOverride
from sales.models.sales_core import (
    SalesInvoiceHeader,
    SalesInvoiceLine,
    SalesTaxSummary,
    SalesEInvoiceDetails,
    SalesEWayBillDetails,
    SalesEWayEvent,
    SalesInvoiceShipToSnapshot,
)
from sales.services.sales_invoice_service import SalesInvoiceService

# If you created separate actions module later, you can swap to that
# from sales.services.sales_invoice_actions import SalesInvoiceActions


# ----------------------------
# Inlines
# ----------------------------

class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 0
    show_change_link = True

    autocomplete_fields = ["product", "uom"]
    fields = (
        "line_no",
        "product",
        "is_service",
        "hsn_sac_code",
        "uom",
        "qty",
        "free_qty",
        "rate",
        "is_rate_inclusive_of_tax",
        "discount_type",
        "discount_percent",
        "discount_amount",
        "gst_rate",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "taxable_value",
        "line_total",
        "sales_account",
    )
    ordering = ("line_no", "id")


class SalesTaxSummaryInline(admin.TabularInline):
    model = SalesTaxSummary
    extra = 0
    can_delete = False
    show_change_link = False

    readonly_fields = (
        "taxability",
        "hsn_sac_code",
        "is_service",
        "gst_rate",
        "is_reverse_charge",
        "taxable_value",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
    )
    fields = readonly_fields
    ordering = ("gst_rate", "taxability", "hsn_sac_code")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
    
class SalesInvoiceShipToSnapshotInline(admin.StackedInline):
    model = SalesInvoiceShipToSnapshot
    extra = 0
    can_delete = False
    show_change_link = False

    readonly_fields = (
        "address1", "address2", "city", "state_code", "pincode",
        "full_name", "phone", "email",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
    
class SalesEInvoiceDetailsInline(admin.StackedInline):
    model = SalesEInvoiceDetails
    extra = 0
    can_delete = False
    show_change_link = True

    readonly_fields = (
        "status",
        "irn", "ack_no", "ack_date",
        "generated_at",
        "cancelled_at", "cancel_reason_code", "cancel_remarks",
        "request_payload", "response_payload", "last_error",
        "signed_invoice", "signed_qr_code",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False
    
class SalesEWayBillDetailsInline(admin.StackedInline):
    model = SalesEWayBillDetails
    extra = 0
    can_delete = False
    show_change_link = True

    readonly_fields = (
        "status",
        "generated_via_irp",
        "eway_bill_no", "eway_bill_date", "valid_upto",
        "transporter_id", "transporter_name",
        "transport_mode", "distance_km",
        "transport_doc_no", "transport_doc_date",
        "from_place", "from_pincode",
        "vehicle_no", "vehicle_type",
        "cancelled_at", "cancel_reason_code", "cancel_remarks",
        "last_vehicle_update_at",
        "original_valid_upto", "current_valid_upto",
        "extension_count", "last_extension_at",
        "last_extension_reason_code", "last_extension_remarks",
        "last_extension_from_place", "last_extension_from_pincode",
        "last_transporter_update_at",
        "request_payload", "response_payload", "last_error",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


# ----------------------------
# Header Admin
# ----------------------------

@admin.register(SalesInvoiceHeader)
class SalesInvoiceHeaderAdmin(admin.ModelAdmin):
    inlines = [SalesInvoiceShipToSnapshotInline,SalesEInvoiceDetailsInline,SalesEWayBillDetailsInline, SalesInvoiceLineInline, SalesTaxSummaryInline]

    list_display = (
        "id",
        "doc_badge",
        "doc_no",
        "bill_date",
        "status_badge",
        "customer_display",
        "customer_gstin",
        "regime_display",
        "pos_display",
        "einvoice_display",
        "eway_display",
        "grand_total",
        "entity",
        "entityfinid",
        "subentity",
    )
    list_select_related = (
        "customer",
        "entity",
        "entityfinid",
        "subentity",
    )
    list_filter = (
        "doc_type",
        "status",
        "supply_category",
        "taxability",
        "tax_regime",
        "is_igst",
        "is_reverse_charge",
        "gst_compliance_mode",
        "is_einvoice_applicable",
        "is_eway_applicable",
        "entity",
        "entityfinid",
        "subentity",
    )
    search_fields = (
        "invoice_number",
        "customer_name",
        "customer_gstin",
        "doc_code",
        "reference",
    )
    date_hierarchy = "bill_date"
    ordering = ("-bill_date", "-id")

    raw_id_fields = (
        "customer",
        "shipping_detail",
        "entity",
        "entityfinid",
        "subentity",
    )

    actions = [
        "delete_selected",
        "action_rebuild_tax_summary",
        "action_confirm",
        "action_post",
        "action_cancel",
    ]

    fieldsets = (
        ("Document", {
            "fields": (
                ("doc_type", "status"),
                ("bill_date", "posting_date"),
                ("doc_code", "doc_no", "invoice_number"),
                ("credit_days", "due_date"),
                ("reference",),
            )
        }),
        ("Customer (Snapshot)", {
            "fields": (
                ("customer",),
                ("customer_name", "customer_gstin"),
                ("customer_state_code",),
                ("shipping_detail",),   # ✅ add
            )
        }),
        ("Seller / POS / Tax", {
            "fields": (
                ("seller_gstin", "seller_state_code"),
                ("place_of_supply_state_code",),
                ("supply_category", "taxability"),
                ("tax_regime", "is_igst"),
                ("is_reverse_charge",),
            )
        }),
        ("Compliance", {
            "fields": (
                ("gst_compliance_mode",),
                ("is_einvoice_applicable", "is_eway_applicable"),
            )
        }),
        ("Totals", {
            "fields": (
                ("total_taxable_value",),
                ("total_cgst", "total_sgst", "total_igst", "total_cess"),
                ("total_discount", "total_other_charges"),
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
        ("Notes", {
            "fields": ("remarks",),
        }),
    )

    readonly_fields = (
        # computed / derived
        "posting_date",
        "due_date",
        "tax_regime",
        "is_igst",
        "total_taxable_value",
        "total_cgst",
        "total_sgst",
        "total_igst",
        "total_cess",
        "total_discount",
        "round_off",
        "grand_total",
        "created_by",
    )

    # ----------------------------
    # Visual helpers
    # ----------------------------
    @admin.display(description="Doc")
    def doc_badge(self, obj: SalesInvoiceHeader):
        t = obj.get_doc_type_display()
        color = "#0d6efd" if obj.doc_type == SalesInvoiceHeader.DocType.TAX_INVOICE else "#6f42c1"
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;background:{};color:white;font-weight:600;">{}</span>',
            color, t
        )

    @admin.display(description="Status")
    def status_badge(self, obj: SalesInvoiceHeader):
        label = obj.get_status_display()
        if obj.status == SalesInvoiceHeader.Status.DRAFT:
            color = "#6c757d"
        elif obj.status == SalesInvoiceHeader.Status.CONFIRMED:
            color = "#0dcaf0"
        elif obj.status == SalesInvoiceHeader.Status.POSTED:
            color = "#198754"
        else:
            color = "#dc3545"
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;background:{};color:white;font-weight:600;">{}</span>',
            color, label
        )

    @admin.display(description="Customer")
    def customer_display(self, obj: SalesInvoiceHeader):
        return obj.customer_name or (str(obj.customer) if obj.customer_id else "-")

    @admin.display(description="Regime")
    def regime_display(self, obj: SalesInvoiceHeader):
        return obj.get_tax_regime_display()

    @admin.display(description="POS")
    def pos_display(self, obj: SalesInvoiceHeader):
        return obj.place_of_supply_state_code or "-"

    @admin.display(description="E-Invoice")
    def einvoice_display(self, obj: SalesInvoiceHeader):
        return "Yes" if obj.is_einvoice_applicable else "No"

    @admin.display(description="E-Way")
    def eway_display(self, obj: SalesInvoiceHeader):
        return "Yes" if obj.is_eway_applicable else "No"

    # ----------------------------
    # Admin protections / auto logic
    # ----------------------------
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.status in (SalesInvoiceHeader.Status.POSTED, SalesInvoiceHeader.Status.CANCELLED):
            ro.extend([
                "doc_type", "bill_date", "doc_code", "doc_no", "invoice_number",
                "credit_days",
                "customer", "customer_name", "customer_gstin", "customer_state_code",
                "seller_gstin", "seller_state_code", "place_of_supply_state_code",
                "supply_category", "taxability",
                "is_reverse_charge",
                "gst_compliance_mode", "is_einvoice_applicable", "is_eway_applicable",
                "total_other_charges",
                "entity", "entityfinid", "subentity",
                "reference",
            ])
        return tuple(dict.fromkeys(ro))

    def save_model(self, request, obj: SalesInvoiceHeader, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """
        After lines saved in inlines:
          - derive regime (tax_regime / is_igst)
          - recompute totals from DB lines
          - rebuild tax summary
        """
        super().save_related(request, form, formsets, change)

        obj: SalesInvoiceHeader = form.instance

        # Lock recalculation for posted/cancelled
        if obj.status in (SalesInvoiceHeader.Status.POSTED, SalesInvoiceHeader.Status.CANCELLED):
            return

        with transaction.atomic():
            # Apply dates and regime
            SalesInvoiceService.apply_dates(obj)
            SalesInvoiceService.derive_tax_regime(obj)

            # recompute line amounts (admin users may change fields in inline)
            for line in obj.lines.all():
                SalesInvoiceService.compute_line_amounts(obj, line)
                line.save(update_fields=[
                    "taxable_value",
                    "cgst_amount",
                    "sgst_amount",
                    "igst_amount",
                    "cess_amount",
                    "discount_amount",
                    "line_total",
                    "updated_at",
                ])

            # rebuild tax summary + totals
            SalesInvoiceService.rebuild_tax_summary(obj)
            SalesInvoiceService.compute_and_persist_totals(obj, user=request.user)

            obj.save(update_fields=["posting_date", "due_date", "tax_regime", "is_igst", "updated_at"])

    # ----------------------------
    # Admin Actions
    # ----------------------------
    @admin.action(description="Rebuild Tax Summary (selected)")
    def action_rebuild_tax_summary(self, request, queryset):
        count = 0
        for obj in queryset:
            SalesInvoiceService.rebuild_tax_summary(obj)
            count += 1
        self.message_user(request, f"Rebuilt tax summary for {count} document(s).", level=messages.SUCCESS)

    @admin.action(description="Confirm (Draft → Confirmed)")
    def action_confirm(self, request, queryset):
        ok, fail = 0, 0
        for obj in queryset:
            try:
                SalesInvoiceService.confirm(header=obj, user=request.user)
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
                SalesInvoiceService.post(header=obj, user=request.user)
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
                SalesInvoiceService.cancel(header=obj, user=request.user, reason="Cancelled from admin action")
                ok += 1
            except Exception as e:
                fail += 1
                self.message_user(request, f"[{obj.pk}] cancel failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Cancelled {ok} document(s).", level=messages.SUCCESS)


# ----------------------------
# Optional: Line Admin
# ----------------------------

@admin.register(SalesInvoiceLine)
class SalesInvoiceLineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "header",
        "line_no",
        "product",
        "qty",
        "rate",
        "taxable_value",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "line_total",
    )
    list_select_related = ("header", "product", "uom")
    list_filter = ("is_service",)
    search_fields = ("hsn_sac_code", "header__invoice_number")
    ordering = ("-id",)



@admin.register(SalesEInvoiceDetails)
class SalesEInvoiceDetailsAdmin(admin.ModelAdmin):
    list_display = ("id", "header", "status", "irn", "ack_no", "ack_date", "entity", "entityfinid", "subentity")
    list_select_related = ("header", "entity", "entityfinid", "subentity")
    list_filter = ("status", "entity", "entityfinid", "subentity")
    search_fields = ("header__invoice_number", "irn", "ack_no")
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False
    
@admin.register(SalesEWayBillDetails)
class SalesEWayBillDetailsAdmin(admin.ModelAdmin):
    list_display = ("id", "header", "status", "eway_bill_no", "eway_bill_date", "valid_upto", "entity", "entityfinid", "subentity")
    list_select_related = ("header", "entity", "entityfinid", "subentity")
    list_filter = ("status", "entity", "entityfinid", "subentity", "generated_via_irp")
    search_fields = ("header__invoice_number", "eway_bill_no", "transporter_id", "vehicle_no")
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False
    

@admin.register(SalesEWayEvent)
class SalesEWayEventAdmin(admin.ModelAdmin):
    list_display = ("id", "eway", "event_type", "event_at", "eway_bill_no", "is_success", "error_code")
    list_select_related = ("eway",)
    list_filter = ("event_type", "is_success")
    search_fields = ("eway_bill_no", "reference_no", "error_code", "error_message")
    ordering = ("-event_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    
@admin.register(SalesInvoiceShipToSnapshot)
class SalesInvoiceShipToSnapshotAdmin(admin.ModelAdmin):
    list_display = ("header", "city", "state_code", "pincode", "full_name", "phone")
    list_select_related = ("header",)
    search_fields = ("header__invoice_number", "city", "pincode", "full_name", "phone", "email")
    ordering = ("-header_id",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ----------------------------
# Optional: Tax Summary Admin (read-only)
# ----------------------------

@admin.register(SalesTaxSummary)
class SalesTaxSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "header",
        "taxability",
        "hsn_sac_code",
        "is_service",
        "gst_rate",
        "is_reverse_charge",
        "taxable_value",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
    )
    list_select_related = ("header",)
    list_filter = ("taxability", "is_service", "is_reverse_charge", "gst_rate")
    search_fields = ("header__invoice_number", "hsn_sac_code")
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ----------------------------
# Settings / Lock / Choice Override Admins
# ----------------------------

@admin.register(SalesSettings)
class SalesSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "default_workflow_action",
        "default_doc_code_invoice",
        "enable_round_off",
        "enable_einvoice",
        "enable_eway",
        "prefer_irp_generate_einvoice_and_eway_together",
    )
    list_filter = ("default_workflow_action", "enable_round_off", "auto_derive_tax_regime", "enable_einvoice", "enable_eway")
    search_fields = ("entity__name", "subentity__name", "default_doc_code_invoice")


@admin.register(SalesLockPeriod)
class SalesLockPeriodAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "lock_date", "reason")
    list_filter = ("entity", "subentity")
    search_fields = ("reason",)


@admin.register(SalesChoiceOverride)
class SalesChoiceOverrideAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "choice_group", "choice_key", "is_enabled", "override_label")
    list_filter = ("choice_group", "is_enabled", "entity")
    search_fields = ("choice_group", "choice_key", "override_label")
