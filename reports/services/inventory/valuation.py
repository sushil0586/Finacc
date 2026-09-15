from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


ZERO = Decimal("0")


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _signed_qty(move: dict) -> Decimal:
    qty = _decimal(move.get("base_qty") if move.get("base_qty") is not None else move.get("qty"))
    move_type = str(move.get("move_type") or "").upper()
    if move_type == "OUT":
        return -abs(qty)
    if move_type == "IN":
        return abs(qty)
    return qty


def _rate(move: dict, qty: Decimal) -> Decimal:
    if move.get("unit_cost") is not None:
        return _decimal(move["unit_cost"])
    if move.get("ext_cost") is not None and qty:
        return _decimal(move["ext_cost"]) / abs(qty)
    return ZERO


def _pool_key(move: dict) -> tuple[int, int | None, str]:
    return (
        int(move["product_id"]),
        move.get("location_id"),
        str(move.get("batch_number") or "").strip().upper(),
    )


def value_moves_by_inventory_identity(moves: list[dict], method: str) -> dict[int, tuple[Decimal, Decimal]]:
    """Value stock without allowing one location or batch to consume another pool."""
    method = (method or "fifo").lower()
    pools: dict[tuple[int, int | None, str], dict] = {}

    for move in moves:
        state = pools.setdefault(
            _pool_key(move),
            {
                "layers": [],
                "deficit": ZERO,
                "qty": ZERO,
                "value": ZERO,
                "latest": ZERO,
                "in_qty": ZERO,
                "in_value": ZERO,
                "issue_qty": ZERO,
            },
        )
        qty = _signed_qty(move)
        rate = _rate(move, qty)

        if method in {"fifo", "lifo"}:
            if qty > 0:
                covered = min(qty, state["deficit"])
                state["deficit"] -= covered
                qty -= covered
                if qty > 0:
                    state["layers"].append({"qty": qty, "rate": rate})
            elif qty < 0:
                need = -qty
                while need > 0 and state["layers"]:
                    index = 0 if method == "fifo" else -1
                    layer = state["layers"][index]
                    taken = min(layer["qty"], need)
                    layer["qty"] -= taken
                    need -= taken
                    if layer["qty"] == 0:
                        state["layers"].pop(index)
                state["deficit"] += need
        elif method in {"mwa", "latest"}:
            if qty > 0:
                covered = min(qty, state["deficit"])
                state["deficit"] -= covered
                qty -= covered
                if qty <= 0:
                    continue
                state["qty"] += qty
                state["value"] += qty * rate
                if method == "latest":
                    state["latest"] = rate
            elif qty < 0:
                need = -qty
                available = state["qty"]
                taken = min(available, need)
                if taken > 0:
                    issue_rate = state["value"] / available if method == "mwa" else state["latest"]
                    state["value"] -= taken * issue_rate
                    state["qty"] -= taken
                    need -= taken
                if state["qty"] == 0:
                    state["value"] = ZERO
                    if method == "latest":
                        state["latest"] = ZERO
                state["deficit"] += need
        elif method == "wac":
            if qty > 0:
                state["in_qty"] += qty
                state["in_value"] += qty * rate
            elif qty < 0:
                state["issue_qty"] += -qty

    products: dict[int, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for (product_id, _location_id, _batch_number), state in pools.items():
        if method in {"fifo", "lifo"}:
            qty = sum((layer["qty"] for layer in state["layers"]), ZERO) - state["deficit"]
            value = sum((layer["qty"] * layer["rate"] for layer in state["layers"]), ZERO)
        elif method in {"mwa", "latest"}:
            qty = state["qty"] - state["deficit"]
            value = state["value"]
        elif method == "wac":
            qty = state["in_qty"] - state["issue_qty"]
            average = state["in_value"] / state["in_qty"] if state["in_qty"] > 0 else ZERO
            value = max(qty, ZERO) * average
        else:
            qty = ZERO
            value = ZERO
        products[product_id][0] += qty
        products[product_id][1] += value

    return {product_id: (values[0], values[1]) for product_id, values in products.items()}
