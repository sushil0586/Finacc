from __future__ import annotations

from core.entitlements import ScopedEntitlementMixin
from reports.gstr9.selectors.scope import Gstr9FilterParams
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class Gstr9ScopedReportMixin(ScopedEntitlementMixin):
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def enforce_report_scope(self, request, scope: Gstr9FilterParams):
        self.enforce_scope(
            request,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
        )

    def enforce_entity_scope(self, request, *, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None):
        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )


def scope_filters(scope: Gstr9FilterParams):
    return {
        "entity": scope.entity_id,
        "entityfinid": scope.entityfinid_id,
        "subentity": scope.subentity_id,
    }


def filtered_query(request, *, exclude=None, overrides=None):
    params = request.GET.copy()
    for key in exclude or []:
        params.pop(key, None)
    for key, value in (overrides or {}).items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    return params.urlencode()


def parse_freeze_version(params):
    raw = params.get("freeze_version")
    if raw in (None, "", "latest", "LATEST"):
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("freeze_version must be an integer or 'latest'.") from exc
    if parsed <= 0:
        raise ValueError("freeze_version must be a positive integer.")
    return parsed
