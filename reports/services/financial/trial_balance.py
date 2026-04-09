from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from financial.models import Debit, Ledger
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)


GROUP_BY_CHOICES = {"ledger", "accounthead", "accounttype"}
PERIOD_BY_CHOICES = {"month", "quarter", "year"}



def _coerce_date(value):
    if value is None or isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value))


def _resolve_trial_balance_window(entityfin_id=None, from_date=None, to_date=None, as_of_date=None):
    explicit_from = _coerce_date(from_date)
    explicit_to = _coerce_date(as_of_date or to_date)

    if entityfin_id:
        fy_start, fy_end = resolve_date_window(entityfin_id, None, None)
        fy_start = _coerce_date(fy_start)
        fy_end = _coerce_date(fy_end)
        return explicit_from or fy_start, explicit_to or fy_end

    return explicit_from, explicit_to


def _sort_key(row, sort_by):
    if sort_by in {"opening", "debit", "credit", "closing"}:
        return row.get(f"{sort_by}_value", Decimal("0.00"))
    if sort_by in {"ledger_code", "code"}:
        return row.get("ledger_code") or 0
    if sort_by in {"accounthead", "accounthead_name"}:
        return (row.get("accounthead_name") or row.get("label") or "").lower()
    if sort_by in {"accounttype", "accounttype_name"}:
        return (row.get("accounttype_name") or row.get("label") or "").lower()
    return (row.get("ledger_name") or row.get("label") or "").lower()


def _paginate(rows, page, page_size):
    total = len(rows)
    start = max((page - 1) * page_size, 0)
    end = start + page_size
    return rows[start:end], total


def _last_day_of_month(d):
    first_next = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first_next - timedelta(days=1)


def _quarter_end(d):
    quarter = ((d.month - 1) // 3) + 1
    last_month = quarter * 3
    return _last_day_of_month(d.replace(month=last_month, day=1))


def _year_end(d):
    return date(d.year, 12, 31)


def _iter_period_ranges(start_date, end_date, period_by):
    cursor = start_date
    while cursor <= end_date:
        if period_by == "month":
            period_end = _last_day_of_month(cursor)
        elif period_by == "quarter":
            period_end = _quarter_end(cursor)
        else:
            period_end = _year_end(cursor)
        if period_end > end_date:
            period_end = end_date
        yield cursor, period_end
        cursor = period_end + timedelta(days=1)


def _resolve_dynamic_party_head(ledger, closing_value):
    """
    Resolve display account head dynamically:
    - non-party: use configured debit head (or credit head fallback)
    - party with positive closing: use debit head
    - party with negative closing: use credit head
    - party with zero closing: use debit head (credit fallback)
    """
    debit_head = getattr(ledger, "accounthead", None)
    credit_head = getattr(ledger, "creditaccounthead", None)

    if not getattr(ledger, "is_party", False):
        selected = debit_head or credit_head
    elif closing_value < 0:
        selected = credit_head or debit_head
    else:
        selected = debit_head or credit_head

    if selected is None:
        return None, None, Debit
    return selected.id, selected.name, selected.drcreffect or Debit


def _raw_trial_balance_rows(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    ledger_ids=None,
    posted_only=True,
    include_zero_balances=False,
    search=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_trial_balance_window(entityfin_id, from_date, to_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    lines = journal_lines_for_scope(
        entity_id,
        entityfin_id,
        subentity_id,
        from_date,
        to_date,
        posted_only=posted_only,
    )
    movement_rows = (
        lines.values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=Decimal("0.00")),
            credit=Sum("amount", filter=Q(drcr=False), default=Decimal("0.00")),
        )
    )
    movement_map = {row["resolved_ledger_id"]: row for row in movement_rows}

    selected_ledger_ids = [int(ledger_id) for ledger_id in (ledger_ids or []) if ledger_id is not None]
    if selected_ledger_ids:
        ledger_ids = selected_ledger_ids
    else:
        ledger_ids = list(movement_map.keys())

    if not ledger_ids:
        return entity_id, entityfin_id, subentity_id, from_date, to_date, scope_names, []

    ledgers = (
        Ledger.objects.filter(id__in=ledger_ids)
        .select_related("accounthead", "creditaccounthead", "accounttype", "account_profile__commercial_profile")
        .order_by("ledger_code", "name")
    )

    rows = []
    search_text = (search or "").strip().lower()
    for ledger in ledgers:
        movement = movement_map.get(ledger.id, {})
        opening_dr = ledger.openingbdr or Decimal("0.00")
        opening_cr = ledger.openingbcr or Decimal("0.00")
        opening = opening_dr - opening_cr
        debit = movement.get("debit") or Decimal("0.00")
        credit = movement.get("credit") or Decimal("0.00")
        closing = opening + debit - credit
        accounthead_id, accounthead_name, normal_balance = _resolve_dynamic_party_head(ledger, closing)
        abnormal_balance = _is_abnormal_balance(closing, normal_balance)
        if not include_zero_balances and opening == 0 and debit == 0 and credit == 0 and closing == 0:
            continue
        row = {
            "ledger_id": ledger.id,
            "ledger_code": ledger.ledger_code,
            "ledger_name": ledger.name,
            "accounthead_id": accounthead_id,
            "accounthead_name": accounthead_name,
            "accounttype_id": ledger.accounttype_id,
            "accounttype_name": ledger.accounttype.accounttypename if ledger.accounttype_id else None,
            "normal_balance": normal_balance,
            "opening": f"{opening:.2f}",
            "debit": f"{debit:.2f}",
            "credit": f"{credit:.2f}",
            "closing": f"{closing:.2f}",
            "opening_value": opening,
            "debit_value": debit,
            "credit_value": credit,
            "closing_value": closing,
            "is_abnormal_balance": abnormal_balance,
        }
        if search_text:
            haystack = " ".join(
                str(v or "")
                for v in (
                    row["ledger_code"],
                    row["ledger_name"],
                    row["accounthead_name"],
                    row["accounttype_name"],
                )
            ).lower()
            if search_text not in haystack:
                continue
        rows.append(row)

    return entity_id, entityfin_id, subentity_id, from_date, to_date, scope_names, rows


def _group_rows(rows, group_by, sort_by, sort_order):
    reverse = (sort_order or "asc").lower() == "desc"
    if group_by == "ledger":
        out = [dict(row) for row in rows]
        out.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
        return out

    grouped = defaultdict(list)
    for row in rows:
        if group_by == "accounttype":
            key = (row["accounttype_id"], row["accounttype_name"] or "Unmapped Account Type")
        else:
            key = (row["accounthead_id"], row["accounthead_name"] or "Unmapped Account Head")
        grouped[key].append(row)

    out = []
    for (group_id, group_name), children in grouped.items():
        opening = sum((child["opening_value"] for child in children), Decimal("0.00"))
        debit = sum((child["debit_value"] for child in children), Decimal("0.00"))
        credit = sum((child["credit_value"] for child in children), Decimal("0.00"))
        closing = sum((child["closing_value"] for child in children), Decimal("0.00"))
        abnormal_children = [child for child in children if child.get("is_abnormal_balance")]
        child_rows = [dict(child) for child in children]
        child_rows.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
        out.append(
            {
                "group_id": group_id,
                "label": group_name,
                "opening": f"{opening:.2f}",
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
                "closing": f"{closing:.2f}",
                "opening_value": opening,
                "debit_value": debit,
                "credit_value": credit,
                "closing_value": closing,
                "children": child_rows,
                "child_count": len(child_rows),
                "is_abnormal_balance": bool(abnormal_children) or _is_abnormal_balance(closing, None),
            }
        )
    out.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
    return out


def _is_abnormal_balance(closing, normal_balance):
    closing_amount = Decimal(str(closing or 0))
    if closing_amount == 0:
        return False
    side = (normal_balance or "").strip().lower()
    if side == "debit":
        return closing_amount < 0
    if side == "credit":
        return closing_amount > 0
    return False


def _row_identity(row, group_by):
    if row.get("children"):
        group_id = row.get("group_id")
        if group_id is not None:
            return f"group:{group_by}:{group_id}"
        fallback_label = row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name")
        return f"group:{group_by}:{fallback_label or 'row'}"

    ledger_id = row.get("ledger_id")
    if ledger_id is not None:
        return f"ledger:{ledger_id}"

    accounthead_id = row.get("accounthead_id")
    if accounthead_id is not None:
        return f"accounthead:{accounthead_id}"

    accounttype_id = row.get("accounttype_id")
    if accounttype_id is not None:
        return f"accounttype:{accounttype_id}"

    fallback_label = row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name")
    return f"row:{fallback_label or 'row'}"


def _build_row_period_map(rows, group_by, period_key, period_label):
    period_map = {}
    for row in rows:
        row_id = _row_identity(row, group_by)
        period_map[row_id] = {
            "key": period_key,
            "label": period_label,
            "code": period_key,
            "name": period_label,
            "title": period_label,
            "opening": row.get("opening", "0.00"),
            "debit": row.get("debit", "0.00"),
            "credit": row.get("credit", "0.00"),
            "closing": row.get("closing", "0.00"),
        }
        if row.get("children"):
            period_map.update(_build_row_period_map(row["children"], group_by, period_key, period_label))
    return period_map


def _attach_period_rows(rows, period_maps, period_meta, group_by):
    for row in rows:
        row_id = _row_identity(row, group_by)
        row["periods"] = []
        for index, meta in enumerate(period_meta):
            period_values = period_maps[index].get(row_id)
            if period_values is None:
                period_values = {
                    "key": meta["period_key"],
                    "label": meta["period_label"],
                    "code": meta["period_key"],
                    "name": meta["period_label"],
                    "title": meta["period_label"],
                    "opening": "0.00",
                    "debit": "0.00",
                    "credit": "0.00",
                    "closing": "0.00",
                }
            row["periods"].append(period_values)
        if row.get("children"):
            _attach_period_rows(row["children"], period_maps, period_meta, group_by)


def _build_snapshot(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    ledger_ids,
    posted_only,
    group_by,
    include_zero_balances,
    search,
    sort_by,
    sort_order,
    page,
    page_size,
    include_pagination=True,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, scope_names, rows = _raw_trial_balance_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        ledger_ids=ledger_ids,
        posted_only=posted_only,
        include_zero_balances=include_zero_balances,
        search=search,
    )

    totals = defaultdict(lambda: Decimal("0.00"))
    totals["opening"] += Decimal("0.00")
    totals["debit"] += Decimal("0.00")
    totals["credit"] += Decimal("0.00")
    totals["closing"] += Decimal("0.00")
    for row in rows:
        totals["opening"] += row["opening_value"]
        totals["debit"] += row["debit_value"]
        totals["credit"] += row["credit_value"]
        totals["closing"] += row["closing_value"]

    grouped_rows = _group_rows(rows, group_by, sort_by, sort_order)
    effective_page = 1 if not include_pagination else page
    effective_page_size = max(len(grouped_rows), 1) if not include_pagination else page_size
    paged_rows, total_rows = _paginate(grouped_rows, effective_page, effective_page_size)

    cleaned_rows = []
    for row in paged_rows:
        item = dict(row)
        item.pop("opening_value", None)
        item.pop("debit_value", None)
        item.pop("credit_value", None)
        item.pop("closing_value", None)
        for child in item.get("children", []):
            child.pop("opening_value", None)
            child.pop("debit_value", None)
            child.pop("credit_value", None)
            child.pop("closing_value", None)
        cleaned_rows.append(item)

    snapshot = {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "group_by": group_by,
        "rows": cleaned_rows,
        "totals": {k: f"{v:.2f}" for k, v in totals.items()},
    }
    if include_pagination:
        snapshot["pagination"] = {
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
        }
    return snapshot


def build_trial_balance(
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    ledger_ids=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    account_group=None,
    include_zero_balances=False,
    posted_only=True,
    search=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
    period_by=None,
    view_type=None,
    include_opening=True,
    include_movement=True,
    include_closing=True,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_trial_balance_window(entityfin_id, from_date, to_date, as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    group_by = (account_group or "ledger").strip().lower()
    if group_by not in GROUP_BY_CHOICES:
        group_by = "ledger"

    view_type = (view_type or "").strip().lower() or None
    if view_type not in {"summary", "detailed"}:
        view_type = None

    period_by = (period_by or "").strip().lower() or None
    if period_by not in PERIOD_BY_CHOICES:
        period_by = None

    sort_by = (sort_by or "ledger_name").strip().lower()
    sort_order = (sort_order or "asc").strip().lower()
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"

    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 100), 1)

    snapshot = _build_snapshot(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        ledger_ids=ledger_ids,
        posted_only=posted_only,
        group_by=group_by,
        include_zero_balances=include_zero_balances,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        include_pagination=True,
    )

    response = {
        **snapshot,
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "reporting": {
            "basis": "period",
            "group_by": group_by,
            "account_group": group_by,
            "view_type": view_type or ("detailed" if group_by != "ledger" else "summary"),
            "period_by": period_by,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search": search,
            "posted_only": posted_only,
            "include_opening": include_opening,
            "include_movement": include_movement,
            "include_closing": include_closing,
            "ledger_ids": ledger_ids or [],
        },
    }

    if period_by and from_date and to_date and from_date <= to_date:
        periods = []
        period_meta = []
        period_maps = []
        for period_start, period_end in _iter_period_ranges(from_date, to_date, period_by):
            period_snapshot = _build_snapshot(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=period_start,
                to_date=period_end,
                ledger_ids=ledger_ids,
                posted_only=posted_only,
                group_by=group_by,
                include_zero_balances=include_zero_balances,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order,
                page=1,
                page_size=page_size,
                include_pagination=False,
            )
            period_snapshot["period_key"] = (
                f"{period_end.year}-Q{((period_end.month - 1) // 3) + 1}"
                if period_by == "quarter"
                else period_end.strftime("%Y")
                if period_by == "year"
                else period_end.strftime("%Y-%m")
            )
            period_snapshot["period_label"] = (
                f"Q{((period_end.month - 1) // 3) + 1} {period_end.year}"
                if period_by == "quarter"
                else period_end.strftime("%Y")
                if period_by == "year"
                else period_end.strftime("%b %Y")
            )
            period_snapshot["key"] = period_snapshot["period_key"]
            period_snapshot["code"] = period_snapshot["period_key"]
            period_snapshot["label"] = period_snapshot["period_label"]
            period_snapshot["name"] = period_snapshot["period_label"]
            period_snapshot["title"] = period_snapshot["period_label"]
            period_meta.append(
                {
                    "period_key": period_snapshot["period_key"],
                    "period_label": period_snapshot["period_label"],
                }
            )
            period_maps.append(_build_row_period_map(period_snapshot["rows"], group_by, period_snapshot["period_key"], period_snapshot["period_label"]))
            periods.append(period_snapshot)
        _attach_period_rows(snapshot["rows"], period_maps, period_meta, group_by)
        response["periods"] = periods

    return response
