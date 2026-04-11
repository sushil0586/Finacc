# services/balance_sheet.py
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple, Optional

from django.db.models import (
    Q, F, Sum, Case, When, Value as V, DecimalField,
    Subquery, OuterRef
)

from catalog.models import Product
from posting.models import InventoryMove, JournalLine
from .trading_account import STRATEGIES, inventory_breakdown_asof, inventory_value_asof
from .profit_and_loss import build_profit_and_loss_statement  # for prior & current earnings


# --------------------------- Helpers ---------------------------

def Q2(x) -> Decimal:
    q = Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return q if q != Decimal("-0.00") else Decimal("0.00")


def _rate_from_move(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / abs(Decimal(str(qty)))
    return Decimal('0')


def _signed_move_qty(move) -> Decimal:
    qty = Decimal(str(move.get("base_qty") if move.get("base_qty") is not None else move.get("qty") or 0))
    move_type = str(move.get("move_type") or "").upper()
    if move_type == "OUT":
        return -abs(qty)
    if move_type == "IN":
        return abs(qty)
    return qty


def _nest_under_accounthead(rows: list, *, head_field: str = "_head") -> list:
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


# --------------------------- Inventory valuation helpers ---------------------------

def _inventory_value_asof(entity_id: int, enddate, method: str, entityfin_id=None, subentity_id=None) -> Decimal:
    return inventory_value_asof(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        enddate=enddate,
        method=method,
    )


def _inventory_breakdown_asof(
    *,
    entity_id: int,
    enddate,
    method: str = "fifo",
    product_ids: Optional[List[int]] = None,
    include_zero: bool = False,
) -> Tuple[List[Dict], Decimal, Decimal]:
    return inventory_breakdown_asof(
        entity_id=entity_id,
        enddate=enddate,
        method=method,
        product_ids=product_ids,
        include_zero=include_zero,
    )


# --------------------------- Labels ---------------------------

def _build_label(level: str, row: dict) -> str:
    if level == 'head':
        return row.get('accounthead__name') or f"Head {row.get('accounthead_id')}"
    if level == 'account':
        nm = row.get('account__accountname') or f"Account {row.get('account_id')}"
        hd = row.get('accounthead__name')
        return f"{nm} ({hd})" if hd else nm
    if level == 'voucher':
        vt = row.get('txn_type') or "TXN"
        vid = row.get('txn_id')
        vno = row.get('voucher_no')
        return vno or f"{vt}#{vid}"
    if level == 'product':
        # align with Product.productname
        return row.get('product__productname') or "Unmapped Product"
    return row.get('accounthead__name') or "Row"


# --------------------------- GL aggregation (CONSISTENT) ---------------------------

def _aggregate_balance_sheet_gl(
    *,
    entity_id: int,
    end,
    level: str,
    bs_detailsingroup_values: tuple = (3,),
    exclude_head_ids: Optional[set] = None,
) -> Tuple[List[Dict], List[Dict], Decimal, Decimal]:
    """
    Consistent aggregation across levels:
    - Compute signed net per group row.
    - For levels with children (account/voucher/product): group by HEAD first,
      sum signed children to a head total, then place the HEAD on its side.
    - For level='head': simply place heads by sign.
    """
    base = JournalLine.objects.filter(
        entity_id=entity_id,
        posting_date__lte=end,
        accounthead__detailsingroup__in=bs_detailsingroup_values
    )
    if exclude_head_ids:
        base = base.exclude(accounthead_id__in=list(exclude_head_ids))

    # Choose group fields + label builder
    if level == 'head':
        qs = base.values('accounthead_id', 'accounthead__name')
        label_build = lambda r: (r.get('accounthead__name') or f"Head {r.get('accounthead_id')}")
    elif level == 'account':
        qs = base.values('accounthead_id', 'accounthead__name', 'account_id', 'account__accountname')
        label_build = lambda r: (r.get('account__accountname') or f"Account {r.get('account_id')}")
    elif level == 'voucher':
        qs = base.values('accounthead_id', 'accounthead__name', 'txn_type', 'txn_id', 'voucher_no')
        label_build = lambda r: (r.get('voucher_no') or f"{r.get('txn_type') or 'TXN'}#{r.get('txn_id')}")
    elif level == 'product':
        # Subqueries aligned with your InventoryMove linkage and Product.productname
        prod_id_sub = Subquery(
            InventoryMove.objects.filter(
                entity_id=entity_id,
                txn_type=OuterRef('txn_type'),
                txn_id=OuterRef('txn_id'),
                detail_id=OuterRef('detail_id')
            ).values('product_id')[:1]
        )
        prod_name_sub = Subquery(
            InventoryMove.objects.filter(
                entity_id=entity_id,
                txn_type=OuterRef('txn_type'),
                txn_id=OuterRef('txn_id'),
                detail_id=OuterRef('detail_id')
            ).values('product__productname')[:1]
        )
        qs = (base.annotate(product_id=prod_id_sub, product__productname=prod_name_sub)
                  .values('accounthead_id', 'accounthead__name', 'product_id', 'product__productname'))
        label_build = lambda r: (r.get('product__productname') or f"Product {r.get('product_id')}")
    else:
        # default to head
        qs = base.values('accounthead_id', 'accounthead__name')
        label_build = lambda r: (r.get('accounthead__name') or f"Head {r.get('accounthead_id')}")
        level = 'head'

    agg = qs.annotate(
        debits=Sum(Case(When(drcr=True, then=F('amount')), default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2))),
        credits=Sum(Case(When(drcr=False, then=F('amount')), default=V(0),
                         output_field=DecimalField(max_digits=18, decimal_places=2))),
    )

    # Signed rows
    signed_rows = []
    for r in agg:
        net = (r['debits'] or Decimal('0')) - (r['credits'] or Decimal('0'))
        if net == 0:
            continue
        signed_rows.append({
            "_head_id": r.get('accounthead_id'),
            "_head": r.get('accounthead__name') or f"Head {r.get('accounthead_id')}",
            "label": label_build(r),
            "net": Q2(net),  # signed
        })

    # With-children levels: group by head first
    if level in ('account', 'voucher', 'product'):
        from collections import OrderedDict
        heads = OrderedDict()  # head_id -> {label, amount (signed), children:[{label, amount(signed)}]}
        for row in signed_rows:
            hid = row["_head_id"]
            if hid not in heads:
                heads[hid] = {"label": row["_head"], "amount": Decimal('0'), "children": []}
            heads[hid]["amount"] += row["net"]
            heads[hid]["children"].append({"label": row["label"], "amount": float(Q2(row["net"]))})  # signed

        assets_rows, liab_rows = [], []
        total_assets = Decimal('0'); total_liab = Decimal('0')

        for h in heads.values():
            head_amt = Q2(h["amount"])
            h_out = {
                "label": h["label"],
                "amount": float(Q2(abs(head_amt))),  # parent displayed as absolute on its side
                "children": sorted(h["children"], key=lambda x: x["amount"], reverse=True)
            }
            if head_amt > 0:
                assets_rows.append(h_out)
                total_assets += head_amt
            else:
                liab_rows.append(h_out)
                total_liab += (-head_amt)

        assets_rows.sort(key=lambda x: x["amount"], reverse=True)
        liab_rows.sort(key=lambda x: x["amount"], reverse=True)
        return assets_rows, liab_rows, Q2(total_assets), Q2(total_liab)

    # level='head': just place heads by sign
    assets_rows, liab_rows = [], []
    total_assets = Decimal('0'); total_liab = Decimal('0')

    for row in signed_rows:
        if row["net"] > 0:
            assets_rows.append({"label": row["_head"], "amount": float(Q2(row["net"]))})
            total_assets += row["net"]
        else:
            liab_rows.append({"label": row["_head"], "amount": float(Q2(-row["net"]))})
            total_liab += (-row["net"])

    assets_rows.sort(key=lambda x: x["amount"], reverse=True)
    liab_rows.sort(key=lambda x: x["amount"], reverse=True)

    return assets_rows, liab_rows, Q2(total_assets), Q2(total_liab)


# --------------------------- Builder ---------------------------

def build_balance_sheet_statement(
    *,
    entity_id: int,
    startdate: str,
    enddate: str,
    level: str = 'head',
    bs_detailsingroup_values: tuple = (3,),
    pl_detailsingroup_values: tuple = (2,),
    trading_detailsingroup_values: tuple = (1,),
    include_current_earnings: bool = True,
    inventory_source: str = "valuation",
    valuation_method: str = "fifo",
    inventory_label: str = "Inventory (Closing Stock)",
    inventory_breakdown: bool = True,
    inventory_include_zero: bool = False,
    inventory_product_ids: Optional[List[int]] = None,
    inventory_replace_gl: bool = True,          # reserved for future: exclude GL stock heads if needed
    inventory_gl_head_ids: tuple = (),
    include_prior_earnings: bool = True,
    prior_earnings_label: str = "Retained Earnings",
):
    start = datetime.strptime(startdate, '%Y-%m-%d').date()
    end   = datetime.strptime(enddate,   '%Y-%m-%d').date()
    opening_asof = start - timedelta(days=1)

    # If you keep stock heads in GL, you can exclude them here to avoid double counting
    exclude_heads: set = set(inventory_gl_head_ids or ())

    # 1) GL closing aggregation (now consistent across levels)
    assets_rows, liab_rows, total_assets, total_liab = _aggregate_balance_sheet_gl(
        entity_id=entity_id, end=end, level=level,
        bs_detailsingroup_values=bs_detailsingroup_values,
        exclude_head_ids=exclude_heads or None
    )

    notes = [
        f"Balance Sheet heads selected via accounthead.detailsingroup ∈ {list(bs_detailsingroup_values)}.",
        "Balances are cumulative up to the 'end' date (as-of statement)."
    ]

    # 2) Inject valuation-based inventory (and optional product drilldown)
    inv_item = None
    if inventory_source.lower() == "valuation":
        closing_inv = _inventory_value_asof(entity_id, end, valuation_method)
        inv_item = {"label": inventory_label, "amount": float(Q2(closing_inv))}
        assets_rows.append(inv_item)
        total_assets += Q2(closing_inv)
        notes.append(f"Inventory valued via '{valuation_method}' strategy as of {end}.")
    else:
        notes.append("Inventory taken from GL balances (no valuation override).")

    if inventory_breakdown:
        details_method = valuation_method if inventory_source.lower() == "valuation" else "mwa"
        detail_rows, _detail_qty, detail_val = _inventory_breakdown_asof(
            entity_id=entity_id,
            enddate=end,
            method=details_method,
            product_ids=inventory_product_ids,
            include_zero=inventory_include_zero,
        )
        if inv_item is None:
            inv_item = {"label": inventory_label, "amount": float(Q2(detail_val))}
            assets_rows.append(inv_item)
            total_assets += Q2(detail_val)

        inv_children = [{
            "label": r["product_name"],
            "qty": r["qty"],
            "amount": r["value"],
        } for r in detail_rows]
        inv_children.sort(key=lambda x: x["amount"], reverse=True)
        inv_item["children"] = inv_children
        notes.append("Inventory details nested under the Inventory (Closing Stock) line (qty and amount per product).")

    # 3) Prior earnings (from inception to start-1) → Equity
    if include_prior_earnings:
        prior = build_profit_and_loss_statement(
            entity_id=entity_id,
            startdate="1900-01-01",
            enddate=str(opening_asof),
            level='head',
            pl_detailsingroup_values=pl_detailsingroup_values,
            trading_detailsingroup_values=trading_detailsingroup_values,
            valuation_method=valuation_method
        )
        prior_profit = Q2(prior.get('net_profit', 0) or 0)
        prior_loss   = Q2(prior.get('net_loss', 0) or 0)

        if prior_profit > 0:
            liab_rows.append({"label": f"{prior_earnings_label} (to {opening_asof})", "amount": float(prior_profit)})
            total_liab += prior_profit
        elif prior_loss > 0:
            assets_rows.append({"label": f"{prior_earnings_label} Loss (to {opening_asof})", "amount": float(prior_loss)})
            total_assets += prior_loss

        notes.append("Prior retained earnings (to start-1) brought into equity.")

    # 4) Current period earnings (start..end) → Equity
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

    # 5) Totals
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
            "valuation_method": valuation_method,
            "inventory_breakdown": bool(inventory_breakdown),
            "inventory_replace_gl": bool(inventory_replace_gl),
            "inventory_gl_head_ids": list(inventory_gl_head_ids),
            "include_prior_earnings": bool(include_prior_earnings),
        },
        "assets_total": float(total_assets),
        "liabilities_total": float(total_liab),
        "assets_rows": assets_rows,
        "liabilities_rows": liab_rows,
        "notes": notes
    }
