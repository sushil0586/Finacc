from __future__ import annotations

from rest_framework import serializers

from entity.models import ApprovalActionLog, ApprovalRequest, ApprovalStep


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.SerializerMethodField()
    acted_by_name = serializers.SerializerMethodField()

    @staticmethod
    def _user_name(user) -> str:
        if not user:
            return ""
        full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return full_name or getattr(user, "username", "") or getattr(user, "email", "")

    def get_approver_name(self, obj):
        return self._user_name(obj.approver_user)

    def get_acted_by_name(self, obj):
        return self._user_name(obj.acted_by)

    class Meta:
        model = ApprovalStep
        fields = [
            "id",
            "step_order",
            "step_name",
            "status",
            "approver_user",
            "approver_name",
            "approver_role",
            "approver_permission",
            "acted_by",
            "acted_by_name",
            "acted_at",
            "remarks",
            "metadata",
        ]


class ApprovalActionLogSerializer(serializers.ModelSerializer):
    acted_by_name = serializers.SerializerMethodField()

    @staticmethod
    def _user_name(user) -> str:
        if not user:
            return ""
        full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return full_name or getattr(user, "username", "") or getattr(user, "email", "")

    def get_acted_by_name(self, obj):
        return self._user_name(obj.acted_by)

    class Meta:
        model = ApprovalActionLog
        fields = [
            "id",
            "action",
            "previous_status",
            "new_status",
            "acted_by",
            "acted_by_name",
            "remarks",
            "payload",
            "created_at",
        ]


class ApprovalRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    rejected_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    locked_by_name = serializers.SerializerMethodField()
    content_type_label = serializers.CharField(source="content_type.model", read_only=True)
    steps = ApprovalStepSerializer(many=True, read_only=True)
    action_logs = ApprovalActionLogSerializer(many=True, read_only=True)

    @staticmethod
    def _user_name(user) -> str:
        if not user:
            return ""
        full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return full_name or getattr(user, "username", "") or getattr(user, "email", "")

    def get_requested_by_name(self, obj):
        return self._user_name(obj.requested_by)

    def get_approved_by_name(self, obj):
        return self._user_name(obj.approved_by)

    def get_rejected_by_name(self, obj):
        return self._user_name(obj.rejected_by)

    def get_cancelled_by_name(self, obj):
        return self._user_name(obj.cancelled_by)

    def get_locked_by_name(self, obj):
        return self._user_name(obj.locked_by)

    class Meta:
        model = ApprovalRequest
        fields = [
            "id",
            "entity",
            "subentity",
            "content_type",
            "content_type_label",
            "object_id",
            "workflow_key",
            "title",
            "status",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "rejected_by",
            "rejected_by_name",
            "cancelled_by",
            "cancelled_by_name",
            "locked_by",
            "locked_by_name",
            "requested_at",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancelled_at",
            "locked_at",
            "remarks",
            "metadata",
            "steps",
            "action_logs",
            "created_at",
            "updated_at",
        ]


class ApprovalRequestActionSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)
