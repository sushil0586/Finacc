from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls, datetime
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from entity.models import Godown
from reports.selectors.financial import resolve_scope_names
from reports.services.inventory.stock_summary import build_inventory_stock_summary


ZERO = Decimal("0")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


def _q2(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.00") else Decimal("0.00")


def _q4(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.0000") else Decimal("0.0000")


def _to_iso_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date_cls):
        return value.isoformat()
    return str(value)


def _resolve_end_date(*, from_date=None, to_date=None, as_of_date=None):
    if as_of_date:
        return as_of_date
    if to_date:
        return to_date
    if from_date:
        return from_date
    return date_cls.today()


def _sort_rows(rows: list[dict], *, sort_by: str, sort_order: str):
    reverse = (sort_order or "desc").lower() == "desc"

    def key(row):
        if sort_by in {"qty", "closing_qty", "total_qty"}:
            return Decimal(str(row.get("closing_qty") or "0"))
        if sort_by in {"value", "closing_value", "total_value"}:
            return Decimal(str(row.get("closing_value") or "0"))
        if sort_by in {"movement_count", "count"}:
            return int(row.get("movement_count") or 0)
        if sort_by in {"product_count", "products"}:
            return int(row.get("product_count") or 0)
        if sort_by in {"last_movement_date", "date"}:
            return row.get("last_movement_date") or ""
        if sort_by == "location":
            return str(row.get("location_name") or "").lower()
        return Decimal(str(row.get("closing_value") or "0"))

    return sorted(rows, key=key, reverse=reverse)


def build_inventory_location_stock(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    valuation_method: str = "fifo",
    product_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
    hsn_ids: list[int] | None = None,
    location_ids: list[int] | None = None,
    search: str | None = None,
    include_zero: bool = True,
    include_negative: bool = True,
    sort_by: str = "value",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    end_date = _resolve_end_date(from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    base_location_ids = location_ids or list(
        Godown.objects.filter(entity_id=entity_id, is_active=True).values_list("id", flat=True)
    )
    location_map = {
        row["id"]: row
        for row in Godown.objects.filter(entity_id=entity_id, id__in=base_location_ids, is_active=True).values("id", "name", "code", "city", "state")
    }
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    groups: dict[int, dict] = {}
    for location_id in base_location_ids:
        location = location_map.get(int(location_id), {})
        location_summary = build_inventory_stock_summary(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=from_date,
            to_date=to_date,
            as_of_date=as_of_date,
            valuation_method=valuation_method,
            product_ids=product_ids,
            category_ids=category_ids,
            hsn_ids=hsn_ids,
            location_ids=[int(location_id)],
            include_zero=include_zero,
            include_negative=include_negative,
            search=search,
            sort_by="value",
            sort_order="desc",
            page=1,
            page_size=100000,
            paginate=False,
        )
        rows_for_location = list(location_summary.get("rows") or [])
        if not rows_for_location:
            continue

        bucket = {
            "location_id": int(location_id),
            "location_name": location.get("name") or location.get("code") or "Location",
            "location_code": location.get("code"),
            "city": location.get("city"),
            "state": location.get("state"),
            "product_count": int(location_summary.get("summary", {}).get("product_count") or 0),
            "movement_count": int(location_summary.get("summary", {}).get("movement_count") or 0),
            "closing_qty": Decimal(str(location_summary.get("summary", {}).get("total_qty") or "0")),
            "closing_value": Decimal(str(location_summary.get("summary", {}).get("total_value") or "0")),
            "low_stock_count": int(location_summary.get("summary", {}).get("low_stock_count") or 0),
            "negative_stock_count": int(location_summary.get("summary", {}).get("negative_stock_count") or 0),
            "zero_stock_count": int(location_summary.get("summary", {}).get("zero_stock_count") or 0),
            "first_movement_date": None,
            "last_movement_date": None,
        }

        for row in rows_for_location:
            first_movement = _to_iso_date(row.get("last_movement_date") or row.get("first_movement_date"))
            last_movement = _to_iso_date(row.get("last_movement_date"))
            if first_movement:
                if bucket["first_movement_date"] is None or first_movement < bucket["first_movement_date"]:
                    bucket["first_movement_date"] = first_movement
            if last_movement:
                if bucket["last_movement_date"] is None or last_movement > bucket["last_movement_date"]:
                    bucket["last_movement_date"] = last_movement

        groups[int(location_id)] = bucket

    rows = []
    total_product_count = 0
    total_movement_count = 0
    total_closing_qty = ZERO
    total_closing_value = ZERO
    low_stock_count = 0
    negative_stock_count = 0
    zero_stock_count = 0

    for bucket in groups.values():
        closing_qty = _q4(bucket["closing_qty"])
        closing_value = _q2(bucket["closing_value"])

        stock_status = "ok"
        if closing_qty < 0:
            stock_status = "negative"
        elif closing_qty == 0:
            stock_status = "out_of_stock"
        elif bucket["low_stock_count"] > 0:
            stock_status = "low"

        row = {
            "location_id": bucket["location_id"],
            "location_name": bucket["location_name"],
            "location_code": bucket["location_code"],
            "city": bucket["city"],
            "state": bucket["state"],
            "product_count": bucket["product_count"],
            "movement_count": bucket["movement_count"],
            "closing_qty": str(closing_qty),
            "closing_value": str(closing_value),
            "rate": str(_q4((closing_value / closing_qty) if closing_qty else ZERO)),
            "low_stock_count": bucket["low_stock_count"],
            "negative_stock_count": bucket["negative_stock_count"],
            "zero_stock_count": bucket["zero_stock_count"],
            "first_movement_date": bucket["first_movement_date"],
            "last_movement_date": bucket["last_movement_date"],
            "stock_status": stock_status,
        }
        rows.append(row)

        total_product_count += bucket["product_count"]
        total_movement_count += bucket["movement_count"]
        total_closing_qty += closing_qty
        total_closing_value += closing_value
        low_stock_count += bucket["low_stock_count"]
        negative_stock_count += bucket["negative_stock_count"]
        zero_stock_count += bucket["zero_stock_count"]

    rows = _sort_rows(rows, sort_by=(sort_by or "value").lower(), sort_order=sort_order)
    count = len(rows)
    if paginate:
        page = max(1, page)
        page_size = max(1, page_size)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        pages = ceil(count / page_size) if count else 0
    else:
        page_rows = rows
        pages = 1 if count else 0
        page = 1
        page_size = count or page_size

    summary_payload = {
        "location_count": count,
        "product_count": total_product_count,
        "movement_count": total_movement_count,
        "closing_qty": str(_q4(total_closing_qty)),
        "closing_value": str(_q2(total_closing_value)),
        "low_stock_count": low_stock_count,
        "negative_stock_count": negative_stock_count,
        "zero_stock_count": zero_stock_count,
    }
    totals = {
        "closing_qty": summary_payload["closing_qty"],
        "closing_value": summary_payload["closing_value"],
        "product_count": summary_payload["product_count"],
        "movement_count": summary_payload["movement_count"],
    }
    pagination = {
        "count": count,
        "page": page,
        "pages": pages,
        "page_size": page_size,
    }
    return {
        "summary": summary_payload,
        "totals": totals,
        "rows": page_rows,
        "pagination": pagination,
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_location_stock",
            "available_exports": [],
            "available_drilldowns": [],
            "end_date": end_date.isoformat() if isinstance(end_date, date_cls) else str(end_date),
        },
    }
