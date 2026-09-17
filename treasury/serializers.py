from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from purchase.serializers.purchase_ap import VendorBillOpenItemSerializer

from .models import (
    TreasuryChequeBook,
    TreasuryChequeLeaf,
    TreasuryCashMovement,
    TreasuryPaymentBatch,
    TreasuryPaymentBatchLine,
    TreasuryPaymentFileExport,
    TreasuryPaymentInstrument,
    TreasuryPaymentStatusLog,
)


class TreasuryPaymentBatchCreateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(
        choices=TreasuryPaymentBatch.SourceType.choices,
        default=TreasuryPaymentBatch.SourceType.VENDOR_PAYABLES,
    )
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    open_item_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    batch_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    payout_date = serializers.DateField(required=False, allow_null=True)
    paid_from = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    payment_mode = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    instrument_bank_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    instrument_no = serializers.CharField(required=False, allow_blank=True, max_length=50)
    instrument_date = serializers.DateField(required=False, allow_null=True)
    export_format = serializers.ChoiceField(
        choices=TreasuryPaymentBatch.ExportFormat.choices,
        default=TreasuryPaymentBatch.ExportFormat.GENERIC_CSV,
    )

    def validate(self, attrs):
        if attrs["source_type"] != TreasuryPaymentBatch.SourceType.VENDOR_PAYABLES:
            raise serializers.ValidationError({"source_type": "Only vendor-payables batches are available in this phase."})
        return attrs


class TreasuryPaymentBatchActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=255)
    export_format = serializers.ChoiceField(required=False, choices=TreasuryPaymentBatch.ExportFormat.choices)
    payment_reference = serializers.CharField(required=False, allow_blank=True, max_length=120)
    paid_from = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    payment_mode = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    instrument_bank_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    instrument_no = serializers.CharField(required=False, allow_blank=True, max_length=50)
    instrument_date = serializers.DateField(required=False, allow_null=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TreasuryPaymentInstrumentActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=255)
    reference_no = serializers.CharField(required=False, allow_blank=True, max_length=120)
    instrument_no = serializers.CharField(required=False, allow_blank=True, max_length=50)
    instrument_date = serializers.DateField(required=False, allow_null=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    cheque_leaf = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TreasuryChequeBookCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    bank_account = serializers.IntegerField(min_value=1)
    book_number = serializers.CharField(max_length=60)
    start_leaf = serializers.CharField(max_length=30)
    end_leaf = serializers.CharField(max_length=30)
    issued_on = serializers.DateField(required=False, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TreasuryCashMovementCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    movement_type = serializers.ChoiceField(choices=TreasuryCashMovement.MovementType.choices)
    movement_date = serializers.DateField(required=False, allow_null=True)
    source_account = serializers.IntegerField(min_value=1)
    destination_account = serializers.IntegerField(min_value=1)
    payment_mode = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    reference_no = serializers.CharField(required=False, allow_blank=True, max_length=120)
    instrument_no = serializers.CharField(required=False, allow_blank=True, max_length=50)
    instrument_date = serializers.DateField(required=False, allow_null=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    narration = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        if attrs["source_account"] == attrs["destination_account"]:
            raise serializers.ValidationError({"destination_account": "Destination account must be different from source account."})
        return attrs


class TreasuryCashMovementCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TreasuryCashMovementSerializer(serializers.ModelSerializer):
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_account_name = serializers.CharField(source="source_account.accountname", read_only=True)
    destination_account_name = serializers.CharField(source="destination_account.accountname", read_only=True)
    payment_mode_name = serializers.SerializerMethodField()
    voucher_code = serializers.CharField(source="voucher.voucher_code", read_only=True)
    voucher_status = serializers.IntegerField(source="voucher.status", read_only=True)

    class Meta:
        model = TreasuryCashMovement
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "movement_number",
            "movement_type",
            "movement_type_label",
            "movement_date",
            "source_account",
            "source_account_name",
            "destination_account",
            "destination_account_name",
            "payment_mode",
            "payment_mode_name",
            "amount",
            "reference_no",
            "instrument_no",
            "instrument_date",
            "bank_name",
            "narration",
            "voucher",
            "voucher_code",
            "voucher_status",
            "status",
            "status_label",
            "posted_by",
            "posted_at",
            "cancelled_by",
            "cancelled_at",
            "cancellation_reason",
            "metadata_json",
            "created_at",
            "updated_at",
        ]

    def get_payment_mode_name(self, obj):
        mode = obj.payment_mode
        if not mode:
            return ""
        return getattr(mode, "paymentmode", "") or getattr(mode, "paymentmodename", "") or str(mode)


class TreasuryChequeLeafSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    cheque_book_number = serializers.CharField(source="cheque_book.book_number", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.accountname", read_only=True)

    class Meta:
        model = TreasuryChequeLeaf
        fields = [
            "id",
            "cheque_book",
            "cheque_book_number",
            "entity",
            "bank_account",
            "bank_account_name",
            "leaf_no",
            "status",
            "status_label",
            "reserved_at",
            "used_at",
            "cancelled_at",
            "remarks",
            "created_at",
            "updated_at",
        ]


class TreasuryChequeBookSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.accountname", read_only=True)
    available_leaf_count = serializers.IntegerField(read_only=True, default=0)
    reserved_leaf_count = serializers.IntegerField(read_only=True, default=0)
    used_leaf_count = serializers.IntegerField(read_only=True, default=0)
    cancelled_leaf_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TreasuryChequeBook
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "bank_account",
            "bank_account_name",
            "book_number",
            "start_leaf",
            "end_leaf",
            "total_leaves",
            "status",
            "status_label",
            "issued_on",
            "remarks",
            "available_leaf_count",
            "reserved_leaf_count",
            "used_leaf_count",
            "cancelled_leaf_count",
            "created_at",
            "updated_at",
        ]


class TreasuryPaymentBatchLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryPaymentBatchLine
        fields = [
            "id",
            "vendor_open_item",
            "sequence",
            "party_account",
            "party_name",
            "party_code",
            "source_doc_type",
            "source_doc_number",
            "source_date",
            "due_date",
            "account_holder_name",
            "bank_name",
            "branch_name",
            "account_number",
            "ifsc_code",
            "amount",
            "narration",
            "line_status",
            "has_duplicate_account_warning",
            "validation_errors_json",
            "validation_warnings_json",
            "source_snapshot_json",
        ]


class TreasuryPaymentFileExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryPaymentFileExport
        fields = [
            "id",
            "export_format",
            "file_name",
            "content_type",
            "row_count",
            "total_amount",
            "export_metadata_json",
            "exported_by",
            "exported_at",
        ]


class TreasuryPaymentInstrumentSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    instrument_type_label = serializers.CharField(source="get_instrument_type_display", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    batch_name = serializers.CharField(source="batch.batch_name", read_only=True)
    batch_status = serializers.CharField(source="batch.status", read_only=True)
    batch_status_label = serializers.CharField(source="batch.get_status_display", read_only=True)
    payout_date = serializers.DateField(source="batch.payout_date", read_only=True)
    party_names = serializers.SerializerMethodField()
    source_account_name = serializers.CharField(source="source_account.accountname", read_only=True)
    payment_mode_name = serializers.SerializerMethodField()
    cheque_leaf_no = serializers.CharField(source="cheque_leaf.leaf_no", read_only=True)
    cheque_book_number = serializers.CharField(source="cheque_leaf.cheque_book.book_number", read_only=True)
    reconciliation_match_code = serializers.CharField(source="reconciliation_match.match_code", read_only=True)
    reconciled_bank_reference = serializers.SerializerMethodField()

    class Meta:
        model = TreasuryPaymentInstrument
        fields = [
            "id",
            "batch",
            "batch_number",
            "batch_name",
            "batch_status",
            "batch_status_label",
            "payout_date",
            "party_names",
            "source_account",
            "source_account_name",
            "payment_mode",
            "payment_mode_name",
            "cheque_leaf",
            "cheque_leaf_no",
            "cheque_book_number",
            "reconciliation_match",
            "reconciliation_match_code",
            "reconciled_bank_line",
            "reconciled_bank_reference",
            "reconciled_at",
            "instrument_type",
            "instrument_type_label",
            "status",
            "status_label",
            "reference_no",
            "instrument_no",
            "instrument_date",
            "bank_name",
            "amount",
            "status_reason",
            "cleared_at",
            "failed_at",
            "cancelled_at",
            "metadata_json",
            "created_at",
            "updated_at",
        ]

    def get_party_names(self, obj):
        names = []
        for line in getattr(obj.batch, "lines", []).all():
            if line.party_name and line.party_name not in names:
                names.append(line.party_name)
            if len(names) >= 3:
                break
        return names

    def get_payment_mode_name(self, obj):
        mode = obj.payment_mode
        if not mode:
            return ""
        return getattr(mode, "paymentmode", "") or getattr(mode, "paymentmodename", "") or str(mode)

    def get_reconciled_bank_reference(self, obj):
        line = obj.reconciled_bank_line
        if not line:
            return ""
        return line.reference_no or line.cheque_no or line.narration or str(line.id)


class TreasuryPaymentStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryPaymentStatusLog
        fields = ["id", "old_status", "new_status", "acted_by", "comment", "payload", "created_at"]


class TreasuryPaymentBatchListSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_type_label = serializers.CharField(source="get_source_type_display", read_only=True)
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)

    class Meta:
        model = TreasuryPaymentBatch
        fields = [
            "id",
            "entity",
            "entity_name",
            "entityfinid",
            "subentity",
            "subentity_name",
            "source_type",
            "source_type_label",
            "batch_number",
            "batch_name",
            "status",
            "status_label",
            "approval_status",
            "payout_date",
            "export_format",
            "total_lines",
            "payable_line_count",
            "invalid_line_count",
            "warning_line_count",
            "total_amount",
            "export_reference",
            "payment_reference",
            "paid_from",
            "payment_mode",
            "instrument_bank_name",
            "instrument_no",
            "instrument_date",
            "created_at",
            "updated_at",
        ]


class TreasuryPaymentBatchDetailSerializer(TreasuryPaymentBatchListSerializer):
    lines = TreasuryPaymentBatchLineSerializer(many=True, read_only=True)
    exports = TreasuryPaymentFileExportSerializer(many=True, read_only=True)
    instruments = TreasuryPaymentInstrumentSerializer(many=True, read_only=True)
    status_logs = TreasuryPaymentStatusLogSerializer(many=True, read_only=True)

    class Meta(TreasuryPaymentBatchListSerializer.Meta):
        fields = TreasuryPaymentBatchListSerializer.Meta.fields + [
            "validation_summary_json",
            "config_json",
            "failure_reason",
            "cancellation_reason",
            "requested_by",
            "approved_by",
            "exported_by",
            "paid_by",
            "failed_by",
            "cancelled_by",
            "approved_at",
            "exported_at",
            "paid_at",
            "failed_at",
            "cancelled_at",
            "lines",
            "exports",
            "instruments",
            "status_logs",
        ]


class TreasuryVendorPayableCandidateSerializer(VendorBillOpenItemSerializer):
    is_selected_in_active_batch = serializers.SerializerMethodField()

    def get_is_selected_in_active_batch(self, obj):
        return False
