from __future__ import annotations

from django.contrib import admin, messages

from receipts.models import (
    ReceiptMode,
    ReceiptSettings,
    ReceiptVoucherHeader,
    ReceiptVoucherAllocation,
    ReceiptVoucherAdjustment,
    ReceiptVoucherAdvanceAdjustment,
)
from receipts.services.receipt_voucher_service import ReceiptVoucherService


@admin.register(ReceiptMode)
class ReceiptModeAdmin(admin.ModelAdmin):
    list_display = ("id", "paymentmode", "paymentmodecode", "iscash", "createdby")
    list_filter = ("iscash",)
    search_fields = ("paymentmode", "paymentmodecode")
    raw_id_fields = ("createdby",)


class ReceiptVoucherAllocationInline(admin.TabularInline):
    model = ReceiptVoucherAllocation
    extra = 0
    show_change_link = True
    fields = (
        "open_item",
        "settled_amount",
        "is_full_settlement",
        "is_advance_adjustment",
    )


class ReceiptVoucherAdjustmentInline(admin.TabularInline):
    model = ReceiptVoucherAdjustment
    extra = 0
    show_change_link = True
    fields = (
        "allocation",
        "adj_type",
        "ledger_account",
        "amount",
        "settlement_effect",
        "remarks",
    )


class ReceiptVoucherAdvanceAdjustmentInline(admin.TabularInline):
    model = ReceiptVoucherAdvanceAdjustment
    extra = 0
    show_change_link = True
    fields = (
        "advance_balance",
        "allocation",
        "open_item",
        "adjusted_amount",
        "ap_settlement",
        "remarks",
    )


@admin.register(ReceiptVoucherHeader)
class ReceiptVoucherHeaderAdmin(admin.ModelAdmin):
    inlines = [ReceiptVoucherAllocationInline, ReceiptVoucherAdjustmentInline, ReceiptVoucherAdvanceAdjustmentInline]
    list_display = (
        "id",
        "voucher_code",
        "doc_code",
        "doc_no",
        "voucher_date",
        "status",
        "approval_status",
        "receipt_type",
        "received_from",
        "cash_received_amount",
        "total_adjustment_amount",
        "settlement_effective_amount",
        "entity",
        "entityfinid",
        "subentity",
    )
    list_filter = (
        "status",
        "receipt_type",
        "supply_type",
        "entity",
        "entityfinid",
        "subentity",
        "voucher_date",
    )
    search_fields = (
        "voucher_code",
        "reference_number",
        "narration",
        "received_from__accountname",
        "received_in__accountname",
    )
    date_hierarchy = "voucher_date"
    ordering = ("-voucher_date", "-id")
    list_select_related = (
        "entity",
        "entityfinid",
        "subentity",
        "received_in",
        "received_from",
        "receipt_mode",
        "created_by",
        "approved_by",
        "cancelled_by",
        "ap_settlement",
    )
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "received_in",
        "received_from",
        "receipt_mode",
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
        "total_adjustment_amount",
        "settlement_effective_amount",
        "approved_at",
        "workflow_payload",
        "cancelled_at",
        "ap_settlement",
        "created_at",
        "updated_at",
    )

    @admin.action(description="Confirm (Draft -> Confirmed)")
    def action_confirm(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                ReceiptVoucherService.confirm_voucher(obj.pk, confirmed_by_id=request.user.id)
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] confirm failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Confirmed {ok} receipt voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Post (Confirmed -> Posted)")
    def action_post(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                ReceiptVoucherService.post_voucher(obj.pk, posted_by_id=request.user.id)
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] post failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Posted {ok} receipt voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Cancel (non-posted)")
    def action_cancel(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                ReceiptVoucherService.cancel_voucher(
                    obj.pk,
                    reason="Cancelled from admin action",
                    cancelled_by_id=request.user.id,
                )
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] cancel failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Cancelled {ok} receipt voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Unpost (Posted -> Confirmed, with reversal)")
    def action_unpost(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                ReceiptVoucherService.unpost_voucher(obj.pk, unposted_by_id=request.user.id)
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] unpost failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Unposted {ok} receipt voucher(s).", level=messages.SUCCESS)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and int(obj.status) in (
            int(ReceiptVoucherHeader.Status.POSTED),
            int(ReceiptVoucherHeader.Status.CANCELLED),
        ):
            ro.extend(
                [
                    "entity",
                    "entityfinid",
                    "subentity",
                    "voucher_date",
                    "doc_code",
                    "receipt_type",
                    "supply_type",
                    "received_in",
                    "received_from",
                    "receipt_mode",
                    "cash_received_amount",
                    "reference_number",
                    "narration",
                    "instrument_bank_name",
                    "instrument_no",
                    "instrument_date",
                    "place_of_supply_state",
                    "customer_gstin",
                    "advance_taxable_value",
                    "advance_cgst",
                    "advance_sgst",
                    "advance_igst",
                    "advance_cess",
                    "created_by",
                    "approved_by",
                    "cancelled_by",
                    "cancel_reason",
                ]
            )
        return tuple(dict.fromkeys(ro))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Approval")
    def approval_status(self, obj):
        payload = obj.workflow_payload if isinstance(obj.workflow_payload, dict) else {}
        state = payload.get("_approval_state") if isinstance(payload.get("_approval_state"), dict) else {}
        return state.get("status") or "DRAFT"


@admin.register(ReceiptVoucherAllocation)
class ReceiptVoucherAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "receipt_voucher",
        "open_item",
        "settled_amount",
        "is_full_settlement",
        "is_advance_adjustment",
    )
    list_filter = (
        "is_full_settlement",
        "is_advance_adjustment",
        "receipt_voucher__status",
    )
    search_fields = (
        "receipt_voucher__voucher_code",
        "open_item__invoice_number",
        "open_item__customer_reference_number",
    )
    raw_id_fields = ("receipt_voucher", "open_item")


@admin.register(ReceiptVoucherAdjustment)
class ReceiptVoucherAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "receipt_voucher",
        "allocation",
        "adj_type",
        "ledger_account",
        "amount",
        "settlement_effect",
    )
    list_filter = ("adj_type", "settlement_effect", "receipt_voucher__status")
    search_fields = ("receipt_voucher__voucher_code", "remarks")
    raw_id_fields = ("receipt_voucher", "allocation", "ledger_account")


@admin.register(ReceiptVoucherAdvanceAdjustment)
class ReceiptVoucherAdvanceAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "receipt_voucher",
        "advance_balance",
        "allocation",
        "open_item",
        "adjusted_amount",
        "ap_settlement",
    )
    list_filter = ("receipt_voucher__status",)
    search_fields = ("receipt_voucher__voucher_code", "remarks", "advance_balance__reference_no")
    raw_id_fields = ("receipt_voucher", "advance_balance", "allocation", "open_item", "ap_settlement")


@admin.register(ReceiptSettings)
class ReceiptSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "default_doc_code_receipt",
        "default_workflow_action",
    )
    list_filter = ("default_workflow_action", "entity")
    search_fields = ("entity__entityname", "subentity__subentityname", "default_doc_code_receipt")
