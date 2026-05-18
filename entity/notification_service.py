from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from Authentication.models import User
from entity.models import NotificationEvent, NotificationPreference, NotificationTemplate, UserNotification


@dataclass(frozen=True)
class NotificationDispatchResult:
    event: NotificationEvent
    notifications: list[UserNotification]


class NotificationService:
    CHANNEL_IN_APP = NotificationEvent.Channel.IN_APP
    CHANNEL_EMAIL = NotificationEvent.Channel.EMAIL
    CHANNEL_SMS = NotificationEvent.Channel.SMS
    CHANNEL_WHATSAPP = NotificationEvent.Channel.WHATSAPP

    @classmethod
    def _content_type(cls, instance):
        return ContentType.objects.get_for_model(instance.__class__)

    @classmethod
    def _normalize_users(cls, users: Iterable[User | None]) -> list[User]:
        unique: dict[int, User] = {}
        for user in users:
            if user is None or not getattr(user, "id", None):
                continue
            unique[int(user.id)] = user
        return list(unique.values())

    @classmethod
    def _preference_map(cls, *, users: list[User], entity_id: int | None, event_code: str) -> dict[int, NotificationPreference]:
        if not users:
            return {}
        user_ids = [int(user.id) for user in users]
        preferences = NotificationPreference.objects.filter(
            user_id__in=user_ids,
            event_code=event_code,
            isactive=True,
        ).filter(Q(entity_id=entity_id) | Q(entity__isnull=True)).order_by("-entity_id", "-id")
        resolved: dict[int, NotificationPreference] = {}
        for preference in preferences:
            resolved.setdefault(int(preference.user_id), preference)
        return resolved

    @classmethod
    def should_deliver_in_app(cls, *, user: User, entity_id: int | None, event_code: str) -> bool:
        preferences = cls._preference_map(users=[user], entity_id=entity_id, event_code=event_code)
        preference = preferences.get(int(user.id))
        return True if preference is None else bool(preference.in_app_enabled)

    @classmethod
    def default_target_url(cls, *, workflow_key: str, instance) -> str:
        if workflow_key == "payroll_run":
            return f"/payroll/runs/{instance.pk}"
        if workflow_key == "payroll_payment_batch":
            return f"/payroll/payment-batches/{instance.pk}"
        if workflow_key == "fnf_settlement":
            return f"/payroll/fnf/{instance.pk}"
        if workflow_key == "contract_tax_declaration":
            return "/payroll/contract-tax-declarations"
        if workflow_key == "leave_application":
            return "/hrms/leave/manager-approval"
        if workflow_key == "attendance_approval":
            return "/hrms/attendance-approvals"
        if workflow_key == "attendance_monthly_close":
            return "/hrms/attendance-monthly-closes"
        return ""

    @classmethod
    @transaction.atomic
    def emit(
        cls,
        *,
        instance,
        workflow_key: str,
        event_code: str,
        title: str,
        message: str,
        users: Iterable[User | None],
        actor: User | None = None,
        target_url: str = "",
        target_label: str = "",
        payload: dict | None = None,
        template_code: str = "",
    ) -> NotificationDispatchResult:
        recipients = cls._normalize_users(users)
        entity_id = getattr(instance, "entity_id", None)
        if entity_id is None:
            raise ValueError("Notifications require an entity-scoped object.")
        event_code = (event_code or "").strip().upper()
        target_url = (target_url or cls.default_target_url(workflow_key=workflow_key, instance=instance)).strip()
        template = None
        if template_code:
            template = NotificationTemplate.objects.filter(code=template_code.strip().upper(), isactive=True).first()
        event = NotificationEvent.objects.create(
            entity_id=entity_id,
            subentity_id=getattr(instance, "subentity_id", None),
            template=template,
            content_type=cls._content_type(instance),
            object_id=str(instance.pk),
            event_code=event_code,
            title=title,
            message=message,
            channel=NotificationEvent.Channel.IN_APP,
            delivery_status=NotificationEvent.DeliveryStatus.CREATED,
            target_url=target_url,
            target_label=target_label,
            actor=actor,
            recipient_count=0,
            payload=payload or {},
        )
        preferences = cls._preference_map(users=recipients, entity_id=entity_id, event_code=event_code)
        notifications: list[UserNotification] = []
        for user in recipients:
            preference = preferences.get(int(user.id))
            if preference is not None and not preference.in_app_enabled:
                continue
            notifications.append(
                UserNotification.objects.create(
                    event=event,
                    user=user,
                )
            )
        if notifications:
            event.recipient_count = len(notifications)
            event.save(update_fields=["recipient_count", "updated_at"])
        return NotificationDispatchResult(event=event, notifications=notifications)

    @classmethod
    def emit_placeholder_channel(
        cls,
        *,
        instance,
        event_code: str,
        title: str,
        message: str,
        channel: str,
        actor: User | None = None,
        payload: dict | None = None,
    ) -> NotificationEvent:
        entity_id = getattr(instance, "entity_id", None)
        if entity_id is None:
            raise ValueError("Notifications require an entity-scoped object.")
        return NotificationEvent.objects.create(
            entity_id=entity_id,
            subentity_id=getattr(instance, "subentity_id", None),
            content_type=cls._content_type(instance),
            object_id=str(instance.pk),
            event_code=(event_code or "").strip().upper(),
            title=title,
            message=message,
            channel=channel,
            delivery_status=NotificationEvent.DeliveryStatus.PENDING,
            actor=actor,
            recipient_count=0,
            payload=payload or {},
        )

    @classmethod
    def unread_count(cls, *, user: User, entity_id: int | None = None, subentity_id: int | None = None) -> int:
        queryset = UserNotification.objects.filter(user=user, is_read=False, event__isactive=True, isactive=True)
        if entity_id is not None:
            queryset = queryset.filter(event__entity_id=entity_id)
        if subentity_id is not None:
            queryset = queryset.filter(event__subentity_id=subentity_id)
        return queryset.count()

    @classmethod
    @transaction.atomic
    def mark_read(cls, *, notification: UserNotification) -> UserNotification:
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])
        return notification

    @classmethod
    @transaction.atomic
    def mark_all_read(cls, *, user: User, entity_id: int | None = None, subentity_id: int | None = None) -> int:
        queryset = UserNotification.objects.filter(user=user, is_read=False, event__isactive=True, isactive=True)
        if entity_id is not None:
            queryset = queryset.filter(event__entity_id=entity_id)
        if subentity_id is not None:
            queryset = queryset.filter(event__subentity_id=subentity_id)
        return queryset.update(is_read=True, read_at=timezone.now(), updated_at=timezone.now())
