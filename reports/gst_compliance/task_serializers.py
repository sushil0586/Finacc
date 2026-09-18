from __future__ import annotations

from rest_framework import serializers

from Authentication.models import User
from reports.models import (
    GstComplianceTask,
    GstComplianceTaskAttachment,
    GstComplianceTaskAudit,
    GstComplianceTaskComment,
)


class GstComplianceTaskUserSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "username", "first_name", "last_name", "label")

    def get_label(self, obj):
        full_name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return full_name or obj.email or obj.username or f"User {obj.pk}"


class GstComplianceTaskCommentSerializer(serializers.ModelSerializer):
    created_by_detail = GstComplianceTaskUserSerializer(source="created_by", read_only=True)

    class Meta:
        model = GstComplianceTaskComment
        fields = ("id", "comment", "created_by", "created_by_detail", "created_at")
        read_only_fields = ("id", "created_by", "created_by_detail", "created_at")


class GstComplianceTaskAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_detail = GstComplianceTaskUserSerializer(source="uploaded_by", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GstComplianceTaskAttachment
        fields = (
            "id",
            "file",
            "file_url",
            "original_name",
            "content_type",
            "size",
            "uploaded_by",
            "uploaded_by_detail",
            "created_at",
        )
        read_only_fields = ("id", "file_url", "original_name", "content_type", "size", "uploaded_by", "uploaded_by_detail", "created_at")

    def get_file_url(self, obj):
        try:
            return obj.file.url
        except Exception:
            return ""


class GstComplianceTaskAuditSerializer(serializers.ModelSerializer):
    actor_detail = GstComplianceTaskUserSerializer(source="actor", read_only=True)

    class Meta:
        model = GstComplianceTaskAudit
        fields = ("id", "action", "actor", "actor_detail", "old_data", "new_data", "note", "created_at")
        read_only_fields = fields


class GstComplianceTaskSerializer(serializers.ModelSerializer):
    owner_detail = GstComplianceTaskUserSerializer(source="owner", read_only=True)
    created_by_detail = GstComplianceTaskUserSerializer(source="created_by", read_only=True)
    updated_by_detail = GstComplianceTaskUserSerializer(source="updated_by", read_only=True)
    closed_by_detail = GstComplianceTaskUserSerializer(source="closed_by", read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    attachment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = GstComplianceTask
        fields = (
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "gstin",
            "return_period",
            "return_type",
            "source",
            "source_code",
            "title",
            "description",
            "status",
            "priority",
            "owner",
            "owner_detail",
            "due_date",
            "closed_at",
            "closed_by",
            "closed_by_detail",
            "closure_note",
            "created_by",
            "created_by_detail",
            "updated_by",
            "updated_by_detail",
            "comment_count",
            "attachment_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "closed_at",
            "closed_by",
            "closed_by_detail",
            "created_by",
            "created_by_detail",
            "updated_by",
            "updated_by_detail",
            "comment_count",
            "attachment_count",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "return_type": {"allow_blank": True, "allow_null": True, "required": False},
        }

    def validate_gstin(self, value):
        value = (value or "").strip().upper()
        if len(value) != 15:
            raise serializers.ValidationError("GSTIN must be 15 characters.")
        return value

    def validate(self, attrs):
        source = (attrs.get("source") or getattr(self.instance, "source", "") or "").strip()
        source_code = (attrs.get("source_code") or getattr(self.instance, "source_code", "") or "").strip()
        if bool(source) != bool(source_code):
            raise serializers.ValidationError({"source_code": "Source and source code must be supplied together."})
        return attrs


class GstComplianceTaskDetailSerializer(GstComplianceTaskSerializer):
    comments = GstComplianceTaskCommentSerializer(many=True, read_only=True)
    attachments = GstComplianceTaskAttachmentSerializer(many=True, read_only=True)
    audit_logs = GstComplianceTaskAuditSerializer(many=True, read_only=True)

    class Meta(GstComplianceTaskSerializer.Meta):
        fields = GstComplianceTaskSerializer.Meta.fields + ("comments", "attachments", "audit_logs")
