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
from purchase.models.purchase_addons import (
    PurchaseChargeType,
    PurchaseChargeLine,
    PurchaseAttachment,
)
from purchase.models.purchase_ap import (
    VendorBillOpenItem,
    VendorSettlement,
    VendorSettlementLine,
)
from purchase.models.purchase_statutory import (
    PurchaseStatutoryChallan,
    PurchaseStatutoryChallanLine,
    PurchaseStatutoryReturn,
    PurchaseStatutoryReturnLine,
)
from purchase.models.gstr2b_models import (
    Gstr2bImportBatch,
    Gstr2bImportRow,
)
from purchase.models.itc_models import (
    PurchaseItcAction,
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


class PurchaseChargeLineInline(admin.TabularInline):
    model = PurchaseChargeLine
    extra = 0
    show_change_link = True
    fields = (
        "line_no",
        "charge_type",
        "description",
        "taxability",
        "is_service",
        "hsn_sac_code",
        "is_rate_inclusive_of_tax",
        "taxable_value",
        "gst_rate",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "total_value",
        "itc_eligible",
        "itc_block_reason",
    )
    ordering = ("line_no", "id")


class PurchaseAttachmentInline(admin.TabularInline):
    model = PurchaseAttachment
    extra = 0
    fields = ("file", "original_name", "content_type", "uploaded_by")
    readonly_fields = ("uploaded_by",)


# ----------------------------
# Header Admin
# ----------------------------

@admin.register(PurchaseInvoiceHeader)
class PurchaseInvoiceHeaderAdmin(admin.ModelAdmin):
    inlines = [PurchaseInvoiceLineInline, PurchaseChargeLineInline, PurchaseTaxSummaryInline, PurchaseAttachmentInline]

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
        "tds_display",
        "gst_tds_display",
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
        "withholding_enabled",
        "gst_tds_enabled",
        "gst_tds_status",
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
        "delete_selected",
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
        ("Withholding (IT-TDS)", {
            "fields": (
                ("withholding_enabled", "tds_is_manual"),
                ("tds_section", "tds_rate"),
                ("tds_base_amount", "tds_amount"),
                ("tds_reason",),
                ("vendor_tds_declared",),
                ("vendor_tds_rate", "vendor_tds_base_amount", "vendor_tds_amount"),
                ("vendor_tds_notes",),
            )
        }),
        ("GST-TDS u/s 51", {
            "fields": (
                ("gst_tds_enabled", "gst_tds_is_manual"),
                ("gst_tds_contract_ref", "gst_tds_status"),
                ("gst_tds_rate", "gst_tds_base_amount"),
                ("gst_tds_cgst_amount", "gst_tds_sgst_amount", "gst_tds_igst_amount"),
                ("gst_tds_amount",),
                ("gst_tds_reason",),
                ("vendor_gst_tds_declared",),
                ("vendor_gst_tds_rate", "vendor_gst_tds_base_amount", "vendor_gst_tds_amount"),
                ("vendor_gst_tds_cgst_amount", "vendor_gst_tds_sgst_amount", "vendor_gst_tds_igst_amount"),
                ("vendor_gst_tds_notes",),
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
        "tds_rate",
        "tds_base_amount",
        "tds_amount",
        "gst_tds_rate",
        "gst_tds_base_amount",
        "gst_tds_cgst_amount",
        "gst_tds_sgst_amount",
        "gst_tds_igst_amount",
        "gst_tds_amount",
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

    @admin.display(description="IT-TDS")
    def tds_display(self, obj: PurchaseInvoiceHeader):
        if not bool(obj.withholding_enabled):
            return "Off"
        section = getattr(getattr(obj, "tds_section", None), "section_code", "-")
        return f"{section} | {obj.tds_amount}"

    @admin.display(description="GST-TDS")
    def gst_tds_display(self, obj: PurchaseInvoiceHeader):
        if not bool(obj.gst_tds_enabled):
            return "Off"
        st = obj.get_gst_tds_status_display() if hasattr(obj, "get_gst_tds_status_display") else str(obj.gst_tds_status)
        return f"{st} | {obj.gst_tds_amount}"

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
                "withholding_enabled", "tds_is_manual", "tds_section", "tds_reason",
                "vendor_tds_declared", "vendor_tds_notes",
                "gst_tds_enabled", "gst_tds_is_manual", "gst_tds_contract_ref", "gst_tds_status", "gst_tds_reason",
                "vendor_gst_tds_declared", "vendor_gst_tds_notes",
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


@admin.register(PurchaseChargeType)
class PurchaseChargeTypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "code",
        "name",
        "base_category",
        "gst_rate_default",
        "itc_eligible_default",
        "is_active",
    )
    list_filter = ("base_category", "is_active", "entity")
    search_fields = ("code", "name", "description", "hsn_sac_code_default")
    ordering = ("entity_id", "code")


@admin.register(PurchaseChargeLine)
class PurchaseChargeLineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "header",
        "line_no",
        "charge_type",
        "taxability",
        "taxable_value",
        "gst_rate",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "total_value",
        "itc_eligible",
    )
    list_filter = ("charge_type", "taxability", "is_service", "itc_eligible")
    search_fields = ("header__purchase_number", "header__supplier_invoice_number", "description", "hsn_sac_code")
    ordering = ("-id",)


@admin.register(PurchaseAttachment)
class PurchaseAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "header", "original_name", "content_type", "uploaded_by", "created_at")
    list_filter = ("content_type", "created_at")
    search_fields = ("header__purchase_number", "header__supplier_invoice_number", "original_name")
    readonly_fields = ("created_at", "updated_at")


class VendorSettlementLineInline(admin.TabularInline):
    model = VendorSettlementLine
    extra = 0
    fields = ("open_item", "amount", "applied_amount_signed", "note")
    readonly_fields = ("applied_amount_signed",)


@admin.register(VendorBillOpenItem)
class VendorBillOpenItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "header",
        "vendor",
        "doc_type",
        "bill_date",
        "due_date",
        "original_amount",
        "settled_amount",
        "outstanding_amount",
        "is_open",
    )
    list_filter = ("doc_type", "is_open", "entity", "entityfinid", "subentity")
    search_fields = ("purchase_number", "supplier_invoice_number", "vendor__accountname")
    ordering = ("-bill_date", "-id")
    list_select_related = ("header", "vendor", "entity", "entityfinid", "subentity")


@admin.register(VendorSettlement)
class VendorSettlementAdmin(admin.ModelAdmin):
    inlines = [VendorSettlementLineInline]
    list_display = (
        "id",
        "settlement_type",
        "settlement_date",
        "vendor",
        "total_amount",
        "status",
        "reference_no",
        "external_voucher_no",
        "entity",
        "entityfinid",
    )
    list_filter = ("settlement_type", "status", "entity", "entityfinid", "subentity")
    search_fields = ("reference_no", "external_voucher_no", "remarks", "vendor__accountname")
    date_hierarchy = "settlement_date"
    list_select_related = ("vendor", "entity", "entityfinid", "subentity", "posted_by")
    readonly_fields = ("total_amount", "posted_at", "posted_by")


@admin.register(VendorSettlementLine)
class VendorSettlementLineAdmin(admin.ModelAdmin):
    list_display = ("id", "settlement", "open_item", "amount", "applied_amount_signed", "note")
    list_filter = ("settlement__status", "settlement__settlement_type")
    search_fields = (
        "settlement__reference_no",
        "settlement__external_voucher_no",
        "open_item__purchase_number",
        "open_item__supplier_invoice_number",
    )


class PurchaseStatutoryChallanLineInline(admin.TabularInline):
    model = PurchaseStatutoryChallanLine
    extra = 0
    fields = ("header", "section", "amount")


@admin.register(PurchaseStatutoryChallan)
class PurchaseStatutoryChallanAdmin(admin.ModelAdmin):
    inlines = [PurchaseStatutoryChallanLineInline]
    list_display = (
        "id",
        "tax_type",
        "challan_no",
        "challan_date",
        "amount",
        "interest_amount",
        "late_fee_amount",
        "penalty_amount",
        "status",
        "deposited_on",
        "entity",
        "entityfinid",
        "subentity",
    )
    list_filter = ("tax_type", "status", "entity", "entityfinid", "subentity")
    search_fields = ("challan_no", "bank_ref_no", "bsr_code", "cin_no", "minor_head_code", "remarks")
    date_hierarchy = "challan_date"
    readonly_fields = ("amount", "deposited_at", "deposited_by", "created_by", "created_at", "updated_at")


@admin.register(PurchaseStatutoryChallanLine)
class PurchaseStatutoryChallanLineAdmin(admin.ModelAdmin):
    list_display = ("id", "challan", "header", "section", "amount")
    list_filter = ("challan__tax_type", "challan__status")
    search_fields = ("challan__challan_no", "header__purchase_number", "header__supplier_invoice_number")


class PurchaseStatutoryReturnLineInline(admin.TabularInline):
    model = PurchaseStatutoryReturnLine
    extra = 0
    fields = (
        "header",
        "challan",
        "amount",
        "section_snapshot_code",
        "deductee_pan_snapshot",
        "deductee_gstin_snapshot",
        "cin_snapshot",
    )


@admin.register(PurchaseStatutoryReturn)
class PurchaseStatutoryReturnAdmin(admin.ModelAdmin):
    inlines = [PurchaseStatutoryReturnLineInline]
    list_display = (
        "id",
        "tax_type",
        "return_code",
        "period_from",
        "period_to",
        "amount",
        "interest_amount",
        "late_fee_amount",
        "penalty_amount",
        "status",
        "filed_on",
        "ack_no",
        "arn_no",
        "revision_no",
        "entity",
        "entityfinid",
        "subentity",
    )
    list_filter = ("tax_type", "status", "entity", "entityfinid", "subentity")
    search_fields = ("return_code", "ack_no", "arn_no", "remarks")
    readonly_fields = ("amount", "filed_at", "filed_by", "created_by", "created_at", "updated_at")


@admin.register(PurchaseStatutoryReturnLine)
class PurchaseStatutoryReturnLineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filing",
        "header",
        "challan",
        "amount",
        "section_snapshot_code",
        "deductee_pan_snapshot",
        "deductee_gstin_snapshot",
        "cin_snapshot",
    )
    list_filter = ("filing__tax_type", "filing__status")
    search_fields = ("filing__return_code", "header__purchase_number", "header__supplier_invoice_number")


@admin.register(Gstr2bImportBatch)
class Gstr2bImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "period", "source", "reference", "entity", "entityfinid", "subentity", "imported_by", "created_at")
    list_filter = ("source", "entity", "entityfinid", "subentity", "period")
    search_fields = ("period", "reference")
    date_hierarchy = "created_at"


@admin.register(Gstr2bImportRow)
class Gstr2bImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "batch",
        "supplier_gstin",
        "supplier_invoice_number",
        "supplier_invoice_date",
        "taxable_value",
        "igst",
        "cgst",
        "sgst",
        "cess",
        "match_status",
        "matched_purchase",
    )
    list_filter = ("match_status", "is_igst", "doc_type")
    search_fields = ("supplier_gstin", "supplier_invoice_number", "supplier_name")
    raw_id_fields = ("batch", "matched_purchase", "pos_state")


@admin.register(PurchaseItcAction)
class PurchaseItcActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "header",
        "action_type",
        "period",
        "from_status",
        "to_status",
        "igst",
        "cgst",
        "sgst",
        "cess",
        "acted_at",
        "acted_by",
    )
    list_filter = ("action_type", "period", "to_status")
    search_fields = ("header__purchase_number", "header__supplier_invoice_number", "reason", "notes")
    raw_id_fields = ("header", "gstr2b_batch", "attachment", "acted_by")

