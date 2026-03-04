from __future__ import annotations

from django.contrib import admin, messages

from payments.models import (
    PaymentSettings,
    PaymentVoucherHeader,
    PaymentVoucherAllocation,
    PaymentVoucherAdjustment,
)
from payments.services.payment_voucher_service import PaymentVoucherService


class PaymentVoucherAllocationInline(admin.TabularInline):
    model = PaymentVoucherAllocation
    extra = 0
    show_change_link = True
    fields = (
        "open_item",
        "settled_amount",
        "is_full_settlement",
        "is_advance_adjustment",
    )


class PaymentVoucherAdjustmentInline(admin.TabularInline):
    model = PaymentVoucherAdjustment
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


@admin.register(PaymentVoucherHeader)
class PaymentVoucherHeaderAdmin(admin.ModelAdmin):
    inlines = [PaymentVoucherAllocationInline, PaymentVoucherAdjustmentInline]
    list_display = (
        "id",
        "voucher_code",
        "doc_code",
        "doc_no",
        "voucher_date",
        "status",
        "payment_type",
        "paid_to",
        "cash_paid_amount",
        "total_adjustment_amount",
        "settlement_effective_amount",
        "entity",
        "entityfinid",
        "subentity",
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
    actions = ["action_confirm", "action_post", "action_cancel"]
    readonly_fields = (
        "doc_no",
        "voucher_code",
        "total_adjustment_amount",
        "settlement_effective_amount",
        "approved_at",
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
                PaymentVoucherService.confirm_voucher(obj.pk, confirmed_by_id=request.user.id)
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] confirm failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Confirmed {ok} payment voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Post (Confirmed -> Posted)")
    def action_post(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                PaymentVoucherService.post_voucher(obj.pk, posted_by_id=request.user.id)
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] post failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Posted {ok} payment voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Cancel (non-posted)")
    def action_cancel(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                PaymentVoucherService.cancel_voucher(
                    obj.pk,
                    reason="Cancelled from admin action",
                    cancelled_by_id=request.user.id,
                )
                ok += 1
            except Exception as e:
                self.message_user(request, f"[{obj.pk}] cancel failed: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Cancelled {ok} payment voucher(s).", level=messages.SUCCESS)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and int(obj.status) in (
            int(PaymentVoucherHeader.Status.POSTED),
            int(PaymentVoucherHeader.Status.CANCELLED),
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
                ]
            )
        return tuple(dict.fromkeys(ro))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PaymentVoucherAllocation)
class PaymentVoucherAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment_voucher",
        "open_item",
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


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "subentity",
        "default_doc_code_payment",
        "default_workflow_action",
    )
    list_filter = ("default_workflow_action", "entity")
    search_fields = ("entity__entityname", "subentity__subentityname", "default_doc_code_payment")
