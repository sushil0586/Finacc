from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from reports.selectors.financial import resolve_scope_names
from reports.services.inventory.stock_summary import build_inventory_stock_summary


ZERO = Decimal("0")
Q4 = Decimal("0.0001")


def _q4(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.0000") else Decimal("0.0000")


def _resolve_end_date(*, from_date=None, to_date=None, as_of_date=None):
    if as_of_date:
        return as_of_date
    if to_date:
        return to_date
    if from_date:
        return from_date
    return date_cls.today()


def _parse_non_moving_days(value) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 90
    return days if days > 0 else 90


def _sort_rows(rows: list[dict], *, sort_by: str, sort_order: str):
    reverse = (sort_order or "desc").lower() == "desc"

    def key(row):
        if sort_by in {"qty", "closing_qty", "total_qty"}:
            return Decimal(str(row.get("closing_qty") or "0"))
        if sort_by in {"value", "closing_value", "total_value"}:
            return Decimal(str(row.get("closing_value") or "0"))
        if sort_by in {"gap", "stock_gap", "reorder_gap"}:
            return Decimal(str(row.get("stock_gap") or row.get("reorder_gap") or "0"))
        if sort_by in {"age_days", "last_movement_date"}:
            return row.get("age_days_sort") or 10**9
        if sort_by == "name":
            return str(row.get("product_name") or "").lower()
        if sort_by == "sku":
            return str(row.get("sku") or "").lower()
        return Decimal(str(row.get("closing_value") or "0"))

    return sorted(rows, key=key, reverse=reverse)


def _base_summary_rows(
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
):
    data = build_inventory_stock_summary(
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
        location_ids=location_ids,
        include_zero=True,
        include_negative=True,
        search=search,
        sort_by="value",
        sort_order="desc",
        page=1,
        page_size=100000,
        paginate=False,
    )
    return data


def _base_row_payload(row: dict, *, end_date, report_variant: str) -> dict:
    last_movement_date = row.get("last_movement_date")
    age_days = None
    if last_movement_date:
        try:
            last_date = date_cls.fromisoformat(str(last_movement_date))
            age_days = max((end_date - last_date).days, 0)
        except ValueError:
            age_days = None
    return {
        "product_id": row.get("product_id"),
        "sku": row.get("sku"),
        "product_name": row.get("product_name"),
        "product_description": row.get("product_description"),
        "category_id": row.get("category_id"),
        "category_name": row.get("category_name"),
        "uom_id": row.get("uom_id"),
        "uom_name": row.get("uom_name"),
        "hsn_id": row.get("hsn_id"),
        "hsn_code": row.get("hsn_code"),
        "hsn_description": row.get("hsn_description"),
        "location_id": row.get("location_id"),
        "location_name": row.get("location_name"),
        "min_stock": row.get("min_stock"),
        "max_stock": row.get("max_stock"),
        "reorder_level": row.get("reorder_level"),
        "reorder_qty": row.get("reorder_qty"),
        "lead_time_days": row.get("lead_time_days"),
        "abc_class": row.get("abc_class"),
        "fsn_class": row.get("fsn_class"),
        "closing_qty": row.get("closing_qty"),
        "closing_value": row.get("closing_value"),
        "rate": row.get("rate"),
        "movement_count": row.get("movement_count"),
        "last_movement_date": last_movement_date,
        "age_days": age_days,
        "stock_status": row.get("stock_status"),
        "stock_gap": row.get("stock_gap"),
        "reorder_gap": row.get("stock_gap"),
        "non_moving_days": None,
        "_variant": report_variant,
        "age_days_sort": age_days if age_days is not None else 10**9,
    }


def build_inventory_non_moving_stock(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    valuation_method: str = "fifo",
    non_moving_days: int | None = None,
    product_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
    hsn_ids: list[int] | None = None,
    location_ids: list[int] | None = None,
    search: str | None = None,
    include_zero: bool = False,
    include_negative: bool = True,
    sort_by: str = "last_movement_date",
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    threshold_days = _parse_non_moving_days(non_moving_days)
    end_date = _resolve_end_date(from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)
    base = _base_summary_rows(
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
        location_ids=location_ids,
        search=search,
    )

    rows = []
    total_qty = ZERO
    total_value = ZERO
    non_moving_qty = ZERO
    oldest_age_days = 0
    for row in base["rows"]:
        payload = _base_row_payload(row, end_date=end_date, report_variant="non_moving")
        age_days = payload["age_days"]
        if age_days is None or age_days >= threshold_days:
            if not include_negative and Decimal(str(payload["closing_qty"] or "0")) < 0:
                continue
            if not include_zero and Decimal(str(payload["closing_qty"] or "0")) == 0:
                continue
            payload["non_moving_days"] = threshold_days
            rows.append(payload)
            total_qty += Decimal(str(payload["closing_qty"] or "0"))
            total_value += Decimal(str(payload["closing_value"] or "0"))
            non_moving_qty += Decimal(str(payload["closing_qty"] or "0"))
            oldest_age_days = max(oldest_age_days, age_days or 0)

    rows = _sort_rows(rows, sort_by=(sort_by or "last_movement_date").lower(), sort_order=sort_order)
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

    summary = {
        "product_count": count,
        "total_qty": str(_q4(total_qty)),
        "total_value": str(total_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "non_moving_qty": str(_q4(non_moving_qty)),
        "oldest_age_days": oldest_age_days,
        "non_moving_days": threshold_days,
    }
    totals = {
        "closing_qty": summary["total_qty"],
        "closing_value": summary["total_value"],
        "non_moving_qty": summary["non_moving_qty"],
    }
    return {
        "summary": summary,
        "totals": totals,
        "rows": page_rows,
        "pagination": {"count": count, "page": page, "pages": pages, "page_size": page_size},
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_non_moving_stock",
            "available_exports": [],
            "available_drilldowns": [],
            "end_date": end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
        },
    }


def build_inventory_reorder_status(
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
    sort_by: str = "reorder_gap",
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    end_date = _resolve_end_date(from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)
    base = _base_summary_rows(
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
        location_ids=location_ids,
        search=search,
    )

    rows = []
    total_qty = ZERO
    total_value = ZERO
    reorder_count = 0
    negative_count = 0
    low_stock_qty = ZERO

    for row in base["rows"]:
        payload = _base_row_payload(row, end_date=end_date, report_variant="reorder_status")
        closing_qty = Decimal(str(payload["closing_qty"] or "0"))
        gap = Decimal(str(payload["stock_gap"] or "0"))
        stock_status = str(payload.get("stock_status") or "")
        needs_reorder = stock_status in {"low", "negative", "out_of_stock"} or gap <= 0
        if not needs_reorder:
            continue
        if not include_negative and closing_qty < 0:
            continue
        if not include_zero and closing_qty == 0:
            continue
        rows.append(payload)
        total_qty += closing_qty
        total_value += Decimal(str(payload["closing_value"] or "0"))
        reorder_count += 1
        if closing_qty < 0:
            negative_count += 1
        if closing_qty <= Decimal(str(payload.get("reorder_level") or payload.get("min_stock") or "0")):
            low_stock_qty += closing_qty

    rows = _sort_rows(rows, sort_by=(sort_by or "reorder_gap").lower(), sort_order=sort_order)
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

    summary = {
        "product_count": count,
        "total_qty": str(_q4(total_qty)),
        "total_value": str(total_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "reorder_count": reorder_count,
        "negative_stock_count": negative_count,
        "low_stock_qty": str(_q4(low_stock_qty)),
    }
    totals = {
        "closing_qty": summary["total_qty"],
        "closing_value": summary["total_value"],
        "reorder_count": reorder_count,
    }
    return {
        "summary": summary,
        "totals": totals,
        "rows": page_rows,
        "pagination": {"count": count, "page": page, "pages": pages, "page_size": page_size},
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_reorder_status",
            "available_exports": [],
            "available_drilldowns": [],
            "end_date": end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
        },
    }
