from __future__ import annotations

"""Metadata builders for payable reporting screens and filter panels."""

from collections import OrderedDict
from datetime import timedelta

from django.utils import timezone

from entity.models import EntityFinancialYear, SubEntity
from reports.selectors.payables import vendor_queryset
from reports.services.payables_config import (
    PAYABLE_DRILLDOWN_TARGETS,
    PAYABLE_REPORT_DEFAULTS,
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
                "gstin": vendor.gstno,
                "currency": vendor.currency or "INR",
                "vendor_group": vendor.agent,
                "region_id": getattr(vendor, "state_id", None),
                "region_name": getattr(getattr(vendor, "state", None), "statename", None),
                "region_code": getattr(getattr(vendor, "state", None), "statecode", None),
                "credit_days": vendor.creditdays,
                "credit_limit": str(vendor.creditlimit) if vendor.creditlimit is not None else None,
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


def build_payables_report_meta(*, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None) -> dict:
    """Return backend-driven metadata for payable report filters and navigation."""
    financial_years = _financial_years(entity_id)
    subentities = _subentities(entity_id)
    vendors = _vendors(entity_id)
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
        "financial_years": financial_years,
        "subentities": subentities,
        "vendors": vendors,
        "vendor_groups": _vendor_groups(vendors),
        "regions": _regions(vendors),
        "currencies": _currencies(vendors),
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
            "date_presets": _date_presets(financial_years),
        },
        "reports": get_payables_registry_payload(),
        "report_definitions": get_payables_registry_meta(),
        "drilldown_targets": list(PAYABLE_DRILLDOWN_TARGETS.values()),
        "actions": {
            "can_view": True,
            "can_export_excel": True,
            "can_export_pdf": True,
            "can_export_csv": True,
            "can_print": True,
            "can_drilldown": True,
        },
    }
