from __future__ import annotations

"""Metadata builders for payable reporting screens and filter panels."""

from collections import OrderedDict
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from entity.models import EntityFinancialYear, SubEntity
from financial.profile_access import (
    account_agent,
    account_creditdays,
    account_creditlimit,
    account_currency,
    account_gstno,
    account_region_state,
    account_region_state_id,
)
from reports.selectors.payables import vendor_queryset
from reports.services.payables_config import (
    PAYABLE_DRILLDOWN_TARGETS,
    PAYABLE_REPORT_DEFAULTS,
    get_payables_report_config,
    get_payables_registry_meta,
    get_payables_registry_payload,
)


def _financial_years(entity_id: int) -> list[dict]:
    return list(
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-finstartyear", "-id")
        .values("id", "desc", "finstartyear", "finendyear")
    )


def _subentities(entity_id: int) -> list[dict]:
    rows = list(
        SubEntity.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-is_head_office", "subentityname", "id")
        .values("id", "subentityname", "is_head_office")
    )
    for row in rows:
        row["ismainentity"] = row["is_head_office"]
    return rows


def _vendors(entity_id: int) -> list[dict]:
    vendors = vendor_queryset(entity_id=entity_id)
    payload = []
    for vendor in vendors:
        payload.append(
            {
                "id": vendor.id,
                "name": vendor.effective_accounting_name,
                "code": vendor.effective_accounting_code,
                "gstin": account_gstno(vendor),
                "currency": account_currency(vendor) or "INR",
                "vendor_group": account_agent(vendor),
                "region_id": account_region_state_id(vendor),
                "region_name": getattr(account_region_state(vendor), "statename", None),
                "region_code": getattr(account_region_state(vendor), "statecode", None),
                "credit_days": account_creditdays(vendor),
                "credit_limit": str(account_creditlimit(vendor)) if account_creditlimit(vendor) is not None else None,
            }
        )
    return payload


def _date_presets(financial_years: list[dict]) -> list[dict]:
    today = timezone.localdate()
    presets = [
        {"value": "today", "label": "Today", "from_date": today, "to_date": today, "as_of_date": today},
        {
            "value": "last_30_days",
            "label": "Last 30 Days",
            "from_date": today - timedelta(days=29),
            "to_date": today,
            "as_of_date": today,
        },
    ]
    if financial_years:
        current = financial_years[0]
        presets.append(
            {
                "value": "financial_year",
                "label": current.get("desc") or "Financial Year",
                "from_date": current.get("finstartyear"),
                "to_date": current.get("finendyear"),
                "as_of_date": today,
            }
        )
    return [
        {
            **row,
            "from_date": row["from_date"].isoformat() if row.get("from_date") else None,
            "to_date": row["to_date"].isoformat() if row.get("to_date") else None,
            "as_of_date": row["as_of_date"].isoformat() if row.get("as_of_date") else None,
        }
        for row in presets
    ]


def _vendor_groups(vendors: list[dict]) -> list[dict]:
    groups = OrderedDict()
    for vendor in vendors:
        value = (vendor.get("vendor_group") or "").strip()
        if value and value.lower() not in groups:
            groups[value.lower()] = {"value": value, "label": value}
    return list(groups.values())


def _regions(vendors: list[dict]) -> list[dict]:
    regions = OrderedDict()
    for vendor in vendors:
        region_id = vendor.get("region_id")
        if region_id and region_id not in regions:
            regions[region_id] = {
                "id": region_id,
                "name": vendor.get("region_name"),
                "code": vendor.get("region_code"),
            }
    return list(regions.values())


def _currencies(vendors: list[dict]) -> list[dict]:
    currencies = OrderedDict()
    for vendor in vendors:
        value = (vendor.get("currency") or "INR").upper()
        if value not in currencies:
            currencies[value] = {"value": value, "label": value}
    return list(currencies.values())


def _catalog_cache_key(entity_id: int) -> str:
    return f"payables:meta:catalog:{entity_id}"


def _build_catalog(entity_id: int) -> dict:
    financial_years = _financial_years(entity_id)
    subentities = _subentities(entity_id)
    vendors = _vendors(entity_id)
    return {
        "financial_years": financial_years,
        "subentities": subentities,
        "vendors": vendors,
        "vendor_groups": _vendor_groups(vendors),
        "regions": _regions(vendors),
        "currencies": _currencies(vendors),
        "date_presets": _date_presets(financial_years),
    }


def _get_catalog(entity_id: int) -> dict:
    cached = cache.get(_catalog_cache_key(entity_id))
    if cached is not None:
        return cached
    catalog = _build_catalog(entity_id)
    cache.set(_catalog_cache_key(entity_id), catalog, timeout=15 * 60)
    return catalog


def _allowed_report_code_set(permission_codes: set[str] | None) -> set[str] | None:
    if permission_codes is None:
        return None
    return {code for code in permission_codes if code}


def _report_is_allowed(report: dict, permission_codes: set[str] | None) -> bool:
    if permission_codes is None:
        return True
    required_permission = report.get("required_permission")
    if not required_permission:
        return True
    return required_permission in permission_codes


def _filter_related_reports(report_codes: list[str], permission_codes: set[str] | None) -> list[str]:
    if permission_codes is None:
        return list(report_codes)
    allowed = []
    for code in report_codes:
        if code in {"ap_aging_summary", "ap_aging_invoice"}:
            base = get_payables_report_config("ap_aging")
            if base and _report_is_allowed(base, permission_codes):
                allowed.append(code)
            continue
        report = get_payables_report_config(code)
        if report and _report_is_allowed(report, permission_codes):
            allowed.append(code)
    return allowed


def _filter_drilldown_targets(target_codes: list[str], permission_codes: set[str] | None) -> list[str]:
    if permission_codes is None:
        return list(target_codes)
    allowed = []
    for code in target_codes:
        if code in {"ap_aging", "ap_aging_summary", "ap_aging_invoice"}:
            base = get_payables_report_config("ap_aging")
            if base and _report_is_allowed(base, permission_codes):
                allowed.append(code)
            continue
        report = get_payables_report_config(code)
        if report and _report_is_allowed(report, permission_codes):
            allowed.append(code)
    return allowed


def build_payables_report_meta(
    *,
    entity_id: int,
    entityfinid_id: int | None = None,
    subentity_id: int | None = None,
    permission_codes: set[str] | None = None,
    user_preferences: dict | None = None,
) -> dict:
    """Return backend-driven metadata for payable report filters and navigation."""
    catalog = _get_catalog(entity_id)
    allowed_permission_codes = _allowed_report_code_set(permission_codes)
    report_registry = get_payables_registry_payload(permission_codes=allowed_permission_codes)
    report_definitions = get_payables_registry_meta(permission_codes=allowed_permission_codes)
    drilldown_targets = []
    for target in PAYABLE_DRILLDOWN_TARGETS.values():
        target_permission = None
        target_report_code = target.get("report_code")
        if target_report_code:
            target_report = get_payables_report_config(target_report_code, view=target.get("view"))
            if target_report:
                target_permission = target_report.get("required_permission")
        if _report_is_allowed({"required_permission": target_permission}, allowed_permission_codes):
            drilldown_targets.append(target)
    return {
        "generated_at": timezone.now().isoformat(),
        "documentation": {
            "path": "reports/PAYABLES_REPORTING_API.md",
            "label": "Payables Reporting API Guide",
        },
        "defaults": {
            **PAYABLE_REPORT_DEFAULTS,
            "default_aging_view": "summary",
            "default_sort_by": "net_outstanding",
            "default_sort_order": "desc",
        },
        "financial_years": catalog["financial_years"],
        "subentities": catalog["subentities"],
        "vendors": catalog["vendors"],
        "vendor_groups": catalog["vendor_groups"],
        "regions": catalog["regions"],
        "currencies": catalog["currencies"],
        "choices": {
            "aging_view_modes": [
                {"value": "summary", "label": "Summary"},
                {"value": "invoice", "label": "Invoice Aging"},
            ],
            "settlement_types": [
                {"value": "payment", "label": "Payment"},
                {"value": "advance_adjustment", "label": "Advance Adjustment"},
                {"value": "credit_note_adjustment", "label": "Credit Note Adjustment"},
                {"value": "debit_note_adjustment", "label": "Debit Note Adjustment"},
                {"value": "writeoff", "label": "Write Off"},
                {"value": "manual", "label": "Manual"},
            ],
            "note_types": [
                {"value": "credit", "label": "Credit Note"},
                {"value": "debit", "label": "Debit Note"},
            ],
            "sort_order": [
                {"value": "asc", "label": "Ascending"},
                {"value": "desc", "label": "Descending"},
            ],
            "export": [
                {"value": "excel", "label": "Excel"},
                {"value": "pdf", "label": "PDF"},
                {"value": "csv", "label": "CSV"},
                {"value": "print", "label": "Print"},
            ],
            "date_presets": catalog["date_presets"],
        },
        "reports": report_registry,
        "report_definitions": report_definitions,
        "drilldown_targets": drilldown_targets,
        "user_preferences": user_preferences or {},
        "actions": {
            "can_view": True,
            "can_export_excel": True,
            "can_export_pdf": True,
            "can_export_csv": True,
            "can_print": True,
            "can_drilldown": True,
        },
    }
