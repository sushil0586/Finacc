from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum

from financial.models import Ledger
from purchase.models.purchase_core import PurchaseInvoiceHeader
from sales.models.sales_core import SalesInvoiceHeader
from reports.services.balance_sheet import _inventory_value_asof
from reports.services.financial.classification import classify_financial_head
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)

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
    bucket = _balance_sheet_bucket(head, acc_type)
    if bucket in {"asset", "liability"}:
        return bucket
    if amount > 0:
        return "asset"
    if amount < 0:
        return "liability"
    return bucket


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


def _detailsingroup_value(head) -> int | None:
    value = getattr(head, "detailsingroup", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_profit_loss_classification(head, acc_type) -> bool:
    return classify_financial_head(head, acc_type).include_in_profit_loss


def _profit_loss_category(head, acc_type, amount) -> str:
    classification = classify_financial_head(head, acc_type)
    if classification.include_in_profit_loss:
        if classification.profit_loss_side in {"income", "expense"}:
            return classification.profit_loss_side

        head_side = _normalize_balance_side(getattr(head, "drcreffect", None) or getattr(head, "balanceType", None))
        if head_side == "debit":
            return "expense"
        if head_side == "credit":
            return "income"

        type_side = _normalize_balance_side(getattr(acc_type, "balanceType", None))
        if type_side == "debit":
            return "expense"
        if type_side == "credit":
            return "income"

        # Final fallback only when grouping metadata is incomplete.
        return "income" if amount < 0 else "expense"
    return "expense"


def _is_balance_sheet_classification(head, acc_type) -> bool:
    return classify_financial_head(head, acc_type).include_in_balance_sheet


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


def _closing_map(
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    posted_only=True,
    ledger_ids=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date)
    lines = journal_lines_for_scope(
        entity_id,
        entityfin_id,
        subentity_id,
        from_date,
        to_date,
        posted_only=posted_only,
    )
    selected_ledger_ids = [int(ledger_id) for ledger_id in (ledger_ids or []) if ledger_id is not None]
    if selected_ledger_ids:
        lines = lines.filter(resolved_ledger_id__in=selected_ledger_ids)
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
    posted_only=True,
    ledger_ids=None,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, closing = _closing_map(
        entity_id,
        entityfin_id,
        subentity_id,
        from_date,
        to_date,
        posted_only=posted_only,
        ledger_ids=ledger_ids,
    )

    rows = []
    excluded_rows = []
    search_text = (search or "").strip().lower()
    for item in closing.values():
        ledger = item["ledger"]
        amount = item["amount"]
        head, acc_type = _resolve_effective_head_and_type(ledger, amount)
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
            "classification_reason": getattr(classify_financial_head(head, acc_type), "reason", ""),
            **_ledger_drilldown_meta(ledger, entity_id, entityfin_id, subentity_id),
        }
        if not _is_balance_sheet_classification(head, acc_type):
            excluded_rows.append({**row, "excluded_reason": "not_balance_sheet_classification"})
            continue
        if not include_zero_balances and amount == 0:
            excluded_rows.append({**row, "excluded_reason": "zero_balance_filtered"})
            continue
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
                excluded_rows.append({**row, "excluded_reason": "search_filtered"})
                continue
        rows.append(row)

    return entity_id, entityfin_id, subentity_id, from_date, to_date, rows, excluded_rows


def _raw_profit_loss_rows(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    include_zero_balances=False,
    search=None,
    posted_only=True,
    ledger_ids=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date)
    lines = journal_lines_for_scope(
        entity_id,
        entityfin_id,
        subentity_id,
        from_date,
        to_date,
        posted_only=posted_only,
    )
    selected_ledger_ids = [int(ledger_id) for ledger_id in (ledger_ids or []) if ledger_id is not None]
    if selected_ledger_ids:
        lines = lines.filter(resolved_ledger_id__in=selected_ledger_ids)
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
        if not _is_profit_loss_classification(head, acc_type):
            continue
        if not include_zero_balances and net == 0:
            continue

        category = _profit_loss_category(head, acc_type, net)

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
            "category": category,
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



def _as_decimal(value):
    return Decimal(str(value or "0.00"))


def _profit_loss_policy(reporting_policy):
    base = FINANCIAL_REPORTING_POLICY_DEFAULTS.get("profit_loss", {})
    cfg = ((reporting_policy or {}).get("profit_loss") or {})

    disclosure_mode = str(cfg.get("accounting_only_notes_disclosure", base.get("accounting_only_notes_disclosure", "summary"))).strip().lower()
    if disclosure_mode not in {"off", "summary"}:
        disclosure_mode = "summary"

    split_mode = str(cfg.get("accounting_only_notes_split", base.get("accounting_only_notes_split", "purchase_sales"))).strip().lower()
    if split_mode not in {"combined", "purchase_sales"}:
        split_mode = "purchase_sales"

    return {
        "accounting_only_notes_disclosure": disclosure_mode,
        "accounting_only_notes_split": split_mode,
    }


def _profit_loss_percent(value, base):
    base_amount = Decimal(str(base or 0))
    if base_amount == 0:
        return Decimal("0.00")
    return (Decimal(str(value or 0)) / base_amount) * Decimal("100")


def _balance_sheet_policy(reporting_policy):
    base = FINANCIAL_REPORTING_POLICY_DEFAULTS.get("balance_sheet", {})
    cfg = ((reporting_policy or {}).get("balance_sheet") or {})
    return {
        "include_accounting_only_notes_disclosure": bool(
            cfg.get(
                "include_accounting_only_notes_disclosure",
                base.get("include_accounting_only_notes_disclosure", True),
            )
        )
    }


def _accounting_only_note_disclosure(
    *,
    entity_id,
    entityfin_id,
    subentity_id,
    from_date,
    to_date,
    split_mode,
):
    sales_filters = {
        "entity_id": entity_id,
        "status": SalesInvoiceHeader.Status.POSTED,
        "doc_type__in": [SalesInvoiceHeader.DocType.CREDIT_NOTE, SalesInvoiceHeader.DocType.DEBIT_NOTE],
        "affects_inventory": False,
    }
    purchase_filters = {
        "entity_id": entity_id,
        "status": PurchaseInvoiceHeader.Status.POSTED,
        "doc_type__in": [PurchaseInvoiceHeader.DocType.CREDIT_NOTE, PurchaseInvoiceHeader.DocType.DEBIT_NOTE],
        "affects_inventory": False,
    }

    if entityfin_id:
        sales_filters["entityfinid_id"] = entityfin_id
        purchase_filters["entityfinid_id"] = entityfin_id
    if subentity_id:
        sales_filters["subentity_id"] = subentity_id
        purchase_filters["subentity_id"] = subentity_id
    if from_date:
        sales_filters["bill_date__gte"] = from_date
        purchase_filters["bill_date__gte"] = from_date
    if to_date:
        sales_filters["bill_date__lte"] = to_date
        purchase_filters["bill_date__lte"] = to_date

    sales_qs = SalesInvoiceHeader.objects.filter(**sales_filters)
    purchase_qs = PurchaseInvoiceHeader.objects.filter(**purchase_filters)

    sales_stats = sales_qs.aggregate(
        credit_count=Count("id", filter=Q(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE)),
        credit_amount=Sum("total_taxable_value", filter=Q(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE), default=Decimal("0.00")),
        debit_count=Count("id", filter=Q(doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE)),
        debit_amount=Sum("total_taxable_value", filter=Q(doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE), default=Decimal("0.00")),
    )
    purchase_stats = purchase_qs.aggregate(
        credit_count=Count("id", filter=Q(doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE)),
        credit_amount=Sum("total_taxable", filter=Q(doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE), default=Decimal("0.00")),
        debit_count=Count("id", filter=Q(doc_type=PurchaseInvoiceHeader.DocType.DEBIT_NOTE)),
        debit_amount=Sum("total_taxable", filter=Q(doc_type=PurchaseInvoiceHeader.DocType.DEBIT_NOTE), default=Decimal("0.00")),
    )

    sales_credit_amount = _as_decimal(sales_stats.get("credit_amount"))
    sales_debit_amount = _as_decimal(sales_stats.get("debit_amount"))
    purchase_credit_amount = _as_decimal(purchase_stats.get("credit_amount"))
    purchase_debit_amount = _as_decimal(purchase_stats.get("debit_amount"))

    sales_credit_count = int(sales_stats.get("credit_count") or 0)
    sales_debit_count = int(sales_stats.get("debit_count") or 0)
    purchase_credit_count = int(purchase_stats.get("credit_count") or 0)
    purchase_debit_count = int(purchase_stats.get("debit_count") or 0)

    total_count = sales_credit_count + sales_debit_count + purchase_credit_count + purchase_debit_count
    total_amount = sales_credit_amount + sales_debit_amount + purchase_credit_amount + purchase_debit_amount

    # Profit impact estimate using taxable amount basis only:
    # + purchase CN (expense reduction), + sales DN (income increase),
    # - purchase DN (expense increase), - sales CN (income reduction).
    estimated_profit_impact = (
        purchase_credit_amount
        + sales_debit_amount
        - purchase_debit_amount
        - sales_credit_amount
    )

    breakdown = {
        "purchase": {
            "credit_notes": {"count": purchase_credit_count, "taxable_amount": f"{purchase_credit_amount:.2f}"},
            "debit_notes": {"count": purchase_debit_count, "taxable_amount": f"{purchase_debit_amount:.2f}"},
            "estimated_profit_impact": f"{(purchase_credit_amount - purchase_debit_amount):.2f}",
        },
        "sales": {
            "credit_notes": {"count": sales_credit_count, "taxable_amount": f"{sales_credit_amount:.2f}"},
            "debit_notes": {"count": sales_debit_count, "taxable_amount": f"{sales_debit_amount:.2f}"},
            "estimated_profit_impact": f"{(sales_debit_amount - sales_credit_amount):.2f}",
        },
    }

    if split_mode == "combined":
        breakdown = {
            "credit_notes": {
                "count": purchase_credit_count + sales_credit_count,
                "taxable_amount": f"{(purchase_credit_amount + sales_credit_amount):.2f}",
            },
            "debit_notes": {
                "count": purchase_debit_count + sales_debit_count,
                "taxable_amount": f"{(purchase_debit_amount + sales_debit_amount):.2f}",
            },
        }

    return {
        "code": "accounting_only_notes",
        "label": "Accounting-only CN/DN impact",
        "basis": "Posted purchase/sales credit-debit notes with affects_inventory=false",
        "amount_basis_field": "total_taxable",
        "split_mode": split_mode,
        "totals": {
            "count": total_count,
            "taxable_amount": f"{total_amount:.2f}",
            "estimated_profit_impact": f"{estimated_profit_impact:.2f}",
        },
        "breakdown": breakdown,
    }

def _iter_period_ranges(start_date, end_date, period_by):
    cursor = start_date
    while cursor <= end_date:
        if period_by == "month":
            period_end = _last_day_of_month(cursor)
        elif period_by == "quarter":
            period_end = _last_day_of_month(_add_months(cursor, 2))
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
    posted_only,
    ledger_ids,
    view_type,
    include_pagination=True,
    reporting_policy=None,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, rows = _raw_profit_loss_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        include_zero_balances=include_zero_balances,
        search=search,
        posted_only=posted_only,
        ledger_ids=ledger_ids,
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    income_source = [row for row in rows if row["category"] == "income"]
    expense_source = [row for row in rows if row["category"] == "expense"]
    total_income = sum((row["amount_decimal"] for row in income_source), Decimal("0.00"))
    total_expense = sum((row["amount_decimal"] for row in expense_source), Decimal("0.00"))

    from reports.services.trading_account import build_trading_account_dynamic

    trading_snapshot = build_trading_account_dynamic(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        startdate=from_date.isoformat(),
        enddate=to_date.isoformat(),
        valuation_method=stock_valuation_method,
        level="head",
        inventory_breakdown=False,
    )
    gross_profit = Decimal(str(trading_snapshot.get("gross_profit", 0) or 0))
    gross_loss = Decimal(str(trading_snapshot.get("gross_loss", 0) or 0))
    opening_inventory = Decimal(str(trading_snapshot.get("opening_stock", 0) or 0))
    closing_inventory = Decimal(str(trading_snapshot.get("closing_stock", 0) or 0))

    # Trading Account carries opening stock, purchases, direct expenses, sales, and closing stock.
    # Only the resulting gross profit/loss flows into Profit & Loss.
    if gross_profit > 0:
        income_source.append(
            {
                "ledger_id": None,
                "ledger_code": None,
                "ledger_name": "Gross Profit b/d",
                "accounthead_id": None,
                "accounthead_name": "Trading Account",
                "accounttype_id": None,
                "accounttype_name": "Gross Profit",
                "debit": "0.00",
                "credit": f"{gross_profit:.2f}",
                "amount_decimal": gross_profit,
                "amount": f"{gross_profit:.2f}",
                "category": "income",
                "can_drilldown": False,
                "drilldown_target": None,
                "drilldown_params": None,
            }
        )
    elif gross_loss > 0:
        expense_source.append(
            {
                "ledger_id": None,
                "ledger_code": None,
                "ledger_name": "Gross Loss b/d",
                "accounthead_id": None,
                "accounthead_name": "Trading Account",
                "accounttype_id": None,
                "accounttype_name": "Gross Loss",
                "debit": f"{gross_loss:.2f}",
                "credit": "0.00",
                "amount_decimal": gross_loss,
                "amount": f"{gross_loss:.2f}",
                "category": "expense",
                "can_drilldown": False,
                "drilldown_target": None,
                "drilldown_params": None,
            }
        )

    adjusted_income = total_income + gross_profit
    adjusted_expense = total_expense + gross_loss
    net_profit = adjusted_income - adjusted_expense
    gross_result = gross_profit - gross_loss
    gross_margin_percent = _profit_loss_percent(gross_result, adjusted_income)
    net_margin_percent = _profit_loss_percent(net_profit, adjusted_income)
    expense_ratio_percent = _profit_loss_percent(adjusted_expense, adjusted_income)

    pl_policy = _profit_loss_policy(reporting_policy)
    accounting_only_notes = None
    if pl_policy["accounting_only_notes_disclosure"] == "summary":
        accounting_only_notes = _accounting_only_note_disclosure(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=from_date,
            to_date=to_date,
            split_mode=pl_policy["accounting_only_notes_split"],
        )

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
            "stock_adjustment": "0.00",
        },
        "summary": {
            "income_rows": income_count,
            "expense_rows": expense_count,
            "opening_inventory_valuation": f"{opening_inventory:.2f}",
            "closing_inventory_valuation": f"{closing_inventory:.2f}",
            "gross_result": f"{gross_result:.2f}",
            "gross_margin_percent": f"{gross_margin_percent:.2f}",
            "net_margin_percent": f"{net_margin_percent:.2f}",
            "expense_ratio_percent": f"{expense_ratio_percent:.2f}",
            "accounting_only_notes_count": (accounting_only_notes or {}).get("totals", {}).get("count", 0),
            "accounting_only_notes_taxable_amount": (accounting_only_notes or {}).get("totals", {}).get("taxable_amount", "0.00"),
            "accounting_only_notes_estimated_profit_impact": (accounting_only_notes or {}).get("totals", {}).get("estimated_profit_impact", "0.00"),
            "gross_profit_from_trading": f"{gross_profit:.2f}",
            "gross_loss_from_trading": f"{gross_loss:.2f}",
            "profit_note": "Net profit includes gross result brought down from Trading Account plus indirect income/expenses.",
        },
        "stock_valuation": {
            "requested_mode": stock_valuation_mode,
            "effective_mode": "trading_account",
            "valuation_method": stock_valuation_method,
            "valuation_available": True,
            "opening_inventory": f"{opening_inventory:.2f}",
            "closing_inventory": f"{closing_inventory:.2f}",
            "inventory_delta": f"{(closing_inventory - opening_inventory):.2f}",
            "gl_inventory_total": "0.00",
            "notes": [
                "Opening and closing inventory are handled in Trading Account.",
                "Profit & Loss receives only Gross Profit/Gross Loss brought down from Trading.",
            ],
        },
    }
    if accounting_only_notes:
        snapshot["disclosures"] = [accounting_only_notes]

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
    view_type="summary",
    posted_only=True,
    hide_zero_rows=True,
    account_group=None,
    ledger_ids=None,
    reporting_policy=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date, as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    view_type = (view_type or "summary").strip().lower()
    if view_type not in {"summary", "detailed"}:
        view_type = "summary"

    if account_group:
        group_by = account_group
    elif not group_by:
        group_by = "ledger" if view_type == "detailed" else "accounthead"

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
        include_zero_balances=include_zero_balances and not hide_zero_rows,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        stock_valuation_mode=stock_valuation_mode,
        stock_valuation_method=stock_valuation_method,
        posted_only=posted_only,
        ledger_ids=ledger_ids,
        view_type=view_type,
        include_pagination=True,
        reporting_policy=reporting_policy,
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
            "view_type": view_type,
            "account_group": group_by,
            "ledger_ids": list(ledger_ids) if ledger_ids else None,
            "posted_only": bool(posted_only),
            "hide_zero_rows": not bool(include_zero_balances),
            "stock_valuation_mode": stock_valuation_mode,
            "stock_valuation_method": stock_valuation_method,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search": search,
            "applied_policy": {
                "profit_loss": _profit_loss_policy(reporting_policy),
            },
            "net_profit_basis": "book_profit",
            "accounting_only_notes_included_in_net_profit": True,
        },
    }

    if period_by and from_date and to_date and from_date <= to_date:
        periods = []
        period_meta = []
        income_period_maps = []
        expense_period_maps = []
        for index, (period_start, period_end) in enumerate(_iter_period_ranges(from_date, to_date, period_by), start=1):
            period_snapshot = _build_profit_loss_snapshot(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=period_start,
                to_date=period_end,
                group_by=group_by,
                include_zero_balances=include_zero_balances and not hide_zero_rows,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order,
                page=1,
                page_size=page_size,
                stock_valuation_mode=stock_valuation_mode,
                stock_valuation_method=stock_valuation_method,
                posted_only=posted_only,
                ledger_ids=ledger_ids,
                view_type=view_type,
                include_pagination=False,
                reporting_policy=reporting_policy,
            )
            period_snapshot["period_key"] = (
                f"Q{index}"
                if period_by == "quarter"
                else period_end.strftime("%Y")
                if period_by == "year"
                else period_end.strftime("%Y-%m")
            )
            period_snapshot["period_label"] = (
                f"Q{index}"
                if period_by == "quarter"
                else period_end.strftime("%Y")
                if period_by == "year"
                else period_end.strftime("%b %Y")
            )
            period_meta.append(
                {
                    "period_key": period_snapshot["period_key"],
                    "period_label": period_snapshot["period_label"],
                }
            )
            income_period_maps.append(
                _build_profit_loss_period_map(
                    period_snapshot["income"],
                    group_by,
                    period_snapshot["period_key"],
                    period_snapshot["period_label"],
                )
            )
            expense_period_maps.append(
                _build_profit_loss_period_map(
                    period_snapshot["expenses"],
                    group_by,
                    period_snapshot["period_key"],
                    period_snapshot["period_label"],
                )
            )
            periods.append(period_snapshot)
        _attach_profit_loss_period_rows(snapshot["income"], income_period_maps, period_meta, group_by)
        _attach_profit_loss_period_rows(snapshot["expenses"], expense_period_maps, period_meta, group_by)
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


def _profit_loss_row_identity(row, group_by):
    group_id = row.get("group_id")
    if group_id is not None:
        return f"group:{group_by}:{group_id}"

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


def _build_profit_loss_period_map(rows, group_by, period_key, period_label):
    period_map = {}
    for row in rows:
        row_id = _profit_loss_row_identity(row, group_by)
        period_map[row_id] = {
            "key": period_key,
            "label": period_label,
            "code": period_key,
            "name": period_label,
            "title": period_label,
            "amount": row.get("amount", "0.00"),
            "value": row.get("amount", "0.00"),
        }
        if row.get("children"):
            period_map.update(_build_profit_loss_period_map(row["children"], group_by, period_key, period_label))
    return period_map


def _attach_profit_loss_period_rows(rows, period_maps, period_meta, group_by):
    for row in rows:
        row_id = _profit_loss_row_identity(row, group_by)
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
                    "amount": "0.00",
                    "value": "0.00",
                }
            row["periods"].append(period_values)
        if row.get("children"):
            _attach_profit_loss_period_rows(row["children"], period_maps, period_meta, group_by)


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


def _stock_context(*, entity_id, entityfin_id=None, subentity_id=None, from_date, to_date, assets_source, requested_mode, valuation_method):
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
            closing_inventory = Decimal(str(_inventory_value_asof(entity_id, to_date, method, entityfin_id=entityfin_id, subentity_id=subentity_id)))
            valuation_available = True
            if from_date:
                opening_inventory = Decimal(str(_inventory_value_asof(entity_id, from_date - timedelta(days=1), method, entityfin_id=entityfin_id, subentity_id=subentity_id)))
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
    posted_only,
    ledger_ids,
    include_pagination=True,
    reporting_policy=None,
):
    entity_id, entityfin_id, subentity_id, from_date, to_date, rows, excluded_rows = _raw_balance_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        include_zero_balances=include_zero_balances,
        search=search,
        posted_only=posted_only,
        ledger_ids=ledger_ids,
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    assets_source = [row for row in rows if row["bucket"] == "asset"]
    liabilities_source = [row for row in rows if row["bucket"] == "liability"]

    stock_context = _stock_context(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
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
    raw_asset_total = asset_total
    raw_liability_total = liability_total

    pnl = build_profit_and_loss(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        stock_valuation_mode=stock_valuation_mode,
        stock_valuation_method=stock_valuation_method,
        reporting_policy=reporting_policy,
    )
    net_profit = Decimal(pnl["totals"]["net_profit"])
    raw_income = Decimal(pnl["totals"].get("raw_income", pnl["totals"]["income"]))
    bs_policy = _balance_sheet_policy(reporting_policy)
    pnl_disclosures = list(pnl.get("disclosures") or [])
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
        "diagnostics": {
            "raw_asset_total": f"{raw_asset_total:.2f}",
            "raw_liability_total": f"{raw_liability_total:.2f}",
            "net_profit_adjustment": f"{net_profit:.2f}",
            "final_asset_total": f"{asset_total:.2f}",
            "final_liability_total": f"{liability_total:.2f}",
            "difference": f"{(asset_total - liability_total):.2f}",
            "stock_effective_mode": stock_context["effective_mode"],
            "stock_valuation_method": stock_context["valuation_method"],
            "inventory_gl_total": f"{stock_context['gl_inventory_total']:.2f}",
            "inventory_delta": f"{stock_context['inventory_delta']:.2f}",
            "raw_rows": [
                {
                    "side": "asset" if row in assets_source else "liability",
                    "ledger_id": row.get("ledger_id"),
                    "ledger_name": row.get("ledger_name"),
                    "ledger_code": row.get("ledger_code"),
                    "amount": row.get("amount"),
                    "bucket": row.get("bucket"),
                    "accounthead_name": row.get("accounthead_name"),
                    "accounttype_name": row.get("accounttype_name"),
                    "classification_reason": row.get("classification_reason"),
                }
                for row in (assets_source + liabilities_source)
            ],
            "excluded_rows": [
                {
                    "ledger_id": row.get("ledger_id"),
                    "ledger_name": row.get("ledger_name"),
                    "ledger_code": row.get("ledger_code"),
                    "amount": row.get("amount"),
                    "bucket": row.get("bucket"),
                    "accounthead_name": row.get("accounthead_name"),
                    "accounttype_name": row.get("accounttype_name"),
                    "classification_reason": row.get("classification_reason"),
                    "excluded_reason": row.get("excluded_reason"),
                }
                for row in excluded_rows
            ],
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
    if bs_policy.get("include_accounting_only_notes_disclosure") and pnl_disclosures:
        snapshot["disclosures"] = pnl_disclosures
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


def _add_months(d, months):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, _last_day_of_month(date(year, month, 1)).day)
    return date(year, month, day)


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
            period_end = _last_day_of_month(_add_months(cursor, 2))
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
    view_type="summary",
    posted_only=True,
    hide_zero_rows=True,
    include_zero_balances=False,
    account_group=None,
    ledger_ids=None,
    search=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
    period_by=None,
    stock_valuation_mode="auto",
    stock_valuation_method="fifo",
    reporting_policy=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = _resolve_balance_sheet_window(entityfin_id, from_date, to_date, as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    view_type = (view_type or "summary").strip().lower()
    if view_type not in {"summary", "detailed"}:
        view_type = "summary"

    if account_group:
        group_by = account_group
    elif not group_by:
        group_by = "ledger" if view_type == "detailed" else "accounthead"

    group_by = (group_by or "ledger").strip().lower()
    if group_by not in GROUP_BY_CHOICES:
        group_by = "ledger" if view_type == "detailed" else "accounthead"

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
    include_zero_balances = bool(include_zero_balances) and not bool(hide_zero_rows)

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
        posted_only=posted_only,
        ledger_ids=ledger_ids,
        include_pagination=True,
        reporting_policy=reporting_policy,
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
            "view_type": view_type,
            "account_group": account_group or group_by,
            "ledger_ids": list(ledger_ids) if ledger_ids else None,
            "posted_only": bool(posted_only),
            "hide_zero_rows": bool(hide_zero_rows),
            "stock_valuation_mode": stock_valuation_mode,
            "stock_valuation_method": stock_valuation_method,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "search": search,
            "applied_policy": {
                "balance_sheet": _balance_sheet_policy(reporting_policy),
            },
            "net_profit_source": "profit_loss.book_profit",
        },
    }

    if period_by and from_date and to_date and from_date <= to_date:
        periods = []
        period_meta = []
        asset_period_maps = []
        liability_period_maps = []
        for index, period_end in enumerate(_iter_period_ends(from_date, to_date, period_by), start=1):
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
                posted_only=posted_only,
                ledger_ids=ledger_ids,
                include_pagination=False,
                reporting_policy=reporting_policy,
            )
            period_snapshot["period_key"] = (
                f"Q{index}"
                if period_by == "quarter"
                else period_end.strftime("%Y")
                if period_by == "year"
                else period_end.strftime("%Y-%m")
            )
            period_snapshot["period_label"] = (
                f"Q{index}"
                if period_by == "quarter"
                else period_end.strftime("%Y")
                if period_by == "year"
                else period_end.strftime("%b %Y")
            )
            period_meta.append(
                {
                    "period_key": period_snapshot["period_key"],
                    "period_label": period_snapshot["period_label"],
                }
            )
            asset_period_maps.append(
                _build_profit_loss_period_map(
                    period_snapshot["assets"],
                    group_by,
                    period_snapshot["period_key"],
                    period_snapshot["period_label"],
                )
            )
            liability_period_maps.append(
                _build_profit_loss_period_map(
                    period_snapshot["liabilities_and_equity"],
                    group_by,
                    period_snapshot["period_key"],
                    period_snapshot["period_label"],
                )
            )
            periods.append(period_snapshot)
        _attach_profit_loss_period_rows(snapshot["assets"], asset_period_maps, period_meta, group_by)
        _attach_profit_loss_period_rows(snapshot["liabilities_and_equity"], liability_period_maps, period_meta, group_by)
        response["periods"] = periods

    return response
