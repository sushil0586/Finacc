# services/balance_sheet.py
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple, Optional

from django.db.models import (
    Q, F, Sum, Case, When, Value as V, DecimalField,
    Subquery, OuterRef
)

# Adjust app labels if needed
from invoice.models import JournalLine, InventoryMove, Product
from .trading_account import STRATEGIES
from .profit_and_loss import build_profit_and_loss_statement  # for prior & current earnings


# --------------------------- Helpers ---------------------------

def Q2(x) -> Decimal:
    q = Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return q if q != Decimal("-0.00") else Decimal("0.00")


def _rate_from_move(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / Decimal(str(qty))
    return Decimal('0')


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

def _inventory_value_asof(entity_id: int, enddate, method: str) -> Decimal:
    method = (method or "fifo").lower()
    strat = STRATEGIES.get(method, STRATEGIES["fifo"])
    _opening, _cogs, closing = strat(entity_id, enddate, enddate)
    return closing


def _inventory_breakdown_asof(
    *,
    entity_id: int,
    enddate,
    method: str = "fifo",
    product_ids: Optional[List[int]] = None,
    include_zero: bool = False,
) -> Tuple[List[Dict], Decimal, Decimal]:
    method = (method or "fifo").lower()
    moves_qs = (InventoryMove.objects
                .filter(entity_id=entity_id, entrydate__lte=enddate)
                .values('product_id', 'entrydate', 'id', 'qty', 'unit_cost', 'ext_cost')
                .order_by('product_id', 'entrydate', 'id'))

    if product_ids:
        moves_qs = moves_qs.filter(product_id__in=product_ids)

    rows: List[Dict] = []
    total_qty = Decimal('0')
    total_val = Decimal('0')

    # Align with your Product model's name field (productname)
    if product_ids:
        prod_map = {p.id: p.productname for p in Product.objects.filter(id__in=product_ids)}
    else:
        prod_map = {p.id: p.productname for p in Product.objects.filter(entity_id=entity_id).only('id', 'productname')}

    cur_pid = None
    layers: List[Dict[str, Decimal]] = []
    q = Decimal('0'); v = Decimal('0')
    latest = Decimal('0')
    sum_in_qty = Decimal('0'); sum_in_val = Decimal('0'); issues_qty = Decimal('0')

    def flush_product(pid):
        nonlocal layers, q, v, latest, sum_in_qty, sum_in_val, issues_qty, total_qty, total_val
        if pid is None:
            return

        if method in ("fifo", "lifo"):
            qty = sum((l["qty"] for l in layers), Decimal('0'))
            val = sum((l["qty"] * l["rate"] for l in layers), Decimal('0'))
        elif method in ("mwa", "latest"):
            qty, val = q, v
        elif method == "wac":
            avg = (sum_in_val / sum_in_qty) if sum_in_qty > 0 else Decimal('0')
            qty = max(sum_in_qty - issues_qty, Decimal('0'))
            val = qty * avg
        else:
            qty, val = Decimal('0'), Decimal('0')

        qty = Q2(qty); val = Q2(val)
        if include_zero or qty != 0:
            name = prod_map.get(pid, f"Product {pid}")
            rate = Q2((val / qty) if qty else Decimal('0'))
            rows.append({
                "product_id": pid,
                "product_name": name,
                "qty": float(qty),
                "value": float(val),
                "rate": float(rate)
            })

        total_qty += qty
        total_val += val

        layers = []
        q = Decimal('0'); v = Decimal('0')
        latest = Decimal('0')
        sum_in_qty = Decimal('0'); sum_in_val = Decimal('0'); issues_qty = Decimal('0')

    for m in moves_qs:
        pid = m['product_id']
        if pid != cur_pid:
            flush_product(cur_pid)
            cur_pid = pid

        qty = Decimal(str(m['qty']))
        rate = _rate_from_move(qty, m['unit_cost'], m['ext_cost'])

        if method == "fifo":
            if qty > 0:
                layers.append({"qty": qty, "rate": rate})
            elif qty < 0:
                need = -qty; i = 0
                while need > 0 and i < len(layers):
                    take = min(layers[i]["qty"], need)
                    layers[i]["qty"] -= take
                    need -= take
                    if layers[i]["qty"] == 0:
                        i += 1
                layers = [l for l in layers if l["qty"] > 0]

        elif method == "lifo":
            if qty > 0:
                layers.append({"qty": qty, "rate": rate})
            elif qty < 0:
                need = -qty; i = len(layers) - 1
                while need > 0 and i >= 0:
                    take = min(layers[i]["qty"], need)
                    layers[i]["qty"] -= take
                    need -= take
                    if layers[i]["qty"] == 0:
                        layers.pop(i)
                        i -= 1

        elif method == "mwa":
            if qty > 0:
                q += qty; v += qty * rate
            elif qty < 0 and q > 0:
                avg = v / q if q else Decimal('0')
                take = min(q, -qty)
                v -= take * avg
                q -= take

        elif method == "latest":
            if qty > 0:
                latest = rate
                q += qty; v += qty * latest
            elif qty < 0:
                take = min(q, -qty)
                v -= take * latest
                q -= take
                if q == 0:
                    latest = Decimal('0')

        elif method == "wac":
            if qty > 0:
                sum_in_qty += qty; sum_in_val += qty * rate
            elif qty < 0:
                issues_qty += -qty

    flush_product(cur_pid)
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows, Q2(total_qty), Q2(total_val)


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
        entrydate__lte=end,
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
        qs = base.values('accounthead_id', 'accounthead__name', 'transactiontype', 'transactionid', 'voucherno')
        label_build = lambda r: (r.get('voucherno') or f"{r.get('transactiontype') or 'TXN'}#{r.get('transactionid')}")
    elif level == 'product':
        # Subqueries aligned with your InventoryMove linkage and Product.productname
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
