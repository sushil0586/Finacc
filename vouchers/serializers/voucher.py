from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from financial.profile_access import account_partytype
from vouchers.models import VoucherHeader, VoucherLine
from vouchers.services.voucher_settings_service import VoucherSettingsService
from vouchers.services.voucher_service import VoucherService

ZERO2 = Decimal("0.00")


def _approval_state(obj: VoucherHeader) -> dict[str, Any]:
    payload = obj.workflow_payload if isinstance(obj.workflow_payload, dict) else {}
    state = payload.get("_approval_state")
    return state if isinstance(state, dict) else {}


class VoucherWriteLineSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    line_no = serializers.IntegerField(required=False)
    ledger_account = serializers.PrimaryKeyRelatedField(
        source="account",
        queryset=VoucherLine._meta.get_field("account").remote_field.model.objects.all(),
    )
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    dr_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    cr_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    entry_type = serializers.ChoiceField(choices=[("DR", "DR"), ("CR", "CR")], required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)


class VoucherJournalLineReadSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.effective_accounting_name", read_only=True)
    accountcode = serializers.IntegerField(source="account.effective_accounting_code", read_only=True)
    ledger_id = serializers.IntegerField(read_only=True)
    partytype = serializers.CharField(source="account.commercial_profile.partytype", read_only=True)

    class Meta:
        model = VoucherLine
        fields = (
            "id",
            "line_no",
            "account",
            "account_name",
            "accountcode",
            "ledger_id",
            "partytype",
            "narration",
            "dr_amount",
            "cr_amount",
            "is_system_generated",
            "system_line_role",
        )


class VoucherEditableLineReadSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.effective_accounting_name", read_only=True)
    accountcode = serializers.IntegerField(source="account.effective_accounting_code", read_only=True)
    ledger_id = serializers.IntegerField(read_only=True)
    partytype = serializers.CharField(source="account.commercial_profile.partytype", read_only=True)
    entry_type = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = VoucherLine
        fields = (
            "id",
            "line_no",
            "account",
            "account_name",
            "accountcode",
            "ledger_id",
            "partytype",
            "narration",
            "entry_type",
            "amount",
            "is_system_generated",
        )

    def get_entry_type(self, obj: VoucherLine) -> str:
        return "DR" if (obj.dr_amount or ZERO2) > ZERO2 else "CR"

    def get_amount(self, obj: VoucherLine):
        return obj.dr_amount if (obj.dr_amount or ZERO2) > ZERO2 else obj.cr_amount


class VoucherListSerializer(serializers.ModelSerializer):
    voucher_type_name = serializers.CharField(source="get_voucher_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    cash_bank_account_name = serializers.CharField(source="cash_bank_account.effective_accounting_name", read_only=True)
    cash_bank_accountcode = serializers.IntegerField(source="cash_bank_account.effective_accounting_code", read_only=True)
    cash_bank_ledger_id = serializers.IntegerField(read_only=True)
    cash_bank_partytype = serializers.CharField(source="cash_bank_account.commercial_profile.partytype", read_only=True)
    approval_status = serializers.SerializerMethodField()
    approval_status_name = serializers.SerializerMethodField()
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = VoucherHeader
        fields = (
            "id",
            "voucher_date",
            "doc_code",
            "doc_no",
            "voucher_code",
            "voucher_type",
            "voucher_type_name",
            "cash_bank_account",
            "cash_bank_account_name",
            "cash_bank_accountcode",
            "cash_bank_ledger_id",
            "cash_bank_partytype",
            "reference_number",
            "status",
            "status_name",
            "approval_status",
            "approval_status_name",
            "total_debit_amount",
            "total_credit_amount",
            "line_count",
        )

    def get_approval_status(self, obj):
        status = _approval_state(obj).get("status")
        if status:
            return status
        if int(obj.status) == int(VoucherHeader.Status.CONFIRMED):
            return "CONFIRMED"
        if int(obj.status) == int(VoucherHeader.Status.POSTED):
            return "POSTED"
        if int(obj.status) == int(VoucherHeader.Status.CANCELLED):
            return "CANCELLED"
        return "DRAFT"

    def get_approval_status_name(self, obj):
        return str(self.get_approval_status(obj)).replace("_", " ").title()

    def get_line_count(self, obj):
        return obj.lines.filter(is_system_generated=False).count()


class VoucherDetailSerializer(serializers.ModelSerializer):
    voucher_type_name = serializers.CharField(source="get_voucher_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    cash_bank_account_name = serializers.CharField(source="cash_bank_account.effective_accounting_name", read_only=True)
    cash_bank_accountcode = serializers.IntegerField(source="cash_bank_account.effective_accounting_code", read_only=True)
    cash_bank_ledger_id = serializers.IntegerField(read_only=True)
    cash_bank_partytype = serializers.CharField(source="cash_bank_account.commercial_profile.partytype", read_only=True)
    approval_status = serializers.SerializerMethodField()
    approval_status_name = serializers.SerializerMethodField()
    approval_state = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    editable_lines = serializers.SerializerMethodField()
    system_line = serializers.SerializerMethodField()
    navigation = serializers.SerializerMethodField()
    number_navigation = serializers.SerializerMethodField()

    class Meta:
        model = VoucherHeader
        fields = (
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "voucher_date",
            "doc_code",
            "doc_no",
            "voucher_code",
            "voucher_type",
            "voucher_type_name",
            "cash_bank_account",
            "cash_bank_account_name",
            "cash_bank_accountcode",
            "cash_bank_ledger_id",
            "cash_bank_partytype",
            "reference_number",
            "narration",
            "instrument_bank_name",
            "instrument_no",
            "instrument_date",
            "total_debit_amount",
            "total_credit_amount",
            "status",
            "status_name",
            "approval_state",
            "approval_status",
            "approval_status_name",
            "approved_by",
            "approved_at",
            "workflow_payload",
            "is_cancelled",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
            "created_by",
            "lines",
            "editable_lines",
            "system_line",
            "navigation",
            "number_navigation",
            "created_at",
            "updated_at",
        )

    def get_approval_state(self, obj):
        return _approval_state(obj)

    def get_approval_status(self, obj):
        status = _approval_state(obj).get("status")
        if status:
            return status
        if int(obj.status) == int(VoucherHeader.Status.CONFIRMED):
            return "CONFIRMED"
        if int(obj.status) == int(VoucherHeader.Status.POSTED):
            return "POSTED"
        if int(obj.status) == int(VoucherHeader.Status.CANCELLED):
            return "CANCELLED"
        return "DRAFT"

    def get_approval_status_name(self, obj):
        return str(self.get_approval_status(obj)).replace("_", " ").title()

    def get_lines(self, obj):
        if obj.voucher_type != VoucherHeader.VoucherType.JOURNAL:
            return []
        lines = [x for x in obj.lines.all() if not x.is_system_generated]
        return VoucherJournalLineReadSerializer(lines, many=True).data

    def get_editable_lines(self, obj):
        if obj.voucher_type == VoucherHeader.VoucherType.JOURNAL:
            return []
        rows = [x for x in obj.lines.all() if not x.is_system_generated]
        return VoucherEditableLineReadSerializer(rows, many=True).data

    def get_system_line(self, obj):
        if obj.voucher_type == VoucherHeader.VoucherType.JOURNAL:
            return None
        rows = [x for x in obj.lines.all() if x.is_system_generated]
        if not rows:
            return None
        dr_total = sum((x.dr_amount for x in rows), ZERO2)
        cr_total = sum((x.cr_amount for x in rows), ZERO2)
        entry_type = "DR" if dr_total > ZERO2 else "CR"
        amount = dr_total if dr_total > ZERO2 else cr_total
        return {
            "account": obj.cash_bank_account_id,
            "account_name": getattr(obj.cash_bank_account, "effective_accounting_name", None) or getattr(obj.cash_bank_account, "accountname", None),
            "accountcode": getattr(obj.cash_bank_account, "effective_accounting_code", None),
            "ledger_id": obj.cash_bank_ledger_id or getattr(obj.cash_bank_account, "ledger_id", None),
            "partytype": account_partytype(obj.cash_bank_account) if obj.cash_bank_account else None,
            "entry_type": entry_type,
            "amount": amount,
            "is_system_generated": True,
        }

    def get_navigation(self, obj):
        if self.context.get("skip_navigation"):
            return None
        scope = VoucherHeader.objects.filter(entity_id=obj.entity_id, entityfinid_id=obj.entityfinid_id, voucher_type=obj.voucher_type)
        scope = scope.filter(subentity__isnull=True) if obj.subentity_id is None else scope.filter(subentity_id=obj.subentity_id)
        prev_obj = scope.filter(id__lt=obj.id).only("id", "doc_no", "voucher_code", "status", "voucher_date").order_by("-id").first()
        next_obj = scope.filter(id__gt=obj.id).only("id", "doc_no", "voucher_code", "status", "voucher_date").order_by("id").first()
        return {
            "previous": {
                "id": prev_obj.id if prev_obj else -1,
                "doc_no": prev_obj.doc_no if prev_obj else None,
                "voucher_code": prev_obj.voucher_code if prev_obj else "",
                "status": prev_obj.status if prev_obj else None,
                "voucher_date": prev_obj.voucher_date if prev_obj else None,
            },
            "next": {
                "id": next_obj.id if next_obj else -1,
                "doc_no": next_obj.doc_no if next_obj else None,
                "voucher_code": next_obj.voucher_code if next_obj else "",
                "status": next_obj.status if next_obj else None,
                "voucher_date": next_obj.voucher_date if next_obj else None,
            },
        }

    def get_number_navigation(self, obj):
        if self.context.get("skip_preview_numbers"):
            return None
        return VoucherSettingsService.current_doc_no_for_type(
            entity_id=obj.entity_id,
            entityfinid_id=obj.entityfinid_id,
            subentity_id=obj.subentity_id,
            voucher_type=obj.voucher_type,
        )


class VoucherWriteSerializer(serializers.ModelSerializer):
    lines = VoucherWriteLineSerializer(many=True)

    class Meta:
        model = VoucherHeader
        fields = (
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "voucher_date",
            "doc_code",
            "voucher_type",
            "cash_bank_account",
            "reference_number",
            "narration",
            "instrument_bank_name",
            "instrument_no",
            "instrument_date",
            "lines",
        )

    def validate(self, attrs: Any):
        voucher_type = attrs.get("voucher_type") or getattr(self.instance, "voucher_type", VoucherHeader.VoucherType.JOURNAL)
        cash_bank_account = attrs.get("cash_bank_account", getattr(self.instance, "cash_bank_account", None))
        lines = attrs.get("lines", [])
        if voucher_type == VoucherHeader.VoucherType.JOURNAL:
            if cash_bank_account is not None:
                raise serializers.ValidationError({"cash_bank_account": "cash_bank_account must be blank for journal vouchers."})
            for idx, line in enumerate(lines, start=1):
                if "entry_type" in line or "amount" in line:
                    raise serializers.ValidationError({"lines": [f"Line {idx}: use dr_amount/cr_amount for journal vouchers."]})
        else:
            if cash_bank_account is None:
                raise serializers.ValidationError({"cash_bank_account": "cash_bank_account is required for cash/bank vouchers."})
            for idx, line in enumerate(lines, start=1):
                if (line.get("dr_amount") not in (None, "", ZERO2) or line.get("cr_amount") not in (None, "", ZERO2)):
                    raise serializers.ValidationError({"lines": [f"Line {idx}: use entry_type/amount for cash/bank vouchers."]})
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        request = self.context.get("request")
        result = VoucherService.create_voucher(data={**validated_data, "lines": lines}, created_by_id=getattr(getattr(request, "user", None), "id", None))
        return result.header

    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", [])
        result = VoucherService.update_voucher(instance=instance, data={**validated_data, "lines": lines})
        return result.header
