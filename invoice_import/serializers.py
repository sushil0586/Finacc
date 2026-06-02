from __future__ import annotations

from rest_framework import serializers

from invoice_import.models import ImportJob, ImportProfile


class ImportProfileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportProfile
        fields = [
            "id",
            "entity",
            "module",
            "name",
            "source_system",
            "description",
            "is_default",
            "mapping",
            "options",
        ]


class ImportProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportProfile
        fields = [
            "id",
            "entity",
            "module",
            "name",
            "source_system",
            "description",
            "is_default",
            "mapping",
            "options",
            "created_at",
            "updated_at",
        ]


class ImportJobCreateSerializer(serializers.Serializer):
    DOCUMENT_NUMBER_STRATEGY_CHOICES = (
        ("preserve_legacy", "Preserve legacy source invoice number"),
        ("generate_finacc", "Generate Finacc document number"),
    )

    entity = serializers.IntegerField()
    profile = serializers.IntegerField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=ImportJob.Mode.choices)
    detail_level = serializers.ChoiceField(choices=ImportJob.DetailLevel.choices, required=False, default=ImportJob.DetailLevel.HEADER_ONLY)
    compliance_mode = serializers.ChoiceField(choices=ImportJob.ComplianceMode.choices, required=False, default=ImportJob.ComplianceMode.PASSIVE)
    withholding_mode = serializers.ChoiceField(choices=ImportJob.WithholdingMode.choices, required=False, default=ImportJob.WithholdingMode.PRESERVE_LEGACY)
    stock_replay = serializers.BooleanField(required=False, default=False)
    document_number_strategy = serializers.ChoiceField(
        choices=DOCUMENT_NUMBER_STRATEGY_CHOICES,
        required=False,
        default="preserve_legacy",
    )
    source_system = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField()


class ImportJobSerializer(serializers.ModelSerializer):
    error_count = serializers.SerializerMethodField()
    warning_count = serializers.SerializerMethodField()
    document_summaries = serializers.SerializerMethodField()
    is_reviewed = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id",
            "module",
            "mode",
            "detail_level",
            "compliance_mode",
            "withholding_mode",
            "stock_replay",
            "status",
            "profile",
            "input_filename",
            "source_system",
            "summary",
            "reconciliation_summary",
            "profile_snapshot",
            "review_required",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "is_reviewed",
            "document_summaries",
            "error_count",
            "warning_count",
            "created_at",
            "updated_at",
        ]

    def get_error_count(self, obj) -> int:
        return int(obj.rows.filter(status="error").count())

    def get_warning_count(self, obj) -> int:
        return sum(len(row.warnings or []) for row in obj.rows.all())

    def get_document_summaries(self, obj) -> list[dict]:
        summary = obj.summary if isinstance(obj.summary, dict) else {}
        rows = summary.get("document_summaries")
        return rows if isinstance(rows, list) else []

    def get_is_reviewed(self, obj) -> bool:
        return bool(getattr(obj, "reviewed_at", None))
