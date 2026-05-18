from __future__ import annotations

from rest_framework import serializers

from entity.models import NotificationEvent, NotificationPreference, NotificationTemplate, UserNotification


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "code",
            "name",
            "channel",
            "subject_template",
            "body_template",
            "description",
            "metadata",
            "created_at",
            "updated_at",
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "user",
            "entity",
            "event_code",
            "in_app_enabled",
            "email_enabled",
            "sms_enabled",
            "whatsapp_enabled",
            "metadata",
            "created_at",
            "updated_at",
        ]


class NotificationEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    content_type_label = serializers.CharField(source="content_type.model", read_only=True)

    @staticmethod
    def get_actor_name(obj) -> str:
        user = obj.actor
        if not user:
            return ""
        full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return full_name or getattr(user, "username", "") or getattr(user, "email", "")

    class Meta:
        model = NotificationEvent
        fields = [
            "id",
            "entity",
            "subentity",
            "event_code",
            "title",
            "message",
            "channel",
            "delivery_status",
            "target_url",
            "target_label",
            "actor",
            "actor_name",
            "content_type",
            "content_type_label",
            "object_id",
            "recipient_count",
            "payload",
            "created_at",
            "updated_at",
        ]


class UserNotificationSerializer(serializers.ModelSerializer):
    event = NotificationEventSerializer(read_only=True)
    title = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()
    target_url = serializers.SerializerMethodField()

    def get_title(self, obj) -> str:
        return obj.title

    def get_message(self, obj) -> str:
        return obj.message

    def get_target_url(self, obj) -> str:
        return obj.target_url

    class Meta:
        model = UserNotification
        fields = [
            "id",
            "event",
            "user",
            "title",
            "message",
            "target_url",
            "is_read",
            "read_at",
            "metadata",
            "created_at",
            "updated_at",
        ]


class NotificationActionSerializer(serializers.Serializer):
    entity = serializers.IntegerField(required=False, min_value=1)
    subentity = serializers.IntegerField(required=False, allow_null=True)
