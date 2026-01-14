from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from django.db.models import Sum, Case, When, F, Value, DecimalField
from django.db.models.functions import Abs
from invoice.models import InventoryMove

DEC_QTY = Decimal("0.0000")
DEC_VAL = Decimal("0.00")

def q4(v): return (Decimal(v) if v is not None else DEC_QTY).quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)
def q2(v): return (Decimal(v) if v is not None else DEC_VAL).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

def _apply_filters(qs, p):
    if "location" in p:
        qs = qs.filter(location=p["location"])
    if "locations" in p:
        qs = qs.filter(location__in=p["locations"])
    if "product" in p:
        qs = qs.filter(product_id=p["product"])
    if "products" in p:
        qs = qs.filter(product_id__in=p["products"])
    if "category" in p:
        qs = qs.filter(product__category_id=p["category"])
    if "brand" in p:
        qs = qs.filter(product__brand_id=p["brand"])
    if "hsn" in p:
        qs = qs.filter(product__hsn_id=p["hsn"])
    if "include_txn_types" in p:
        qs = qs.filter(transactiontype__in=p["include_txn_types"])
    if "exclude_txn_types" in p:
        qs = qs.exclude(transactiontype__in=p["exclude_txn_types"])
    if p.get("search"):
        qs = qs.filter(product__productname__icontains=p["search"])
    return qs

def compute_stock_movement(*, p):
    """
    Returns dict:
      summary_rows, details(optional), totals
    """
    entity_id = p["entity"]
    from_date = p["from_date"]
    to_date = p["to_date"]
    group_by_location = p.get("group_by_location", True)

    base_qs = InventoryMove.objects.filter(entity_id=entity_id).select_related("product")
    base_qs = _apply_filters(base_qs, p)

    # Opening = sum(qty/ext_cost) before from_date
    open_qs = base_qs.filter(entrydate__lt=from_date)

    open_group = ["product_id", "product__productname"]
    if group_by_location:
        open_group.append("location")

    opening_map_qty = {}
    opening_map_val = {}

    # ext_cost is abs(qty)*unit_cost per your model; for opening value we need signed effect:
    # For IN: +ext_cost, for OUT: -ext_cost
    signed_val_expr = Case(
        When(qty__gt=0, then=F("ext_cost")),
        When(qty__lt=0, then=Value(0) - F("ext_cost")),
        default=Value(0),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    for r in open_qs.values(*open_group).annotate(
        opening_qty=Sum("qty"),
        opening_val=Sum(signed_val_expr),
    ):
        key = (r["product_id"], r.get("location") if group_by_location else None)
        opening_map_qty[key] = q4(r["opening_qty"])
        opening_map_val[key] = q2(r["opening_val"])

    # Movements in range
    range_qs = base_qs.filter(entrydate__gte=from_date, entrydate__lte=to_date)

    group = ["product_id", "product__productname"]
    if group_by_location:
        group.append("location")

    in_qty_expr = Case(
        When(qty__gt=0, then=F("qty")),
        default=Value(0),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    out_qty_expr = Case(
        When(qty__lt=0, then=Abs(F("qty"))),
        default=Value(0),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )

    in_val_expr = Case(
        When(qty__gt=0, then=F("ext_cost")),
        default=Value(0),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    out_val_expr = Case(
        When(qty__lt=0, then=F("ext_cost")),
        default=Value(0),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    agg_rows = list(
        range_qs.values(*group).annotate(
            in_qty=Sum(in_qty_expr),
            out_qty=Sum(out_qty_expr),
            net_qty=Sum("qty"),
            in_value=Sum(in_val_expr),
            out_value=Sum(out_val_expr),
        ).order_by("product__productname")
    )

    summary = []
    totals = {"opening_qty": DEC_QTY, "opening_value": DEC_VAL,
              "in_qty": DEC_QTY, "in_value": DEC_VAL,
              "out_qty": DEC_QTY, "out_value": DEC_VAL,
              "closing_qty": DEC_QTY, "closing_value": DEC_VAL}

    for r in agg_rows:
        pid = r["product_id"]
        loc = r.get("location") if group_by_location else None
        key = (pid, loc)

        opening_qty = opening_map_qty.get(key, DEC_QTY)
        opening_val = opening_map_val.get(key, DEC_VAL)

        in_qty = q4(r["in_qty"])
        out_qty = q4(r["out_qty"])
        net_qty = q4(r["net_qty"])

        in_val = q2(r["in_value"])
        out_val = q2(r["out_value"])

        closing_qty = q4(opening_qty + net_qty)
        closing_val = q2(opening_val + in_val - out_val)

        if not p.get("include_zero", False) and closing_qty == DEC_QTY and in_qty == DEC_QTY and out_qty == DEC_QTY:
            continue

        row = {
            "product_id": pid,
            "product_name": r.get("product__productname"),
            "location": loc,
            "opening_qty": opening_qty,
            "opening_value": opening_val,
            "in_qty": in_qty,
            "in_value": in_val,
            "out_qty": out_qty,
            "out_value": out_val,
            "net_qty": net_qty,
            "closing_qty": closing_qty,
            "closing_value": closing_val,
        }
        summary.append(row)

        totals["opening_qty"] += opening_qty
        totals["opening_value"] += opening_val
        totals["in_qty"] += in_qty
        totals["in_value"] += in_val
        totals["out_qty"] += out_qty
        totals["out_value"] += out_val
        totals["closing_qty"] += closing_qty
        totals["closing_value"] += closing_val

    # Ordering
    ordv = p.get("ordering", "product")
    if ordv == "-value":
        summary.sort(key=lambda x: x["closing_value"], reverse=True)
    elif ordv == "value":
        summary.sort(key=lambda x: x["closing_value"])
    elif ordv == "-qty":
        summary.sort(key=lambda x: x["closing_qty"], reverse=True)
    elif ordv == "qty":
        summary.sort(key=lambda x: x["closing_qty"])
    elif ordv == "-product":
        summary.sort(key=lambda x: x["product_name"] or "", reverse=True)
    else:
        summary.sort(key=lambda x: x["product_name"] or "")

    # Details (optional)
    details = None
    if p.get("include_details"):
        dqs = range_qs.order_by("entrydate", "id").values(
            "entrydate", "transactiontype", "transactionid", "detailid", "voucherno",
            "product_id", "product__productname", "location",
            "qty", "unit_cost", "ext_cost", "move_type"
        )
        details = []
        for d in dqs:
            details.append({
                **d,
                "qty": q4(d["qty"]),
                "unit_cost": q4(d["unit_cost"]),
                "ext_cost": q2(d["ext_cost"]),
            })

    # finalize totals quantize
    totals = {k: (q4(v) if "qty" in k else q2(v)) for k, v in totals.items()}

    return {
        "summary": summary,
        "details": details,
        "totals": totals,
    }
