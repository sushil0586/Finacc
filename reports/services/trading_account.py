# services/trading_account.py
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, List, Dict

from django.db.models import (
    Q, F, Sum, Case, When, Value as V, DecimalField,
    Subquery, OuterRef
)

# ⬇️ Adjust app label(s) if needed
from invoice.models import JournalLine, InventoryMove


# --------------------------- Common helpers ---------------------------

def Q2(x) -> Decimal:
    """Quantize to 2 decimals with standard rounding."""
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _in_rate(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    """Reliable IN rate: prefer unit_cost, else ext_cost/qty, else 0."""
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / Decimal(str(qty))
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


# --------------------------- Valuation: FIFO ---------------------------

def _value_by_fifo(entity_id, start_date, end_date) -> Tuple[Decimal, Decimal, Decimal]:
    """
    FIFO layers:
      - IN adds a layer
      - OUT consumes earliest layers
      Returns (opening_value, cogs_issues_in_period, closing_value) at 2 decimals.
    """
    moves = (InventoryMove.objects
             .filter(entity_id=entity_id, entrydate__lte=end_date)
             .values('id', 'entrydate', 'qty', 'unit_cost', 'ext_cost')
             .order_by('entrydate', 'id'))

    layers: List[Dict[str, Decimal]] = []
    opening_value = Decimal('0')
    cogs_issues   = Decimal('0')

    def add_layer(qty: Decimal, rate: Decimal):
        if qty > 0 and rate >= 0:
            layers.append({"qty": qty, "rate": rate})

    def consume(qty_out: Decimal) -> Decimal:
        nonlocal layers
        need = -qty_out
        spent = Decimal('0')
        i = 0
        while need > 0 and i < len(layers):
            take = min(layers[i]["qty"], need)
            spent += take * layers[i]["rate"]
            layers[i]["qty"] -= take
            need -= take
            if layers[i]["qty"] == 0:
                i += 1
        layers = [l for l in layers if l["qty"] > 0]
        return spent

    day_before = start_date - timedelta(days=1)
    # Build opening
    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d > day_before:
            break
        if qty > 0:
            add_layer(qty, _in_rate(qty, m['unit_cost'], m['ext_cost']))
        elif qty < 0:
            consume(qty)
    opening_value = sum((l["qty"] * l["rate"] for l in layers), Decimal('0'))

    # Period movements
    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d < start_date:
            continue
        if qty > 0:
            add_layer(qty, _in_rate(qty, m['unit_cost'], m['ext_cost']))
        elif qty < 0:
            cogs_issues += consume(qty)

    closing_value = sum((l["qty"] * l["rate"] for l in layers), Decimal('0'))
    return Q2(opening_value), Q2(cogs_issues), Q2(closing_value)


# --------------------------- Valuation: LIFO ---------------------------

def _value_by_lifo(entity_id, start_date, end_date) -> Tuple[Decimal, Decimal, Decimal]:
    """
    LIFO layers (stack):
      - IN pushes a layer
      - OUT pops from most recent layers first
    """
    moves = (InventoryMove.objects
             .filter(entity_id=entity_id, entrydate__lte=end_date)
             .values('id', 'entrydate', 'qty', 'unit_cost', 'ext_cost')
             .order_by('entrydate', 'id'))

    layers: List[Dict[str, Decimal]] = []
    opening_value = Decimal('0')
    cogs_issues   = Decimal('0')

    def add_layer(qty: Decimal, rate: Decimal):
        if qty > 0 and rate >= 0:
            layers.append({"qty": qty, "rate": rate})

    def consume(qty_out: Decimal) -> Decimal:
        nonlocal layers
        need = -qty_out
        spent = Decimal('0')
        i = len(layers) - 1
        while need > 0 and i >= 0:
            take = min(layers[i]["qty"], need)
            spent += take * layers[i]["rate"]
            layers[i]["qty"] -= take
            need -= take
            if layers[i]["qty"] == 0:
                layers.pop(i)
                i -= 1
        return spent

    day_before = start_date - timedelta(days=1)
    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d > day_before:
            break
        if qty > 0:
            add_layer(qty, _in_rate(qty, m['unit_cost'], m['ext_cost']))
        elif qty < 0:
            consume(qty)
    opening_value = sum((l["qty"] * l["rate"] for l in layers), Decimal('0'))

    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d < start_date:
            continue
        if qty > 0:
            add_layer(qty, _in_rate(qty, m['unit_cost'], m['ext_cost']))
        elif qty < 0:
            cogs_issues += consume(qty)

    closing_value = sum((l["qty"] * l["rate"] for l in layers), Decimal('0'))
    return Q2(opening_value), Q2(cogs_issues), Q2(closing_value)


# ------------- Valuation: Moving Weighted Average (perpetual) ----------

def _value_by_mwa(entity_id, start_date, end_date) -> Tuple[Decimal, Decimal, Decimal]:
    moves = (InventoryMove.objects
             .filter(entity_id=entity_id, entrydate__lte=end_date)
             .values('id', 'entrydate', 'qty', 'unit_cost', 'ext_cost')
             .order_by('entrydate', 'id'))

    day_before = start_date - timedelta(days=1)

    # Opening running avg
    oq = Decimal('0'); ov = Decimal('0')
    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d > day_before:
            break
        if qty > 0:
            rate = _in_rate(qty, m['unit_cost'], m['ext_cost'])
            oq += qty; ov += qty * rate
        elif qty < 0 and oq > 0:
            avg = ov / oq
            take = min(oq, -qty)
            ov -= take * avg
            oq -= take
    opening_value = ov

    # Period with moving avg
    q = oq; v = ov
    cogs = Decimal('0')
    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d < start_date:
            continue
        if qty > 0:
            rate = _in_rate(qty, m['unit_cost'], m['ext_cost'])
            v += qty * rate
            q += qty
        elif qty < 0 and q > 0:
            avg = v / q
            take = min(q, -qty)
            cogs += take * avg
            v -= take * avg
            q -= take

    return Q2(opening_value), Q2(cogs), Q2(v)


# ------------- Valuation: Periodic Weighted Average (WAC) --------------

def _value_by_wac(entity_id, start_date, end_date) -> Tuple[Decimal, Decimal, Decimal]:
    day_before = start_date - timedelta(days=1)

    # Opening (<= start-1)
    opening_in = (InventoryMove.objects
                  .filter(entity_id=entity_id, entrydate__lte=day_before, qty__gt=0)
                  .values('qty', 'unit_cost', 'ext_cost'))
    opening_out = (InventoryMove.objects
                   .filter(entity_id=entity_id, entrydate__lte=day_before, qty__lt=0)
                   .values('qty'))

    oq = Decimal('0'); ov = Decimal('0')
    for m in opening_in:
        qty = Decimal(str(m['qty'])); rate = _in_rate(qty, m['unit_cost'], m['ext_cost'])
        oq += qty; ov += qty * rate
    for m in opening_out:
        qty = -Decimal(str(m['qty']))
        take = min(oq, qty)
        if oq > 0:
            avg = ov / oq
            ov -= take * avg
            oq -= take

    # Period purchases (IN)
    period_in = (InventoryMove.objects
                 .filter(entity_id=entity_id, entrydate__range=(start_date, end_date), qty__gt=0)
                 .values('qty', 'unit_cost', 'ext_cost'))
    pq = Decimal('0'); pv = Decimal('0')
    for m in period_in:
        qty = Decimal(str(m['qty'])); rate = _in_rate(qty, m['unit_cost'], m['ext_cost'])
        pq += qty; pv += qty * rate

    # Period issues (OUT)
    issues_qty = (InventoryMove.objects
                  .filter(entity_id=entity_id, entrydate__range=(start_date, end_date), qty__lt=0)
                  .aggregate(v=Sum(-F('qty')))['v'] or Decimal('0'))

    denom_qty = oq + pq
    avg = (ov + pv) / denom_qty if denom_qty > 0 else Decimal('0')

    cogs_issues = issues_qty * avg
    closing_value = (ov + pv) - cogs_issues
    opening_value = ov

    return Q2(opening_value), Q2(cogs_issues), Q2(closing_value)


# --------------------------- Valuation: Latest --------------------------

def _value_by_latest(entity_id, start_date, end_date) -> Tuple[Decimal, Decimal, Decimal]:
    moves = (InventoryMove.objects
             .filter(entity_id=entity_id, entrydate__lte=end_date)
             .values('id', 'entrydate', 'qty', 'unit_cost', 'ext_cost')
             .order_by('entrydate', 'id'))

    day_before = start_date - timedelta(days=1)

    latest = Decimal('0')
    oq = Decimal('0'); ov = Decimal('0')

    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d > day_before:
            break
        if qty > 0:
            latest = _in_rate(qty, m['unit_cost'], m['ext_cost'])
            oq += qty; ov += qty * latest
        elif qty < 0:
            take = min(oq, -qty)
            ov -= take * latest
            oq -= take
    opening_value = ov

    q = oq; v = ov
    cogs = Decimal('0')
    for m in moves:
        d = m['entrydate']; qty = Decimal(str(m['qty']))
        if d < start_date:
            continue
        if qty > 0:
            latest = _in_rate(qty, m['unit_cost'], m['ext_cost'])
            q += qty; v += qty * latest
        elif qty < 0:
            take = min(q, -qty)
            cogs += take * latest
            v -= take * latest
            q -= take

    return Q2(opening_value), Q2(cogs), Q2(v)


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
        return row.get('accounthead__name') or f"Head {row.get('accounthead_id')}"
    if level == 'account':
        nm = row.get('account__accountname') or f"Account {row.get('account_id')}"
        hd = row.get('accounthead__name')
        return f"{nm} ({hd})" if hd else nm
    if level == 'product':
        return row.get('product__name') or "Unmapped Product"
    if level == 'voucher':
        vt = row.get('transactiontype') or "TXN"
        vid = row.get('transactionid')
        vno = row.get('voucherno')
        return vno or f"{vt}#{vid}"
    return row.get('accounthead__name') or "Row"

def _aggregate_journal(entity_id, start, end, detailsingroup_values, level):
    """
    Aggregate JournalLine by requested level (head|account|product|voucher).
    Returns: (debit_rows, credit_rows, total_period_debits, total_period_credits, warnings[])
    """
    warnings = []
    jl_base = JournalLine.objects.filter(
        entity_id=entity_id,
        entrydate__range=(start, end),
        accounthead__detailsingroup__in=detailsingroup_values
    )

    if level == 'head':
        values_fields = ['accounthead_id', 'accounthead__name']
        qs = jl_base.values(*values_fields)
    elif level == 'account':
        values_fields = ['accounthead_id', 'accounthead__name', 'account_id', 'account__accountname']
        qs = jl_base.values(*values_fields)
    elif level == 'voucher':
        values_fields = ['accounthead_id', 'accounthead__name', 'transactiontype', 'transactionid', 'voucherno']
        qs = jl_base.values(*values_fields)
    elif level == 'product':
        # Map product via InventoryMove keys; first matching product per line
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
        qs = jl_base.annotate(product_id=prod_id_sub, product__name=prod_name_sub)\
                    .values('product_id', 'product__name')
        values_fields = ['product_id', 'product__name']
    else:
        # default fallback to head
        values_fields = ['accounthead_id', 'accounthead__name']
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
        net = (row['debits'] or Decimal('0')) - (row['credits'] or Decimal('0'))

        if level == 'account':
            head_name = row.get('accounthead__name') or f"Head {row.get('accounthead_id')}"
            account_label = row.get('account__accountname') or f"Account {row.get('account_id')}"
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
                "msg": "Some journals could not be mapped to products (missing detailid or no InventoryMove match)."
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
    startdate: str,
    enddate: str,
    valuation_method: str = "fifo",      # fifo | lifo | mwa | wac | latest
    detailsingroup_values=(1,),          # which accounthead groups count as "Trading"
    level='head',                        # head | account | product | voucher
    fold_returns=True,                   # reserved for UI presentation
    round_decimals=2,                    # presentation rounding (not used internally)
):
    """
    Trading Account:
      - Amounts from JournalLine (accounthead.detailsingroup in values),
      - Inventory valuation chosen via valuation_method (opening, COGS issues, closing),
      - Dr/Cr rows built by net balance and balanced with GP on DEBIT (or GL on CREDIT).
    """
    start = datetime.strptime(startdate, '%Y-%m-%d').date()
    end   = datetime.strptime(enddate,   '%Y-%m-%d').date()

    # 1) Aggregate journals by requested level
    debit_rows, credit_rows, total_dr, total_cr, warns = \
        _aggregate_journal(entity_id, start, end, detailsingroup_values, level)

    # 2) Inventory valuation (opening/closing/COGS by strategy)
    method = (valuation_method or "fifo").lower()
    if method not in STRATEGIES:
        method = "fifo"
    opening_value, cogs_issues, closing_value = STRATEGIES[method](entity_id, start, end)

    # 3) Place Opening/Closing; balance with GP/GL (GP on DEBIT, GL on CREDIT)
    debit_rows.insert(0, {"label": "Opening Stock", "amount": float(opening_value)})
    credit_rows.append({"label": "Closing Stock", "amount": float(closing_value)})

    total_debits  = total_dr + opening_value
    total_credits = total_cr + closing_value

    gross_profit = Decimal('0')
    gross_loss   = Decimal('0')
    if total_credits >= total_debits:
        gross_profit = Q2(total_credits - total_debits)
        if gross_profit > 0:
            debit_rows.append({"label": "Gross Profit c/d", "amount": float(gross_profit)})
            total_debits += gross_profit
    else:
        gross_loss = Q2(total_debits - total_credits)
        if gross_loss > 0:
            credit_rows.append({"label": "Gross Loss c/d", "amount": float(gross_loss)})
            total_credits += gross_loss

    debit_total  = Q2(total_debits)
    credit_total = Q2(total_credits)

    resp = {
        "period": {"start": str(start), "end": str(end)},
        "entity_id": entity_id,
        "params": {
            "detailsingroup": list(detailsingroup_values),
            "level": level,
            "fold_returns": bool(fold_returns),
            "round": int(round_decimals),
            "valuation_method": method
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
            "Heads included where accounthead.detailsingroup ∈ provided values.",
            "Net = (debits - credits) from JournalLine decides Dr/Cr placement.",
            f"Inventory valued using '{method}' strategy; OUTs priced by strategy (not sales values)."
        ]
    }
    if warns:
        resp["warnings"] = warns
    return resp
