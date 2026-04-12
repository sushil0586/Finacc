from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP

from catalog.models import Product
from reports.selectors.financial import resolve_scope_names
from reports.services.inventory.stock_ledger import (
    _apply_movement,
    _build_product_map,
    _movement_rows,
    _new_valuation_state,
    _normalize_method,
    _product_filters,
    _snapshot_state,
)
from reports.services.inventory.stock_summary import _planning_for_product, _status_for_row, _product_hsn
from posting.models import InventoryMove


ZERO = Decimal("0")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


def _q2(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.00") else Decimal("0.00")


def _q4(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.0000") else Decimal("0.0000")


def _resolve_dates(*, entityfin_id=None, from_date=None, to_date=None, as_of_date=None):
    start_date = from_date
    end_date = to_date or as_of_date
    if entityfin_id:
        from entity.models import EntityFinancialYear

        fy = EntityFinancialYear.objects.filter(id=entityfin_id).only("finstartyear", "finendyear").first()
        if fy:
            if start_date is None:
                start_date = getattr(fy.finstartyear, "date", lambda: fy.finstartyear)()
            if end_date is None:
                end_date = getattr(fy.finendyear, "date", lambda: fy.finendyear)()
    if end_date is None:
        end_date = as_of_date or date_cls.today()
    return start_date, end_date


def _normalize_bucket_ends(bucket_ends) -> list[int]:
    if bucket_ends in (None, "", []):
        return [30, 60, 90, 120, 150]
    values = []
    if isinstance(bucket_ends, str):
        parts = bucket_ends.split(",")
    else:
        parts = bucket_ends
    for item in parts:
        text = str(item).strip()
        if not text:
            continue
        try:
            value = int(float(text))
        except ValueError:
            continue
        if value > 0:
            values.append(value)
    unique = sorted(set(values))
    return unique or [30, 60, 90, 120, 150]


def _bucket_definitions(bucket_ends: list[int]) -> list[dict]:
    definitions = []
    previous = 0
    for end in bucket_ends:
        definitions.append(
            {
                "key": f"{previous}_{end}",
                "label": f"{previous + 1}-{end}" if previous else f"0-{end}",
                "start": previous,
                "end": end,
            }
        )
        previous = end
    definitions.append(
        {
            "key": f"{previous}_plus",
            "label": f"{previous}+",
            "start": previous,
            "end": None,
        }
    )
    definitions.append(
        {
            "key": "no_movement",
            "label": "No Movement",
            "start": None,
            "end": None,
        }
    )
    return definitions


def _bucket_for_age(age_days: int | None, definitions: list[dict]) -> dict:
    if age_days is None:
        return definitions[-1]
    for definition in definitions[:-2]:
        if age_days <= definition["end"]:
            return definition
    return definitions[-2]


def _sort_rows(rows: list[dict], *, sort_by: str, sort_order: str):
    reverse = (sort_order or "desc").lower() == "desc"

    def key(row):
        if sort_by == "age_days":
            return row.get("_age_days_sort") or 10**9
        if sort_by == "qty":
            return Decimal(row["closing_qty"])
        if sort_by == "name":
            return str(row.get("product_name") or "").lower()
        if sort_by == "sku":
            return str(row.get("sku") or "").lower()
        if sort_by == "last_movement_date":
            return row.get("last_movement_date") or ""
        if sort_by == "bucket":
            return str(row.get("age_bucket") or "")
        return Decimal(row["closing_value"])

    return sorted(rows, key=key, reverse=reverse)


def build_inventory_stock_aging(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    valuation_method: str = "fifo",
    bucket_ends: list[int] | None = None,
    group_by_location: bool = True,
    product_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
    hsn_ids: list[int] | None = None,
    location_ids: list[int] | None = None,
    search: str | None = None,
    include_zero: bool = False,
    include_negative: bool = True,
    sort_by: str = "age_days",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    method = _normalize_method(valuation_method)
    start_date, end_date = _resolve_dates(
        entityfin_id=entityfin_id,
        from_date=from_date,
        to_date=to_date,
        as_of_date=as_of_date,
    )
    bucket_ends = _normalize_bucket_ends(bucket_ends)
    bucket_definitions = _bucket_definitions(bucket_ends)

    base_qs = InventoryMove.objects.filter(
        _product_filters(
            entity_id,
            product_ids=product_ids,
            category_ids=category_ids,
            hsn_ids=hsn_ids,
            location_ids=location_ids,
            search=search,
        )
    )
    if entityfin_id:
        base_qs = base_qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        base_qs = base_qs.filter(subentity_id=subentity_id)

    move_rows = _movement_rows(base_qs.filter(posting_date__lte=end_date))
    product_ids_in_scope = sorted({row["product_id"] for row in move_rows})
    product_map = _build_product_map(entity_id, product_ids_in_scope)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    groups: dict[tuple, dict] = {}
    for row in move_rows:
        product_id = row["product_id"]
        location_id = row.get("location_id")
        key = (product_id, location_id) if group_by_location else (product_id, None)
        group = groups.setdefault(
            key,
            {
                "state": _new_valuation_state(method),
                "last_movement_date": None,
                "movement_count": 0,
                "location_name": (row.get("location__name") or row.get("location__code")) if group_by_location else "All Locations",
                "location_id": location_id,
            },
        )
        _apply_movement(group["state"], row, method)
        group["movement_count"] += 1
        current_date = row.get("posting_date")
        if current_date and (group["last_movement_date"] is None or current_date > group["last_movement_date"]):
            group["last_movement_date"] = current_date

    rows = []
    bucket_totals: dict[str, dict[str, Decimal | int]] = {
        definition["label"]: {"qty": ZERO, "value": ZERO, "count": 0} for definition in bucket_definitions
    }
    total_qty = ZERO
    total_value = ZERO
    non_moving_qty = ZERO
    aged_90_plus_qty = ZERO
    oldest_age_days = 0

    for (product_id, location_id), group in groups.items():
        product = product_map.get(product_id)
        if product is None:
            continue

        closing_qty, closing_value = _snapshot_state(group["state"], method)
        closing_qty = _q4(closing_qty)
        closing_value = _q2(closing_value)
        if not include_negative and closing_qty < 0:
            continue
        if not include_zero and closing_qty == 0:
            continue

        age_days = None
        if group["last_movement_date"] is not None:
            age_days = max((end_date - group["last_movement_date"]).days, 0)
            oldest_age_days = max(oldest_age_days, age_days)

        bucket = _bucket_for_age(age_days, bucket_definitions)
        bucket_label = bucket["label"]

        planning = _planning_for_product(product)
        hsn = _product_hsn(product)
        rate = _q4((closing_value / closing_qty) if closing_qty else ZERO)
        stock_status = _status_for_row(qty=closing_qty, planning=planning)

        rows.append(
            {
                "product_id": product_id,
                "sku": getattr(product, "sku", None),
                "product_name": getattr(product, "productname", None),
                "product_description": getattr(product, "productdesc", None),
                "category_id": getattr(product, "productcategory_id", None),
                "category_name": getattr(getattr(product, "productcategory", None), "pcategoryname", None),
                "location_id": location_id,
                "location_name": group["location_name"] or "All Locations",
                **hsn,
                **planning,
                "closing_qty": str(closing_qty),
                "closing_value": str(closing_value),
                "rate": str(rate),
                "movement_count": group["movement_count"],
                "last_movement_date": group["last_movement_date"].isoformat() if group["last_movement_date"] else None,
                "age_days": age_days,
                "age_bucket": bucket_label,
                "stock_status": stock_status,
                "stock_gap": str(_q4(closing_qty - Decimal(str(planning["reorder_level"]))) if planning.get("reorder_level") is not None else ZERO),
                "_age_days_sort": age_days if age_days is not None else 10**9,
            }
        )

        total_qty += closing_qty
        total_value += closing_value
        bucket_totals[bucket_label]["qty"] += closing_qty
        bucket_totals[bucket_label]["value"] += closing_value
        bucket_totals[bucket_label]["count"] += 1

        if age_days is None:
            non_moving_qty += closing_qty
        if age_days is not None and age_days >= 90:
            aged_90_plus_qty += closing_qty

    rows = _sort_rows(rows, sort_by=(sort_by or "age_days").lower(), sort_order=sort_order)
    for row in rows:
        row.pop("_age_days_sort", None)

    count = len(rows)
    if paginate:
        page = max(1, page)
        page_size = max(1, page_size)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        pages = (count + page_size - 1) // page_size if count else 0
    else:
        page_rows = rows
        pages = 1 if count else 0
        page = 1
        page_size = count or page_size

    summary = {
        "product_count": count,
        "total_qty": str(_q4(total_qty)),
        "total_value": str(_q2(total_value)),
        "aged_90_plus_qty": str(_q4(aged_90_plus_qty)),
        "non_moving_qty": str(_q4(non_moving_qty)),
        "oldest_age_days": oldest_age_days,
        "bucket_totals": {
            label: {
                "qty": str(_q4(values["qty"])),
                "value": str(_q2(values["value"])),
                "count": values["count"],
            }
            for label, values in bucket_totals.items()
        },
    }
    totals = {
        "closing_qty": summary["total_qty"],
        "closing_value": summary["total_value"],
        "aged_90_plus_qty": summary["aged_90_plus_qty"],
        "non_moving_qty": summary["non_moving_qty"],
    }
    pagination = {
        "count": count,
        "page": page,
        "pages": pages,
        "page_size": page_size,
    }

    return {
        "summary": summary,
        "totals": totals,
        "rows": page_rows,
        "pagination": pagination,
        "bucket_labels": [definition["label"] for definition in bucket_definitions],
        "bucket_ends": bucket_ends,
        "group_by_location": bool(group_by_location),
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_stock_aging",
            "available_exports": [],
            "available_drilldowns": [],
            "end_date": end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
            "start_date": start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date) if start_date else None,
        },
    }
