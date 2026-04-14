from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from entity.models import Godown
from posting.common.location_resolver import resolve_posting_location_id
from posting.models import InventoryMove


ZERO4 = Decimal("0.0000")


def _q4(value) -> Decimal:
    try:
        quantized = Decimal(value or 0).quantize(ZERO4, rounding=ROUND_HALF_UP)
    except Exception:
        quantized = ZERO4
    return quantized if quantized != Decimal("-0.0000") else ZERO4


class SalesStockBalanceService:
    @staticmethod
    def _signed_move_qty(move: dict) -> Decimal:
        qty = Decimal(str(move.get("base_qty") if move.get("base_qty") is not None else move.get("qty") or 0))
        move_type = str(move.get("move_type") or "").upper()
        if move_type == InventoryMove.MoveType.OUT:
            return -abs(qty)
        if move_type == InventoryMove.MoveType.IN_:
            return abs(qty)
        return qty

    @classmethod
    def _build_balance_maps(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int | None,
        subentity_id: int | None,
        product_id: int,
        bill_date,
        location_id: int | None,
    ) -> tuple[dict[tuple[str, int | None], Decimal], dict[tuple[str, int | None, object], Decimal], Decimal]:
        qs = InventoryMove.objects.filter(
            entity_id=entity_id,
            posting_date__lte=bill_date,
            product_id=product_id,
            product__is_service=False,
        )
        if entityfinid_id:
            qs = qs.filter(entityfin_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if location_id is not None:
            qs = qs.filter(location_id=location_id)

        rows = qs.values("batch_number", "expiry_date", "move_type", "base_qty", "location_id")
        by_batch: dict[tuple[str, int | None], Decimal] = defaultdict(lambda: ZERO4)
        by_batch_expiry: dict[tuple[str, int | None, object], Decimal] = defaultdict(lambda: ZERO4)
        total_available = ZERO4

        for row in rows:
            batch_number = str(row.get("batch_number") or "").strip()
            expiry_date = row.get("expiry_date")
            row_location_id = row.get("location_id")
            signed_qty = _q4(cls._signed_move_qty(row))
            batch_key = (batch_number, row_location_id)
            expiry_key = (batch_number, row_location_id, expiry_date)
            by_batch[batch_key] = _q4(by_batch[batch_key] + signed_qty)
            by_batch_expiry[expiry_key] = _q4(by_batch_expiry[expiry_key] + signed_qty)
            total_available = _q4(total_available + signed_qty)

        return by_batch, by_batch_expiry, total_available

    @staticmethod
    def _best_batch(
        *,
        by_batch_expiry: dict[tuple[str, int | None, object], Decimal],
        location_id: int | None,
    ) -> tuple[str, object, Decimal] | None:
        candidates: list[tuple[object, str, Decimal]] = []
        for (batch_number, row_location_id, expiry_date), balance in by_batch_expiry.items():
            if location_id is not None and row_location_id != location_id:
                continue
            if not batch_number or _q4(balance) <= ZERO4:
                continue
            candidates.append((expiry_date or date.max, batch_number, _q4(balance)))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        expiry_date, batch_number, balance = candidates[0]
        return batch_number, expiry_date, balance

    @classmethod
    def _build_available_batch_rows(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int | None,
        subentity_id: int | None,
        product_id: int,
        bill_date,
        location_id: int | None,
    ) -> list[dict[str, Any]]:
        qs = InventoryMove.objects.filter(
            entity_id=entity_id,
            posting_date__lte=bill_date,
            product_id=product_id,
            product__is_service=False,
        )
        if entityfinid_id:
            qs = qs.filter(entityfin_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if location_id is not None:
            qs = qs.filter(location_id=location_id)

        rows = qs.values("batch_number", "manufacture_date", "expiry_date", "move_type", "base_qty", "location_id")
        batch_map: dict[tuple[str, int | None], dict[str, Any]] = {}

        for row in rows:
            batch_number = str(row.get("batch_number") or "").strip()
            if not batch_number:
                continue
            row_location_id = row.get("location_id")
            key = (batch_number, row_location_id)
            item = batch_map.setdefault(
                key,
                {
                    "batch_number": batch_number,
                    "location_id": row_location_id,
                    "manufacture_date": None,
                    "expiry_date": None,
                    "available_qty": ZERO4,
                },
            )
            signed_qty = _q4(cls._signed_move_qty(row))
            item["available_qty"] = _q4(item["available_qty"] + signed_qty)
            if item["manufacture_date"] is None and row.get("manufacture_date") is not None:
                item["manufacture_date"] = row.get("manufacture_date")
            if item["expiry_date"] is None and row.get("expiry_date") is not None:
                item["expiry_date"] = row.get("expiry_date")

        available_rows: list[dict[str, Any]] = []
        for item in batch_map.values():
            if _q4(item["available_qty"]) <= ZERO4:
                continue
            available_rows.append(item)

        available_rows.sort(key=lambda item: (item.get("expiry_date") or date.max, item.get("batch_number") or ""))
        return available_rows

    @classmethod
    def build_hint(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int | None,
        subentity_id: int | None,
        bill_date,
        product,
        requested_qty,
        batch_number: str | None = None,
        expiry_date=None,
        location_id: int | None = None,
        policy=None,
    ) -> dict:
        requested_qty = _q4(abs(Decimal(str(requested_qty or 0))))
        resolved_location_id = resolve_posting_location_id(
            entity_id=entity_id,
            subentity_id=subentity_id,
            location_id=location_id,
        )

        resolved_location_name = None
        if resolved_location_id:
            resolved_location_name = Godown.objects.filter(id=resolved_location_id).values_list("name", flat=True).first()

        mode = str(getattr(policy, "mode", "") or "").upper()
        allow_negative_stock = bool(getattr(policy, "allow_negative_stock", True))
        batch_required = bool(getattr(policy, "batch_required_for_sales", False)) or mode == "STRICT"
        expiry_required = bool(getattr(policy, "expiry_validation_required", False)) or mode == "STRICT"
        fefo_required = bool(getattr(policy, "fefo_required", False)) or mode == "STRICT"
        allow_manual_override = bool(getattr(policy, "allow_manual_batch_override", True))

        batch_number = str(batch_number or "").strip()
        expiry_date_value = expiry_date
        if isinstance(expiry_date_value, str) and expiry_date_value.strip():
            try:
                expiry_date_value = date.fromisoformat(expiry_date_value.strip())
            except ValueError:
                expiry_date_value = None

        if not product or bool(getattr(product, "is_service", False)):
            return {
                "status": "info",
                "message": "Stock check is not applicable for service items.",
                "requested_qty": str(requested_qty),
                "available_qty": str(ZERO4),
                "shortage_qty": str(ZERO4),
                "resolved_location_id": resolved_location_id,
                "resolved_location_name": resolved_location_name,
                "batch_required": False,
                "expiry_required": False,
                "fefo_required": False,
            }

        by_batch, by_batch_expiry, total_available = cls._build_balance_maps(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            product_id=int(product.id),
            bill_date=bill_date,
            location_id=resolved_location_id,
        )
        suggested_batch = cls._best_batch(by_batch_expiry=by_batch_expiry, location_id=resolved_location_id)
        suggested_batch_number = suggested_batch[0] if suggested_batch else None
        suggested_batch_expiry = suggested_batch[1] if suggested_batch else None
        suggested_batch_available = suggested_batch[2] if suggested_batch else ZERO4

        selected_batch_available = ZERO4
        if batch_number:
            selected_batch_available = _q4(by_batch.get((batch_number, resolved_location_id), ZERO4))

        available_qty = selected_batch_available if batch_number else total_available
        shortage_qty = _q4(max(requested_qty - available_qty, ZERO4))

        status = "info"
        message = ""
        if batch_required and not batch_number:
            if suggested_batch_number:
                message = (
                    f"Batch required. Suggested batch {suggested_batch_number}"
                    f"{' (' + suggested_batch_expiry.isoformat() + ')' if hasattr(suggested_batch_expiry, 'isoformat') and suggested_batch_expiry else ''}"
                    f" with {suggested_batch_available} available."
                )
            else:
                message = "Batch required, but no available batch was found for this product."
            status = "warning"
        elif batch_number:
            if selected_batch_available <= ZERO4:
                message = f"Batch '{batch_number}' has no available stock at the selected location."
                status = "danger"
            elif shortage_qty > ZERO4:
                message = f"Only {available_qty} available in batch '{batch_number}'. Short by {shortage_qty}."
                status = "danger" if not allow_negative_stock else "warning"
            else:
                message = f"{available_qty} available in batch '{batch_number}' at the selected location."
                status = "info"
        else:
            if available_qty <= ZERO4:
                message = "No available stock found for this product at the selected location."
                status = "danger"
            elif shortage_qty > ZERO4:
                message = f"Only {available_qty} available at the selected location. Short by {shortage_qty}."
                status = "danger" if not allow_negative_stock else "warning"
            else:
                message = f"{available_qty} available at the selected location."
                status = "info"

        if expiry_required:
            if not batch_number and suggested_batch_number and suggested_batch_expiry:
                if not message:
                    message = f"Suggested batch {suggested_batch_number} expires on {suggested_batch_expiry.isoformat()}."
                elif suggested_batch_expiry:
                    message = f"{message} Suggested batch expires on {suggested_batch_expiry.isoformat()}."
                status = "warning" if status == "info" else status
            elif batch_number and expiry_date_value is None and suggested_batch_expiry is not None:
                expiry_text = suggested_batch_expiry.isoformat() if hasattr(suggested_batch_expiry, "isoformat") else str(suggested_batch_expiry)
                message = f"{message} Suggested expiry date: {expiry_text}."
                if status == "info":
                    status = "warning"

        if fefo_required and not allow_manual_override and suggested_batch_number:
            if not batch_number or batch_number != suggested_batch_number:
                expiry_text = (
                    f" ({suggested_batch_expiry.isoformat()})"
                    if hasattr(suggested_batch_expiry, "isoformat") and suggested_batch_expiry
                    else ""
                )
                message = f"FEFO suggests batch '{suggested_batch_number}'{expiry_text}."
                status = "warning"

        return {
            "status": status,
            "message": message,
            "requested_qty": str(requested_qty),
            "available_qty": str(available_qty),
            "shortage_qty": str(shortage_qty),
            "resolved_location_id": resolved_location_id,
            "resolved_location_name": resolved_location_name,
            "batch_required": batch_required,
            "expiry_required": expiry_required,
            "fefo_required": fefo_required,
            "allow_negative_stock": allow_negative_stock,
            "allow_manual_batch_override": allow_manual_override,
            "batch_number": batch_number or None,
            "expiry_date": expiry_date_value.isoformat() if hasattr(expiry_date_value, "isoformat") and expiry_date_value else None,
            "best_batch_number": suggested_batch_number,
            "best_batch_expiry_date": suggested_batch_expiry.isoformat() if hasattr(suggested_batch_expiry, "isoformat") and suggested_batch_expiry else None,
            "best_batch_available_qty": str(suggested_batch_available),
            "product_id": int(product.id),
            "product_name": getattr(product, "productname", None),
        }

    @classmethod
    def list_available_batches(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int | None,
        subentity_id: int | None,
        bill_date,
        product,
        location_id: int | None = None,
        policy=None,
    ) -> dict:
        resolved_location_id = resolve_posting_location_id(
            entity_id=entity_id,
            subentity_id=subentity_id,
            location_id=location_id,
        )

        resolved_location_name = None
        if resolved_location_id:
            resolved_location_name = Godown.objects.filter(id=resolved_location_id).values_list("name", flat=True).first()

        if not product or bool(getattr(product, "is_service", False)):
            return {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "product_id": getattr(product, "id", None),
                "product_name": getattr(product, "productname", None),
                "resolved_location_id": resolved_location_id,
                "resolved_location_name": resolved_location_name,
                "items": [],
                "count": 0,
                "policy": {
                    "mode": str(getattr(policy, "mode", "") or "").upper(),
                    "batch_required_for_sales": bool(getattr(policy, "batch_required_for_sales", False)),
                    "expiry_validation_required": bool(getattr(policy, "expiry_validation_required", False)),
                    "fefo_required": bool(getattr(policy, "fefo_required", False)),
                    "allow_manual_batch_override": bool(getattr(policy, "allow_manual_batch_override", True)),
                    "allow_negative_stock": bool(getattr(policy, "allow_negative_stock", True)),
                    "allow_oversell": bool(getattr(policy, "allow_oversell", True)),
                },
            }

        items = cls._build_available_batch_rows(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            product_id=int(product.id),
            bill_date=bill_date,
            location_id=resolved_location_id,
        )
        return {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "product_id": int(product.id),
            "product_name": getattr(product, "productname", None),
            "resolved_location_id": resolved_location_id,
            "resolved_location_name": resolved_location_name,
            "items": [
                {
                    "batch_number": row["batch_number"],
                    "available_qty": str(row["available_qty"]),
                    "manufacture_date": row["manufacture_date"].isoformat() if row.get("manufacture_date") else None,
                    "expiry_date": row["expiry_date"].isoformat() if row.get("expiry_date") else None,
                    "location_id": row.get("location_id"),
                    "location_name": resolved_location_name,
                }
                for row in items
            ],
            "count": len(items),
            "policy": {
                "mode": str(getattr(policy, "mode", "") or "").upper(),
                "batch_required_for_sales": bool(getattr(policy, "batch_required_for_sales", False)),
                "expiry_validation_required": bool(getattr(policy, "expiry_validation_required", False)),
                "fefo_required": bool(getattr(policy, "fefo_required", False)),
                "allow_manual_batch_override": bool(getattr(policy, "allow_manual_batch_override", True)),
                "allow_negative_stock": bool(getattr(policy, "allow_negative_stock", True)),
                "allow_oversell": bool(getattr(policy, "allow_oversell", True)),
            },
        }
