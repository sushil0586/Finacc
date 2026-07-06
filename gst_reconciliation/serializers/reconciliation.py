from __future__ import annotations

from rest_framework import serializers

from gst_reconciliation.models import (
    GstImportedReturn,
    GstImportedReturnRow,
    GstMismatchReason,
    GstReconciliationActionLog,
    GstReconciliationItem,
    GstReconciliationRun,
)


class GstMismatchReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstMismatchReason
        fields = ("id", "code", "category", "severity", "message", "details_json")


class GstReconciliationItemSerializer(serializers.ModelSerializer):
    mismatch_reasons = GstMismatchReasonSerializer(many=True, read_only=True)
    operational_status = serializers.CharField(source="resolution_status", read_only=True)
    assigned_to = serializers.IntegerField(source="assigned_reviewer_id", read_only=True)
    reviewer_notes = serializers.CharField(source="reviewer_note", read_only=True)
    resolution_notes = serializers.CharField(source="resolution_note", read_only=True)

    class Meta:
        model = GstReconciliationItem
        fields = (
            "id",
            "run",
            "item_type",
            "direction",
            "match_key",
            "source_document_type",
            "source_document_id",
            "linked_document_type",
            "linked_document_id",
            "gstin",
            "counterparty_gstin",
            "invoice_number",
            "invoice_date",
            "doc_type_code",
            "taxable_value_books",
            "cgst_books",
            "sgst_books",
            "igst_books",
            "cess_books",
            "taxable_value_imported",
            "cgst_imported",
            "sgst_imported",
            "igst_imported",
            "cess_imported",
            "match_status",
            "resolution_status",
            "operational_status",
            "mismatch_count",
            "match_confidence_score",
            "assigned_reviewer",
            "assigned_to",
            "assigned_by",
            "assigned_at",
            "reviewer_note",
            "reviewer_notes",
            "mismatch_summary",
            "resolution_note",
            "resolution_notes",
            "accepted_mismatch_at",
            "accepted_mismatch_by",
            "reviewed_by",
            "reviewed_at",
            "resolved_by",
            "resolved_at",
            "metadata_json",
            "mismatch_reasons",
        )
        read_only_fields = fields


class GstReconciliationItemGridSerializer(serializers.ModelSerializer):
    mismatch_reason_codes = serializers.SerializerMethodField()
    mismatch_reason_messages = serializers.SerializerMethodField()
    assigned_reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = GstReconciliationItem
        fields = (
            "id",
            "run",
            "item_type",
            "direction",
            "source_document_type",
            "source_document_id",
            "linked_document_type",
            "linked_document_id",
            "gstin",
            "counterparty_gstin",
            "invoice_number",
            "invoice_date",
            "doc_type_code",
            "match_status",
            "resolution_status",
            "match_confidence_score",
            "assigned_reviewer",
            "assigned_reviewer_name",
            "reviewed_by",
            "reviewed_at",
            "resolved_by",
            "resolved_at",
            "mismatch_count",
            "mismatch_reason_codes",
            "mismatch_reason_messages",
            "taxable_value_books",
            "cgst_books",
            "sgst_books",
            "igst_books",
            "cess_books",
            "taxable_value_imported",
            "cgst_imported",
            "sgst_imported",
            "igst_imported",
            "cess_imported",
            "reviewer_note",
            "resolution_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_mismatch_reason_codes(self, obj):
        return list(obj.mismatch_reasons.values_list("code", flat=True))

    def get_mismatch_reason_messages(self, obj):
        return list(obj.mismatch_reasons.values_list("message", flat=True)[:3])

    def get_assigned_reviewer_name(self, obj):
        reviewer = getattr(obj, "assigned_reviewer", None)
        if not reviewer:
            return None
        return reviewer.username or getattr(reviewer, "email", None) or str(reviewer.id)


class GstImportedReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstImportedReturn
        fields = (
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "gst_registration_gstin",
            "return_type",
            "return_period",
            "source",
            "reference",
            "source_reference",
            "status",
            "checksum",
            "raw_payload_json",
            "normalized_payload_json",
            "validation_summary_json",
            "imported_by",
            "imported_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at", "imported_by", "imported_at")


class GstImportedReturnRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstImportedReturnRow
        fields = (
            "id",
            "imported_return",
            "row_no",
            "source_section",
            "source_row_reference",
            "row_hash",
            "doc_type_code",
            "counterparty_gstin",
            "counterparty_gstin_normalized",
            "counterparty_name",
            "invoice_number",
            "invoice_number_normalized",
            "invoice_date",
            "taxable_value",
            "cgst",
            "sgst",
            "igst",
            "cess",
            "total_amount",
            "pos_state_name",
            "normalized_row_json",
        )
        read_only_fields = fields


class GstReconciliationActionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstReconciliationActionLog
        fields = (
            "id",
            "run",
            "item",
            "action_type",
            "actor",
            "from_status",
            "to_status",
            "comment",
            "details_json",
            "created_at",
        )
        read_only_fields = fields


class GstReconciliationRunSerializer(serializers.ModelSerializer):
    imported_return = GstImportedReturnSerializer(read_only=True)
    items = GstReconciliationItemSerializer(many=True, read_only=True)
    action_logs = GstReconciliationActionLogSerializer(many=True, read_only=True)

    class Meta:
        model = GstReconciliationRun
        fields = (
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "gst_registration_gstin",
            "reconciliation_type",
            "period_type",
            "period_from",
            "period_to",
            "return_period",
            "revision_no",
            "source_mode",
            "status",
            "match_strategy_code",
            "tolerance_config_json",
            "imported_return",
            "source_reference",
            "summary_json",
            "notes",
            "review_comment",
            "approval_comment",
            "close_comment",
            "submitted_by",
            "reviewed_by",
            "approved_by",
            "closed_by",
            "submitted_at",
            "reviewed_at",
            "approved_at",
            "closed_at",
            "created_at",
            "updated_at",
            "items",
            "action_logs",
        )
        read_only_fields = (
            "status",
            "summary_json",
            "tolerance_config_json",
            "submitted_by",
            "reviewed_by",
            "approved_by",
            "closed_by",
            "submitted_at",
            "reviewed_at",
            "approved_at",
            "closed_at",
            "created_at",
            "updated_at",
            "items",
            "action_logs",
        )


class GstReconciliationRunWorkspaceSerializer(serializers.ModelSerializer):
    imported_return = GstImportedReturnSerializer(read_only=True)
    action_logs = GstReconciliationActionLogSerializer(many=True, read_only=True)

    class Meta:
        model = GstReconciliationRun
        fields = (
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "gst_registration_gstin",
            "reconciliation_type",
            "period_type",
            "period_from",
            "period_to",
            "return_period",
            "revision_no",
            "source_mode",
            "status",
            "match_strategy_code",
            "tolerance_config_json",
            "imported_return",
            "source_reference",
            "summary_json",
            "notes",
            "review_comment",
            "approval_comment",
            "close_comment",
            "submitted_by",
            "reviewed_by",
            "approved_by",
            "closed_by",
            "submitted_at",
            "reviewed_at",
            "approved_at",
            "closed_at",
            "created_at",
            "updated_at",
            "action_logs",
        )
        read_only_fields = fields


class GstReconciliationRunListRowSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    reconciliation_type = serializers.CharField(read_only=True)
    return_period = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    gst_registration_gstin = serializers.CharField(read_only=True, allow_null=True)
    entity_id = serializers.IntegerField(read_only=True)
    entityfinid_id = serializers.IntegerField(read_only=True)
    subentity_id = serializers.IntegerField(read_only=True, allow_null=True)
    source_mode = serializers.CharField(read_only=True)
    imported_return_id = serializers.IntegerField(read_only=True, allow_null=True)
    total_items = serializers.IntegerField(read_only=True)
    matched_count = serializers.IntegerField(read_only=True)
    pending_review_count = serializers.IntegerField(read_only=True)
    resolved_count = serializers.IntegerField(read_only=True)
    mismatch_count = serializers.IntegerField(read_only=True)
    accepted_mismatch_count = serializers.IntegerField(read_only=True)
    ignored_count = serializers.IntegerField(read_only=True)
    match_percentage = serializers.FloatField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class GstReconciliationRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GstReconciliationRun
        fields = (
            "entity",
            "entityfinid",
            "subentity",
            "gst_registration_gstin",
            "reconciliation_type",
            "period_type",
            "period_from",
            "period_to",
            "return_period",
            "revision_no",
            "source_mode",
            "match_strategy_code",
            "tolerance_config_json",
            "notes",
        )


class GstRunActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GstItemAssignSerializer(serializers.Serializer):
    reviewer_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GstItemManualMatchSerializer(serializers.Serializer):
    source_document_type = serializers.CharField(required=False, max_length=64)
    source_document_id = serializers.CharField(required=False, max_length=64)
    purchase_invoice_id = serializers.IntegerField(required=False, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if attrs.get("purchase_invoice_id"):
            attrs.setdefault("source_document_type", "purchase_invoice_header")
            attrs.setdefault("source_document_id", str(attrs["purchase_invoice_id"]))
        if not attrs.get("source_document_type") or not attrs.get("source_document_id"):
            raise serializers.ValidationError("source_document_type and source_document_id are required.")
        return attrs


class GstItemNotesSerializer(serializers.Serializer):
    reviewer_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    resolution_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GstBulkItemActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=(
            "assign",
            "ignore",
            "reopen",
            "accept_mismatch",
            "mark_reviewed",
            "unmatch",
        )
    )
    item_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    reviewer_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GstSourceDocumentMetadataSerializer(serializers.Serializer):
    provider_code = serializers.CharField(read_only=True)
    source_document_type = serializers.CharField(read_only=True)
    source_document_id = serializers.CharField(read_only=True)
    document_number = serializers.CharField(read_only=True)
    document_date = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True, allow_null=True)
    item_type = serializers.CharField(read_only=True)
    direction = serializers.CharField(read_only=True)
    party_name = serializers.CharField(read_only=True, allow_null=True)
    party_gstin = serializers.CharField(read_only=True, allow_null=True)
    gstin = serializers.CharField(read_only=True, allow_null=True)
    taxable_value = serializers.CharField(read_only=True)
    cgst = serializers.CharField(read_only=True)
    sgst = serializers.CharField(read_only=True)
    igst = serializers.CharField(read_only=True)
    cess = serializers.CharField(read_only=True)
    total_amount = serializers.CharField(read_only=True)
    summary = serializers.CharField(read_only=True)
    normalized_comparison_payload = serializers.JSONField(read_only=True)


class GstSourceDocumentSearchSerializer(serializers.Serializer):
    item_id = serializers.IntegerField(required=False, min_value=1)
    source_document_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    query = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)


class GstItemActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PurchaseGstr2bBatchAdapterSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField(min_value=1)
    match_strategy_code = serializers.CharField(required=False, allow_blank=True, max_length=64)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GstGstr2bJsonImportSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    return_period = serializers.CharField(max_length=7)
    gst_registration_gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    payload = serializers.JSONField()
    create_run = serializers.BooleanField(required=False, default=True)
    tolerance_config_json = serializers.JSONField(required=False)


class GstGstr2bExcelImportSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    return_period = serializers.CharField(max_length=7)
    gst_registration_gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    file = serializers.FileField()
    create_run = serializers.BooleanField(required=False, default=True)
    tolerance_config_json = serializers.JSONField(required=False)
