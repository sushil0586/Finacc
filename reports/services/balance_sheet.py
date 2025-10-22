# services/balance_sheet.py
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple

from django.db.models import (
    F, Sum, Case, When, Value as V, DecimalField,
    Subquery, OuterRef
)

# Adjust app labels if needed
from invoice.models import JournalLine, InventoryMove
from .trading_account import STRATEGIES  # valuation methods registry
from .profit_and_loss import build_profit_and_loss_statement  # to get current earnings


# --------------------------- Helpers ---------------------------

def Q2(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _in_rate(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / Decimal(str(qty))
    return Decimal('0')

def _nest_under_accounthead(rows: list, *, head_field: str = "_head") -> list:
    """
    Convert flat account rows into parent Account Head nodes with children and subtotals.
    Each row must include rows[i][head_field] which holds the head name.
    """
    from collections import OrderedDict
    groups = OrderedDict()
    for r in rows:
        head = r.get(head_field) or "Unknown Head"
        amt = Decimal(str(r.get("amount", 0)))
        if head not in groups:
            groups[head] = {"label": head, "amount": Decimal('0'), "children": []}
        groups[head]["amount"] += amt
        child = dict(r)
        child.pop(head_field, None)
        groups[head]["children"].append(child)

    out = []
    for head, blob in groups.items():
        blob["amount"] = float(Q2(blob["amount"]))
        blob["children"].sort(key=lambda x: x["amount"], reverse=True)
        out.append(blob)
    out.sort(key=lambda x: x["amount"], reverse=True)
    return out


# --------------------------- Inventory valuation at date ---------------------------

def _inventory_value_asof(entity_id: int, enddate, method: str) -> Decimal:
    """
    Point-in-time inventory valuation as of enddate using the chosen method.
    Reuse STRATEGIES but feed start=end so we only care about closing value.
    """
    method = (method or "fifo").lower()
    strat = STRATEGIES.get(method, STRATEGIES["fifo"])
    opening, _cogs, closing = strat(entity_id, enddate, enddate)
    return closing  # already Q2'd in strategies


# --------------------------- Labels ---------------------------

def _build_label(level: str, row: dict) -> str:
    if level == 'head':
        return row.get('accounthead__name') or f"Head {row.get('accounthead_id')}"
    if level == 'account':
        nm = row.get('account__accountname') or f"Account {row.get('account_id')}"
        hd = row.get('accounthead__name')
        return f"{nm} ({hd})" if hd else nm
    if level == 'voucher':
        vt = row.get('transactiontype') or "TXN"
        vid = row.get('transactionid')
        vno = row.get('voucherno')
        return vno or f"{vt}#{vid}"
    if level == 'product':
        # Only meaningful when inventory breakdown is enabled; else fallback text
        return row.get('product__name') or "Unmapped Product"
    return row.get('accounthead__name') or "Row"


# --------------------------- GL aggregation ---------------------------

def _aggregate_balance_sheet_gl(
    *,
    entity_id: int,
    end,
    level: str,
    bs_detailsingroup_values: tuple = (3,),
) -> Tuple[List[Dict], List[Dict], Decimal, Decimal]:
    """
    Aggregate JournalLine cumulatively up to 'end' for BS heads (detailsingroup in (3,)).
    Debit (Dr) balances → Assets; Credit (Cr) balances → Liabilities/Equity.
    """
    base = JournalLine.objects.filter(
        entity_id=entity_id,
        entrydate__lte=end,
        accounthead__detailsingroup__in=bs_detailsingroup_values
    )

    # Grouping by level
    if level == 'head':
        qs = base.values('accounthead_id', 'accounthead__name')
    elif level == 'account':
        qs = base.values('accounthead_id', 'accounthead__name', 'account_id', 'account__accountname')
    elif level == 'voucher':
        qs = base.values('accounthead_id', 'accounthead__name', 'transactiontype', 'transactionid', 'voucherno')
    elif level == 'product':
        # For BS we typically don't aggregate by product, except inventory breakdown.
        prod_id_sub = Subquery(
            InventoryMove.objects.filter(
                entity_id=entity_id,
                transactiontype=OuterRef('transactiontype'),
                transactionid=OuterRef('transactionid'),
                detailid=OuterRef('detailid')
            ).values('product_id')[:1]
        )
        prod_name_sub = Subquery(
            InventoryMove.objects.filter(
                entity_id=entity_id,
                transactiontype=OuterRef('transactiontype'),
                transactionid=OuterRef('transactionid'),
                detailid=OuterRef('detailid')
            ).values('product__name')[:1]
        )
        qs = base.annotate(product_id=prod_id_sub, product__name=prod_name_sub)\
                 .values('product_id', 'product__name')
    else:
        qs = base.values('accounthead_id', 'accounthead__name')
        level = 'head'

    agg = qs.annotate(
        debits=Sum(Case(When(drcr=True, then=F('amount')),
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2))),
        credits=Sum(Case(When(drcr=False, then=F('amount')),
                         default=V(0),
                         output_field=DecimalField(max_digits=18, decimal_places=2))),
    )

    assets_rows: List[Dict] = []
    liab_rows: List[Dict] = []
    total_assets = Decimal('0')
    total_liab   = Decimal('0')

    for row in agg:
        net = (row['debits'] or Decimal('0')) - (row['credits'] or Decimal('0'))

        if level == 'account':
            head_name = row.get('accounthead__name') or f"Head {row.get('accounthead_id')}"
            account_label = row.get('account__accountname') or f"Account {row.get('account_id')}"
            label = account_label
        else:
            head_name = None
            label = _build_label(level, row)

        if net > 0:  # Dr balance → Asset
            amt = Q2(net)
            item = {"label": label, "amount": float(amt)}
            if level == 'account':
                item["_head"] = head_name
            assets_rows.append(item)
            total_assets += amt
        elif net < 0:  # Cr balance → Liability/Equity
            amt = Q2(-net)
            item = {"label": label, "amount": float(amt)}
            if level == 'account':
                item["_head"] = head_name
            liab_rows.append(item)
            total_liab += amt

    # Nest accounts under their heads with head subtotals (when requested)
    if level == 'account':
        assets_rows = _nest_under_accounthead(assets_rows)
        liab_rows   = _nest_under_accounthead(liab_rows)

    return assets_rows, liab_rows, total_assets, total_liab


# --------------------------- Builder ---------------------------

def build_balance_sheet_statement(
    *,
    entity_id: int,
    startdate: str,                        # for current period P&L (earnings)
    enddate: str,                          # as-of date for the Balance Sheet
    level: str = 'head',                   # head | account | voucher | product (limited)
    bs_detailsingroup_values: tuple = (3,),  # <<< Balance Sheet heads
    pl_detailsingroup_values: tuple = (2,),  # used to compute current earnings via P&L
    trading_detailsingroup_values: tuple = (1,),  # trading heads (for P&L)
    include_current_earnings: bool = True,
    inventory_source: str = "valuation",   # "valuation" | "gl"
    valuation_method: str = "fifo",        # used when inventory_source="valuation"
    inventory_label: str = "Inventory (Closing Stock)"
):
    """
    Balance Sheet as of 'enddate':
      - Aggregates JournalLine balances for BS heads (detailsingroup in bs_detailsingroup_values).
      - Optionally replaces/overrides GL stock with valuation-based closing stock.
      - Brings current period Net Profit/Loss from P&L into Equity (liab side if profit, asset side if loss).
      - Returns balanced Assets and Liabilities+Equity.
    """
    start = datetime.strptime(startdate, '%Y-%m-%d').date()
    end   = datetime.strptime(enddate,   '%Y-%m-%d').date()

    # 1) GL aggregation up to 'end'
    assets_rows, liab_rows, total_assets, total_liab = _aggregate_balance_sheet_gl(
        entity_id=entity_id, end=end, level=level, bs_detailsingroup_values=bs_detailsingroup_values
    )

    notes = [
        f"Balance Sheet heads selected via accounthead.detailsingroup ∈ {list(bs_detailsingroup_values)}.",
        "Balances are cumulative up to the 'end' date (as-of statement)."
    ]

    # 2) Inventory valuation override (optional)
    if inventory_source.lower() == "valuation":
        closing_inv = _inventory_value_asof(entity_id, end, valuation_method)
        # Add valuation as a separate asset line (you can choose to adjust/replace GL stock externally)
        assets_rows.append({"label": inventory_label, "amount": float(closing_inv)})
        total_assets += closing_inv
        notes.append(f"Inventory valued via '{valuation_method}' strategy as of {end}.")
    else:
        notes.append("Inventory taken from GL balances (no valuation override).")

    # 3) Current period earnings (via P&L) → Equity
    net_profit = Decimal('0')
    net_loss   = Decimal('0')
    if include_current_earnings:
        pl = build_profit_and_loss_statement(
            entity_id=entity_id,
            startdate=startdate,
            enddate=enddate,
            level='head',
            pl_detailsingroup_values=pl_detailsingroup_values,
            trading_detailsingroup_values=trading_detailsingroup_values,
            valuation_method=valuation_method
        )
        net_profit = Q2(pl.get('net_profit', 0) or 0)
        net_loss   = Q2(pl.get('net_loss', 0) or 0)

        if net_profit > 0:
            liab_rows.append({"label": "Current Period Profit", "amount": float(net_profit)})
            total_liab += net_profit
        elif net_loss > 0:
            assets_rows.append({"label": "Current Period Loss", "amount": float(net_loss)})
            total_assets += net_loss

        notes.append("Current period earnings brought from P&L (profit to equity; loss to assets).")

    # 4) Final totals
    total_assets  = Q2(total_assets)
    total_liab    = Q2(total_liab)

    return {
        "as_of": str(end),
        "period": {"start": str(start), "end": str(end)},
        "entity_id": entity_id,
        "params": {
            "level": level,
            "bs_detailsingroup_values": list(bs_detailsingroup_values),
            "pl_detailsingroup_values": list(pl_detailsingroup_values),
            "trading_detailsingroup_values": list(trading_detailsingroup_values),
            "include_current_earnings": bool(include_current_earnings),
            "inventory_source": inventory_source,
            "valuation_method": valuation_method
        },
        "assets_total": float(total_assets),
        "liabilities_total": float(total_liab),
        "assets_rows": assets_rows,
        "liabilities_rows": liab_rows,
        "notes": notes
    }
