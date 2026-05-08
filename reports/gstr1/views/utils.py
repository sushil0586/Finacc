from __future__ import annotations

from core.entitlements import ScopedEntitlementMixin
from reports.gstr1.selectors.scope import Gstr1FilterParams
from reports.gstr1.selectors.smart_filters import Gstr1SmartFilters, smart_filters_as_dict
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class Gstr1ScopedReportMixin(ScopedEntitlementMixin):
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def enforce_report_scope(self, request, scope: Gstr1FilterParams):
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


def scope_filters(scope: Gstr1FilterParams, smart_filters: Gstr1SmartFilters | None = None):
    payload = {
        "entity": scope.entity_id,
        "entityfinid": scope.entityfinid_id,
        "subentity": scope.subentity_id,
        "from_date": scope.from_date,
        "to_date": scope.to_date,
        "month": scope.month,
        "year": scope.year,
        "include_cancelled": scope.include_cancelled,
    }
    if smart_filters:
        payload.update(smart_filters_as_dict(smart_filters))
    return payload


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
