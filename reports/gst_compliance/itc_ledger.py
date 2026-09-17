from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce

from financial.models import Ledger
from posting.models import EntryStatus, JournalLine
from posting.services.static_accounts import StaticAccountService

ZERO = Decimal("0.00")
TOLERANCE = Decimal("0.05")

INPUT_TAX_LEDGER_CODES = (
    ("INPUT_CGST", "cgst", "Input CGST"),
    ("INPUT_SGST", "sgst", "Input SGST"),
    ("INPUT_IGST", "igst", "Input IGST"),
    ("INPUT_CESS", "cess", "Input CESS"),
)


def _q(value) -> Decimal:
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _normalize_scope_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _net_itc_bucket(gstr3b_summary: dict[str, Any]) -> dict[str, Decimal]:
    section_4 = gstr3b_summary.get("section_4") or {}
    net_itc = section_4.get("net_itc") or {}
    return {
        "cgst": _q(net_itc.get("cgst")),
        "sgst": _q(net_itc.get("sgst")),
        "igst": _q(net_itc.get("igst")),
        "cess": _q(net_itc.get("cess")),
    }


def _input_tax_ledger_amounts(scope) -> tuple[dict[str, Decimal], dict[str, int | None], list[dict[str, Any]]]:
    ledger_amounts = {component: ZERO for _, component, _ in INPUT_TAX_LEDGER_CODES}
    ledger_ids = {component: None for _, component, _ in INPUT_TAX_LEDGER_CODES}
    warnings: list[dict[str, Any]] = []
    if not scope or not getattr(scope, "entity_id", None):
        warnings.append(
            {
                "code": "GST_INPUT_LEDGER_SCOPE_MISSING",
                "severity": "warning",
                "message": "Input GST ledger comparison could not run because entity scope is missing.",
            }
        )
        return ledger_amounts, ledger_ids, warnings

    for static_code, component, label in INPUT_TAX_LEDGER_CODES:
        ledger_id = StaticAccountService.get_ledger_id(scope.entity_id, static_code, required=False)
        ledger_ids[component] = ledger_id
        if not ledger_id:
            warnings.append(
                {
                    "code": "GST_INPUT_LEDGER_MAPPING_MISSING",
                    "severity": "warning",
                    "message": f"{label} static ledger mapping is missing; ITC books comparison for this tax component is unavailable.",
                    "static_account_code": static_code,
                    "component": component,
                }
            )

    configured_ledger_ids = [ledger_id for ledger_id in ledger_ids.values() if ledger_id]
    if not configured_ledger_ids:
        return ledger_amounts, ledger_ids, warnings

    filters: dict[str, Any] = {
        "entity_id": scope.entity_id,
        "ledger_id__in": configured_ledger_ids,
        "entry__status": EntryStatus.POSTED,
    }
    if getattr(scope, "entityfinid_id", None):
        filters["entityfin_id"] = scope.entityfinid_id
    if getattr(scope, "subentity_id", None) is not None:
        filters["subentity_id"] = scope.subentity_id
    from_date = _normalize_scope_date(getattr(scope, "from_date", None))
    to_date = _normalize_scope_date(getattr(scope, "to_date", None))
    if from_date:
        filters["posting_date__gte"] = from_date
    if to_date:
        filters["posting_date__lte"] = to_date

    aggregates = (
        JournalLine.objects.filter(**filters)
        .values("ledger_id")
        .annotate(
            debit=Coalesce(Sum("amount", filter=Q(drcr=True)), Value(ZERO)),
            credit=Coalesce(Sum("amount", filter=Q(drcr=False)), Value(ZERO)),
        )
    )
    net_debit_by_ledger = {int(row["ledger_id"]): _q(row["debit"]) - _q(row["credit"]) for row in aggregates}
    for _, component, _ in INPUT_TAX_LEDGER_CODES:
        ledger_id = ledger_ids.get(component)
        if ledger_id:
            ledger_amounts[component] = net_debit_by_ledger.get(int(ledger_id), ZERO)
    return ledger_amounts, ledger_ids, warnings


def build_input_tax_ledger_reconciliation(*, gstr3b_summary: dict[str, Any], scope) -> dict[str, Any]:
    return_bucket = _net_itc_bucket(gstr3b_summary)
    ledger_amounts, ledger_ids, warnings = _input_tax_ledger_amounts(scope)
    ledger_names = {
        row["id"]: row["name"]
        for row in Ledger.objects.filter(id__in=[ledger_id for ledger_id in ledger_ids.values() if ledger_id]).values("id", "name")
    }

    rows = []
    for static_code, component, label in INPUT_TAX_LEDGER_CODES:
        return_itc = _q(return_bucket.get(component))
        ledger_itc = _q(ledger_amounts.get(component))
        difference = return_itc - ledger_itc
        ledger_id = ledger_ids.get(component)
        rows.append(
            {
                "code": static_code,
                "component": component,
                "label": label,
                "status": "matched" if ledger_id and abs(difference) <= TOLERANCE else "mismatch",
                "mapping_status": "configured" if ledger_id else "missing_mapping",
                "return_itc": return_itc,
                "ledger_itc": ledger_itc,
                "difference": difference,
                "ledger_id": ledger_id,
                "ledger_name": ledger_names.get(ledger_id),
                "drilldowns": (
                    {
                        "ledger_book": {
                            "target": "ledger_book",
                            "label": "Open ledger book",
                            "kind": "report",
                            "route": "/reports/financial/ledger-book",
                            "params": {
                                "ledger": ledger_id,
                                "ledger_id": ledger_id,
                                "entityfinid": getattr(scope, "entityfinid_id", None),
                                "subentity": getattr(scope, "subentity_id", None),
                                "from_date": getattr(scope, "from_date", None),
                                "to_date": getattr(scope, "to_date", None),
                            },
                        }
                    }
                    if ledger_id
                    else {}
                ),
            }
        )

    return {
        "rows": rows,
        "summary": {
            "comparison_count": len(rows),
            "matched_count": len([row for row in rows if row["status"] == "matched"]),
            "mismatch_count": len([row for row in rows if row["status"] == "mismatch"]),
            "return_total_itc": sum((_q(row["return_itc"]) for row in rows), ZERO),
            "ledger_total_itc": sum((_q(row["ledger_itc"]) for row in rows), ZERO),
            "difference_total_itc": sum((_q(row["difference"]) for row in rows), ZERO),
        },
        "warnings": warnings,
    }
