from collections import defaultdict
from decimal import Decimal
from django.db.models import Q

from invoice.models import InventoryMove
from decimal import Decimal, ROUND_HALF_UP

DEC_QTY = Decimal("0.0000")
DEC_VAL = Decimal("0.00")
def q4(x) -> Decimal:
    return (Decimal(x) if x is not None else DEC_QTY).quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

def q2(x) -> Decimal:
    return (Decimal(x) if x is not None else DEC_VAL).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

DEC_QTY = Decimal("0.0000")

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

def _make_bucket_labels(bucket_ends):
    # [30,60,90,180] -> ["0-30","31-60","61-90","91-180","181+"]
    labels = []
    start = 0
    for end in bucket_ends:
        labels.append((start, end, f"{start}-{end}" if start == 0 else f"{start+1}-{end}"))
        start = end
    labels.append((start + 1, 10_000_000, f"{start+1}+"))
    return labels

def compute_stock_aging(*, p):
    """
    Returns:
      rows: list with one row per product (+ location)
      bucket_labels: list[str] in order
      totals: per bucket totals
    """
    entity_id = p["entity"]
    as_on = p["as_on_date"]
    group_by_location = p.get("group_by_location", True)
    include_zero = p.get("include_zero", False)
    bucket_ends = p.get("bucket_ends", [30, 60, 90, 180])

    bucket_defs = _make_bucket_labels(bucket_ends)
    bucket_labels = [b[2] for b in bucket_defs]

    qs = InventoryMove.objects.filter(entity_id=entity_id, entrydate__lte=as_on).select_related("product")
    qs = _apply_filters(qs, p)
    qs = qs.order_by("product_id", "location", "entrydate", "id").values(
        "product_id",
        "product__productname",
        "location",
        "qty",
        "unit_cost",
        "entrydate",
    )

    def key_of(r):
        return (r["product_id"], r["location"] if group_by_location else None)

    layers = defaultdict(list)  # key -> list of [qty_remaining, entrydate, unit_cost]
    names = {}

    # Build FIFO layers and consume OUT
    for r in qs:
        key = key_of(r)
        names[r["product_id"]] = r["product__productname"]

        mqty = q4(r["qty"])
        if mqty > 0:
            layers[key].append([mqty, r["entrydate"], r["unit_cost"]])
        else:
            out = q4(-mqty)
            while out > 0 and layers[key]:
                l = layers[key][0]
                take = min(out, l[0])
                l[0] = q4(l[0] - take)
                out = q4(out - take)
                if l[0] == DEC_QTY:
                    layers[key].pop(0)
            # if negative stock remains, ignore for aging (no layer to age)

    rows = []
    totals = {lbl: DEC_QTY for lbl in bucket_labels}
    total_closing = DEC_QTY

    for (pid, loc), layer_list in layers.items():
        bucket_qty = {lbl: DEC_QTY for lbl in bucket_labels}
        closing_qty = DEC_QTY

        for q, dt, cost in layer_list:
            if q == DEC_QTY:
                continue
            age_days = (as_on - dt).days
            closing_qty += q

            # assign to bucket
            for start, end, lbl in bucket_defs:
                if start <= age_days <= end:
                    bucket_qty[lbl] += q
                    break

        if not include_zero and closing_qty == DEC_QTY:
            continue

        for lbl in bucket_labels:
            totals[lbl] += bucket_qty[lbl]
        total_closing += closing_qty

        rows.append({
            "product_id": pid,
            "product_name": names.get(pid),
            "location": loc,
            "closing_qty": closing_qty,
            "buckets": bucket_qty,  # lbl -> qty
        })

    # ordering
    ordv = p.get("ordering", "product")
    if ordv == "-qty":
        rows.sort(key=lambda r: r["closing_qty"], reverse=True)
    elif ordv == "qty":
        rows.sort(key=lambda r: r["closing_qty"])
    elif ordv == "-product":
        rows.sort(key=lambda r: (r["product_name"] or ""), reverse=True)
    else:
        rows.sort(key=lambda r: (r["product_name"] or ""))

    return rows, bucket_labels, {"closing_qty": total_closing, "buckets": totals}
