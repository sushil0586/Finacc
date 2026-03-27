from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from financial.models import Ledger
from reports.services.balance_sheet import _inventory_value_asof
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)


PNL_INCOME_TYPE_CODES = {"1014", "1015"}
PNL_EXPENSE_TYPE_CODES = {"1016"}

GROUP_BY_CHOICES = {"ledger", "accounthead", "accounttype"}
PERIOD_BY_CHOICES = {"month", "quarter", "year"}
STOCK_VALUATION_MODES = {"auto", "gl", "valuation", "none"}
STOCK_VALUATION_METHODS = {"fifo", "lifo", "mwa", "wac", "latest"}
INVENTORY_LABEL = "Inventory (Closing Stock)"


def _normalize_balance_side(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text in {"debit", "dr", "true", "1"}:
        return "debit"
    if text in {"credit", "cr", "false", "0"}:
        return "credit"
    return text


def _balance_sheet_bucket(head, acc_type):
    head_side = _normalize_balance_side(getattr(head, "drcreffect", None) or getattr(head, "balanceType", None))
    if head_side == "debit":
        return "asset"
    if head_side == "credit":
        return "liability"

    type_side = _normalize_balance_side(getattr(acc_type, "balanceType", None))
    if type_side == "debit":
        return "asset"
    if type_side == "credit":
        return "liability"
    return ""


def _balance_sheet_bucket_for_amount(amount, head, acc_type):
    if amount > 0:
        return "asset"
    if amount < 0:
        return "liability"
    return _balance_sheet_bucket(head, acc_type)


def _resolve_effective_head_and_type(ledger, amount):
    """
    Dynamic head selection:
    - For party ledgers, choose debit/credit head by sign.
    - For others, prefer debit head with credit fallback.
    """
    debit_head = getattr(ledger, "accounthead", None)
    credit_head = getattr(ledger, "creditaccounthead", None)

    if getattr(ledger, "is_party", False) and amount < 0:
        head = credit_head or debit_head
    else:
        head = debit_head or credit_head

    acc_type = getattr(head, "accounttype", None) if head else getattr(ledger, "accounttype", None)
    return head, acc_type


def _coerce_date(value):
    if value is None or isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value))


def _resolve_balance_sheet_window(entityfin_id=None, from_date=None, to_date=None, as_of_date=None):
    explicit_from = _coerce_date(from_date)
    explicit_to = _coerce_date(as_of_date or to_date)

    if entityfin_id:
        fy_start, fy_end = resolve_date_window(entityfin_id, None, None)
        fy_start = _coerce_date(fy_start)
        fy_end = _coerce_date(fy_end)
        return explicit_from or fy_start, explicit_to or fy_end

    return explicit_from, explicit_to


def _ledger_drilldown_meta(ledger, entity_id, entityfin_id, subentity_id):
    return {
        "can_drilldown": True,
        "drilldown_target": "ledger_book",
        "drilldown_params": {
            "entity": entity_id,
            "entityfinid": entityfin_id,
            "subentity": subentity_id,
            "ledger": ledger.id,
        },
    }


def _closing_map(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date)
    lines = journal_lines_for_scope(entity_id, entityfin_id, subentity_id, from_date, to_date)
    movement_rows = (
        lines.values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=Decimal("0.00")),
            credit=Sum("amount", filter=Q(drcr=False), default=Decimal("0.00")),
        )
    )
    movement_map = {row["resolved_ledger_id"]: row for row in movement_rows}
    ledgers = (
        Ledger.objects.filter(id__in=movement_map.keys())
        .select_related("accounthead", "accounthead__accounttype", "creditaccounthead", "creditaccounthead__accounttype", "accounttype")
        .order_by("accounthead__code", "ledger_code", "name")
    )
    closing = {}
    for ledger in ledgers:
        move = movement_map.get(ledger.id, {})
        opening = (ledger.openingbdr or Decimal("0.00")) - (ledger.openingbcr or Decimal("0.00"))
        closing[ledger.id] = {
            "ledger": ledger,
            "amount": opening + (move.get("debit") or Decimal("0.00")) - (move.get("credit") or Decimal("0.00")),
        }
    return entity_id, entityfin_id, subentity_id, from_date, to_date, closing


def _raw_balance_rows(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    include_zero_balances=False,
    search=None,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, closing = _closing_map(
        entity_id, entityfin_id, subentity_id, from_date, to_date
    )

    rows = []
    search_text = (search or "").strip().lower()
    for item in closing.values():
        ledger = item["ledger"]
        amount = item["amount"]
        head, acc_type = _resolve_effective_head_and_type(ledger, amount)
        type_code = str(getattr(acc_type, "accounttypecode", "")) if acc_type else ""
        if type_code in PNL_INCOME_TYPE_CODES or type_code in PNL_EXPENSE_TYPE_CODES:
            continue
        if not include_zero_balances and amount == 0:
            continue

        row = {
            "ledger_id": ledger.id,
            "ledger_code": ledger.ledger_code,
            "ledger_name": ledger.name,
            "accounthead_id": head.id if head else None,
            "accounthead_name": head.name if head else None,
            "accounttype_id": acc_type.id if acc_type else None,
            "accounttype_name": acc_type.accounttypename if acc_type else None,
            "amount_decimal": amount,
            "amount": f"{abs(amount):.2f}",
            "bucket": _balance_sheet_bucket_for_amount(amount, head, acc_type),
            **_ledger_drilldown_meta(ledger, entity_id, entityfin_id, subentity_id),
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

    return entity_id, entityfin_id, subentity_id, from_date, to_date, rows


def _raw_profit_loss_rows(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    include_zero_balances=False,
    search=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date)
    lines = journal_lines_for_scope(entity_id, entityfin_id, subentity_id, from_date, to_date)
    movement_rows = (
        lines.values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=Decimal("0.00")),
            credit=Sum("amount", filter=Q(drcr=False), default=Decimal("0.00")),
        )
    )
    movement_map = {row["resolved_ledger_id"]: row for row in movement_rows}

    ledgers = (
        Ledger.objects.filter(id__in=movement_map.keys())
        .select_related("accounthead", "accounthead__accounttype", "creditaccounthead", "creditaccounthead__accounttype", "accounttype")
        .order_by("accounthead__code", "ledger_code", "name")
    )

    rows = []
    search_text = (search or "").strip().lower()
    for ledger in ledgers:
        move = movement_map.get(ledger.id, {})
        debit = move.get("debit") or Decimal("0.00")
        credit = move.get("credit") or Decimal("0.00")
        net = debit - credit

        head, acc_type = _resolve_effective_head_and_type(ledger, net)
        type_code = str(getattr(acc_type, "accounttypecode", "")) if acc_type else ""
        if type_code not in PNL_INCOME_TYPE_CODES and type_code not in PNL_EXPENSE_TYPE_CODES:
            continue
        if not include_zero_balances and net == 0:
            continue

        row = {
            "ledger_id": ledger.id,
            "ledger_code": ledger.ledger_code,
            "ledger_name": ledger.name,
            "accounthead_id": head.id if head else None,
            "accounthead_name": head.name if head else None,
            "accounttype_id": acc_type.id if acc_type else None,
            "accounttype_name": acc_type.accounttypename if acc_type else None,
            "debit": f"{debit:.2f}",
            "credit": f"{credit:.2f}",
            "amount_decimal": abs(net),
            "amount": f"{abs(net):.2f}",
            "category": "income" if type_code in PNL_INCOME_TYPE_CODES else "expense",
            **_ledger_drilldown_meta(ledger, entity_id, entityfin_id, subentity_id),
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

    return entity_id, entityfin_id, subentity_id, from_date, to_date, rows


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


def _build_profit_loss_snapshot(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    group_by,
    include_zero_balances,
    search,
    sort_by,
    sort_order,
    page,
    page_size,
    stock_valuation_mode,
    stock_valuation_method,
    include_pagination=True,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, rows = _raw_profit_loss_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        include_zero_balances=include_zero_balances,
        search=search,
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    income_source = [row for row in rows if row["category"] == "income"]
    expense_source = [row for row in rows if row["category"] == "expense"]
    total_income = sum((row["amount_decimal"] for row in income_source), Decimal("0.00"))
    total_expense = sum((row["amount_decimal"] for row in expense_source), Decimal("0.00"))

    stock_context = _stock_context(
        entity_id=entity_id,
        from_date=from_date,
        to_date=to_date,
        assets_source=[],
        requested_mode=stock_valuation_mode,
        valuation_method=stock_valuation_method,
    )
    stock_adjustment = Decimal("0.00")
    if stock_context["effective_mode"] == "valuation":
        stock_adjustment = stock_context["inventory_delta"]
        if stock_adjustment > 0:
            income_source.append(
                {
                    "ledger_id": None,
                    "ledger_code": None,
                    "ledger_name": "Closing Stock Adjustment",
                    "accounthead_id": None,
                    "accounthead_name": "Stock Adjustment",
                    "accounttype_id": None,
                    "accounttype_name": "Inventory",
                    "debit": "0.00",
                    "credit": f"{stock_adjustment:.2f}",
                    "amount_decimal": stock_adjustment,
                    "amount": f"{stock_adjustment:.2f}",
                    "category": "income",
                    "can_drilldown": False,
                    "drilldown_target": None,
                    "drilldown_params": None,
                }
            )
        elif stock_adjustment < 0:
            loss_stock = abs(stock_adjustment)
            expense_source.append(
                {
                    "ledger_id": None,
                    "ledger_code": None,
                    "ledger_name": "Stock Consumption Adjustment",
                    "accounthead_id": None,
                    "accounthead_name": "Stock Adjustment",
                    "accounttype_id": None,
                    "accounttype_name": "Inventory",
                    "debit": f"{loss_stock:.2f}",
                    "credit": "0.00",
                    "amount_decimal": loss_stock,
                    "amount": f"{loss_stock:.2f}",
                    "category": "expense",
                    "can_drilldown": False,
                    "drilldown_target": None,
                    "drilldown_params": None,
                }
            )

    adjusted_income = total_income + max(stock_adjustment, Decimal("0.00"))
    adjusted_expense = total_expense + abs(min(stock_adjustment, Decimal("0.00")))
    net_profit = adjusted_income - adjusted_expense

    effective_page = 1 if not include_pagination else page
    effective_page_size = max(len(income_source), len(expense_source), 1) if not include_pagination else page_size
    income_rows, income_count = _build_side_rows(
        income_source,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        page=effective_page,
        page_size=effective_page_size,
    )
    expense_rows, expense_count = _build_side_rows(
        expense_source,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        page=effective_page,
        page_size=effective_page_size,
    )

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
        "income": income_rows,
        "expenses": expense_rows,
        "totals": {
            "income": f"{adjusted_income:.2f}",
            "expense": f"{adjusted_expense:.2f}",
            "net_profit": f"{net_profit:.2f}",
            "raw_income": f"{total_income:.2f}",
            "raw_expense": f"{total_expense:.2f}",
            "stock_adjustment": f"{stock_adjustment:.2f}",
        },
        "summary": {
            "income_rows": income_count,
            "expense_rows": expense_count,
            "opening_inventory_valuation": f"{stock_context['opening_inventory']:.2f}",
            "closing_inventory_valuation": f"{stock_context['closing_inventory']:.2f}",
        },
        "stock_valuation": {
            "requested_mode": stock_context["requested_mode"],
            "effective_mode": stock_context["effective_mode"],
            "valuation_method": stock_context["valuation_method"],
            "valuation_available": stock_context["valuation_available"],
            "opening_inventory": f"{stock_context['opening_inventory']:.2f}",
            "closing_inventory": f"{stock_context['closing_inventory']:.2f}",
            "inventory_delta": f"{stock_context['inventory_delta']:.2f}",
            "gl_inventory_total": f"{stock_context['gl_inventory_total']:.2f}",
            "notes": stock_context["notes"],
        },
    }
    if include_pagination:
        snapshot["pagination"] = {
            "page": page,
            "page_size": page_size,
            "income_total_rows": income_count,
            "expense_total_rows": expense_count,
        }
    return snapshot


def build_profit_and_loss(
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    group_by=None,
    include_zero_balances=False,
    search=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
    period_by=None,
    stock_valuation_mode="auto",
    stock_valuation_method="fifo",
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date, as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    group_by = (group_by or "ledger").strip().lower()
    if group_by not in GROUP_BY_CHOICES:
        group_by = "ledger"

    period_by = (period_by or "").strip().lower() or None
    if period_by not in PERIOD_BY_CHOICES:
        period_by = None

    stock_valuation_mode = (stock_valuation_mode or "auto").strip().lower()
    if stock_valuation_mode not in STOCK_VALUATION_MODES:
        stock_valuation_mode = "auto"

    stock_valuation_method = (stock_valuation_method or "fifo").strip().lower()
    if stock_valuation_method not in STOCK_VALUATION_METHODS:
        stock_valuation_method = "fifo"

    sort_by = (sort_by or "ledger_name").strip().lower()
    sort_order = (sort_order or "asc").strip().lower()
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"

    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 100), 1)

    snapshot = _build_profit_loss_snapshot(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        group_by=group_by,
        include_zero_balances=include_zero_balances,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        stock_valuation_mode=stock_valuation_mode,
        stock_valuation_method=stock_valuation_method,
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
            "period_by": period_by,
            "stock_valuation_mode": stock_valuation_mode,
            "stock_valuation_method": stock_valuation_method,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search": search,
        },
    }

    if period_by and from_date and to_date and from_date <= to_date:
        periods = []
        for period_start, period_end in _iter_period_ranges(from_date, to_date, period_by):
            period_snapshot = _build_profit_loss_snapshot(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=period_start,
                to_date=period_end,
                group_by=group_by,
                include_zero_balances=include_zero_balances,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order,
                page=1,
                page_size=page_size,
                stock_valuation_mode=stock_valuation_mode,
                stock_valuation_method=stock_valuation_method,
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
            periods.append(period_snapshot)
        response["periods"] = periods

    return response


def _sort_key(row, sort_by):
    if sort_by == "amount":
        return row.get("amount_value", Decimal("0.00"))
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


def _build_grouped_rows(rows, group_by, sort_by, sort_order):
    reverse = (sort_order or "asc").lower() == "desc"
    if group_by == "ledger":
        out = []
        for row in rows:
            item = dict(row)
            item.pop("amount_decimal", None)
            item["amount_value"] = Decimal(item["amount"])
            out.append(item)
        out.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
        return out

    grouped = defaultdict(list)
    for row in rows:
        if group_by == "accounttype":
            key = (
                row["accounttype_id"],
                row["accounttype_name"] or "Unmapped Account Type",
            )
        else:
            key = (
                row["accounthead_id"],
                row["accounthead_name"] or "Unmapped Account Head",
            )
        grouped[key].append(row)

    out = []
    for (group_id, group_name), children in grouped.items():
        child_rows = []
        total_amount = Decimal("0.00")
        for child in children:
            item = dict(child)
            item.pop("amount_decimal", None)
            item["amount_value"] = Decimal(item["amount"])
            child_rows.append(item)
            total_amount += abs(child["amount_decimal"])
        child_rows.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
        out.append(
            {
                "group_id": group_id,
                "label": group_name,
                "amount": f"{total_amount:.2f}",
                "amount_value": total_amount,
                "children": child_rows,
                "child_count": len(child_rows),
            }
        )

    out.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
    return out


def _build_side_rows(
    rows,
    *,
    group_by,
    sort_by,
    sort_order,
    page,
    page_size,
):
    grouped_rows = _build_grouped_rows(rows, group_by, sort_by, sort_order)
    paged_rows, total_rows = _paginate(grouped_rows, page, page_size)
    for row in paged_rows:
        row.pop("amount_value", None)
        for child in row.get("children", []):
            child.pop("amount_value", None)
    return paged_rows, total_rows


def _inventory_keyword(*values):
    text = " ".join(str(value or "") for value in values).strip().lower()
    return any(token in text for token in ("inventory", "closing stock", "stock in hand", "stock", "inventory asset"))


def _inventory_rows(rows):
    return [
        row for row in rows
        if _inventory_keyword(
            row.get("ledger_name"),
            row.get("accounthead_name"),
            row.get("accounttype_name"),
        )
    ]


def _stock_context(*, entity_id, from_date, to_date, assets_source, requested_mode, valuation_method):
    mode = (requested_mode or "auto").strip().lower()
    if mode not in STOCK_VALUATION_MODES:
        mode = "auto"

    method = (valuation_method or "fifo").strip().lower()
    if method not in STOCK_VALUATION_METHODS:
        method = "fifo"

    opening_inventory = Decimal("0.00")
    closing_inventory = Decimal("0.00")
    valuation_available = False
    if to_date:
        try:
            closing_inventory = Decimal(str(_inventory_value_asof(entity_id, to_date, method)))
            valuation_available = True
            if from_date:
                opening_inventory = Decimal(str(_inventory_value_asof(entity_id, from_date - timedelta(days=1), method)))
        except Exception:
            opening_inventory = Decimal("0.00")
            closing_inventory = Decimal("0.00")
            valuation_available = False

    inventory_gl_rows = _inventory_rows(assets_source)
    inventory_gl_total = sum((abs(row["amount_decimal"]) for row in inventory_gl_rows), Decimal("0.00"))

    effective_mode = mode
    notes = []
    if mode == "auto":
        if not valuation_available:
            effective_mode = "gl"
            notes.append("Stock valuation not available; report uses GL stock balances only.")
        elif closing_inventory <= 0:
            effective_mode = "gl"
            notes.append("Stock valuation is zero for the selected date; report uses GL stock balances only.")
        elif inventory_gl_total > 0:
            effective_mode = "gl"
            notes.append("Inventory-like asset balances found in GL; auto mode keeps GL stock to avoid double counting.")
        else:
            effective_mode = "valuation"
            notes.append(f"Inventory injected from stock valuation using '{method.upper()}' because no GL stock asset was detected.")
    elif mode == "valuation":
        if valuation_available:
            notes.append(f"Inventory injected from stock valuation using '{method.upper()}'.")
        else:
            effective_mode = "gl"
            notes.append("Requested stock valuation is unavailable; falling back to GL stock balances.")
    elif mode == "gl":
        notes.append("Inventory taken from GL balances.")
    else:
        notes.append("Stock excluded from balance sheet by request.")

    inventory_delta = Decimal("0.00")
    if effective_mode == "valuation" and valuation_available:
        inventory_delta = closing_inventory - opening_inventory

    return {
        "requested_mode": mode,
        "effective_mode": effective_mode,
        "valuation_method": method,
        "opening_inventory": opening_inventory,
        "closing_inventory": closing_inventory,
        "inventory_delta": inventory_delta,
        "valuation_available": valuation_available,
        "gl_inventory_total": inventory_gl_total,
        "gl_inventory_rows": inventory_gl_rows,
        "notes": notes,
    }


def _build_snapshot(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    group_by,
    include_zero_balances,
    search,
    sort_by,
    sort_order,
    page,
    page_size,
    stock_valuation_mode,
    stock_valuation_method,
    include_pagination=True,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, rows = _raw_balance_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        include_zero_balances=include_zero_balances,
        search=search,
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    assets_source = [row for row in rows if row["bucket"] == "asset"]
    liabilities_source = [row for row in rows if row["bucket"] == "liability"]

    stock_context = _stock_context(
        entity_id=entity_id,
        from_date=from_date,
        to_date=to_date,
        assets_source=assets_source,
        requested_mode=stock_valuation_mode,
        valuation_method=stock_valuation_method,
    )
    if stock_context["effective_mode"] == "valuation":
        gl_inventory_ids = {id(row) for row in stock_context["gl_inventory_rows"]}
        assets_source = [row for row in assets_source if id(row) not in gl_inventory_ids]
        if stock_context["closing_inventory"] != Decimal("0.00"):
            closing_inventory = stock_context["closing_inventory"].copy_abs()
            assets_source.append(
                {
                    "ledger_id": None,
                    "ledger_code": None,
                    "ledger_name": INVENTORY_LABEL,
                    "accounthead_id": None,
                    "accounthead_name": "Inventory",
                    "accounttype_id": None,
                    "accounttype_name": "Inventory",
                    "amount_decimal": closing_inventory,
                    "amount": f"{closing_inventory:.2f}",
                    "bucket": "asset",
                    "can_drilldown": False,
                    "drilldown_target": None,
                    "drilldown_params": None,
                }
            )

    asset_total = sum((abs(row["amount_decimal"]) for row in assets_source), Decimal("0.00"))
    liability_total = sum((abs(row["amount_decimal"]) for row in liabilities_source), Decimal("0.00"))

    pnl = build_profit_and_loss(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        stock_valuation_mode=stock_valuation_mode,
        stock_valuation_method=stock_valuation_method,
    )
    net_profit = Decimal(pnl["totals"]["net_profit"])
    raw_income = Decimal(pnl["totals"].get("raw_income", pnl["totals"]["income"]))
    raw_expense = Decimal(pnl["totals"].get("raw_expense", pnl["totals"]["expense"]))
    raw_net_profit = raw_income - raw_expense
    if net_profit > 0:
        liabilities_source.append(
            {
                "ledger_id": None,
                "ledger_code": None,
                "ledger_name": "Current Period Profit",
                "accounthead_id": None,
                "accounthead_name": "Equity",
                "accounttype_id": None,
                "accounttype_name": "Equity",
                "amount_decimal": net_profit,
                "amount": f"{net_profit:.2f}",
                "bucket": "liability",
                "can_drilldown": False,
                "drilldown_target": None,
                "drilldown_params": None,
            }
        )
        liability_total += net_profit
    elif net_profit < 0:
        loss_amount = abs(net_profit)
        assets_source.append(
            {
                "ledger_id": None,
                "ledger_code": None,
                "ledger_name": "Current Period Loss",
                "accounthead_id": None,
                "accounthead_name": "Equity",
                "accounttype_id": None,
                "accounttype_name": "Equity",
                "amount_decimal": loss_amount,
                "amount": f"{loss_amount:.2f}",
                "bucket": "asset",
                "can_drilldown": False,
                "drilldown_target": None,
                "drilldown_params": None,
            }
        )
        asset_total += loss_amount

    effective_page = 1 if not include_pagination else page
    effective_page_size = max(len(assets_source), len(liabilities_source), 1) if not include_pagination else page_size
    assets, assets_count = _build_side_rows(
        assets_source,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        page=effective_page,
        page_size=effective_page_size,
    )
    liabilities, liabilities_count = _build_side_rows(
        liabilities_source,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        page=effective_page,
        page_size=effective_page_size,
    )

    snapshot = {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "as_of_date": to_date,
        "group_by": group_by,
        "assets": assets,
        "liabilities_and_equity": liabilities,
        "totals": {
            "assets": f"{asset_total:.2f}",
            "liabilities_and_equity": f"{liability_total:.2f}",
        },
        "summary": {
            "asset_rows": assets_count,
            "liability_rows": liabilities_count,
            "net_profit_brought_to_equity": f"{net_profit:.2f}",
            "raw_net_profit": f"{raw_net_profit:.2f}",
            "inventory_adjustment_to_profit": pnl["totals"].get("stock_adjustment", f"{stock_context['inventory_delta']:.2f}"),
            "opening_inventory_valuation": f"{stock_context['opening_inventory']:.2f}",
            "closing_inventory_valuation": f"{stock_context['closing_inventory']:.2f}",
        },
        "stock_valuation": {
            "requested_mode": stock_context["requested_mode"],
            "effective_mode": stock_context["effective_mode"],
            "valuation_method": stock_context["valuation_method"],
            "valuation_available": stock_context["valuation_available"],
            "opening_inventory": f"{stock_context['opening_inventory']:.2f}",
            "closing_inventory": f"{stock_context['closing_inventory']:.2f}",
            "inventory_delta": f"{stock_context['inventory_delta']:.2f}",
            "gl_inventory_total": f"{stock_context['gl_inventory_total']:.2f}",
            "notes": stock_context["notes"],
        },
    }
    if include_pagination:
        snapshot["pagination"] = {
            "page": page,
            "page_size": page_size,
            "assets_total_rows": assets_count,
            "liabilities_total_rows": liabilities_count,
        }
    return snapshot


def _last_day_of_month(d):
    first_next = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first_next - timedelta(days=1)


def _quarter_end(d):
    quarter = ((d.month - 1) // 3) + 1
    last_month = quarter * 3
    return _last_day_of_month(d.replace(month=last_month, day=1))


def _year_end(d):
    return date(d.year, 12, 31)


def _iter_period_ends(start_date, end_date, period_by):
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
        yield period_end
        cursor = period_end + timedelta(days=1)


def build_balance_sheet(
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    group_by=None,
    include_zero_balances=False,
    search=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
    period_by=None,
    stock_valuation_mode="auto",
    stock_valuation_method="fifo",
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date, as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    group_by = (group_by or "ledger").strip().lower()
    if group_by not in GROUP_BY_CHOICES:
        group_by = "ledger"

    period_by = (period_by or "").strip().lower() or None
    if period_by not in PERIOD_BY_CHOICES:
        period_by = None

    stock_valuation_mode = (stock_valuation_mode or "auto").strip().lower()
    if stock_valuation_mode not in STOCK_VALUATION_MODES:
        stock_valuation_mode = "auto"

    stock_valuation_method = (stock_valuation_method or "fifo").strip().lower()
    if stock_valuation_method not in STOCK_VALUATION_METHODS:
        stock_valuation_method = "fifo"

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
        group_by=group_by,
        include_zero_balances=include_zero_balances,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        stock_valuation_mode=stock_valuation_mode,
        stock_valuation_method=stock_valuation_method,
        include_pagination=True,
    )

    response = {
        **snapshot,
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "reporting": {
            "basis": "as_of",
            "group_by": group_by,
            "period_by": period_by,
            "stock_valuation_mode": stock_valuation_mode,
            "stock_valuation_method": stock_valuation_method,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search": search,
        },
    }

    if period_by and from_date and to_date and from_date <= to_date:
        periods = []
        for period_end in _iter_period_ends(from_date, to_date, period_by):
            period_snapshot = _build_snapshot(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=period_end,
                group_by=group_by,
                include_zero_balances=include_zero_balances,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order,
                page=1,
                page_size=page_size,
                stock_valuation_mode=stock_valuation_mode,
                stock_valuation_method=stock_valuation_method,
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
            periods.append(period_snapshot)
        response["periods"] = periods

    return response
