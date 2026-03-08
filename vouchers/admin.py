from __future__ import annotations

from django.contrib import admin, messages

from vouchers.models import VoucherHeader, VoucherLine, VoucherSettings
from vouchers.services.voucher_service import VoucherService


class VoucherLineInline(admin.TabularInline):
    model = VoucherLine
    extra = 0
    fields = (
        "line_no",
        "account",
        "narration",
        "dr_amount",
        "cr_amount",
        "is_system_generated",
        "system_line_role",
        "generated_from_line",
        "pair_no",
    )
    raw_id_fields = ("account", "generated_from_line")
    readonly_fields = ("is_system_generated", "system_line_role", "generated_from_line", "pair_no")


@admin.register(VoucherHeader)
class VoucherHeaderAdmin(admin.ModelAdmin):
    inlines = [VoucherLineInline]
    list_display = (
        "id", "voucher_code", "doc_code", "doc_no", "voucher_date", "voucher_type", "cash_bank_account", "status", "approval_status", "total_debit_amount", "total_credit_amount", "entity",
    )
    list_filter = ("status", "voucher_type", "entity", "entityfinid", "subentity", "voucher_date")
    search_fields = ("voucher_code", "reference_number", "narration", "cash_bank_account__accountname")
    raw_id_fields = ("entity", "entityfinid", "subentity", "cash_bank_account", "created_by", "approved_by", "cancelled_by")
    readonly_fields = ("doc_no", "voucher_code", "total_debit_amount", "total_credit_amount", "workflow_payload", "approved_at", "cancelled_at", "created_at", "updated_at")
    actions = ["action_confirm", "action_post", "action_unpost", "action_cancel"]

    @admin.display(description="Approval")
    def approval_status(self, obj):
        payload = obj.workflow_payload if isinstance(obj.workflow_payload, dict) else {}
        state = payload.get("_approval_state") if isinstance(payload.get("_approval_state"), dict) else {}
        return state.get("status") or "DRAFT"

    @admin.action(description="Confirm selected vouchers")
    def action_confirm(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                VoucherService.confirm_voucher(obj.pk, confirmed_by_id=request.user.id)
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] confirm failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Confirmed {ok} voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Post selected vouchers")
    def action_post(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                VoucherService.post_voucher(obj.pk, posted_by_id=request.user.id)
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] post failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Posted {ok} voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Unpost selected vouchers")
    def action_unpost(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                VoucherService.unpost_voucher(obj.pk, unposted_by_id=request.user.id)
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] unpost failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Unposted {ok} voucher(s).", level=messages.SUCCESS)

    @admin.action(description="Cancel selected vouchers")
    def action_cancel(self, request, queryset):
        ok = 0
        for obj in queryset:
            try:
                VoucherService.cancel_voucher(obj.pk, cancelled_by_id=request.user.id, reason="Cancelled from admin")
                ok += 1
            except Exception as exc:
                self.message_user(request, f"[{obj.pk}] cancel failed: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Cancelled {ok} voucher(s).", level=messages.SUCCESS)


@admin.register(VoucherLine)
class VoucherLineAdmin(admin.ModelAdmin):
    list_display = ("id", "header", "line_no", "account", "dr_amount", "cr_amount", "is_system_generated", "system_line_role", "pair_no")
    list_filter = ("is_system_generated", "system_line_role", "header__voucher_type", "header__status")
    search_fields = ("header__voucher_code", "account__accountname", "narration")
    raw_id_fields = ("header", "account", "generated_from_line")


@admin.register(VoucherSettings)
class VoucherSettingsAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "default_workflow_action", "default_doc_code_cash", "default_doc_code_bank", "default_doc_code_journal")
    raw_id_fields = ("entity", "subentity")
