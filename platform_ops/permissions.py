from rest_framework.permissions import BasePermission

from .services import PlatformAccessService, PlatformAuditService
from .models import PlatformAuditEvent


class IsPlatformOperator(BasePermission):
    message = "Platform operations access is not available."

    def has_permission(self, request, view):
        if not PlatformAccessService.is_enabled():
            return False
        allowed = bool(PlatformAccessService.effective_assignments(request.user))
        user = getattr(request, "user", None)
        if not allowed and user and user.is_authenticated:
            PlatformAuditService.log(
                actor=user,
                event_type="platform.access.denied",
                outcome=PlatformAuditEvent.Outcome.DENIED,
                request=request,
            )
        return allowed


class HasPlatformPermissions(BasePermission):
    message = "Required platform permission is missing."

    def has_permission(self, request, view):
        required = tuple(getattr(view, "required_platform_permissions", ()))
        if not required:
            return True
        granted = PlatformAccessService.permission_codes(request.user)
        allowed = all(code in granted for code in required)
        if not allowed:
            PlatformAuditService.log(
                actor=request.user,
                event_type="platform.permission.denied",
                outcome=PlatformAuditEvent.Outcome.DENIED,
                request=request,
                permission_code=",".join(required),
            )
        return allowed


class PlatformMutationsEnabled(BasePermission):
    message = "Platform mutations are temporarily disabled."

    def has_permission(self, request, view):
        allowed = request.method in {"GET", "HEAD", "OPTIONS"} or PlatformAccessService.mutations_enabled()
        user = getattr(request, "user", None)
        if not allowed and user and user.is_authenticated:
            PlatformAuditService.log(
                actor=user,
                event_type="platform.mutation.disabled",
                outcome=PlatformAuditEvent.Outcome.DENIED,
                request=request,
            )
        return allowed
