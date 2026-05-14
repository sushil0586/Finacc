from __future__ import annotations

from collections.abc import Iterable

from rest_framework.exceptions import PermissionDenied

from rbac.services import EffectivePermissionService


def permission_codes_for_entity(*, user, entity_id: int | None) -> set[str]:
    if entity_id is None:
        return set()
    return set(EffectivePermissionService.permission_codes_for_user(user, entity_id))


def assert_any_report_permission(*, user, entity_id: int | None, required_permissions: Iterable[str], message: str | None = None) -> set[str]:
    resolved_permissions = permission_codes_for_entity(user=user, entity_id=entity_id)
    required_permissions = tuple(required_permissions or ())
    if required_permissions and not any(code in resolved_permissions for code in required_permissions):
        raise PermissionDenied(message or "You do not have permission to access this report.")
    return resolved_permissions
