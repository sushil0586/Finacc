# reports/services/stock_ledger_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Dict, Any, List

from invoice.models import InventoryMove  # adjust import
from reports.serializers import StockValuationMethod

DEC_QTY = Decimal("0.0000")
DEC_VAL = Decimal("0.00")


def q4(x) -> Decimal:
    return (Decimal(x) if x is not None else DEC_QTY).quantize(DEC_QTY, rounding=ROUND_HALF_UP)


def q2(x) -> Decimal:
    return (Decimal(x) if x is not None else DEC_VAL).quantize(DEC_VAL, rounding=ROUND_HALF_UP)

def _pos_unit_cost_from_amount(amount: Decimal, out_qty: Decimal) -> Decimal:
    """
    amount is signed (OUT negative), out_qty positive
    returns positive unit cost that MATCHES the amount.
    """
    if out_qty == 0:
        return Decimal("0")
    return abs(Decimal(amount)) / Decimal(out_qty)


def fifo_opening(moves_upto_before_from_date):
    layers = []
    bal_qty = Decimal("0")
    bal_val = Decimal("0")

    for m in moves_upto_before_from_date:
        qty = Decimal(m["qty"])
        unit_cost_in = Decimal(m["unit_cost"] or 0)

        if qty > 0:
            layers.append([qty, unit_cost_in])
            bal_qty += qty
            bal_val += qty * unit_cost_in
        else:
            out_qty = -qty
            remaining = out_qty
            issue_val = Decimal("0")

            while remaining > 0 and layers:
                layer_qty, layer_cost = layers[0]
                take = layer_qty if layer_qty <= remaining else remaining
                issue_val += take * layer_cost
                layer_qty -= take
                remaining -= take
                if layer_qty == 0:
                    layers.pop(0)
                else:
                    layers[0][0] = layer_qty

            if remaining > 0:
                last_cost = layers[-1][1] if layers else unit_cost_in
                issue_val += remaining * (last_cost or Decimal("0"))

            bal_qty -= out_qty
            bal_val -= issue_val

    return q4(bal_qty), q2(bal_val)


def wavg_opening(moves_upto_before_from_date):
    bal_qty = Decimal("0")
    bal_val = Decimal("0")
    avg = Decimal("0")

    for m in moves_upto_before_from_date:
        qty = Decimal(m["qty"])
        unit_cost = Decimal(m["unit_cost"] or 0)

        if qty > 0:
            bal_qty += qty
            bal_val += qty * unit_cost
            avg = (bal_val / bal_qty) if bal_qty != 0 else Decimal("0")
        else:
            out_qty = -qty
            bal_qty -= out_qty
            bal_val -= out_qty * avg
            if bal_qty == 0:
                bal_val = Decimal("0")
                avg = Decimal("0")

    return q4(bal_qty), q2(bal_val)


def wavg_rows(moves_in_range, opening_qty, opening_val):
    bal_qty = Decimal(opening_qty)
    bal_val = Decimal(opening_val)
    avg = (bal_val / bal_qty) if bal_qty != 0 else Decimal("0")

    rows = []
    for m in moves_in_range:
        qty = Decimal(m["qty"])
        unit_cost = Decimal(m["unit_cost"] or 0)

        if qty > 0:
            move_cost = qty * unit_cost
            bal_qty += qty
            bal_val += move_cost
            avg = (bal_val / bal_qty) if bal_qty != 0 else Decimal("0")
            used_uc = unit_cost
        else:
            out_qty = -qty
            move_cost = -(out_qty * avg)
            bal_qty -= out_qty
            bal_val += move_cost
            if bal_qty == 0:
                bal_val = Decimal("0")
                avg = Decimal("0")
            used_uc = avg

        rows.append({
            "entrydate": m["entrydate"],
            "transactiontype": m["transactiontype"],
            "transactionid": m["transactionid"],
            "detailid": m["detailid"],
            "voucherno": m["voucherno"],
            "qty_in": q4(qty) if qty > 0 else DEC_QTY,
            "qty_out": q4(-qty) if qty < 0 else DEC_QTY,
            "unit_cost": q4(used_uc),
            "amount": q2(move_cost),
            "balance_qty": q4(bal_qty),
            "balance_value": q2(bal_val),
        })
    return rows


def _resolve_entity_and_product_names(entity_id: int, product_id: int) -> Tuple[str, str]:
    """
    Adjust imports/fieldnames as per your project.
    Safe fallbacks included.
    """
    entity_name = f"Entity#{entity_id}"
    product_name = f"Product#{product_id}"

    try:
        from entity.models import Entity  # adjust app name if different
        e = Entity.objects.only("id", "entityname").filter(id=entity_id).first()
        if e:
            entity_name = getattr(e, "entityname", None) or getattr(e, "name", None) or entity_name
    except Exception:
        pass

    try:
        from catalog.models import Product  # adjust app name if different
        p = Product.objects.only("id", "productname").filter(id=product_id).first()
        if p:
            product_name = getattr(p, "productname", None) or getattr(p, "name", None) or product_name
    except Exception:
        pass

    return entity_name, product_name


def compute_stock_ledger(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes ledger for the full range (no pagination).
    Returns dict:
      { meta..., opening..., results..., closing..., totals... }
    """
    entity_id = p["entity"]
    product_id = p["product"]
    from_date = p["from_date"]
    to_date = p["to_date"]
    method = p.get("valuation_method", StockValuationMethod.FIFO)

    entity_name, product_name = _resolve_entity_and_product_names(entity_id, product_id)

    base = InventoryMove.objects.filter(entity_id=entity_id, product_id=product_id)

    # location filter (NULL allowed)
    if "location" in p:
        base = base.filter(location=p["location"])

    # txn type filters (audit)
    if "include_txn_types" in p:
        base = base.filter(transactiontype__in=p["include_txn_types"])
    if "exclude_txn_types" in p:
        base = base.exclude(transactiontype__in=p["exclude_txn_types"])

    # Ordering
    if p.get("ordering") == "date_desc":
        order_by = ["-entrydate", "-id"]
    else:
        order_by = ["entrydate", "id"]

    opening_moves = list(
        base.filter(entrydate__lt=from_date)
        .order_by("entrydate", "id")
        .values("entrydate", "transactiontype", "transactionid", "detailid", "voucherno", "qty", "unit_cost", "ext_cost")

    )

    range_moves = list(
        base.filter(entrydate__gte=from_date, entrydate__lte=to_date)
        .order_by(*order_by)
        .values("entrydate", "transactiontype", "transactionid", "detailid", "voucherno", "qty", "unit_cost", "ext_cost")


    )

    if method == StockValuationMethod.FIFO:
        opening_qty, opening_val = fifo_opening(opening_moves)

        all_moves = list(
            base.filter(entrydate__lte=to_date)
            .order_by("entrydate", "id")
            .values("entrydate", "transactiontype", "transactionid", "detailid", "voucherno", "qty", "unit_cost", "ext_cost")

        )

        layers = []
        bal_qty = Decimal("0")
        bal_val = Decimal("0")
        rows = []
        last_known_cost = Decimal("0")

        for m in all_moves:
            dt = m["entrydate"]
            qty = Decimal(m["qty"])

            stored_uc = Decimal(m.get("unit_cost") or 0)
            stored_ext = Decimal(m.get("ext_cost") or 0)  # in your model: positive abs value

            if qty > 0:
                # IN: layer uses stored unit_cost
                layers.append([qty, stored_uc])

                if stored_uc > 0:
                    last_known_cost = stored_uc

                # amount: prefer stored ext_cost if available else qty*unit_cost
                move_cost = stored_ext if stored_ext > 0 else (qty * stored_uc)

                bal_qty += qty
                bal_val += move_cost

                used_uc = stored_uc if stored_uc > 0 else (move_cost / qty if qty else Decimal("0"))

            else:
                # OUT
                out_qty = -qty
                remaining = out_qty

                fifo_issue_val = Decimal("0")
                fifo_issue_weighted = Decimal("0")
                last_consumed_cost = None

                # consume FIFO layers
                while remaining > 0 and layers:
                    lq, lc = layers[0]
                    take = lq if lq <= remaining else remaining

                    fifo_issue_val += take * lc
                    fifo_issue_weighted += take * lc
                    last_consumed_cost = lc

                    lq -= take
                    remaining -= take

                    if lq == 0:
                        layers.pop(0)
                    else:
                        layers[0][0] = lq

                # negative stock fallback (never use 0)
                if remaining > 0:
                    fallback_cost = (
                        last_consumed_cost
                        if last_consumed_cost is not None
                        else (layers[-1][1] if layers else None)
                    )
                    if fallback_cost is None or fallback_cost == 0:
                        fallback_cost = last_known_cost
                    if fallback_cost == 0:
                        fallback_cost = stored_uc  # last resort (if posting stored something)

                    fifo_issue_val += remaining * fallback_cost
                    fifo_issue_weighted += remaining * fallback_cost

                # ✅ amount: prefer posted ext_cost if available
                # stored_ext is ABS, so move_cost should be negative for OUT
                if stored_ext > 0:
                    move_cost = -stored_ext
                else:
                    move_cost = -fifo_issue_val

                # ✅ unit_cost MUST match amount
                used_uc = _pos_unit_cost_from_amount(move_cost, out_qty)

                # update balances using chosen amount
                bal_qty -= out_qty
                bal_val += move_cost

            if from_date <= dt <= to_date:
                rows.append({
                    "entrydate": dt,
                    "transactiontype": m["transactiontype"],
                    "transactionid": m["transactionid"],
                    "detailid": m["detailid"],
                    "voucherno": m["voucherno"],
                    "qty_in": q4(qty) if qty > 0 else DEC_QTY,
                    "qty_out": q4(-qty) if qty < 0 else DEC_QTY,
                    "unit_cost": q4(used_uc),
                    "amount": q2(move_cost),
                    "balance_qty": q4(bal_qty),
                    "balance_value": q2(bal_val),
                })
    else:
        opening_qty, opening_val = wavg_opening(opening_moves)
        rows = wavg_rows(range_moves, opening_qty, opening_val)

    if rows:
        closing_qty = rows[-1]["balance_qty"]
        closing_val = rows[-1]["balance_value"]
    else:
        closing_qty = opening_qty
        closing_val = opening_val

    # Totals
    total_in_qty = sum((Decimal(r["qty_in"]) for r in rows), Decimal("0"))
    total_out_qty = sum((Decimal(r["qty_out"]) for r in rows), Decimal("0"))
    total_amount = sum((Decimal(r["amount"]) for r in rows), Decimal("0"))  # signed
    net_qty = total_in_qty - total_out_qty

    totals = {
        "total_in_qty": str(q4(total_in_qty)),
        "total_out_qty": str(q4(total_out_qty)),
        "net_qty": str(q4(net_qty)),
        "total_amount": str(q2(total_amount)),
        "rows": len(rows),
    }

    return {
        "entity": entity_id,
        "entity_name": entity_name,
        "product": product_id,
        "product_name": product_name,
        "location": p.get("location", None),
        "from_date": str(from_date),
        "to_date": str(to_date),
        "valuation_method": method,
        "opening": {"qty": str(opening_qty), "value": str(opening_val)},
        "closing": {"qty": str(closing_qty), "value": str(closing_val)},
        "totals": totals,
        "results": rows,
    }
