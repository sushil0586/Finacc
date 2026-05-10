from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from catalog.uom_helpers import q8, resolve_product_uom
from posting.models import InventoryMove, TxnType
from purchase.models import PurchaseInvoiceLine
from sales.models import SalesInvoiceLine


Q2 = Decimal("0.01")
Q4 = Decimal("0.0000")

TARGET_TXN_TYPES = (
    TxnType.PURCHASE,
    TxnType.PURCHASE_CREDIT_NOTE,
    TxnType.PURCHASE_DEBIT_NOTE,
    TxnType.SALES,
    TxnType.SALES_CREDIT_NOTE,
    TxnType.SALES_DEBIT_NOTE,
)

LINE_MODEL_BY_TXN_TYPE = {
    TxnType.PURCHASE: PurchaseInvoiceLine,
    TxnType.PURCHASE_CREDIT_NOTE: PurchaseInvoiceLine,
    TxnType.PURCHASE_DEBIT_NOTE: PurchaseInvoiceLine,
    TxnType.SALES: SalesInvoiceLine,
    TxnType.SALES_CREDIT_NOTE: SalesInvoiceLine,
    TxnType.SALES_DEBIT_NOTE: SalesInvoiceLine,
}


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def q4(value) -> Decimal:
    return Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)


def _load_line_maps(moves: list[InventoryMove]) -> dict[str, dict[int, object]]:
    line_maps: dict[str, dict[int, object]] = {}
    for txn_type, model in LINE_MODEL_BY_TXN_TYPE.items():
        line_ids = sorted({int(move.detail_id) for move in moves if move.txn_type == txn_type and move.detail_id})
        if not line_ids:
            continue
        line_maps[txn_type] = model.objects.filter(id__in=line_ids).select_related(
            "product__base_uom",
            "uom",
        ).prefetch_related(
            "product__uom_conversions__from_uom",
            "product__uom_conversions__to_uom",
        ).in_bulk()
    return line_maps


def backfill_inventory_move_uom_base_qty(
    *,
    entity_id: int | None = None,
    dry_run: bool = False,
    txn_types: Iterable[str] | None = None,
    limit: int | None = None,
) -> dict:
    allowed_txn_types = tuple(txn_types or TARGET_TXN_TYPES)
    qs = InventoryMove.objects.select_related("product", "uom", "base_uom").filter(
        txn_type__in=allowed_txn_types,
        detail_id__isnull=False,
    ).order_by("id")
    if entity_id is not None:
        qs = qs.filter(entity_id=entity_id)
    if limit:
        moves = list(qs[: max(1, int(limit))])
    else:
        moves = list(qs)

    result = {
        "dry_run": bool(dry_run),
        "moves_scanned": len(moves),
        "mismatched_moves": 0,
        "moves_updated": 0,
        "skipped_missing_line": 0,
        "skipped_missing_product": 0,
        "skipped_missing_conversion": 0,
        "samples": [],
    }
    if not moves:
        return result

    line_maps = _load_line_maps(moves)
    updates: list[InventoryMove] = []

    for move in moves:
        line = line_maps.get(move.txn_type, {}).get(int(move.detail_id or 0))
        if line is None:
            result["skipped_missing_line"] += 1
            continue

        product = getattr(line, "product", None) or getattr(move, "product", None)
        if product is None:
            result["skipped_missing_product"] += 1
            continue

        raw_uom_id = getattr(line, "uom_id", None) or getattr(move, "uom_id", None)
        try:
            _, factor_to_base = resolve_product_uom(product=product, raw_uom_id=raw_uom_id)
        except ValueError:
            result["skipped_missing_conversion"] += 1
            continue

        expected_uom_id = int(raw_uom_id) if raw_uom_id else getattr(product, "base_uom_id", None)
        expected_base_uom_id = getattr(product, "base_uom_id", None)
        expected_factor = q8(factor_to_base)
        expected_base_qty = q4(Decimal(move.qty or 0) * expected_factor)
        expected_ext_cost = q2(abs(expected_base_qty) * Decimal(move.unit_cost or 0))

        changed_fields: list[str] = []
        if (move.uom_id or None) != (expected_uom_id or None):
            move.uom_id = expected_uom_id
            changed_fields.append("uom")
        if (move.base_uom_id or None) != (expected_base_uom_id or None):
            move.base_uom_id = expected_base_uom_id
            changed_fields.append("base_uom")
        if q8(move.uom_factor) != expected_factor:
            move.uom_factor = expected_factor
            changed_fields.append("uom_factor")
        if q4(move.base_qty) != expected_base_qty:
            move.base_qty = expected_base_qty
            changed_fields.append("base_qty")
        if q2(move.ext_cost) != expected_ext_cost:
            move.ext_cost = expected_ext_cost
            changed_fields.append("ext_cost")

        if not changed_fields:
            continue

        result["mismatched_moves"] += 1
        if len(result["samples"]) < 20:
            result["samples"].append(
                {
                    "move_id": move.id,
                    "txn_type": move.txn_type,
                    "txn_id": move.txn_id,
                    "detail_id": move.detail_id,
                    "product_id": move.product_id,
                    "fields": changed_fields,
                    "expected_factor": str(expected_factor),
                    "expected_base_qty": str(expected_base_qty),
                }
            )
        if not dry_run:
            updates.append(move)

    if updates:
        InventoryMove.objects.bulk_update(
            updates,
            ["uom", "base_uom", "uom_factor", "base_qty", "ext_cost"],
            batch_size=500,
        )
        result["moves_updated"] = len(updates)

    return result
