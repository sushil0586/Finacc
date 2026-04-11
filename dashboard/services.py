from __future__ import annotations

from collections import OrderedDict, defaultdict

from django.utils import timezone

from entity.models import EntityFinancialYear, SubEntity
from rbac.services import EffectivePermissionService

from .registry import (
    DASHBOARD_CODE,
    DASHBOARD_NAME,
    DASHBOARD_PAGE_PERMISSION,
    DASHBOARD_PHASE,
    DASHBOARD_TYPE,
    DASHBOARD_TYPES,
    FILTER_CATALOG,
    FILTER_GROUPS,
    LAYOUT_ZONES,
    ROLE_VIEW_PROFILES,
    WIDGET_CATALOG,
    widget_by_code,
)


def _serialize_entity(entity):
    if not entity:
        return None
    return {
        "id": entity.id,
        "name": entity.entityname,
        "legal_name": getattr(entity, "legalname", None),
        "code": getattr(entity, "entity_code", None),
        "short_name": getattr(entity, "short_name", None),
        "status": getattr(entity, "organization_status", None),
    }


def _serialize_financial_year(financial_year):
    if not financial_year:
        return None
    return {
        "id": financial_year.id,
        "label": financial_year.desc,
        "year_code": financial_year.year_code,
        "start_date": financial_year.finstartyear.date().isoformat() if financial_year.finstartyear else None,
        "end_date": financial_year.finendyear.date().isoformat() if financial_year.finendyear else None,
        "period_status": financial_year.period_status,
        "is_year_closed": financial_year.is_year_closed,
    }


def _serialize_subentity(subentity):
    if not subentity:
        return None
    return {
        "id": subentity.id,
        "name": subentity.subentityname,
        "code": subentity.subentity_code,
        "branch_type": subentity.branch_type,
        "is_head_office": subentity.is_head_office,
    }


def _default_financial_year(entity_id):
    current = (
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True, is_year_closed=False)
        .order_by("-finendyear", "-finstartyear", "-id")
        .first()
    )
    if current:
        return current
    return (
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-finendyear", "-finstartyear", "-id")
        .first()
    )


def _default_subentity(entity_id):
    return (
        SubEntity.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-is_head_office", "sort_order", "subentityname", "-id")
        .first()
    )


def _build_widget_availability(*, current_phase, permission_codes):
    catalog = []
    visible_codes = []
    locked_codes = []
    by_zone = defaultdict(list)

    for widget in WIDGET_CATALOG:
        required_permissions = widget.get("required_permissions") or []
        phase_index = widget.get("phase", 0)
        phase_ready = phase_index <= current_phase
        permission_ready = all(code in permission_codes for code in required_permissions)
        available = phase_ready and permission_ready
        if available:
            visible_codes.append(widget["code"])
            by_zone[widget["zone"]].append(widget["code"])
        else:
            locked_codes.append(widget["code"])

        catalog.append(
            {
                **widget,
                "available": available,
                "availability_reason": (
                    "ready"
                    if available
                    else (
                        f"planned_for_phase_{phase_index}"
                        if not phase_ready
                        else "permission_required"
                    )
                ),
                "required_permissions": required_permissions,
            }
        )

    return {
        "widget_catalog": catalog,
        "visible_widget_codes": visible_codes,
        "locked_widget_codes": locked_codes,
        "zone_widget_codes": OrderedDict(
            (zone["code"], by_zone.get(zone["code"], [])) for zone in sorted(LAYOUT_ZONES, key=lambda item: item["order"])
        ),
    }


def build_dashboard_home_contract(*, request, scope):
    entity = EffectivePermissionService.entity_for_user(request.user, scope["entity"])
    if entity is None:
        return None

    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity.id)
    roles = EffectivePermissionService.role_summaries_for_user(request.user, entity.id)

    financial_year = None
    if scope.get("entityfinid"):
        financial_year = EntityFinancialYear.objects.filter(entity_id=entity.id, id=scope["entityfinid"], isactive=True).first()
    if financial_year is None:
        financial_year = _default_financial_year(entity.id)

    subentity = None
    if scope.get("subentity"):
        subentity = SubEntity.objects.filter(entity_id=entity.id, id=scope["subentity"], isactive=True).first()
    if subentity is None:
        subentity = _default_subentity(entity.id)

    as_of_date = scope.get("as_of_date") or timezone.localdate()
    scope_context = {
        "entity": _serialize_entity(entity),
        "financial_year": _serialize_financial_year(financial_year),
        "subentity": _serialize_subentity(subentity),
        "as_of_date": as_of_date.isoformat(),
        "from_date": scope.get("from_date").isoformat() if scope.get("from_date") else None,
        "to_date": scope.get("to_date").isoformat() if scope.get("to_date") else None,
        "currency": scope.get("currency"),
        "search": scope.get("search"),
    }

    widgets = _build_widget_availability(current_phase=DASHBOARD_PHASE, permission_codes=permission_codes)
    widget_catalog = widgets["widget_catalog"]

    return {
        "dashboard_code": DASHBOARD_CODE,
        "dashboard_name": DASHBOARD_NAME,
        "dashboard_type": DASHBOARD_TYPE,
        "phase": DASHBOARD_PHASE,
        "page_permission": DASHBOARD_PAGE_PERMISSION,
        "dashboard_types": list(DASHBOARD_TYPES.values()),
        "scope": scope_context,
        "default_scope": {
            "entity": entity.id,
            "entityfinid": financial_year.id if financial_year else None,
            "subentity": subentity.id if subentity else None,
            "as_of_date": as_of_date.isoformat(),
        },
        "filters": {
            "groups": FILTER_GROUPS,
            "catalog": FILTER_CATALOG,
            "default_values": {
                "entity": entity.id,
                "entityfinid": financial_year.id if financial_year else None,
                "subentity": subentity.id if subentity else None,
                "as_of_date": as_of_date.isoformat(),
                "currency": scope.get("currency"),
                "search": scope.get("search"),
            },
        },
        "permissions": {
            "page": {
                "code": DASHBOARD_PAGE_PERMISSION,
                "granted": DASHBOARD_PAGE_PERMISSION in permission_codes,
            },
            "granted_widget_codes": widgets["visible_widget_codes"],
            "locked_widget_codes": widgets["locked_widget_codes"],
            "widget_permission_codes": sorted(
                {
                    permission
                    for widget in widget_catalog
                    for permission in widget.get("required_permissions", [])
                    if permission != DASHBOARD_PAGE_PERMISSION
                }
            ),
            "role_summaries": roles,
        },
        "layout": {
            "zones": LAYOUT_ZONES,
            "zone_widget_codes": widgets["zone_widget_codes"],
            "max_widgets_per_zone": {zone["code"]: zone["max_widgets"] for zone in LAYOUT_ZONES},
        },
        "widget_catalog": widget_catalog,
        "widget_registry": widget_by_code(),
        "available_widget_codes": widgets["visible_widget_codes"],
        "role_view_profiles": ROLE_VIEW_PROFILES,
        "notes": [
            "Phase 0 is the structural contract only.",
            "Only shell widgets are active at this phase.",
            "Planned widgets remain in the registry so frontend and backend can evolve together.",
        ],
    }
