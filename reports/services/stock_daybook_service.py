from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Case, When, F, DecimalField, Value
from django.db.models.functions import Abs
from invoice.models import InventoryMove

DEC_QTY = Decimal("0.0000")
DEC_VAL = Decimal("0.00")

def q4(x) -> Decimal:
    return (Decimal(x) if x is not None else DEC_QTY).quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

def q2(x) -> Decimal:
    return (Decimal(x) if x is not None else DEC_VAL).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

def compute_stock_daybook(
    *,
    entity_id: int,
    from_date,
    to_date,
    product_id=None,
    location_id=None,
    group_by_location=True,
    include_details=False,
):
    """
    Stock Day Book:
    For each day (and product/location), show Opening, In, Out, Closing.
    Opening is computed as closing qty before from_date.
    """
    base_qs = InventoryMove.objects.filter(entity_id=entity_id)

    if product_id:
        base_qs = base_qs.filter(product_id=product_id)
    if location_id is not None:
        base_qs = base_qs.filter(location=location_id)

    # Opening (closing qty BEFORE from_date)
    open_qs = base_qs.filter(entrydate__lt=from_date)

    open_group_fields = ["product_id"]
    if group_by_location:
        open_group_fields.append("location")

    opening_map = {}
    for row in (
        open_qs.values(*open_group_fields)
        .annotate(opening_qty=Sum("qty"))
    ):
        key = (row["product_id"], row.get("location") if group_by_location else None)
        opening_map[key] = q4(row["opening_qty"])

    # Movements in range grouped day-wise
    range_qs = base_qs.filter(entrydate__gte=from_date, entrydate__lte=to_date).select_related("product")

    group_fields = ["entrydate", "product_id", "product__productname"]
    if group_by_location:
        group_fields.append("location")

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

    # value columns (optional but useful)
    # ext_cost is already abs(qty)*unit_cost per your model comment
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

    day_rows = list(
        range_qs.values(*group_fields).annotate(
            in_qty=Sum(in_qty_expr),
            out_qty=Sum(out_qty_expr),
            net_qty=Sum("qty"),
            in_value=Sum(in_val_expr),
            out_value=Sum(out_val_expr),
        ).order_by("entrydate", "product__productname")
    )

    # Build daybook with running closing per (product,location)
    running_qty = dict(opening_map)  # key -> qty

    results = []
    for r in day_rows:
        pid = r["product_id"]
        loc = r.get("location") if group_by_location else None
        key = (pid, loc)

        opening_qty = running_qty.get(key, DEC_QTY)
        in_qty = q4(r["in_qty"])
        out_qty = q4(r["out_qty"])
        net_qty = q4(r["net_qty"])
        closing_qty = q4(opening_qty + net_qty)

        running_qty[key] = closing_qty

        results.append({
            "date": str(r["entrydate"]),
            "product_id": pid,
            "product_name": r.get("product__productname"),
            "location": loc,
            "opening_qty": str(opening_qty),
            "in_qty": str(in_qty),
            "out_qty": str(out_qty),
            "closing_qty": str(closing_qty),
            "in_value": str(q2(r.get("in_value"))),
            "out_value": str(q2(r.get("out_value"))),
        })

    payload = {
        "rows": results,
        "from_date": str(from_date),
        "to_date": str(to_date),
    }

    # Optional: add voucher-level details
    if include_details:
        details = list(
            range_qs.order_by("entrydate", "id").values(
                "entrydate",
                "transactiontype",
                "transactionid",
                "detailid",
                "voucherno",
                "product_id",
                "product__productname",
                "location",
                "qty",
                "unit_cost",
                "ext_cost",
                "move_type",
            )
        )
        # stringify decimals safely
        for d in details:
            d["qty"] = str(q4(d["qty"]))
            d["unit_cost"] = str(q4(d["unit_cost"]))
            d["ext_cost"] = str(q2(d["ext_cost"]))
        payload["details"] = details

    return payload
