from __future__ import annotations

from reports.gstr1.selectors.scope import Gstr1FilterParams


def scope_filters(scope: Gstr1FilterParams):
    return {
        "entity": scope.entity_id,
        "entityfinid": scope.entityfinid_id,
        "subentity": scope.subentity_id,
        "from_date": scope.from_date,
        "to_date": scope.to_date,
        "month": scope.month,
        "year": scope.year,
        "include_cancelled": scope.include_cancelled,
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
