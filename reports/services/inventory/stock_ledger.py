from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from catalog.models import Product
from posting.models import InventoryMove
from reports.selectors.financial import resolve_scope_names


ZERO = Decimal("0")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


def _q2(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.00") else Decimal("0.00")


def _q4(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal("-0.0000") else Decimal("0.0000")


def _signed_move_qty(move: dict) -> Decimal:
    qty = Decimal(str(move.get("base_qty") if move.get("base_qty") is not None else move.get("qty") or 0))
    move_type = str(move.get("move_type") or "").upper()
    if move_type == "OUT":
        return -abs(qty)
    if move_type == "IN":
        return abs(qty)
    return qty


def _rate_from_move(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / abs(Decimal(str(qty)))
    return ZERO


def _normalize_method(value: str | None) -> str:
    method = (value or "fifo").strip().lower()
    return method if method in {"fifo", "lifo", "mwa", "wac", "latest"} else "fifo"


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


def _product_filters(entity_id, *, product_ids=None, category_ids=None, hsn_ids=None, location_ids=None, search=None):
    qs = Q(entity_id=entity_id, product__is_service=False)
    if product_ids:
        qs &= Q(product_id__in=product_ids)
    if category_ids:
        qs &= Q(product__productcategory_id__in=category_ids)
    if location_ids:
        qs &= Q(location_id__in=location_ids)
    if hsn_ids:
        from catalog.models import ProductGstRate

        hsn_product_ids = ProductGstRate.objects.filter(
            product__entity_id=entity_id,
            hsn_id__in=hsn_ids,
        ).values_list("product_id", flat=True).distinct()
        qs &= Q(product_id__in=list(hsn_product_ids))
    if search:
        token = str(search).strip()
        if token:
            qs &= (
                Q(product__productname__icontains=token)
                | Q(product__sku__icontains=token)
                | Q(product__productdesc__icontains=token)
                | Q(product__productcategory__pcategoryname__icontains=token)
                | Q(location__name__icontains=token)
                | Q(voucher_no__icontains=token)
            )
    return qs


def _build_product_map(entity_id: int, product_ids: list[int]):
    if not product_ids:
        return {}
    qs = Product.objects.filter(entity_id=entity_id, is_service=False, id__in=product_ids).select_related(
        "productcategory",
        "base_uom",
    )
    return {product.id: product for product in qs}


def _movement_rows(moves_qs):
    return list(
        moves_qs.values(
            "product_id",
            "posting_date",
            "voucher_no",
            "txn_type",
            "txn_id",
            "detail_id",
            "move_type",
            "qty",
            "base_qty",
            "unit_cost",
            "ext_cost",
            "location_id",
            "location__name",
            "location__code",
        ).order_by("product_id", "posting_date", "txn_id", "detail_id", "id")
    )


def _new_valuation_state(method: str):
    if method in {"fifo", "lifo"}:
        return {"layers": []}
    if method in {"mwa", "latest"}:
        return {"qty": ZERO, "value": ZERO, "latest": ZERO}
    if method == "wac":
        return {"sum_in_qty": ZERO, "sum_in_val": ZERO, "issues_qty": ZERO}
    return {"qty": ZERO, "value": ZERO}


def _snapshot_state(state: dict, method: str) -> tuple[Decimal, Decimal]:
    if method in {"fifo", "lifo"}:
        qty = sum((layer["qty"] for layer in state["layers"]), ZERO)
        value = sum((layer["qty"] * layer["rate"] for layer in state["layers"]), ZERO)
        return qty, value
    if method in {"mwa", "latest"}:
        return state["qty"], state["value"]
    if method == "wac":
        qty = max(state["sum_in_qty"] - state["issues_qty"], ZERO)
        avg = (state["sum_in_val"] / state["sum_in_qty"]) if state["sum_in_qty"] > 0 else ZERO
        return qty, qty * avg
    return ZERO, ZERO


def _apply_movement(state: dict, move: dict, method: str) -> tuple[Decimal, Decimal]:
    signed_qty = _signed_move_qty(move)
    rate = _rate_from_move(signed_qty, move.get("unit_cost"), move.get("ext_cost"))

    if method == "fifo":
        if signed_qty > 0:
            state["layers"].append({"qty": signed_qty, "rate": rate})
            return signed_qty, signed_qty * rate
        if signed_qty < 0:
            need = abs(signed_qty)
            consumed = ZERO
            idx = 0
            while need > 0 and idx < len(state["layers"]):
                take = min(state["layers"][idx]["qty"], need)
                state["layers"][idx]["qty"] -= take
                need -= take
                consumed += take * state["layers"][idx]["rate"]
                if state["layers"][idx]["qty"] == 0:
                    idx += 1
            state["layers"] = [layer for layer in state["layers"] if layer["qty"] > 0]
            return signed_qty, consumed

    if method == "lifo":
        if signed_qty > 0:
            state["layers"].append({"qty": signed_qty, "rate": rate})
            return signed_qty, signed_qty * rate
        if signed_qty < 0:
            need = abs(signed_qty)
            consumed = ZERO
            idx = len(state["layers"]) - 1
            while need > 0 and idx >= 0:
                take = min(state["layers"][idx]["qty"], need)
                state["layers"][idx]["qty"] -= take
                need -= take
                consumed += take * state["layers"][idx]["rate"]
                if state["layers"][idx]["qty"] == 0:
                    state["layers"].pop(idx)
                idx -= 1
            return signed_qty, consumed

    if method == "mwa":
        if signed_qty > 0:
            state["qty"] += signed_qty
            state["value"] += signed_qty * rate
            return signed_qty, signed_qty * rate
        if signed_qty < 0:
            issue_qty = abs(signed_qty)
            avg = (state["value"] / state["qty"]) if state["qty"] > 0 else ZERO
            take = min(state["qty"], issue_qty)
            cost = take * avg
            state["value"] -= cost
            state["qty"] -= take
            return signed_qty, cost

    if method == "latest":
        if signed_qty > 0:
            state["latest"] = rate
            state["qty"] += signed_qty
            state["value"] += signed_qty * state["latest"]
            return signed_qty, signed_qty * state["latest"]
        if signed_qty < 0:
            issue_qty = abs(signed_qty)
            take = min(state["qty"], issue_qty)
            cost = take * state["latest"]
            state["value"] -= cost
            state["qty"] -= take
            if state["qty"] == 0:
                state["latest"] = ZERO
            return signed_qty, cost

    if method == "wac":
        if signed_qty > 0:
            state["sum_in_qty"] += signed_qty
            state["sum_in_val"] += signed_qty * rate
            return signed_qty, signed_qty * rate
        if signed_qty < 0:
            issue_qty = abs(signed_qty)
            available_qty = max(state["sum_in_qty"] - state["issues_qty"], ZERO)
            take = min(available_qty, issue_qty)
            avg = (state["sum_in_val"] / state["sum_in_qty"]) if state["sum_in_qty"] > 0 else ZERO
            cost = take * avg
            state["issues_qty"] += take
            return signed_qty, cost

    return signed_qty, signed_qty * rate


def build_inventory_stock_ledger(
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
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    method = _normalize_method(valuation_method)
    start_date, end_date = _resolve_dates(entityfin_id=entityfin_id, from_date=from_date, to_date=to_date, as_of_date=as_of_date)
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

    opening_qs = base_qs.filter(posting_date__lt=start_date) if start_date else base_qs.none()
    period_qs = base_qs.filter(posting_date__lte=end_date)
    if start_date:
        period_qs = period_qs.filter(posting_date__gte=start_date)

    opening_rows = _movement_rows(opening_qs)
    period_rows = _movement_rows(period_qs)

    product_ids_in_scope = sorted({row["product_id"] for row in (opening_rows + period_rows)})
    product_map = _build_product_map(entity_id, product_ids_in_scope)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    opening_state = {}
    for row in opening_rows:
        pid = row["product_id"]
        state = opening_state.setdefault(pid, _new_valuation_state(method))
        _apply_movement(state, row, method)

    rows = []
    running_state = {
        pid: opening_state.get(pid, _new_valuation_state(method))
        for pid in product_ids_in_scope
    }
    for row in period_rows:
        pid = row["product_id"]
        product = product_map.get(pid)
        if product is None:
            continue

        state = running_state.setdefault(pid, _new_valuation_state(method))
        opening_qty, opening_value = _snapshot_state(state, method)
        signed_qty, line_cost = _apply_movement(state, row, method)
        running_qty, running_value = _snapshot_state(state, method)
        line_value = _q2(line_cost if signed_qty > 0 else -line_cost if signed_qty < 0 else ZERO)
        rate = _q4((line_cost / abs(signed_qty)) if signed_qty else ZERO)

        if not include_negative and running_qty < 0:
            continue
        if not include_zero and running_qty == 0:
            continue

        rows.append(
            {
                "product_id": pid,
                "product_name": getattr(product, "productname", None),
                "sku": getattr(product, "sku", None),
                "category_name": getattr(getattr(product, "productcategory", None), "pcategoryname", None),
                "location_name": row.get("location__name") or row.get("location__code"),
                "posting_date": row["posting_date"].isoformat() if row.get("posting_date") else None,
                "voucher_no": row.get("voucher_no"),
                "txn_type": row.get("txn_type"),
                "txn_id": row.get("txn_id"),
                "detail_id": row.get("detail_id"),
                "move_type": row.get("move_type"),
                "qty_in": str(_q4(signed_qty if signed_qty > 0 else ZERO)),
                "qty_out": str(_q4(abs(signed_qty) if signed_qty < 0 else ZERO)),
                "unit_cost": str(_q4(rate)),
                "line_value": str(line_value),
                "opening_qty": str(opening_qty),
                "opening_value": str(opening_value),
                "running_qty": str(running_qty),
                "running_value": str(running_value),
            }
        )

    rows.sort(key=lambda item: (item["product_name"] or "", item["posting_date"] or "", item["txn_id"] or 0, item["detail_id"] or 0), reverse=(sort_order or "asc").lower() == "desc")

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

    opening_qty_total = ZERO
    opening_value_total = ZERO
    for state in opening_state.values():
        qty, value = _snapshot_state(state, method)
        opening_qty_total += qty
        opening_value_total += value

    closing_qty_total = ZERO
    closing_value_total = ZERO
    for state in running_state.values():
        qty, value = _snapshot_state(state, method)
        closing_qty_total += qty
        closing_value_total += value
    inward_qty = sum((Decimal(row["qty_in"]) for row in rows), ZERO)
    outward_qty = sum((Decimal(row["qty_out"]) for row in rows), ZERO)

    summary = {
        "product_count": len(product_ids_in_scope),
        "movement_count": count,
        "opening_qty": str(_q4(opening_qty_total)),
        "opening_value": str(_q2(opening_value_total)),
        "inward_qty": str(_q4(inward_qty)),
        "outward_qty": str(_q4(outward_qty)),
        "closing_qty": str(_q4(closing_qty_total)),
        "closing_value": str(_q2(closing_value_total)),
    }
    totals = {
        "opening_qty": summary["opening_qty"],
        "opening_value": summary["opening_value"],
        "inward_qty": summary["inward_qty"],
        "outward_qty": summary["outward_qty"],
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
            "report_kind": "inventory_stock_ledger",
            "available_exports": [],
            "available_drilldowns": [],
            "end_date": end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
            "start_date": start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date) if start_date else None,
        },
    }
