from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from entity.models import EntityFinancialYear
from gst_reconciliation.services.normalization import normalize_gstin, normalize_return_period
from reports.selectors.financial import ensure_date


GST_COMPLIANCE_STATUS_VALUES = (
    "not_configured",
    "ready",
    "needs_review",
    "blocked",
    "prepared",
    "frozen",
    "filed",
    "amendment_needed",
    "overdue",
)

GST_COMPLIANCE_RETURN_TYPES = (
    "GSTR1",
    "GSTR3B",
    "GSTR9",
    "GSTR2B",
    "IMS",
    "EINVOICE",
    "EWAY",
    "GSTTDS",
    "TCS",
)

GST_COMPLIANCE_TARGETS = (
    "gstr1",
    "gstr3b",
    "gstr9",
    "gstr1_vs_gstr3b",
    "gst_exception_dashboard",
    "gst_reconciliation",
    "gst_reconciliation_run",
    "gst_portal",
    "sales_compliance",
    "gst_tds",
    "tcs",
)

GST_COMPLIANCE_DEEP_LINKS: dict[str, dict[str, Any]] = {
    "gstr1": {
        "route": "/gstreport",
        "permissions": ("reports.gst.view", "reports.gstr1report.view"),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "gstr3b": {
        "route": "/gstr3breport",
        "permissions": ("reports.gstr3b.view",),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "gstr9": {
        "route": "/gstr9report",
        "permissions": ("reports.gstr9.view",),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "gstr1_vs_gstr3b": {
        "route": "/reports/compliance/gstr1-vs-gstr3b",
        "permissions": ("reports.gstr1_gstr3b_reconciliation.view",),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "gst_exception_dashboard": {
        "route": "/reports/compliance/gst-exception-dashboard",
        "permissions": ("reports.gst_exception_dashboard.view",),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "gst_reconciliation": {
        "route": "/gst-reconciliation",
        "permissions": ("gst.reconciliation.view",),
        "feature": "feature_financial",
        "access_mode": "operational",
    },
    "gst_reconciliation_run": {
        "route": "/gst-reconciliation/runs/{run_id}",
        "permissions": ("gst.reconciliation.view",),
        "feature": "feature_financial",
        "access_mode": "operational",
        "required_params": ("run_id",),
    },
    "gst_portal": {
        "route": "/gstreport",
        "permissions": ("reports.gst.view", "reports.gstr1report.view"),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "sales_compliance": {
        "route": "/saleinvoice",
        "permissions": ("sales.invoice.view",),
        "feature": "feature_sales",
        "access_mode": "operational",
    },
    "gst_tds": {
        "route": "/reports/gst-tds",
        "permissions": (
            "reports.financial_hub.gst_tds_compliance_center.view",
            "reports.gst.view",
            "purchase.statutory.view",
            "reports.financial_hub.tds_compliance_center.view",
        ),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
    "tcs": {
        "route": "/reports/tcs",
        "permissions": (
            "reports.financial_hub.tcs_compliance_center.view",
            "compliance.tcs_statutory.view",
            "compliance.tcs_return_27eq.view",
            "tcs.menu.access",
            "tcs.return_27eq.view",
        ),
        "feature": "feature_reporting",
        "access_mode": "operational",
    },
}


@dataclass(frozen=True)
class GstComplianceScope:
    entity_id: int
    entityfinid_id: int | None = None
    subentity_id: int | None = None
    gstin: str | None = None
    return_type: str | None = None
    return_period: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    month: int | None = None
    year: int | None = None

    def as_filters(self) -> dict[str, Any]:
        return {
            "entity": self.entity_id,
            "entityfinid": self.entityfinid_id,
            "subentity": self.subentity_id,
            "gstin": self.gstin,
            "return_type": self.return_type,
            "return_period": self.return_period,
            "from_date": self.from_date.isoformat() if self.from_date else None,
            "to_date": self.to_date.isoformat() if self.to_date else None,
            "month": self.month,
            "year": self.year,
        }

    def as_query_params(self) -> dict[str, Any]:
        return {key: value for key, value in self.as_filters().items() if value not in (None, "")}


def parse_gst_compliance_scope(params: Any, *, require_period: bool = True) -> GstComplianceScope:
    entity_id = _parse_int(params.get("entity"), "entity")
    entityfinid_id = _parse_int(params.get("entityfinid"), "entityfinid", required=False)
    subentity_id = _parse_int(params.get("subentity"), "subentity", required=False)
    month = _parse_int(params.get("month"), "month", required=False)
    year = _parse_int(params.get("year"), "year", required=False)

    gstin = _parse_gstin(params.get("gstin"))
    return_type = _parse_return_type(params.get("return_type"))
    return_period = _parse_return_period(params.get("return_period") or params.get("period"))
    from_date = ensure_date(params.get("from_date"))
    to_date = ensure_date(params.get("to_date"))

    if (month or year) and not (month and year):
        raise ValidationError({"month": ["Both month and year are required when filtering by month."]})

    if month and year and not (from_date or to_date):
        _validate_month(month)
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        from_date = start
        to_date = end
        return_period = return_period or f"{year}-{month:02d}"

    if return_period and not (from_date or to_date):
        period_year, period_month = _parse_period_parts(return_period)
        if period_year and period_month:
            from_date = date(period_year, period_month, 1)
            to_date = date(period_year, period_month, monthrange(period_year, period_month)[1])
            month = month or period_month
            year = year or period_year

    if require_period and not (from_date and to_date):
        raise ValidationError({"from_date": ["from_date/to_date, month/year, or return_period is required."]})

    _validate_financial_year(entity_id, entityfinid_id, from_date, to_date)

    if from_date and to_date and from_date > to_date:
        raise ValidationError({"from_date": ["from_date cannot be after to_date."]})

    return GstComplianceScope(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        gstin=gstin,
        return_type=return_type,
        return_period=return_period,
        from_date=from_date,
        to_date=to_date,
        month=month,
        year=year,
    )


def build_gst_compliance_deep_link(
    target: str,
    scope: GstComplianceScope,
    *,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = GST_COMPLIANCE_DEEP_LINKS.get(target)
    if not config:
        raise ValidationError({"target": [f"Unsupported GST compliance target: {target}."]})

    route = config["route"]
    params = {**scope.as_query_params(), **(extra_params or {})}
    for required_param in config.get("required_params", ()):
        value = params.pop(required_param, None)
        if value in (None, ""):
            raise ValidationError({required_param: [f"{required_param} is required for {target}."]})
        route = route.replace(f"{{{required_param}}}", str(value))

    return {
        "target": target,
        "route": route,
        "params": params,
        "permissions": list(config["permissions"]),
        "feature": config["feature"],
        "access_mode": config["access_mode"],
    }


def _parse_int(value: Any, field: str, *, required: bool = True) -> int | None:
    if value in (None, "", 0, "0"):
        if required:
            raise ValidationError({field: [f"{field} is required."]})
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: [f"{field} must be an integer."]}) from exc


def _parse_gstin(value: Any) -> str | None:
    if value in (None, ""):
        return None
    gstin = normalize_gstin(value)
    if len(gstin) != 15:
        raise ValidationError({"gstin": ["GSTIN must be 15 characters after normalization."]})
    return gstin


def _parse_return_type(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return_type = str(value).replace("-", "").replace("_", "").strip().upper()
    if return_type not in GST_COMPLIANCE_RETURN_TYPES:
        raise ValidationError({"return_type": [f"Unsupported GST return type: {value}."]})
    return return_type


def _parse_return_period(value: Any) -> str | None:
    if value in (None, ""):
        return None
    period = normalize_return_period(value)
    year, month = _parse_period_parts(period)
    if not year or not month:
        raise ValidationError({"return_period": ["Return period must be YYYY-MM or MM-YYYY."]})
    return period


def _parse_period_parts(value: str) -> tuple[int | None, int | None]:
    parts = str(value or "").split("-")
    if len(parts) != 2:
        return None, None
    try:
        year = int(parts[0])
        month = int(parts[1])
    except (TypeError, ValueError):
        return None, None
    _validate_month(month)
    return year, month


def _validate_month(month: int) -> None:
    if month < 1 or month > 12:
        raise ValidationError({"month": ["month must be between 1 and 12."]})


def _validate_financial_year(
    entity_id: int,
    entityfinid_id: int | None,
    from_date: date | None,
    to_date: date | None,
) -> None:
    if not entityfinid_id:
        return
    fy = EntityFinancialYear.objects.filter(id=entityfinid_id, entity_id=entity_id).first()
    if not fy:
        raise ValidationError({"entityfinid": ["Financial year is not valid for this entity."]})
    fy_start = ensure_date(fy.finstartyear)
    fy_end = ensure_date(fy.finendyear)
    if from_date and (from_date < fy_start or from_date > fy_end):
        raise ValidationError({"from_date": ["from_date is outside the financial year."]})
    if to_date and (to_date < fy_start or to_date > fy_end):
        raise ValidationError({"to_date": ["to_date is outside the financial year."]})
