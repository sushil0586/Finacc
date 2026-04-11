from __future__ import annotations

from typing import Iterable

from rest_framework.exceptions import PermissionDenied

from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionService


def _has_any_code(available_codes: Iterable[str], required_codes: Iterable[str]) -> bool:
    available = set(available_codes)
    return any(code in available for code in required_codes)


def require_sales_scope_permission(
    *,
    user,
    entity_id: int,
    permission_codes: Iterable[str],
    access_mode: str | None = None,
    feature_code: str | None = None,
    message: str | None = None,
):
    entity = EffectivePermissionService.entity_for_user(user, int(entity_id))
    if entity is None:
        raise PermissionDenied("You do not have access to this entity.")

    if access_mode or feature_code:
        SubscriptionService.assert_entity_access(
            user=user,
            entity=entity,
            access_mode=access_mode or SubscriptionService.ACCESS_MODE_OPERATIONAL,
            feature_code=feature_code,
        )

    available_codes = EffectivePermissionService.permission_codes_for_user(user, int(entity.id))
    if _has_any_code(available_codes, permission_codes):
        return entity

    raise PermissionDenied(message or "You do not have permission to access this sales feature.")
