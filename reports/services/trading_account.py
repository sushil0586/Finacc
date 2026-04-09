# services/trading_account.py
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, List, Dict, Optional

from django.db.models import (
    Q, F, Sum, Case, When, Value as V, DecimalField,
    Subquery, OuterRef
)
from django.db.models.functions import Coalesce

from catalog.models import Product
from posting.models import EntryStatus, InventoryMove, JournalLine


# --------------------------- Common helpers ---------------------------

def Q2(x) -> Decimal:
    """Quantize to 2 decimals with standard rounding (no -0.00)."""
    q = Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return q if q != Decimal("-0.00") else Decimal("0.00")

def _in_rate(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    """Reliable IN rate: prefer unit_cost, else ext_cost/qty, else 0."""
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / abs(Decimal(str(qty)))
    return Decimal('0')

def _sum_debits(qs):
    return qs.aggregate(v=Sum(Case(When(drcr=True, then=F('amount')),
                                   default=V(0),
                                   output_field=DecimalField(max_digits=18, decimal_places=2))))['v'] or Decimal('0')

def _sum_credits(qs):
    return qs.aggregate(v=Sum(Case(When(drcr=False, then=F('amount')),
                                   default=V(0),
                                   output_field=DecimalField(max_digits=18, decimal_places=2))))['v'] or Decimal('0')

def _nest_under_accounthead(rows: list, *, head_field: str = "_head") -> list:
    """
    Convert flat account rows into parent Account Head nodes with children and subtotals.
    Each row must include an internal key rows[i][head_field] that holds the head name.
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


# --------------------------- Per-product inventory valuation (as-of) ---------------------------

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


def _apply_scope_filters(qs, *, entityfin_id=None, subentity_id=None):
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id:
        qs = qs.filter(subentity_id=subentity_id)
    return qs


def inventory_breakdown_asof(
    *,
    entity_id: int,
    entityfin_id: Optional[int] = None,
    subentity_id: Optional[int] = None,
    enddate,
    method: str = "fifo",
    product_ids: Optional[List[int]] = None,
    include_zero: bool = False,
) -> Tuple[List[Dict], Decimal, Decimal]:
    return _inventory_breakdown_asof(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        enddate=enddate,
        method=method,
        product_ids=product_ids,
        include_zero=include_zero,
    )


def inventory_value_asof(
    *,
    entity_id: int,
    entityfin_id: Optional[int] = None,
    subentity_id: Optional[int] = None,
    enddate,
    method: str = "fifo",
) -> Decimal:
    _rows, _qty, closing_value = inventory_breakdown_asof(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        enddate=enddate,
        method=method,
        include_zero=False,
    )
    return Q2(closing_value)

def _inventory_breakdown_asof(
    *,
    entity_id: int,
    entityfin_id: Optional[int] = None,
    subentity_id: Optional[int] = None,
    enddate,
    method: str = "fifo",
    product_ids: Optional[List[int]] = None,
    include_zero: bool = False,
) -> Tuple[List[Dict], Decimal, Decimal]:
    """
    Returns per-product closing qty and value as-of enddate using chosen valuation method.
    Output: (rows, total_qty, total_value) where rows = [{product_id, product_name, qty, value, rate}]
    """
    method = (method or "fifo").lower()

    moves_qs = (InventoryMove.objects
                .filter(entity_id=entity_id, posting_date__lte=enddate)
                .values('product_id', 'posting_date', 'id', 'qty', 'base_qty', 'move_type', 'unit_cost', 'ext_cost')
                .order_by('product_id', 'posting_date', 'id'))
    moves_qs = _apply_scope_filters(moves_qs, entityfin_id=entityfin_id, subentity_id=subentity_id)

    if product_ids:
        moves_qs = moves_qs.filter(product_id__in=product_ids)

    rows: List[Dict] = []
    total_qty = Decimal('0')
    total_val = Decimal('0')

    # Preload product names
    if product_ids:
        prod_map = {p.id: p.productname for p in Product.objects.filter(id__in=product_ids)}
    else:
        prod_map = {p.id: p.productname for p in Product.objects.filter(entity_id=entity_id).only('id', 'productname')}

    cur_pid = None

    # State for each strategy
    layers: List[Dict[str, Decimal]] = []     # fifo/lifo layers
    q = Decimal('0'); v = Decimal('0')        # mwa/latest running qty/value
    latest = Decimal('0')                     # latest cost
    sum_in_qty = Decimal('0'); sum_in_val = Decimal('0'); issues_qty = Decimal('0')  # wac accumulators

    def flush_product(pid):
        nonlocal layers, q, v, latest, sum_in_qty, sum_in_val, issues_qty, total_qty, total_val
        if pid is None:
            return

        if method in ("fifo", "lifo"):
            qty = sum((l["qty"] for l in layers), Decimal('0'))
            val = sum((l["qty"] * l["rate"] for l in layers), Decimal('0'))
        elif method == "mwa":
            qty, val = q, v
        elif method == "latest":
            qty, val = q, v
        elif method == "wac":
            avg = (sum_in_val / sum_in_qty) if sum_in_qty > 0 else Decimal('0')
            qty = max(sum_in_qty - issues_qty, Decimal('0'))
            val = qty * avg
        else:
            qty, val = Decimal('0'), Decimal('0')

        qty = Q2(qty)
        val = Q2(val)
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

        # reset state
        layers = []
        q = Decimal('0'); v = Decimal('0')
        latest = Decimal('0')
        sum_in_qty = Decimal('0'); sum_in_val = Decimal('0'); issues_qty = Decimal('0')

    for m in moves_qs:
        pid = m['product_id']
        if pid != cur_pid:
            flush_product(cur_pid)
            cur_pid = pid

        qty = _signed_move_qty(m)
        rate = _rate_from_move(qty, m['unit_cost'], m['ext_cost'])

        if method == "fifo":
            if qty > 0:
                layers.append({"qty": qty, "rate": rate})
            elif qty < 0:
                need = -qty
                i = 0
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
                need = -qty
                i = len(layers) - 1
                while need > 0 and i >= 0:
                    take = min(layers[i]["qty"], need)
                    layers[i]["qty"] -= take
                    need -= take
                    if layers[i]["qty"] == 0:
                        layers.pop(i)
                        i -= 1

        elif method == "mwa":
            if qty > 0:
                q += qty
                v += qty * rate
            elif qty < 0 and q > 0:
                avg = v / q if q else Decimal('0')
                take = min(q, -qty)
                v -= take * avg
                q -= take

        elif method == "latest":
            if qty > 0:
                latest = rate
                q += qty
                v += qty * latest
            elif qty < 0:
                take = min(q, -qty)
                v -= take * latest
                q -= take
                if q == 0:
                    latest = Decimal('0')

        elif method == "wac":
            if qty > 0:
                sum_in_qty += qty
                sum_in_val += qty * rate
            elif qty < 0:
                issues_qty += -qty

    # final product
    flush_product(cur_pid)

    # Sort by value desc
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows, Q2(total_qty), Q2(total_val)


def _period_inventory_inflow_value(*, entity_id, entityfin_id=None, subentity_id=None, start_date, end_date) -> Decimal:
    inflow = _apply_scope_filters(
        InventoryMove.objects.filter(
            entity_id=entity_id,
            posting_date__range=(start_date, end_date),
            move_type="IN",
        ),
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).aggregate(total=Sum("ext_cost"))["total"] or Decimal("0")
    return Q2(inflow)


def _value_by_inventory_identity(*, entity_id, entityfin_id=None, subentity_id=None, start_date, end_date, method: str) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Canonical inventory valuation shared by Trading and Balance Sheet.
    We value opening/closing per product, then derive COGS using:
      opening inventory + period inflows - closing inventory
    This avoids cross-product consumption bugs from pooled FIFO/LIFO layers.
    """
    opening_asof = start_date - timedelta(days=1)
    opening_value = inventory_value_asof(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        enddate=opening_asof,
        method=method,
    )
    closing_value = inventory_value_asof(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        enddate=end_date,
        method=method,
    )
    inflow_value = _period_inventory_inflow_value(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        start_date=start_date,
        end_date=end_date,
    )
    cogs_issues = Q2(opening_value + inflow_value - closing_value)
    return Q2(opening_value), cogs_issues, Q2(closing_value)


# --------------------------- Valuation: strategies (totals) ---------------------------

def _value_by_fifo(entity_id, start_date, end_date, entityfin_id=None, subentity_id=None) -> Tuple[Decimal, Decimal, Decimal]:
    return _value_by_inventory_identity(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        start_date=start_date,
        end_date=end_date,
        method="fifo",
    )


def _value_by_lifo(entity_id, start_date, end_date, entityfin_id=None, subentity_id=None) -> Tuple[Decimal, Decimal, Decimal]:
    return _value_by_inventory_identity(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        start_date=start_date,
        end_date=end_date,
        method="lifo",
    )


def _value_by_mwa(entity_id, start_date, end_date, entityfin_id=None, subentity_id=None) -> Tuple[Decimal, Decimal, Decimal]:
    return _value_by_inventory_identity(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        start_date=start_date,
        end_date=end_date,
        method="mwa",
    )


def _value_by_wac(entity_id, start_date, end_date, entityfin_id=None, subentity_id=None) -> Tuple[Decimal, Decimal, Decimal]:
    return _value_by_inventory_identity(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        start_date=start_date,
        end_date=end_date,
        method="wac",
    )


def _value_by_latest(entity_id, start_date, end_date, entityfin_id=None, subentity_id=None) -> Tuple[Decimal, Decimal, Decimal]:
    return _value_by_inventory_identity(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        start_date=start_date,
        end_date=end_date,
        method="latest",
    )


# --------------------------- Strategy registry --------------------------

STRATEGIES = {
    "fifo": _value_by_fifo,
    "lifo": _value_by_lifo,
    "mwa": _value_by_mwa,   # Moving Weighted Average (perpetual)
    "wac": _value_by_wac,   # Periodic Weighted Average
    "latest": _value_by_latest
}


# --------------------------- Aggregation by level -----------------------

def _build_label(level: str, row: dict) -> str:
    if level == 'head':
        return row.get('resolved_head_name') or row.get('accounthead__name') or f"Head {row.get('resolved_head_id') or row.get('accounthead_id')}"
    if level == 'account':
        nm = row.get('resolved_account_name') or row.get('account__accountname') or f"Account {row.get('resolved_account_id') or row.get('account_id')}"
        hd = row.get('resolved_head_name') or row.get('accounthead__name')
        return f"{nm} ({hd})" if hd else nm
    if level == 'product':
        return row.get('product__productname') or "Unmapped Product"
    if level == 'voucher':
        vt = row.get('txn_type') or "TXN"
        vid = row.get('txn_id')
        vno = row.get('voucher_no')
        return vno or f"{vt}#{vid}"
    return row.get('accounthead__name') or "Row"

def _aggregate_journal(
    entity_id,
    start,
    end,
    detailsingroup_values,
    level,
    *,
    entityfin_id=None,
    subentity_id=None,
    posted_only=True,
    ledger_ids: Optional[List[int]] = None,
):
    """
    Aggregate JournalLine by requested level (head|account|product|voucher).
    Returns: (debit_rows, credit_rows, total_period_debits, total_period_credits, warnings[])
    """
    warnings = []
    detail_groups = {int(value) for value in (detailsingroup_values or (1,))}
    base_qs = JournalLine.objects.filter(
        entity_id=entity_id,
        posting_date__range=(start, end),
    )
    if posted_only:
        base_qs = base_qs.filter(entry__status=EntryStatus.POSTED)
    jl_base = _apply_scope_filters((
        base_qs
        .annotate(
            resolved_head_id=Coalesce(
                F('accounthead_id'),
                F('ledger__accounthead_id'),
                F('account__ledger__accounthead_id'),
            ),
            resolved_head_name=Coalesce(
                F('accounthead__name'),
                F('ledger__accounthead__name'),
                F('account__ledger__accounthead__name'),
            ),
            resolved_head_detailsingroup=Coalesce(
                F('accounthead__detailsingroup'),
                F('ledger__accounthead__detailsingroup'),
                F('account__ledger__accounthead__detailsingroup'),
            ),
            resolved_account_id=Coalesce(
                F('account_id'),
                F('ledger_id'),
            ),
            resolved_account_name=Coalesce(
                F('account__accountname'),
                F('ledger__name'),
            ),
        )
    ), entityfin_id=entityfin_id, subentity_id=subentity_id)

    if ledger_ids:
        jl_base = jl_base.filter(resolved_account_id__in=ledger_ids)

    common_fields = [
        'resolved_head_id',
        'resolved_head_name',
        'resolved_head_detailsingroup',
    ]

    if level == 'head':
        values_fields = [*common_fields]
        qs = jl_base.values(*values_fields)
    elif level == 'account':
        values_fields = [*common_fields, 'resolved_account_id', 'resolved_account_name']
        qs = jl_base.values(*values_fields)
    elif level == 'voucher':
        values_fields = [*common_fields, 'txn_type', 'txn_id', 'voucher_no']
        qs = jl_base.values(*values_fields)
    elif level == 'product':
        # Map product via InventoryMove keys; first matching product per line
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
        qs = jl_base.annotate(product_id=prod_id_sub, product__productname=prod_name_sub)\
                    .values(*common_fields, 'product_id', 'product__productname')
        values_fields = [*common_fields, 'product_id', 'product__productname']
    else:
        # default fallback to head
        values_fields = [*common_fields]
        qs = jl_base.values(*values_fields)
        level = 'head'

    agg = qs.annotate(
        debits=Sum(Case(When(drcr=True, then=F('amount')),
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2))),
        credits=Sum(Case(When(drcr=False, then=F('amount')),
                         default=V(0),
                         output_field=DecimalField(max_digits=18, decimal_places=2))),
    )

    debit_rows, credit_rows = [], []
    total_period_debits = Decimal('0')
    total_period_credits = Decimal('0')

    for row in agg:
        head_detailsingroup = row.get("resolved_head_detailsingroup")
        try:
            head_detailsingroup = int(head_detailsingroup) if head_detailsingroup is not None else None
        except (TypeError, ValueError):
            head_detailsingroup = None
        if head_detailsingroup not in detail_groups:
            continue
        net = (row['debits'] or Decimal('0')) - (row['credits'] or Decimal('0'))

        if level == 'account':
            head_name = row.get('resolved_head_name') or f"Head {row.get('resolved_head_id')}"
            account_label = row.get('resolved_account_name') or f"Account {row.get('resolved_account_id')}"
            label = account_label
        else:
            head_name = None
            label = _build_label(level, row)

        if net > 0:
            amt = Q2(net)
            item = {"label": label, "amount": float(amt)}
            if level == 'account':
                item["_head"] = head_name
            debit_rows.append(item)
            total_period_debits += amt
        elif net < 0:
            amt = Q2(-net)
            item = {"label": label, "amount": float(amt)}
            if level == 'account':
                item["_head"] = head_name
            credit_rows.append(item)
            total_period_credits += amt

    if level == 'product':
        if any(r['label'] == "Unmapped Product" for r in debit_rows + credit_rows):
            warnings.append({
                "code": "UNMAPPED_PRODUCT",
                "msg": "Some journals could not be mapped to products (missing detail_id or no InventoryMove match)."
            })

    # ⬇️ When level='account', group accounts under their Account Head parents with subtotals
    if level == 'account':
        debit_rows  = _nest_under_accounthead(debit_rows)
        credit_rows = _nest_under_accounthead(credit_rows)

    return debit_rows, credit_rows, total_period_debits, total_period_credits, warnings


# --------------------------- Main builder ------------------------------

def build_trading_account_dynamic(
    *,
    entity_id: int,
    entityfin_id: Optional[int] = None,
    subentity_id: Optional[int] = None,
    startdate: str,
    enddate: str,
    posted_only: bool = True,
    hide_zero_rows: bool = True,
    view_type: str = "summary",
    account_group: str | None = None,
    ledger_ids: Optional[List[int]] = None,
    valuation_method: str = "fifo",      # fifo | lifo | mwa | wac | latest
    detailsingroup_values=(1,),          # which accounthead groups count as "Trading"
    level='head',                        # head | account | product | voucher
    fold_returns=True,                   # reserved for UI presentation
    round_decimals=2,                    # presentation rounding (not used internally)

    # NEW: opening/closing inventory product-wise details
    inventory_breakdown: bool = True,
    inventory_include_zero: bool = False,
    inventory_product_ids: Optional[List[int]] = None,
):
    """
    Trading Account:
      - Amounts from JournalLine for heads configured in the trading section,
      - Inventory valuation chosen via valuation_method (opening, COGS issues, closing),
      - Opening and Closing stock lines include product-wise children when inventory_breakdown=True,
      - Dr/Cr rows built by net balance and balanced with GP on DEBIT (or GL on CREDIT).
    """
    start = datetime.strptime(startdate, '%Y-%m-%d').date()
    end   = datetime.strptime(enddate,   '%Y-%m-%d').date()
    opening_asof = start - timedelta(days=1)

    # 1) Aggregate journals by requested level
    effective_level = (level or ("account" if view_type == "detailed" else "head")).lower()
    debit_rows, credit_rows, total_dr, total_cr, warns = _aggregate_journal(
        entity_id,
        start,
        end,
        detailsingroup_values,
        effective_level,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        posted_only=posted_only,
        ledger_ids=ledger_ids,
    )

    # 2) Inventory valuation (opening/closing/COGS by strategy)
    method = (valuation_method or "fifo").lower()
    if method not in STRATEGIES:
        method = "fifo"
    opening_value, cogs_issues, closing_value = STRATEGIES[method](entity_id, start, end, entityfin_id, subentity_id)

    # 2a) Build product-wise children for opening/closing, if requested
    opening_children = []
    closing_children = []
    if inventory_breakdown:
        # Opening = as-of start-1
        op_rows, _op_qty, _op_val = _inventory_breakdown_asof(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            enddate=opening_asof,
            method=method,
            product_ids=inventory_product_ids,
            include_zero=inventory_include_zero,
        )
        for r in op_rows:
            opening_children.append({
                "label": r["product_name"],
                "qty": r["qty"],
                "amount": r["value"],
            })
        opening_children.sort(key=lambda x: x["amount"], reverse=True)

        # Closing = as-of end
        cl_rows, _cl_qty, _cl_val = _inventory_breakdown_asof(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            enddate=end,
            method=method,
            product_ids=inventory_product_ids,
            include_zero=inventory_include_zero,
        )
        for r in cl_rows:
            closing_children.append({
                "label": r["product_name"],
                "qty": r["qty"],
                "amount": r["value"],
            })
        closing_children.sort(key=lambda x: x["amount"], reverse=True)

    # 3) Place Opening/Closing; balance with GP/GL (GP on DEBIT, GL on CREDIT)
    if not hide_zero_rows or opening_value != 0:
        opening_item = {"label": "Opening Stock", "amount": float(opening_value)}
        if opening_children:
            opening_item["children"] = opening_children
        debit_rows.insert(0, opening_item)

    if not hide_zero_rows or closing_value != 0:
        closing_item = {"label": "Closing Stock", "amount": float(closing_value)}
        if closing_children:
            closing_item["children"] = closing_children
        credit_rows.append(closing_item)

    total_debits  = total_dr + opening_value
    total_credits = total_cr + closing_value

    gross_profit = Decimal('0')
    gross_loss   = Decimal('0')
    if total_credits >= total_debits:
        gross_profit = Q2(total_credits - total_debits)
        if gross_profit > 0 and (not hide_zero_rows or gross_profit != 0):
            debit_rows.append({"label": "Gross Profit c/d", "amount": float(gross_profit)})
            total_debits += gross_profit
    else:
        gross_loss = Q2(total_debits - total_credits)
        if gross_loss > 0 and (not hide_zero_rows or gross_loss != 0):
            credit_rows.append({"label": "Gross Loss c/d", "amount": float(gross_loss)})
            total_credits += gross_loss

    debit_total  = Q2(total_debits)
    credit_total = Q2(total_credits)

    resp = {
        "period": {"start": str(start), "end": str(end)},
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "params": {
            "detailsingroup": list(detailsingroup_values),
            "level": effective_level,
            "view_type": view_type,
            "fold_returns": bool(fold_returns),
            "round": int(round_decimals),
            "valuation_method": method,
            "posted_only": bool(posted_only),
            "hide_zero_rows": bool(hide_zero_rows),
            "account_group": account_group,
            "ledger_ids": list(ledger_ids) if ledger_ids else None,
            "inventory_breakdown": bool(inventory_breakdown),
            "inventory_include_zero": bool(inventory_include_zero),
            "inventory_product_ids": list(inventory_product_ids) if inventory_product_ids else None,
        },
        "debit_total": float(debit_total),
        "credit_total": float(credit_total),
        "opening_stock": float(opening_value),
        "closing_stock": float(closing_value),
        "gross_profit": float(Q2(gross_profit)),
        "gross_loss": float(Q2(gross_loss)),
        "debit_rows": debit_rows,
        "credit_rows": credit_rows,
        # Operational COGS (issues) — for reconciliation/analytics
        "cogs_from_issues": float(cogs_issues),
        "notes": [
            "Heads included where accounthead.detailsingroup ∈ configured trading values.",
            "Net = (debits - credits) from JournalLine decides Dr/Cr placement.",
            f"Inventory valued using '{method}' strategy; OUTs priced by strategy (not sales values).",
            "Opening/Closing stock include product-wise nested details when inventory_breakdown=True."
        ]
    }
    if warns:
        resp["warnings"] = warns
    return resp
