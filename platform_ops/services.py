from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from Authentication.models import AuthSession
from Authentication.services import AuthTokenService

from .models import PlatformAuditEvent, PlatformUserRole


class PlatformAccessService:
    @staticmethod
    def is_enabled():
        return bool(getattr(settings, "PLATFORM_OPS_ENABLED", False))

    @staticmethod
    def mutations_enabled():
        return bool(getattr(settings, "PLATFORM_OPS_MUTATIONS_ENABLED", False))

    @classmethod
    def effective_assignments(cls, user):
        if not cls.is_enabled() or not user or not user.is_authenticated or not user.is_active:
            return PlatformUserRole.objects.none()
        now = timezone.now()
        return (
            PlatformUserRole.objects.filter(
                user=user,
                is_active=True,
                revoked_at__isnull=True,
                valid_from__lte=now,
                role__is_active=True,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .select_related("role")
            .prefetch_related("role__permissions")
        )

    @classmethod
    def permission_codes(cls, user):
        assignments = cls.effective_assignments(user)
        return set(
            assignments.filter(role__permissions__is_active=True)
            .values_list("role__permissions__code", flat=True)
            .distinct()
        )

    @classmethod
    def has_permission(cls, user, code):
        return code in cls.permission_codes(user)

    @classmethod
    def capability_snapshot(cls, user):
        assignments = list(cls.effective_assignments(user))
        return {
            "enabled": cls.is_enabled(),
            "mutations_enabled": cls.mutations_enabled(),
            "is_platform_operator": bool(assignments),
            "roles": [
                {"code": assignment.role.code, "name": assignment.role.name}
                for assignment in assignments
            ],
            "permissions": sorted(cls.permission_codes(user)),
        }

    @classmethod
    def expire_assignments(cls, *, dry_run=False, now=None):
        now = now or timezone.now()
        assignments = list(
            PlatformUserRole.objects.filter(
                is_active=True, revoked_at__isnull=True, expires_at__isnull=False, expires_at__lte=now,
            ).select_related("user", "role").order_by("id")
        )
        result = {"matched": len(assignments), "expired": 0, "sessions_revoked": 0, "assignment_ids": []}
        if dry_run:
            return result
        for assignment in assignments:
            assignment.is_active = False
            assignment.revoked_at = now
            assignment.save(update_fields=["is_active", "revoked_at", "updated_at"])
            result["expired"] += 1
            result["assignment_ids"].append(assignment.id)
            remaining = cls.effective_assignments(assignment.user).exists()
            revoked_sessions = 0
            if not remaining:
                revoked_sessions = AuthSession.objects.filter(
                    user=assignment.user, revoked_at__isnull=True,
                ).update(revoked_at=now, revoked_reason="platform_access_expired", updated_at=now)
                if revoked_sessions:
                    AuthTokenService.bump_token_version(assignment.user)
            result["sessions_revoked"] += revoked_sessions
            PlatformAuditService.log(
                actor=None,
                event_type="platform.security.assignment.expired",
                outcome=PlatformAuditEvent.Outcome.SUCCESS,
                permission_code="system.platform_access_expiry",
                details={
                    "assignment_id": assignment.id, "user_id": assignment.user_id,
                    "role_code": assignment.role.code, "sessions_revoked": revoked_sessions,
                },
            )
        return result


class PlatformAuditService:
    SENSITIVE_KEYS = {
        "password",
        "old_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "credential",
        "credentials",
        "client_secret",
        "gst_password",
        "bank_account_number",
    }

    @classmethod
    def redact(cls, value):
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if str(key).lower() in cls.SENSITIVE_KEYS else cls.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls.redact(item) for item in value]
        return value

    @classmethod
    def log(
        cls, *, actor, event_type, outcome, request=None, permission_code="",
        customer_account_id=None, entity_id=None, details=None,
    ):
        return PlatformAuditEvent.objects.create(
            actor=actor,
            event_type=event_type,
            outcome=outcome,
            permission_code=permission_code,
            customer_account_id=customer_account_id,
            entity_id=entity_id,
            request_method=getattr(request, "method", ""),
            request_path=getattr(request, "path", ""),
            ip_address=(request.META.get("REMOTE_ADDR") if request else None),
            user_agent=((request.META.get("HTTP_USER_AGENT", "") if request else "")[:255]),
            details=cls.redact(details or {}),
        )
