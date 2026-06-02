from __future__ import annotations

from decimal import Decimal

from reports.services.financial.trial_balance import (
    _group_rows,
    _raw_trial_balance_rows,
    _resolve_trial_balance_window,
)


GROUP_BY_CHOICES = {"ledger", "accounthead", "accounttype"}
VIEW_TYPE_CHOICES = {"summary", "detailed"}
SORT_BY_MAP = {
    "account_name": "ledger_name",
    "account_head": "accounthead_name",
    "account_type": "accounttype_name",
    "opening": "opening",
    "debit": "debit",
    "credit": "credit",
    "balance": "closing",
}


def _dc_label(value: Decimal) -> str:
    if value > 0:
        return "Dr"
    if value < 0:
        return "Cr"
    return "-"


def _format_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _positive_total(values: list[Decimal]) -> Decimal:
    return sum((value for value in values if value > 0), Decimal("0.00"))


def _negative_total(values: list[Decimal]) -> Decimal:
    return sum((abs(value) for value in values if value < 0), Decimal("0.00"))


def _map_ledger_row(row: dict) -> dict:
    opening_value = row.get("opening_value") or Decimal("0.00")
    closing_value = row.get("closing_value") or Decimal("0.00")
    return {
        "ledger_id": row.get("ledger_id"),
        "ledger_code": row.get("ledger_code"),
        "ledger_name": row.get("ledger_name"),
        "accounthead_id": row.get("accounthead_id"),
        "accounthead_name": row.get("accounthead_name"),
        "accounttype_id": row.get("accounttype_id"),
        "accounttype_name": row.get("accounttype_name"),
        "opening": _format_amount(opening_value),
        "debit": _format_amount(row.get("debit_value") or Decimal("0.00")),
        "credit": _format_amount(row.get("credit_value") or Decimal("0.00")),
        "balance": _format_amount(closing_value),
        "opening_value": opening_value,
        "debit_value": row.get("debit_value") or Decimal("0.00"),
        "credit_value": row.get("credit_value") or Decimal("0.00"),
        "balance_value": closing_value,
        "ob_drcr": _dc_label(opening_value),
        "drcr": _dc_label(closing_value),
    }


def _map_group_row(row: dict, *, include_children: bool) -> dict:
    opening_value = row.get("opening_value") or Decimal("0.00")
    closing_value = row.get("closing_value") or Decimal("0.00")
    children = [_map_ledger_row(child) for child in (row.get("children") or [])] if include_children else []
    return {
        "group_id": row.get("group_id"),
        "label": row.get("label"),
        "ledger_name": row.get("label"),
        "opening": _format_amount(opening_value),
        "debit": _format_amount(row.get("debit_value") or Decimal("0.00")),
        "credit": _format_amount(row.get("credit_value") or Decimal("0.00")),
        "balance": _format_amount(closing_value),
        "opening_value": opening_value,
        "debit_value": row.get("debit_value") or Decimal("0.00"),
        "credit_value": row.get("credit_value") or Decimal("0.00"),
        "balance_value": closing_value,
        "ob_drcr": _dc_label(opening_value),
        "drcr": _dc_label(closing_value),
        "child_count": row.get("child_count") or len(children),
        "children": children,
    }


def build_ledger_summary(
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    *,
    from_date=None,
    to_date=None,
    as_of_date=None,
    group_by=None,
    include_zero_balance=False,
    include_opening=True,
    posted_only=True,
    search=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
    view_type=None,
):
    from_date, to_date = _resolve_trial_balance_window(entityfin_id, from_date, to_date, as_of_date)

    _, entityfin_id, subentity_id, from_date, to_date, scope_names, raw_rows = _raw_trial_balance_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        ledger_ids=None,
        posted_only=posted_only,
        include_zero_balances=include_zero_balance,
        include_opening=include_opening,
        search=search,
    )

    resolved_group_by = (group_by or "ledger").strip().lower()
    if resolved_group_by not in GROUP_BY_CHOICES:
        resolved_group_by = "ledger"

    resolved_view_type = (view_type or "summary").strip().lower()
    if resolved_view_type not in VIEW_TYPE_CHOICES:
        resolved_view_type = "summary"

    resolved_sort_by = SORT_BY_MAP.get((sort_by or "account_name").strip().lower(), "ledger_name")
    resolved_sort_order = (sort_order or "asc").strip().lower()
    if resolved_sort_order not in {"asc", "desc"}:
        resolved_sort_order = "asc"

    if resolved_group_by == "ledger":
        prepared_rows = [_map_ledger_row(row) for row in raw_rows]
    else:
        grouped_rows = _group_rows(raw_rows, resolved_group_by, resolved_sort_by, resolved_sort_order)
        prepared_rows = [
            _map_group_row(group_row, include_children=resolved_view_type == "detailed")
            for group_row in grouped_rows
        ]

    total_records = len(prepared_rows)
    try:
        safe_page_size = max(int(page_size or 100), 1)
    except (TypeError, ValueError):
        safe_page_size = 100
    total_pages = max((total_records + safe_page_size - 1) // safe_page_size, 1)
    safe_page = min(max(int(page or 1), 1), total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    paged_rows = prepared_rows[start:end]

    opening_values = [row.get("opening_value") or Decimal("0.00") for row in raw_rows]
    balance_values = [row.get("closing_value") or Decimal("0.00") for row in raw_rows]
    total_opening_debit = _positive_total(opening_values)
    total_opening_credit = _negative_total(opening_values)
    total_balance_debit = _positive_total(balance_values)
    total_balance_credit = _negative_total(balance_values)
    total_opening = max(total_opening_debit, total_opening_credit)
    total_debit = sum((row.get("debit_value") or Decimal("0.00") for row in raw_rows), Decimal("0.00"))
    total_credit = sum((row.get("credit_value") or Decimal("0.00") for row in raw_rows), Decimal("0.00"))
    total_closing = max(total_balance_debit, total_balance_credit)

    return {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "rows": paged_rows,
        "totals": {
            "opening": _format_amount(total_opening),
            "debit": _format_amount(total_debit),
            "credit": _format_amount(total_credit),
            "balance": _format_amount(total_closing),
            "opening_debit": _format_amount(total_opening_debit),
            "opening_credit": _format_amount(total_opening_credit),
            "balance_debit": _format_amount(total_balance_debit),
            "balance_credit": _format_amount(total_balance_credit),
        },
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
            "total_records": total_records,
        },
        "reporting": {
            "basis": "ledger_summary",
            "group_by": resolved_group_by,
            "view_type": resolved_view_type,
            "sort_by": sort_by or "account_name",
            "sort_order": resolved_sort_order,
            "include_zero_balances": include_zero_balance,
            "include_opening": include_opening,
            "posted_only": posted_only,
            "search": search,
        },
    }
