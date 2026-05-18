from __future__ import annotations

from rest_framework import serializers

from payroll.models import (
    FnFSettlement,
    PayrollPaymentBatch,
    PayrollPaymentBatchLine,
    PayrollPaymentFileExport,
    PayrollPaymentStatusLog,
    PayrollRun,
)


class PayrollPaymentBatchCreateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=PayrollPaymentBatch.SourceType.choices)
    payroll_run = serializers.PrimaryKeyRelatedField(queryset=PayrollRun.objects.all(), required=False, allow_null=True)
    fnf_settlement = serializers.PrimaryKeyRelatedField(queryset=FnFSettlement.objects.all(), required=False, allow_null=True)
    batch_name = serializers.CharField(required=False, allow_blank=True, default="")
    payout_date = serializers.DateField(required=False, allow_null=True)
    allow_non_positive_amounts = serializers.BooleanField(required=False, default=False)
    export_format = serializers.ChoiceField(
        required=False,
        choices=PayrollPaymentBatch.ExportFormat.choices,
        default=PayrollPaymentBatch.ExportFormat.GENERIC_CSV,
    )

    def validate(self, attrs):
        source_type = attrs["source_type"]
        payroll_run = attrs.get("payroll_run")
        fnf_settlement = attrs.get("fnf_settlement")
        if source_type == PayrollPaymentBatch.SourceType.PAYROLL_RUN:
            if payroll_run is None:
                raise serializers.ValidationError({"payroll_run": "Payroll run is required for payroll payment batches."})
            if fnf_settlement is not None:
                raise serializers.ValidationError({"fnf_settlement": "FnF settlement is not allowed for payroll-run batches."})
        if source_type == PayrollPaymentBatch.SourceType.FNF_SETTLEMENT:
            if fnf_settlement is None:
                raise serializers.ValidationError({"fnf_settlement": "FnF settlement is required for FnF payment batches."})
            if payroll_run is not None:
                raise serializers.ValidationError({"payroll_run": "Payroll run is not allowed for FnF payment batches."})
        return attrs


class PayrollPaymentBatchActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
    export_format = serializers.ChoiceField(required=False, choices=PayrollPaymentBatch.ExportFormat.choices)
    payment_reference = serializers.CharField(required=False, allow_blank=True, default="")
    failure_reason = serializers.CharField(required=False, allow_blank=True, default="")
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, default="")


class PayrollPaymentStatusLogSerializer(serializers.ModelSerializer):
    acted_by_name = serializers.SerializerMethodField()

    def get_acted_by_name(self, obj):
        if not obj.acted_by_id:
            return ""
        full_name = obj.acted_by.get_full_name() if hasattr(obj.acted_by, "get_full_name") else ""
        return full_name or getattr(obj.acted_by, "username", "") or getattr(obj.acted_by, "email", "")

    class Meta:
        model = PayrollPaymentStatusLog
        fields = [
            "id",
            "old_status",
            "new_status",
            "acted_by",
            "acted_by_name",
            "comment",
            "payload",
            "created_at",
        ]


class PayrollPaymentFileExportSerializer(serializers.ModelSerializer):
    exported_by_name = serializers.SerializerMethodField()

    def get_exported_by_name(self, obj):
        if not obj.exported_by_id:
            return ""
        full_name = obj.exported_by.get_full_name() if hasattr(obj.exported_by, "get_full_name") else ""
        return full_name or getattr(obj.exported_by, "username", "") or getattr(obj.exported_by, "email", "")

    class Meta:
        model = PayrollPaymentFileExport
        fields = [
            "id",
            "export_format",
            "file_name",
            "content_type",
            "row_count",
            "export_metadata_json",
            "exported_by",
            "exported_by_name",
            "exported_at",
            "created_at",
        ]


class PayrollPaymentBatchLineSerializer(serializers.ModelSerializer):
    payment_account_name = serializers.CharField(source="payment_account.accountname", read_only=True)
    contract_payroll_profile_uuid = serializers.UUIDField(source="contract_payroll_profile_id", read_only=True)

    class Meta:
        model = PayrollPaymentBatchLine
        fields = [
            "id",
            "sequence",
            "payroll_run_employee",
            "fnf_settlement",
            "contract_payroll_profile_uuid",
            "employee_code",
            "employee_name",
            "employee_user_id",
            "payment_account",
            "payment_account_name",
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
            "created_at",
            "updated_at",
        ]


class PayrollPaymentBatchListSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    entityfin_name = serializers.CharField(source="entityfinid.desc", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)
    payroll_run_number = serializers.CharField(source="payroll_run.run_number", read_only=True)
    fnf_settlement_number = serializers.CharField(source="fnf_settlement.settlement_number", read_only=True)
    source_reference = serializers.SerializerMethodField()

    def get_source_reference(self, obj):
        if obj.payroll_run_id:
            return obj.payroll_run.run_number or obj.payroll_run.payroll_period.code
        if obj.fnf_settlement_id:
            return obj.fnf_settlement.settlement_number or f"FNF-{obj.fnf_settlement_id}"
        return ""

    class Meta:
        model = PayrollPaymentBatch
        fields = [
            "id",
            "batch_number",
            "batch_name",
            "entity",
            "entity_name",
            "entityfinid",
            "entityfin_name",
            "subentity",
            "subentity_name",
            "source_type",
            "source_reference",
            "payroll_run",
            "payroll_run_number",
            "fnf_settlement",
            "fnf_settlement_number",
            "status",
            "approval_status",
            "payout_date",
            "export_format",
            "allow_non_positive_amounts",
            "total_lines",
            "payable_line_count",
            "skipped_line_count",
            "invalid_line_count",
            "warning_line_count",
            "total_amount",
            "export_reference",
            "payment_reference",
            "created_at",
            "updated_at",
        ]


class PayrollPaymentBatchDetailSerializer(PayrollPaymentBatchListSerializer):
    lines = PayrollPaymentBatchLineSerializer(many=True, read_only=True)
    exports = PayrollPaymentFileExportSerializer(many=True, read_only=True)
    status_logs = PayrollPaymentStatusLogSerializer(many=True, read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    exported_by_name = serializers.SerializerMethodField()
    paid_by_name = serializers.SerializerMethodField()
    failed_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()

    @staticmethod
    def _user_name(user):
        if not user:
            return ""
        full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return full_name or getattr(user, "username", "") or getattr(user, "email", "")

    def get_approved_by_name(self, obj):
        return self._user_name(obj.approved_by)

    def get_exported_by_name(self, obj):
        return self._user_name(obj.exported_by)

    def get_paid_by_name(self, obj):
        return self._user_name(obj.paid_by)

    def get_failed_by_name(self, obj):
        return self._user_name(obj.failed_by)

    def get_cancelled_by_name(self, obj):
        return self._user_name(obj.cancelled_by)

    class Meta(PayrollPaymentBatchListSerializer.Meta):
        fields = PayrollPaymentBatchListSerializer.Meta.fields + [
            "validation_summary_json",
            "config_json",
            "failure_reason",
            "cancellation_reason",
            "approval_remarks",
            "requested_by",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "locked_by",
            "locked_at",
            "exported_by",
            "exported_by_name",
            "exported_at",
            "paid_by",
            "paid_by_name",
            "paid_at",
            "failed_by",
            "failed_by_name",
            "failed_at",
            "cancelled_by",
            "cancelled_by_name",
            "cancelled_at",
            "lines",
            "exports",
            "status_logs",
        ]
