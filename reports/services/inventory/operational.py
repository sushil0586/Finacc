from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from catalog.models import Product
from posting.models import InventoryMove
from reports.selectors.financial import resolve_scope_names
from reports.services.inventory.stock_ledger import (
    _apply_movement,
    _build_product_map,
    _normalize_method,
    _product_filters,
    _snapshot_state,
    _new_valuation_state,
)
from reports.services.inventory.stock_summary import _planning_for_product, _product_hsn, _status_for_row


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


def _base_queryset(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    end_date=None,
    product_ids=None,
    category_ids=None,
    hsn_ids=None,
    location_ids=None,
    search=None,
):
    qs = InventoryMove.objects.filter(
        _product_filters(
            entity_id,
            product_ids=product_ids,
            category_ids=category_ids,
            hsn_ids=hsn_ids,
            location_ids=location_ids,
            search=search,
        ),
        posting_date__lte=end_date,
        product__is_service=False,
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    return qs


def _movement_rows(qs, *, group_by_location: bool):
    ordering = ["product_id"]
    if group_by_location:
        ordering.append("location_id")
    ordering.extend(["posting_date", "txn_id", "detail_id", "id"])
    return list(
        qs.values(
            "product_id",
            "posting_date",
            "txn_type",
            "txn_id",
            "detail_id",
            "voucher_no",
            "move_type",
            "movement_nature",
            "movement_reason",
            "movement_group",
            "qty",
            "base_qty",
            "unit_cost",
            "ext_cost",
            "location_id",
            "location__name",
            "location__code",
            "source_location_id",
            "source_location__name",
            "destination_location_id",
            "destination_location__name",
        ).order_by(*ordering)
    )


def _group_key(row: dict, *, group_by_location: bool):
    return (row["product_id"], row.get("location_id") if group_by_location else None)


def _group_location_name(row: dict, *, group_by_location: bool) -> str:
    if not group_by_location:
        return "All Locations"
    return row.get("location__name") or row.get("location__code") or "Location"


def _sort_rows(rows: list[dict], *, sort_by: str, sort_order: str):
    reverse = (sort_order or "desc").lower() == "desc"

    def key(row):
        if sort_by in {"qty", "closing_qty", "opening_qty", "inward_qty", "outward_qty", "net_qty"}:
            return Decimal(str(row.get(sort_by) or "0"))
        if sort_by in {"value", "closing_value", "opening_value", "inward_value", "outward_value", "net_value"}:
            return Decimal(str(row.get(sort_by) or "0"))
        if sort_by in {"movement_count", "count"}:
            return int(row.get("movement_count") or 0)
        if sort_by in {"date", "posting_date"}:
            return row.get("posting_date") or row.get("date") or ""
        if sort_by == "last_movement_date":
            return row.get("last_movement_date") or ""
        if sort_by == "name":
            return str(row.get("product_name") or "").lower()
        if sort_by == "sku":
            return str(row.get("sku") or "").lower()
        if sort_by == "location":
            return str(row.get("location_name") or "").lower()
        return Decimal(str(row.get("closing_value") or row.get("value") or "0"))

    return sorted(rows, key=key, reverse=reverse)


def _finalize_group_row(
    *,
    group: dict,
    product: Product,
    method: str,
    include_zero: bool,
    include_negative: bool,
    group_by_location: bool,
    report_variant: str,
):
    closing_qty, closing_value = _snapshot_state(group["state"], method)
    closing_qty = _q4(closing_qty)
    closing_value = _q2(closing_value)

    if not group["period_started"]:
        group["opening_qty"] = closing_qty
        group["opening_value"] = closing_value

    if not include_negative and closing_qty < 0:
        return None
    if not include_zero and closing_qty == 0:
        return None

    opening_qty = _q4(group["opening_qty"])
    opening_value = _q2(group["opening_value"])
    inward_qty = _q4(group["inward_qty"])
    outward_qty = _q4(group["outward_qty"])
    inward_value = _q2(group["inward_value"])
    outward_value = _q2(group["outward_value"])
    net_qty = _q4(inward_qty - outward_qty)
    net_value = _q2(inward_value - outward_value)
    rate = _q4((closing_value / closing_qty) if closing_qty else ZERO)
    planning = _planning_for_product(product)
    hsn = _product_hsn(product)
    stock_status = _status_for_row(qty=closing_qty, planning=planning)
    stock_gap = ZERO
    if planning.get("reorder_level") is not None:
        stock_gap = closing_qty - Decimal(str(planning["reorder_level"]))

    row = {
        "product_id": group["product_id"],
        "sku": getattr(product, "sku", None),
        "product_name": getattr(product, "productname", None),
        "product_description": getattr(product, "productdesc", None),
        "category_id": getattr(product, "productcategory_id", None),
        "category_name": getattr(getattr(product, "productcategory", None), "pcategoryname", None),
        "uom_id": getattr(product, "base_uom_id", None),
        "uom_name": getattr(getattr(product, "base_uom", None), "code", None),
        "location_id": group["location_id"] if group_by_location else None,
        "location_name": group["location_name"],
        **hsn,
        **planning,
        "opening_qty": str(opening_qty),
        "opening_value": str(opening_value),
        "inward_qty": str(inward_qty),
        "inward_value": str(inward_value),
        "outward_qty": str(outward_qty),
        "outward_value": str(outward_value),
        "net_qty": str(net_qty),
        "net_value": str(net_value),
        "closing_qty": str(closing_qty),
        "closing_value": str(closing_value),
        "rate": str(rate),
        "movement_count": group["movement_count"],
        "first_movement_date": group["first_movement_date"].isoformat() if group["first_movement_date"] else None,
        "last_movement_date": group["last_movement_date"].isoformat() if group["last_movement_date"] else None,
        "stock_status": stock_status,
        "stock_gap": str(_q4(stock_gap)),
        "_variant": report_variant,
    }
    return row


def _append_period_movement(group: dict, row: dict, method: str):
    signed_qty, line_cost = _apply_movement(group["state"], row, method)
    if signed_qty > 0:
        group["inward_qty"] += signed_qty
        group["inward_value"] += line_cost
    elif signed_qty < 0:
        group["outward_qty"] += abs(signed_qty)
        group["outward_value"] += line_cost
    group["movement_count"] += 1
    current_date = row.get("posting_date")
    if current_date and (group["first_movement_date"] is None or current_date < group["first_movement_date"]):
        group["first_movement_date"] = current_date
    if current_date and (group["last_movement_date"] is None or current_date > group["last_movement_date"]):
        group["last_movement_date"] = current_date
    return signed_qty, line_cost


def build_inventory_stock_movement(
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
    group_by_location: bool = True,
    include_zero: bool = True,
    include_negative: bool = True,
    search: str | None = None,
    sort_by: str = "value",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    method = _normalize_method(valuation_method)
    start_date, end_date = _resolve_dates(entityfin_id=entityfin_id, from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    qs = _base_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        end_date=end_date,
        product_ids=product_ids,
        category_ids=category_ids,
        hsn_ids=hsn_ids,
        location_ids=location_ids,
        search=search,
    )
    moves = _movement_rows(qs, group_by_location=group_by_location)
    product_map = _build_product_map(entity_id, sorted({row["product_id"] for row in moves}))
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    groups: dict[tuple, dict] = {}
    for row in moves:
        key = _group_key(row, group_by_location=group_by_location)
        group = groups.setdefault(
            key,
            {
                "product_id": row["product_id"],
                "location_id": row.get("location_id") if group_by_location else None,
                "location_name": _group_location_name(row, group_by_location=group_by_location),
                "state": _new_valuation_state(method),
                "opening_qty": ZERO,
                "opening_value": ZERO,
                "inward_qty": ZERO,
                "inward_value": ZERO,
                "outward_qty": ZERO,
                "outward_value": ZERO,
                "movement_count": 0,
                "first_movement_date": None,
                "last_movement_date": None,
                "period_started": False,
            },
        )

        if start_date and row["posting_date"] < start_date:
            _apply_movement(group["state"], row, method)
            if group["first_movement_date"] is None or row["posting_date"] < group["first_movement_date"]:
                group["first_movement_date"] = row["posting_date"]
            if group["last_movement_date"] is None or row["posting_date"] > group["last_movement_date"]:
                group["last_movement_date"] = row["posting_date"]
            continue

        if not group["period_started"]:
            group["opening_qty"], group["opening_value"] = _snapshot_state(group["state"], method)
            group["period_started"] = True
        _append_period_movement(group, row, method)

    rows = []
    total_opening_qty = ZERO
    total_opening_value = ZERO
    total_inward_qty = ZERO
    total_inward_value = ZERO
    total_outward_qty = ZERO
    total_outward_value = ZERO
    total_closing_qty = ZERO
    total_closing_value = ZERO
    total_movement_count = 0

    for key, group in groups.items():
        product = product_map.get(group["product_id"])
        if product is None:
            continue
        row = _finalize_group_row(
            group=group,
            product=product,
            method=method,
            include_zero=include_zero,
            include_negative=include_negative,
            group_by_location=group_by_location,
            report_variant="movement",
        )
        if row is None:
            continue
        rows.append(row)
        total_opening_qty += Decimal(row["opening_qty"])
        total_opening_value += Decimal(row["opening_value"])
        total_inward_qty += Decimal(row["inward_qty"])
        total_inward_value += Decimal(row["inward_value"])
        total_outward_qty += Decimal(row["outward_qty"])
        total_outward_value += Decimal(row["outward_value"])
        total_closing_qty += Decimal(row["closing_qty"])
        total_closing_value += Decimal(row["closing_value"])
        total_movement_count += int(row["movement_count"] or 0)

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

    summary = {
        "product_count": count,
        "movement_count": total_movement_count,
        "opening_qty": str(_q4(total_opening_qty)),
        "opening_value": str(_q2(total_opening_value)),
        "inward_qty": str(_q4(total_inward_qty)),
        "inward_value": str(_q2(total_inward_value)),
        "outward_qty": str(_q4(total_outward_qty)),
        "outward_value": str(_q2(total_outward_value)),
        "net_qty": str(_q4(total_inward_qty - total_outward_qty)),
        "net_value": str(_q2(total_inward_value - total_outward_value)),
        "closing_qty": str(_q4(total_closing_qty)),
        "closing_value": str(_q2(total_closing_value)),
    }
    totals = {
        "opening_qty": summary["opening_qty"],
        "opening_value": summary["opening_value"],
        "inward_qty": summary["inward_qty"],
        "inward_value": summary["inward_value"],
        "outward_qty": summary["outward_qty"],
        "outward_value": summary["outward_value"],
        "net_qty": summary["net_qty"],
        "net_value": summary["net_value"],
        "closing_qty": summary["closing_qty"],
        "closing_value": summary["closing_value"],
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
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_stock_movement",
            "available_exports": [],
            "available_drilldowns": [],
            "start_date": start_date.isoformat() if isinstance(start_date, date_cls) else str(start_date) if start_date else None,
            "end_date": end_date.isoformat() if isinstance(end_date, date_cls) else str(end_date),
        },
    }


def build_inventory_stock_day_book(
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
    group_by_location: bool = False,
    include_zero: bool = True,
    include_negative: bool = True,
    search: str | None = None,
    sort_by: str = "posting_date",
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    method = _normalize_method(valuation_method)
    start_date, end_date = _resolve_dates(entityfin_id=entityfin_id, from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    qs = _base_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        end_date=end_date,
        product_ids=product_ids,
        category_ids=category_ids,
        hsn_ids=hsn_ids,
        location_ids=location_ids,
        search=search,
    )
    moves = _movement_rows(qs, group_by_location=False)
    product_map = _build_product_map(entity_id, sorted({row["product_id"] for row in moves}))
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    product_states: dict[int, dict] = defaultdict(lambda: _new_valuation_state(method))
    for row in moves:
        if start_date and row["posting_date"] < start_date:
            _apply_movement(product_states[row["product_id"]], row, method)
            continue

    opening_qty_total = ZERO
    opening_value_total = ZERO
    for state in product_states.values():
        qty, value = _snapshot_state(state, method)
        opening_qty_total += qty
        opening_value_total += value

    period_rows = [row for row in moves if (not start_date or row["posting_date"] >= start_date)]
    grouped_by_date: dict[str, list[dict]] = defaultdict(list)
    for row in period_rows:
        grouped_by_date[row["posting_date"].isoformat()].append(row)

    rows = []
    for date_key in sorted(grouped_by_date.keys()):
        day_rows = grouped_by_date[date_key]
        opening_qty = ZERO
        opening_value = ZERO
        for state in product_states.values():
            qty, value = _snapshot_state(state, method)
            opening_qty += qty
            opening_value += value

        inward_qty = ZERO
        inward_value = ZERO
        outward_qty = ZERO
        outward_value = ZERO
        movement_count = 0
        product_ids_touched = set()
        day_date = day_rows[0]["posting_date"]
        for row in day_rows:
            state = product_states[row["product_id"]]
            signed_qty, line_cost = _apply_movement(state, row, method)
            product_ids_touched.add(row["product_id"])
            movement_count += 1
            if signed_qty > 0:
                inward_qty += signed_qty
                inward_value += line_cost
            elif signed_qty < 0:
                outward_qty += abs(signed_qty)
                outward_value += line_cost

        closing_qty = ZERO
        closing_value = ZERO
        for state in product_states.values():
            qty, value = _snapshot_state(state, method)
            closing_qty += qty
            closing_value += value

        if not include_negative and closing_qty < 0:
            continue
        if not include_zero and closing_qty == 0:
            continue

        rows.append(
            {
                "date": date_key,
                "posting_date": day_date.isoformat(),
                "opening_qty": str(_q4(opening_qty)),
                "opening_value": str(_q2(opening_value)),
                "inward_qty": str(_q4(inward_qty)),
                "inward_value": str(_q2(inward_value)),
                "outward_qty": str(_q4(outward_qty)),
                "outward_value": str(_q2(outward_value)),
                "net_qty": str(_q4(inward_qty - outward_qty)),
                "net_value": str(_q2(inward_value - outward_value)),
                "closing_qty": str(_q4(closing_qty)),
                "closing_value": str(_q2(closing_value)),
                "movement_count": movement_count,
                "product_count": len(product_ids_touched),
            }
        )

    rows = _sort_rows(rows, sort_by=(sort_by or "posting_date").lower(), sort_order=sort_order)

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

    closing_qty = ZERO
    closing_value = ZERO
    for state in product_states.values():
        qty, value = _snapshot_state(state, method)
        closing_qty += qty
        closing_value += value

    summary = {
        "day_count": count,
        "movement_count": sum(int(row["movement_count"] or 0) for row in rows),
        "opening_qty": str(_q4(opening_qty_total)),
        "opening_value": str(_q2(opening_value_total)),
        "inward_qty": str(_q4(sum((Decimal(row["inward_qty"]) for row in rows), ZERO))),
        "inward_value": str(_q2(sum((Decimal(row["inward_value"]) for row in rows), ZERO))),
        "outward_qty": str(_q4(sum((Decimal(row["outward_qty"]) for row in rows), ZERO))),
        "outward_value": str(_q2(sum((Decimal(row["outward_value"]) for row in rows), ZERO))),
        "closing_qty": str(_q4(closing_qty)),
        "closing_value": str(_q2(closing_value)),
    }
    totals = {
        "opening_qty": summary["opening_qty"],
        "opening_value": summary["opening_value"],
        "inward_qty": summary["inward_qty"],
        "inward_value": summary["inward_value"],
        "outward_qty": summary["outward_qty"],
        "outward_value": summary["outward_value"],
        "closing_qty": summary["closing_qty"],
        "closing_value": summary["closing_value"],
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
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_stock_day_book",
            "available_exports": [],
            "available_drilldowns": [],
            "start_date": start_date.isoformat() if isinstance(start_date, date_cls) else str(start_date) if start_date else None,
            "end_date": end_date.isoformat() if isinstance(end_date, date_cls) else str(end_date),
        },
    }


def build_inventory_stock_book_summary(
    **kwargs,
):
    kwargs.setdefault("group_by_location", False)
    payload = build_inventory_stock_movement(**kwargs)
    payload.setdefault("_meta", {})["report_kind"] = "inventory_stock_book_summary"
    return payload


def build_inventory_stock_book_detail(
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
    group_by_location: bool = True,
    include_zero: bool = True,
    include_negative: bool = True,
    search: str | None = None,
    sort_by: str = "posting_date",
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    method = _normalize_method(valuation_method)
    start_date, end_date = _resolve_dates(entityfin_id=entityfin_id, from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    qs = _base_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        end_date=end_date,
        product_ids=product_ids,
        category_ids=category_ids,
        hsn_ids=hsn_ids,
        location_ids=location_ids,
        search=search,
    )
    moves = _movement_rows(qs, group_by_location=group_by_location)
    product_map = _build_product_map(entity_id, sorted({row["product_id"] for row in moves}))
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    groups: dict[tuple, dict] = {}
    for row in moves:
        key = _group_key(row, group_by_location=group_by_location)
        group = groups.setdefault(
            key,
            {
                "product_id": row["product_id"],
                "location_id": row.get("location_id") if group_by_location else None,
                "location_name": _group_location_name(row, group_by_location=group_by_location),
                "state": _new_valuation_state(method),
                "opening_qty": ZERO,
                "opening_value": ZERO,
                "period_started": False,
            },
        )
        if start_date and row["posting_date"] < start_date:
            _apply_movement(group["state"], row, method)
            continue

        if not group["period_started"]:
            group["opening_qty"], group["opening_value"] = _snapshot_state(group["state"], method)
            group["period_started"] = True

        opening_qty, opening_value = _snapshot_state(group["state"], method)
        signed_qty, line_cost = _apply_movement(group["state"], row, method)
        running_qty, running_value = _snapshot_state(group["state"], method)
        rate = _q4((line_cost / abs(signed_qty)) if signed_qty else ZERO)

        if not include_negative and running_qty < 0:
            continue
        if not include_zero and running_qty == 0:
            continue

        product = product_map.get(group["product_id"])
        if product is None:
            continue
        qty_in = signed_qty if signed_qty > 0 else ZERO
        qty_out = abs(signed_qty) if signed_qty < 0 else ZERO
        rows_entry = {
            "product_id": group["product_id"],
            "sku": getattr(product, "sku", None),
            "product_name": getattr(product, "productname", None),
            "category_name": getattr(getattr(product, "productcategory", None), "pcategoryname", None),
            "location_name": group["location_name"],
            "source_location_name": row.get("source_location__name"),
            "destination_location_name": row.get("destination_location__name"),
            "posting_date": row["posting_date"].isoformat() if row.get("posting_date") else None,
            "voucher_no": row.get("voucher_no"),
            "txn_type": row.get("txn_type"),
            "txn_id": row.get("txn_id"),
            "detail_id": row.get("detail_id"),
            "move_type": row.get("move_type"),
            "movement_nature": row.get("movement_nature"),
            "movement_reason": row.get("movement_reason"),
            "movement_group": str(row.get("movement_group")) if row.get("movement_group") else None,
            "qty_in": str(_q4(qty_in)),
            "qty_out": str(_q4(qty_out)),
            "unit_cost": str(rate),
            "line_value": str(_q2(line_cost if signed_qty > 0 else line_cost)),
            "opening_qty": str(_q4(opening_qty)),
            "opening_value": str(_q2(opening_value)),
            "running_qty": str(_q4(running_qty)),
            "running_value": str(_q2(running_value)),
        }
        rows = group.setdefault("rows", [])
        rows.append(rows_entry)

        rows = []
    for group in groups.values():
        if not group["period_started"]:
            group["opening_qty"], group["opening_value"] = _snapshot_state(group["state"], method)
        rows.extend(group.get("rows", []))

    rows = _sort_rows(rows, sort_by=(sort_by or "posting_date").lower(), sort_order=sort_order)

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

    total_opening_qty = sum((Decimal(group["opening_qty"]) for group in groups.values()), ZERO)
    total_opening_value = sum((Decimal(group["opening_value"]) for group in groups.values()), ZERO)
    total_closing_qty = ZERO
    total_closing_value = ZERO
    for group in groups.values():
        qty, value = _snapshot_state(group["state"], method)
        total_closing_qty += qty
        total_closing_value += value
    total_inward_qty = sum((Decimal(row["qty_in"]) for row in rows), ZERO)
    total_outward_qty = sum((Decimal(row["qty_out"]) for row in rows), ZERO)
    total_inward_value = sum((Decimal(row["line_value"]) for row in rows if Decimal(row["qty_in"]) > 0), ZERO)
    total_outward_value = sum((Decimal(row["line_value"]) for row in rows if Decimal(row["qty_out"]) > 0), ZERO)

    summary = {
        "movement_count": count,
        "opening_qty": str(_q4(total_opening_qty)),
        "opening_value": str(_q2(total_opening_value)),
        "inward_qty": str(_q4(total_inward_qty)),
        "inward_value": str(_q2(total_inward_value)),
        "outward_qty": str(_q4(total_outward_qty)),
        "outward_value": str(_q2(total_outward_value)),
        "closing_qty": str(_q4(total_closing_qty)),
        "closing_value": str(_q2(total_closing_value)),
    }
    totals = {
        "opening_qty": summary["opening_qty"],
        "opening_value": summary["opening_value"],
        "inward_qty": summary["inward_qty"],
        "inward_value": summary["inward_value"],
        "outward_qty": summary["outward_qty"],
        "outward_value": summary["outward_value"],
        "closing_qty": summary["closing_qty"],
        "closing_value": summary["closing_value"],
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
        "entity_name": scope_names["entity_name"],
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_name": scope_names["subentity_name"],
        "_meta": {
            "report_kind": "inventory_stock_book_detail",
            "available_exports": [],
            "available_drilldowns": [],
            "start_date": start_date.isoformat() if isinstance(start_date, date_cls) else str(start_date) if start_date else None,
            "end_date": end_date.isoformat() if isinstance(end_date, date_cls) else str(end_date),
        },
    }
