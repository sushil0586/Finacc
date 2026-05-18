from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.notification_serializers import NotificationActionSerializer, UserNotificationSerializer
from entity.notification_service import NotificationService
from entity.models import UserNotification
from subscriptions.services import SubscriptionService


class NotificationScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    @staticmethod
    def _parse_int(raw_value, field_name, *, required):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity=False):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        if entity_id is not None:
            self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _scope_from_body(self, request):
        serializer = NotificationActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data.get("entity")
        subentity_id = serializer.validated_data.get("subentity")
        if entity_id is not None:
            self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _get_notification(self, request, pk):
        obj = UserNotification.objects.select_related("event", "event__actor", "event__content_type").filter(
            pk=pk,
            user=request.user,
            event__isactive=True,
            isactive=True,
        ).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.event.entity_id, subentity_id=obj.event.subentity_id)
        return obj


class UserNotificationListAPIView(NotificationScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request, require_entity=False)
        queryset = UserNotification.objects.select_related(
            "event",
            "event__actor",
            "event__content_type",
        ).filter(user=request.user, event__isactive=True, isactive=True)
        unread_only = (request.query_params.get("unread_only") or "").strip().lower() in {"1", "true", "yes"}
        if entity_id is not None:
            queryset = queryset.filter(event__entity_id=entity_id)
        if subentity_id is not None:
            queryset = queryset.filter(event__subentity_id=subentity_id)
        if unread_only:
            queryset = queryset.filter(is_read=False)
        queryset = queryset.order_by("-created_at", "-id")[:100]
        return Response(UserNotificationSerializer(queryset, many=True).data)


class UserNotificationUnreadCountAPIView(NotificationScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request, require_entity=False)
        return Response(
            {
                "count": NotificationService.unread_count(
                    user=request.user,
                    entity_id=entity_id,
                    subentity_id=subentity_id,
                )
            }
        )


class UserNotificationMarkReadAPIView(NotificationScopedAPIView):
    def post(self, request, pk):
        notification = self._get_notification(request, pk)
        if notification is None:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        NotificationService.mark_read(notification=notification)
        return Response(UserNotificationSerializer(notification).data)


class UserNotificationMarkAllReadAPIView(NotificationScopedAPIView):
    def post(self, request):
        entity_id, subentity_id = self._scope_from_body(request)
        updated = NotificationService.mark_all_read(
            user=request.user,
            entity_id=entity_id,
            subentity_id=subentity_id,
        )
        return Response({"updated": updated})
