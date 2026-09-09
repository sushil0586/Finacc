from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from posting.models import InventoryMove, TxnType


ZERO = Decimal("0")
Q4 = Decimal("0.0001")


def _q4(value) -> Decimal:
    return Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)


def _move_qty(move: dict) -> Decimal:
    qty = _q4(move.get("base_qty") if move.get("base_qty") is not None else move.get("qty"))
    move_type = move.get("move_type")
    if move_type == InventoryMove.MoveType.OUT:
        return -abs(qty)
    if move_type == InventoryMove.MoveType.IN_:
        return abs(qty)
    return qty


def fifo_issue_unit_cost(
    *,
    entity_id: int,
    product_id: int,
    location_id: int | None,
    posting_date,
    required_qty: Decimal,
    batch_number: str = "",
) -> Decimal:
    """Return the weighted FIFO cost of the requested issue from prior movements."""
    qty_needed = abs(_q4(required_qty))
    if qty_needed == ZERO:
        return ZERO

    moves = InventoryMove.objects.filter(
        entity_id=entity_id,
        product_id=product_id,
        posting_date__lte=posting_date,
    )
    if location_id is not None:
        moves = moves.filter(location_id=location_id)
    if batch_number:
        moves = moves.filter(batch_number=batch_number)

    layers: list[list[Decimal]] = []
    rows = moves.values("move_type", "qty", "base_qty", "unit_cost").order_by("posting_date", "id")
    for row in rows:
        signed_qty = _move_qty(row)
        if signed_qty > ZERO:
            layers.append([signed_qty, _q4(row.get("unit_cost"))])
            continue
        if signed_qty >= ZERO:
            continue

        consume = abs(signed_qty)
        while consume > ZERO and layers:
            take = min(layers[0][0], consume)
            layers[0][0] -= take
            consume -= take
            if layers[0][0] == ZERO:
                layers.pop(0)

    remaining = qty_needed
    consumed_value = ZERO
    for layer_qty, layer_rate in layers:
        take = min(layer_qty, remaining)
        consumed_value += take * layer_rate
        remaining -= take
        if remaining == ZERO:
            break

    if consumed_value == ZERO:
        return ZERO
    # Negative stock can be permitted by entity policy. Uncovered quantity has no
    # defensible acquisition layer, so value only the quantity actually on hand.
    return _q4(consumed_value / qty_needed)


def original_sales_issue_unit_cost(
    *,
    original_invoice_id: int | None,
    product_id: int,
    batch_number: str = "",
) -> Decimal:
    """Return the weighted issue cost recorded by the original sales invoice."""
    if not original_invoice_id:
        return ZERO
    moves = InventoryMove.objects.filter(
        txn_type=TxnType.SALES,
        txn_id=original_invoice_id,
        product_id=product_id,
        move_type=InventoryMove.MoveType.OUT,
    )
    if batch_number:
        moves = moves.filter(batch_number=batch_number)

    total_qty = ZERO
    total_value = ZERO
    for qty, unit_cost in moves.values_list("base_qty", "unit_cost"):
        normalized_qty = abs(_q4(qty))
        total_qty += normalized_qty
        total_value += normalized_qty * _q4(unit_cost)
    return _q4(total_value / total_qty) if total_qty > ZERO else ZERO


def original_purchase_receipt_unit_cost(
    *,
    original_invoice_id: int | None,
    product_id: int,
    batch_number: str = "",
) -> Decimal:
    """Return the weighted receipt cost recorded by the referenced purchase invoice."""
    if not original_invoice_id:
        return ZERO
    moves = InventoryMove.objects.filter(
        txn_type=TxnType.PURCHASE,
        txn_id=original_invoice_id,
        product_id=product_id,
        move_type=InventoryMove.MoveType.IN_,
    )
    if batch_number:
        moves = moves.filter(batch_number=batch_number)

    total_qty = ZERO
    total_value = ZERO
    for qty, unit_cost in moves.values_list("base_qty", "unit_cost"):
        normalized_qty = abs(_q4(qty))
        total_qty += normalized_qty
        total_value += normalized_qty * _q4(unit_cost)
    return _q4(total_value / total_qty) if total_qty > ZERO else ZERO
