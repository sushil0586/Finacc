from __future__ import annotations

from typing import Any, Optional

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class PayrollScopedAPIView(ScopedEntitlementMixin, APIView):
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_PAYROLL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    @staticmethod
    def _parse_int(raw_value: Any, field_name: str, *, required: bool) -> Optional[int]:
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity: bool = True, require_entityfinid: bool = False):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        if entity_id is None:
            return None, None, None
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    def _scope_from_payload(self, request, payload, *, require_entityfinid: bool = False):
        entity_id = self._parse_int(payload.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(payload.get("subentity"), "subentity", required=False)
        entityfinid_id = self._parse_int(payload.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    def _assert_entity_permission(self, request, *, entity_id: int, permission_codes: set[str], label: str) -> None:
        self.enforce_scope(request, entity_id=entity_id)
        if getattr(request.user, "is_superuser", False):
            return

        available_codes = set(EffectivePermissionService.permission_codes_for_user(request.user, entity_id))
        if permission_codes & available_codes:
            return

        raise PermissionDenied(detail=f"Missing permission to {label}.")

    def _enforce_object_scope(self, request, obj) -> None:
        self.enforce_scope(
            request,
            entity_id=getattr(obj, "entity_id"),
            entityfinid_id=getattr(obj, "entityfinid_id", None),
            subentity_id=getattr(obj, "subentity_id", None),
        )
