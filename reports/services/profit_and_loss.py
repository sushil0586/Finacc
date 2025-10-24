# services/profit_and_loss.py
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple

from django.db.models import (
    Q, F, Sum, Case, When, Value as V, DecimalField,
    Subquery, OuterRef
)

# Adjust app labels if needed
from invoice.models import JournalLine, InventoryMove
from .trading_account import build_trading_account_dynamic  # safe: one-way dependency


# --------------------------- Helpers ---------------------------

def Q2(x) -> Decimal:
    """Quantize to 2 decimals with standard rounding."""
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


# --------------------------- Aggregation ---------------------------

def _aggregate_pl(
    *,
    entity_id: int,
    start,
    end,
    level: str,
    pl_detailsingroup_values: tuple,          # e.g. (2,)
    trading_detailsingroup_values: tuple      # e.g. (1,)
) -> Tuple[List[Dict], List[Dict], Decimal, Decimal, List[Dict]]:
    """
    Aggregate indirect P&L from JournalLine where accounthead.detailsingroup ∈ pl_detailsingroup_values,
    while EXCLUDING Trading heads (detailsingroup ∈ trading_detailsingroup_values).
    """
    warnings: List[Dict] = []

    base = (JournalLine.objects
            .filter(
                entity_id=entity_id,
                entrydate__range=(start, end),
                accounthead__detailsingroup__in=pl_detailsingroup_values
            )
            .exclude(accounthead__detailsingroup__in=trading_detailsingroup_values))

    # Grouping by level
    if level == 'head':
        values_fields = ['accounthead_id', 'accounthead__name']
        qs = base.values(*values_fields)
    elif level == 'account':
        values_fields = ['accounthead_id', 'accounthead__name', 'account_id', 'account__accountname']
        qs = base.values(*values_fields)
    elif level == 'voucher':
        values_fields = ['accounthead_id', 'accounthead__name', 'transactiontype', 'transactionid', 'voucherno']
        qs = base.values(*values_fields)
    elif level == 'product':
        # Map product via InventoryMove keys; first match per line
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
        values_fields = ['product_id', 'product__name']
    else:
        # default to head
        values_fields = ['accounthead_id', 'accounthead__name']
        qs = base.values(*values_fields)
        level = 'head'

    agg = qs.annotate(
        debits=Sum(Case(When(drcr=True, then=F('amount')),
                        default=V(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2))),
        credits=Sum(Case(When(drcr=False, then=F('amount')),
                         default=V(0),
                         output_field=DecimalField(max_digits=18, decimal_places=2))),
    )

    debit_rows: List[Dict] = []
    credit_rows: List[Dict] = []
    tot_dr = Decimal('0')
    tot_cr = Decimal('0')

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
            amt = Q2(net)           # indirect expense → DEBIT
            item = {"label": label, "amount": float(amt)}
            if level == 'account':
                item["_head"] = head_name
            debit_rows.append(item)
            tot_dr += amt
        elif net < 0:
            amt = Q2(-net)          # income → CREDIT
            item = {"label": label, "amount": float(amt)}
            if level == 'account':
                item["_head"] = head_name
            credit_rows.append(item)
            tot_cr += amt

    if level == 'product':
        if any(r['label'] == "Unmapped Product" for r in debit_rows + credit_rows):
            warnings.append({
                "code": "UNMAPPED_PRODUCT",
                "msg": "Some journals could not be mapped to products (missing detailid or no InventoryMove match)."
            })

    # Group accounts under their Account Head parents with subtotals when level='account'
    if level == 'account':
        debit_rows  = _nest_under_accounthead(debit_rows)
        credit_rows = _nest_under_accounthead(credit_rows)

    return debit_rows, credit_rows, tot_dr, tot_cr, warnings


# --------------------------- Builder ---------------------------

def build_profit_and_loss_statement(
    *,
    entity_id: int,
    startdate: str,
    enddate: str,
    level: str = 'head',                       # head | account | product | voucher
    pl_detailsingroup_values: tuple = (2,),    # P&L heads (default: 2)
    trading_detailsingroup_values: tuple = (1,),   # Trading heads (default: 1) — excluded from P&L aggregate
    valuation_method: str = "fifo"             # used to fetch GP/GL via Trading
):
    """
    Profit & Loss (period):
      - Indirect expenses and incomes from JournalLine where accounthead.detailsingroup ∈ pl_detailsingroup_values,
        excluding Trading heads (detailsingroup ∈ trading_detailsingroup_values).
      - Gross Profit/Loss brought down from Trading; statement balanced with Net Profit (DEBIT) or Net Loss (CREDIT).
    """
    start = datetime.strptime(startdate, '%Y-%m-%d').date()
    end   = datetime.strptime(enddate,   '%Y-%m-%d').date()

    # 1) Trading → Gross Profit/Loss b/d
    trading = build_trading_account_dynamic(
        entity_id=entity_id,
        startdate=startdate,
        enddate=enddate,
        valuation_method=valuation_method,
        detailsingroup_values=trading_detailsingroup_values,
        level='head'
    )
    gross_profit = Decimal(str(trading.get('gross_profit', 0) or 0))
    gross_loss   = Decimal(str(trading.get('gross_loss', 0) or 0))

    # 2) Aggregate P&L lines
    debit_rows, credit_rows, tot_dr, tot_cr, warns = _aggregate_pl(
        entity_id=entity_id,
        start=start,
        end=end,
        level=level,
        pl_detailsingroup_values=pl_detailsingroup_values,
        trading_detailsingroup_values=trading_detailsingroup_values
    )

    # 3) Bring down GP/GL
    if gross_profit > 0:
        gp = Q2(gross_profit)
        credit_rows.insert(0, {"label": "Gross Profit b/d", "amount": float(gp)})
        tot_cr += gp
    elif gross_loss > 0:
        gl = Q2(gross_loss)
        debit_rows.insert(0, {"label": "Gross Loss b/d", "amount": float(gl)})
        tot_dr += gl

    # 4) Balance with Net Profit (DEBIT) / Net Loss (CREDIT)
    net_profit = Decimal('0')
    net_loss   = Decimal('0')
    if tot_cr >= tot_dr:
        net_profit = Q2(tot_cr - tot_dr)
        if net_profit > 0:
            debit_rows.append({"label": "Net Profit c/d", "amount": float(net_profit)})
            tot_dr += net_profit
    else:
        net_loss = Q2(tot_dr - tot_cr)
        if net_loss > 0:
            credit_rows.append({"label": "Net Loss c/d", "amount": float(net_loss)})
            tot_cr += net_loss

    # 5) Totals (equal by construction)
    debit_total  = Q2(tot_dr)
    credit_total = Q2(tot_cr)

    return {
        "period": {"start": str(start), "end": str(end)},
        "entity_id": entity_id,
        "params": {
            "level": level,
            "pl_detailsingroup_values": list(pl_detailsingroup_values),
            "trading_detailsingroup_values": list(trading_detailsingroup_values),
            "valuation_method": valuation_method
        },
        "debit_total": float(debit_total),
        "credit_total": float(credit_total),

        # Key results
        "gross_profit_brought_down": float(Q2(gross_profit)),
        "gross_loss_brought_down": float(Q2(gross_loss)),
        "net_profit": float(Q2(net_profit)),
        "net_loss": float(Q2(net_loss)),

        # Rows (T-format)
        "debit_rows": debit_rows,    # expenses + (Gross Loss b/d) + (Net Profit c/d)
        "credit_rows": credit_rows,  # income + (Gross Profit b/d) + (Net Loss c/d)

        "notes": [
            "P&L heads selected via accounthead.detailsingroup ∈ pl_detailsingroup_values (default: 2).",
            "Trading heads excluded via accounthead.detailsingroup ∈ trading_detailsingroup_values (default: 1).",
            "Gross Profit b/d appears on CREDIT; Gross Loss b/d appears on DEBIT.",
            "Net Profit c/d is the DEBIT balancing item; Net Loss c/d is the CREDIT balancing item."
        ],
        **({"warnings": warns} if warns else {})
    }
