from __future__ import annotations

from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Prefetch
from django.utils.html import format_html

from payments.models import (
    PaymentMode,
    PaymentSettings,
    PaymentVoucherAdvanceAdjustment,
    PaymentVoucherAdjustment,
    PaymentVoucherAllocation,
    PaymentVoucherHeader,
)
from payments.services.payment_voucher_service import PaymentVoucherService


ZERO = Decimal("0.00")


def _approval_state(payload):
    if not isinstance(payload, dict):
        return {}
    state = payload.get("_approval_state")
    return state if isinstance(state, dict) else {}


@admin.register(PaymentMode)
class PaymentModeAdmin(admin.ModelAdmin):
    list_display = ("id", "paymentmode", "paymentmodecode", "iscash", "createdby")
    list_filter = ("iscash",)
    search_fields = ("paymentmode", "paymentmodecode")
    raw_id_fields = ("createdby",)


class PaymentVoucherAllocationInline(admin.TabularInline):
    model = PaymentVoucherAllocation
    extra = 0
    show_change_link = True
    raw_id_fields = ("open_item",)
    readonly_fields = ("open_item_ref", "open_item_vendor", "open_item_outstanding")
    fields = (
        "open_item",
        "open_item_ref",
        "open_item_vendor",
        "open_item_outstanding",
        "settled_amount",
        "is_full_settlement",
        "is_advance_adjustment",
    )

    @admin.display(description="Bill Ref")
    def open_item_ref(self, obj):
        if not obj.open_item_id:
            return "-"
        return obj.open_item.purchase_number or obj.open_item.supplier_invoice_number or f"Open Item #{obj.open_item_id}"

    @admin.display(description="Vendor")
    def open_item_vendor(self, obj):
        if not obj.open_item_id:
            return "-"
        return getattr(obj.open_item.vendor, "accountname", "-")

    @admin.display(description="Outstanding")
    def open_item_outstanding(self, obj):
        if not obj.open_item_id:
            return "-"
        return obj.open_item.outstanding_amount


class PaymentVoucherAdjustmentInline(admin.TabularInline):
    model = PaymentVoucherAdjustment
    extra = 0
    show_change_link = True
    raw_id_fields = ("allocation", "ledger_account")
    readonly_fields = ("allocation_ref",)
    fields = (
        "allocation",
        "allocation_ref",
        "adj_type",
        "ledger_account",
        "amount",
        "settlement_effect",
        "remarks",
    )

    @admin.display(description="Allocation Bill")
    def allocation_ref(self, obj):
        if not obj.allocation_id or not obj.allocation.open_item_id:
            return "-"
        return obj.allocation.open_item.purchase_number or obj.allocation.open_item.supplier_invoice_number or obj.allocation.open_item_id


class PaymentVoucherAdvanceAdjustmentInline(admin.TabularInline):
    model = PaymentVoucherAdvanceAdjustment
    extra = 0
    show_change_link = True
    raw_id_fields = ("advance_balance", "allocation", "open_item", "ap_settlement")
    readonly_fields = (
        "advance_source_ref",
        "advance_balance_open",
        "open_item_ref",
        "ap_settlement_ref",
    )
    fields = (
        "advance_balance",
        "advance_source_ref",
        "advance_balance_open",
        "allocation",
        "open_item",
        "open_item_ref",
        "adjusted_amount",
        "ap_settlement",
        "ap_settlement_ref",
        "remarks",
    )

    @admin.display(description="Advance Source")
    def advance_source_ref(self, obj):
        if not obj.advance_balance_id:
            return "-"
        ref = obj.advance_balance.reference_no or f"Advance #{obj.advance_balance_id}"
        voucher = getattr(obj.advance_balance, "payment_voucher", None)
        if voucher:
            code = voucher.voucher_code or f"{voucher.doc_code}-{voucher.doc_no or 'Draft'}"
            return f"{ref} / {code}"
        return ref

    @admin.display(description="Advance Open")
    def advance_balance_open(self, obj):
        if not obj.advance_balance_id:
            return "-"
        return obj.advance_balance.outstanding_amount

    @admin.display(description="Bill Ref")
    def open_item_ref(self, obj):
        if not obj.open_item_id:
            return "-"
        return obj.open_item.purchase_number or obj.open_item.supplier_invoice_number or f"Open Item #{obj.open_item_id}"

    @admin.display(description="AP Settlement")
    def ap_settlement_ref(self, obj):
        if not obj.ap_settlement_id:
            return "-"
        return f"#{obj.ap_settlement_id} / {obj.ap_settlement.get_status_display()}"


@admin.register(PaymentVoucherHeader)
class PaymentVoucherHeaderAdmin(admin.ModelAdmin):
    inlines = [PaymentVoucherAllocationInline, PaymentVoucherAdjustmentInline, PaymentVoucherAdvanceAdjustmentInline]
    list_display = (
        "id",
        "voucher_identity",
        "voucher_date",
        "status",
        "approval_status",
        "payment_type",
        "paid_to",
        "cash_paid_amount",
        "advance_consumed_amount",
        "total_support_amount",
        "allocated_amount",
        "settlement_gap",
        "ap_settlement_ref",
    )
    list_filter = (
        "status",
        "payment_type",
        "supply_type",
        "entity",
        "entityfinid",
        "subentity",
        "voucher_date",
    )
    search_fields = (
        "voucher_code",
        "doc_code",
        "doc_no",
        "reference_number",
        "narration",
        "paid_to__accountname",
        "paid_from__accountname",
    )
    date_hierarchy = "voucher_date"
    ordering = ("-voucher_date", "-id")
    list_select_related = (
        "entity",
        "entityfinid",
        "subentity",
        "paid_from",
        "paid_to",
        "payment_mode",
        "created_by",
        "approved_by",
        "cancelled_by",
        "ap_settlement",
    )
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "paid_from",
        "paid_to",
        "payment_mode",
        "place_of_supply_state",
        "created_by",
        "approved_by",
        "cancelled_by",
        "ap_settlement",
    )
    actions = ["action_confirm", "action_post", "action_unpost", "action_cancel"]
    readonly_fields = (
        "doc_no",
        "voucher_code",
        "voucher_identity",
        "approval_status",
        "approval_people",
        "allocation_count",
        "adjustment_count",
        "advance_adjustment_count",
        "advance_consumed_amount",
        "total_support_amount",
        "allocated_amount",
        "settlement_gap",
        "ap_settlement_ref",
        "advance_balance_ref",
        "total_adjustment_amount",
        "settlement_effective_amount",
        "settlement_effective_amount_base_currency",
        "approved_at",
        "workflow_payload",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        ("Document", {
            "fields": (
                ("entity", "entityfinid", "subentity"),
                ("voucher_date", "doc_code", "doc_no", "voucher_code"),
                "voucher_identity",
                ("status", "approval_status"),
            )
        }),
        ("Party And Mode", {
            "fields": (
                ("payment_type", "supply_type"),
                ("paid_from", "paid_to", "payment_mode"),
                ("reference_number", "narration"),
            )
        }),
        ("Settlement Snapshot", {
            "fields": (
                ("cash_paid_amount", "total_adjustment_amount", "settlement_effective_amount"),
                ("advance_consumed_amount", "total_support_amount"),
                ("allocated_amount", "settlement_gap"),
                ("allocation_count", "adjustment_count", "advance_adjustment_count"),
                ("ap_settlement", "ap_settlement_ref"),
                "advance_balance_ref",
            )
        }),
        ("Currency And Instrument", {
            "classes": ("collapse",),
            "fields": (
                ("currency_code", "base_currency_code", "exchange_rate"),
                "settlement_effective_amount_base_currency",
                ("instrument_bank_name", "instrument_no", "instrument_date"),
            )
        }),
        ("Advance GST", {
            "classes": ("collapse",),
            "fields": (
                ("place_of_supply_state", "vendor_gstin"),
                ("advance_taxable_value", "advance_cgst", "advance_sgst"),
                ("advance_igst", "advance_cess"),
            )
        }),
        ("Workflow And Audit", {
            "classes": ("collapse",),
            "fields": (
                ("created_by", "approved_by", "approved_at"),
                "approval_people",
                ("is_cancelled", "cancelled_by", "cancelled_at"),
                "cancel_reason",
                "workflow_payload",
                ("created_at", "updated_at"),
            )
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            "allocations__open_item",
            "adjustments",
            Prefetch(
                "advance_adjustments",
                queryset=PaymentVoucherAdvanceAdjustment.objects.select_related(
                    "advance_balance",
                    "advance_balance__payment_voucher",
                    "open_item",
                    "ap_settlement",
                ),
            ),
        )

    @admin.action(description="Confirm (Draft -> Confirmed)")
    def action_confirm(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                PaymentVoucherService.confirm_voucher(obj.pk, confirmed_by_id=request.user.id)
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] confirm failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Confirmed {ok} payment voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Post (Confirmed/Draft -> Posted by policy)")
    def action_post(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                PaymentVoucherService.post_voucher(obj.pk, posted_by_id=request.user.id)
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] post failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Posted {ok} payment voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Unpost (Posted -> Draft/Confirmed by policy)")
    def action_unpost(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                PaymentVoucherService.unpost_voucher(obj.pk, unposted_by_id=request.user.id)
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] unpost failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Unposted {ok} payment voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Cancel (non-posted)")
    def action_cancel(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                PaymentVoucherService.cancel_voucher(obj.pk, cancelled_by_id=request.user.id, reason="Cancelled from admin")
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] cancel failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Cancelled {ok} payment voucher(s).", level=messages.SUCCESS)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.status in (
            PaymentVoucherHeader.Status.POSTED,
            PaymentVoucherHeader.Status.CANCELLED,
        ):
            ro.extend(
                [
                    "entity",
                    "entityfinid",
                    "subentity",
                    "voucher_date",
                    "doc_code",
                    "payment_type",
                    "supply_type",
                    "paid_from",
                    "paid_to",
                    "payment_mode",
                    "cash_paid_amount",
                    "reference_number",
                    "narration",
                    "instrument_bank_name",
                    "instrument_no",
                    "instrument_date",
                    "place_of_supply_state",
                    "vendor_gstin",
                    "advance_taxable_value",
                    "advance_cgst",
                    "advance_sgst",
                    "advance_igst",
                    "advance_cess",
                    "created_by",
                    "approved_by",
                    "cancelled_by",
                    "cancel_reason",
                    "status",
                    "is_cancelled",
                ]
            )
        return tuple(dict.fromkeys(ro))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Voucher")
    def voucher_identity(self, obj):
        if obj.voucher_code:
            return obj.voucher_code
        draft_no = obj.doc_no or "Draft"
        return f"{obj.doc_code}-{draft_no}"

    @admin.display(description="Approval")
    def approval_status(self, obj):
        state = _approval_state(obj.workflow_payload)
        return state.get("status") or "DRAFT"

    @admin.display(description="Approval People")
    def approval_people(self, obj):
        state = _approval_state(obj.workflow_payload)
        parts = []
        if state.get("submitted_by"):
            parts.append(f"Submitted by {state['submitted_by']}")
        if state.get("approved_by"):
            parts.append(f"Approved by {state['approved_by']}")
        if state.get("rejected_by"):
            parts.append(f"Rejected by {state['rejected_by']}")
        return " | ".join(parts) or "-"

    @admin.display(description="Allocations")
    def allocation_count(self, obj):
        return obj.allocations.count()

    @admin.display(description="Adjustments")
    def adjustment_count(self, obj):
        return obj.adjustments.count()

    @admin.display(description="Advance Rows")
    def advance_adjustment_count(self, obj):
        return obj.advance_adjustments.count()

    @admin.display(description="Advance Consumed")
    def advance_consumed_amount(self, obj):
        total = ZERO
        for row in obj.advance_adjustments.all():
            total += row.adjusted_amount or ZERO
        return total

    @admin.display(description="Settlement Support")
    def total_support_amount(self, obj):
        return (obj.settlement_effective_amount or ZERO) + self.advance_consumed_amount(obj)

    @admin.display(description="Allocated")
    def allocated_amount(self, obj):
        total = ZERO
        for row in obj.allocations.all():
            total += row.settled_amount or ZERO
        return total

    @admin.display(description="Balance")
    def settlement_gap(self, obj):
        return self.total_support_amount(obj) - self.allocated_amount(obj)

    @admin.display(description="AP Settlement")
    def ap_settlement_ref(self, obj):
        if not obj.ap_settlement_id:
            return "-"
        return format_html(
            "#{id} / {kind} / {status}",
            id=obj.ap_settlement_id,
            kind=obj.ap_settlement.get_settlement_type_display(),
            status=obj.ap_settlement.get_status_display(),
        )

    @admin.display(description="New Advance")
    def advance_balance_ref(self, obj):
        advance_balance = getattr(obj, "vendor_advance_balance", None)
        if not advance_balance:
            return "-"
        ref = advance_balance.reference_no or f"Advance #{advance_balance.pk}"
        return f"{ref} / outstanding {advance_balance.outstanding_amount}"


@admin.register(PaymentVoucherAllocation)
class PaymentVoucherAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment_voucher",
        "open_item",
        "open_item_ref",
        "open_item_outstanding",
        "settled_amount",
        "is_full_settlement",
        "is_advance_adjustment",
    )
    list_filter = (
        "is_full_settlement",
        "is_advance_adjustment",
        "payment_voucher__status",
    )
    search_fields = (
        "payment_voucher__voucher_code",
        "open_item__purchase_number",
        "open_item__supplier_invoice_number",
    )
    raw_id_fields = ("payment_voucher", "open_item")
    list_select_related = ("payment_voucher", "open_item", "open_item__vendor")

    @admin.display(description="Bill Ref")
    def open_item_ref(self, obj):
        if not obj.open_item_id:
            return "-"
        return obj.open_item.purchase_number or obj.open_item.supplier_invoice_number or f"Open Item #{obj.open_item_id}"

    @admin.display(description="Outstanding")
    def open_item_outstanding(self, obj):
        if not obj.open_item_id:
            return "-"
        return obj.open_item.outstanding_amount


@admin.register(PaymentVoucherAdjustment)
class PaymentVoucherAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment_voucher",
        "allocation",
        "adj_type",
        "ledger_account",
        "amount",
        "settlement_effect",
    )
    list_filter = ("adj_type", "settlement_effect", "payment_voucher__status")
    search_fields = ("payment_voucher__voucher_code", "remarks")
    raw_id_fields = ("payment_voucher", "allocation", "ledger_account")
    list_select_related = ("payment_voucher", "allocation", "ledger_account")


@admin.register(PaymentVoucherAdvanceAdjustment)
class PaymentVoucherAdvanceAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment_voucher",
        "advance_balance",
        "advance_source_ref",
        "allocation",
        "open_item",
        "adjusted_amount",
        "ap_settlement",
    )
    list_filter = ("payment_voucher__status",)
    search_fields = ("payment_voucher__voucher_code", "remarks", "advance_balance__reference_no")
    raw_id_fields = ("payment_voucher", "advance_balance", "allocation", "open_item", "ap_settlement")
    list_select_related = (
        "payment_voucher",
        "advance_balance",
        "advance_balance__payment_voucher",
        "allocation",
        "open_item",
        "ap_settlement",
    )

    @admin.display(description="Advance Source")
    def advance_source_ref(self, obj):
        if not obj.advance_balance_id:
            return "-"
        ref = obj.advance_balance.reference_no or f"Advance #{obj.advance_balance_id}"
        voucher = getattr(obj.advance_balance, "payment_voucher", None)
        if voucher:
            return f"{ref} / {voucher.voucher_code or voucher.doc_code}"
        return ref


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "default_doc_code_payment",
        "default_workflow_action",
        "maker_checker_mode",
        "confirm_rule",
        "allocation_rule",
    )
    list_filter = ("default_workflow_action", "entity")
    search_fields = ("entity__entityname", "subentity__subentityname", "default_doc_code_payment")
    raw_id_fields = ("entity", "subentity")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Scope", {"fields": (("entity", "subentity"),)}),
        ("Defaults", {"fields": (("default_doc_code_payment", "default_workflow_action"),)}),
        ("Policies", {"fields": ("policy_controls",)}),
        ("Audit", {"classes": ("collapse",), "fields": (("created_at", "updated_at"),)}),
    )

    @admin.display(description="Maker Checker")
    def maker_checker_mode(self, obj):
        return (obj.policy_controls or {}).get("payment_maker_checker", "off")

    @admin.display(description="Confirm Before Post")
    def confirm_rule(self, obj):
        return (obj.policy_controls or {}).get("require_confirm_before_post", "on")

    @admin.display(description="Allocation Rule")
    def allocation_rule(self, obj):
        return (obj.policy_controls or {}).get("require_allocation_on_post", "hard")
