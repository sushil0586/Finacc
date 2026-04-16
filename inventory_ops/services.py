from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from django.db.models import Sum
from django.db import transaction
from rest_framework.exceptions import ValidationError

from catalog.models import Product
from posting.common.location_resolver import resolve_posting_location_id
from posting.models import InventoryMove, TxnType
from posting.services.posting_service import IMInput, PostingService

from .models import (
    InventoryAdjustment,
    InventoryAdjustmentLine,
    InventoryAdjustmentStatus,
    InventoryTransfer,
    InventoryTransferLine,
    InventoryTransferStatus,
)


def _q4(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0000"))


def _q4_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return _q4(value)


def _default_unit_cost(product: Product) -> Decimal:
    price = getattr(product, "purchase_rate", None)
    if price in (None, ""):
        price = getattr(product, "selling_price", None)
    return _q4(price or 0)


def _clean_batch_number(value) -> str:
    return str(value or "").strip()


def _available_base_qty(*, entity_id: int, product_id: int, location_id: int, batch_number: str = "") -> Decimal:
    rows = InventoryMove.objects.filter(
        entity_id=entity_id,
        product_id=product_id,
        location_id=location_id,
    )
    if batch_number:
        rows = rows.filter(batch_number=batch_number)
    summary = rows.values("move_type").annotate(total=Sum("base_qty"))
    in_total = Decimal("0")
    out_total = Decimal("0")
    for row in summary:
        if row["move_type"] == InventoryMove.MoveType.IN_:
            in_total += Decimal(row["total"] or 0)
        elif row["move_type"] == InventoryMove.MoveType.OUT:
            out_total += Decimal(row["total"] or 0)
    return _q4(in_total - out_total)


def _load_product_for_line(*, entity_id: int, product_id: int, line_kind: str, line_no: int) -> Product:
    try:
        return Product.objects.select_related("base_uom").get(id=product_id, entity_id=entity_id)
    except Product.DoesNotExist as exc:
        raise ValidationError({"lines": [f"Invalid product selected for {line_kind} line {line_no}."]}) from exc


def _resolve_unit_cost_for_line(*, product: Product, raw_line: dict, line_kind: str, line_no: int, require_explicit_or_default: bool) -> Decimal:
    explicit_cost = _q4_or_none(raw_line.get("unit_cost"))
    if explicit_cost is not None:
        if explicit_cost < 0:
            raise ValidationError({"lines": [f"Unit cost cannot be negative for {line_kind} line {line_no}."]})
        return explicit_cost
    default_cost = _default_unit_cost(product)
    if require_explicit_or_default and default_cost <= Decimal("0.0000"):
        raise ValidationError(
            {"lines": [f"Unit cost is required for {line_kind} line {line_no} because stock value is being introduced."]}
        )
    return default_cost


def _extract_batch_fields(*, product: Product, raw_line: dict, line_kind: str, line_no: int) -> tuple[str, object | None, object | None]:
    batch_number = _clean_batch_number(raw_line.get("batch_number"))
    manufacture_date = raw_line.get("manufacture_date")
    expiry_date = raw_line.get("expiry_date")
    if getattr(product, "is_batch_managed", False):
        if not batch_number:
            raise ValidationError({"lines": [f"Batch number is required for batch-managed {line_kind} line {line_no}."]})
    elif batch_number or manufacture_date or expiry_date:
        raise ValidationError({"lines": [f"Batch details are only allowed for batch-managed items on {line_kind} line {line_no}."]})
    return batch_number, manufacture_date, expiry_date


def _assert_stock_available(
    *,
    entity_id: int,
    product: Product,
    location_id: int,
    required_qty: Decimal,
    batch_number: str,
    reserved_by_key: dict[tuple[int, int, str], Decimal],
    line_kind: str,
    line_no: int,
):
    reservation_key = (product.id, location_id, batch_number)
    already_reserved = reserved_by_key.get(reservation_key, Decimal("0"))
    available_qty = _available_base_qty(
        entity_id=entity_id,
        product_id=product.id,
        location_id=location_id,
        batch_number=batch_number,
    )
    effective_available = _q4(available_qty - already_reserved)
    if effective_available < required_qty:
        shortage = _q4(required_qty - max(effective_available, Decimal("0")))
        scope = f"batch {batch_number}" if batch_number else "selected location"
        raise ValidationError(
            {
                "lines": [
                    f"Insufficient stock for {line_kind} line {line_no}. Available at {scope}: {effective_available}, short by {shortage}."
                ]
            }
        )
    reserved_by_key[reservation_key] = _q4(already_reserved + required_qty)


@dataclass
class InventoryTransferResult:
    transfer: InventoryTransfer
    entry_id: int


class InventoryTransferService:
    @staticmethod
    @transaction.atomic
    def create_transfer(*, payload: dict, user_id: int | None) -> InventoryTransferResult:
        source_location_id = resolve_posting_location_id(
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
            godown_id=payload.get("source_location"),
            location_id=payload.get("source_location"),
        )
        destination_location_id = resolve_posting_location_id(
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
            godown_id=payload.get("destination_location"),
            location_id=payload.get("destination_location"),
        )
        if source_location_id is None or destination_location_id is None:
            raise ValidationError("A source and destination location are required for inventory transfer.")
        if source_location_id == destination_location_id:
            raise ValidationError("Source and destination locations must be different.")

        transfer = InventoryTransfer.objects.create(
            entity_id=payload["entity"],
            entityfin_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
            transfer_date=payload["transfer_date"],
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            reference_no=payload.get("reference_no") or "",
            narration=payload.get("narration") or "",
            status=InventoryTransferStatus.DRAFT,
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        transfer.transfer_no = f"ITF-{transfer.id:06d}"
        transfer.save(update_fields=["transfer_no"])

        line_objs = []
        im_inputs: list[IMInput] = []
        reserved_stock: dict[tuple[int, int, str], Decimal] = {}
        for idx, raw_line in enumerate(payload["lines"], start=1):
            product = _load_product_for_line(entity_id=payload["entity"], product_id=raw_line["product"], line_kind="transfer", line_no=idx)
            qty = _q4(raw_line["qty"])
            if qty <= 0:
                continue
            batch_number, manufacture_date, expiry_date = _extract_batch_fields(
                product=product,
                raw_line=raw_line,
                line_kind="transfer",
                line_no=idx,
            )
            _assert_stock_available(
                entity_id=payload["entity"],
                product=product,
                location_id=source_location_id,
                required_qty=qty,
                batch_number=batch_number,
                reserved_by_key=reserved_stock,
                line_kind="transfer",
                line_no=idx,
            )
            unit_cost = _resolve_unit_cost_for_line(
                product=product,
                raw_line=raw_line,
                line_kind="transfer",
                line_no=idx,
                require_explicit_or_default=False,
            )

            line_objs.append(
                InventoryTransferLine(
                    transfer=transfer,
                    product=product,
                    uom=getattr(product, "base_uom", None),
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    qty=qty,
                    unit_cost=unit_cost,
                    note=raw_line.get("note") or "",
                )
            )
            group = uuid4()
            im_inputs.append(
                IMInput(
                    product_id=product.id,
                    qty=qty,
                    base_qty=qty,
                    uom_id=getattr(product, "base_uom_id", None),
                    base_uom_id=getattr(product, "base_uom_id", None),
                    uom_factor=Decimal("1"),
                    unit_cost=unit_cost,
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    move_type=InventoryMove.MoveType.OUT,
                    cost_source=InventoryMove.CostSource.MANUAL,
                    detail_id=idx,
                    location_id=transfer.source_location_id,
                    source_location_id=transfer.source_location_id,
                    destination_location_id=transfer.destination_location_id,
                    movement_nature=InventoryMove.MovementNature.TRANSFER,
                    movement_group=group,
                    movement_reason="inventory transfer out",
                )
            )
            im_inputs.append(
                IMInput(
                    product_id=product.id,
                    qty=qty,
                    base_qty=qty,
                    uom_id=getattr(product, "base_uom_id", None),
                    base_uom_id=getattr(product, "base_uom_id", None),
                    uom_factor=Decimal("1"),
                    unit_cost=unit_cost,
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    move_type=InventoryMove.MoveType.IN_,
                    cost_source=InventoryMove.CostSource.MANUAL,
                    detail_id=idx,
                    location_id=transfer.destination_location_id,
                    source_location_id=transfer.source_location_id,
                    destination_location_id=transfer.destination_location_id,
                    movement_nature=InventoryMove.MovementNature.TRANSFER,
                    movement_group=group,
                    movement_reason="inventory transfer in",
                )
            )

        InventoryTransferLine.objects.bulk_create(line_objs)

        posting = PostingService(
            entity_id=transfer.entity_id,
            entityfin_id=transfer.entityfin_id,
            subentity_id=transfer.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.INVENTORY_TRANSFER,
            txn_id=transfer.id,
            voucher_no=transfer.transfer_no,
            voucher_date=transfer.transfer_date,
            posting_date=transfer.transfer_date,
            narration=transfer.narration or f"Inventory transfer {transfer.transfer_no}",
            jl_inputs=[],
            im_inputs=im_inputs,
            use_advisory_lock=False,
            mark_posted=True,
        )

        InventoryTransfer.objects.filter(id=transfer.id).update(status=InventoryTransferStatus.POSTED, posting_entry_id=entry.id)
        transfer.refresh_from_db()
        return InventoryTransferResult(transfer=transfer, entry_id=entry.id)


@dataclass
class InventoryAdjustmentResult:
    adjustment: InventoryAdjustment
    entry_id: int


class InventoryAdjustmentService:
    @staticmethod
    @transaction.atomic
    def create_adjustment(*, payload: dict, user_id: int | None) -> InventoryAdjustmentResult:
        location_id = resolve_posting_location_id(
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
            godown_id=payload.get("location"),
            location_id=payload.get("location"),
        )
        if location_id is None:
            raise ValidationError("A stock location is required for inventory adjustment.")

        adjustment = InventoryAdjustment.objects.create(
            entity_id=payload["entity"],
            entityfin_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
            adjustment_date=payload["adjustment_date"],
            location_id=location_id,
            reference_no=payload.get("reference_no") or "",
            narration=payload.get("narration") or "",
            status=InventoryAdjustmentStatus.DRAFT,
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        adjustment.adjustment_no = f"IAD-{adjustment.id:06d}"
        adjustment.save(update_fields=["adjustment_no"])

        line_objs = []
        im_inputs: list[IMInput] = []
        reserved_stock: dict[tuple[int, int, str], Decimal] = {}
        for idx, raw_line in enumerate(payload["lines"], start=1):
            product = _load_product_for_line(entity_id=payload["entity"], product_id=raw_line["product"], line_kind="adjustment", line_no=idx)
            qty = _q4(raw_line["qty"])
            if qty <= 0:
                continue
            direction = raw_line["direction"]
            batch_number, manufacture_date, expiry_date = _extract_batch_fields(
                product=product,
                raw_line=raw_line,
                line_kind="adjustment",
                line_no=idx,
            )
            if direction == InventoryAdjustmentLine.Direction.DECREASE:
                _assert_stock_available(
                    entity_id=payload["entity"],
                    product=product,
                    location_id=location_id,
                    required_qty=qty,
                    batch_number=batch_number,
                    reserved_by_key=reserved_stock,
                    line_kind="adjustment",
                    line_no=idx,
                )
            unit_cost = _resolve_unit_cost_for_line(
                product=product,
                raw_line=raw_line,
                line_kind="adjustment",
                line_no=idx,
                require_explicit_or_default=direction == InventoryAdjustmentLine.Direction.INCREASE,
            )
            move_type = InventoryMove.MoveType.IN_ if direction == InventoryAdjustmentLine.Direction.INCREASE else InventoryMove.MoveType.OUT

            line_objs.append(
                InventoryAdjustmentLine(
                    adjustment=adjustment,
                    product=product,
                    uom=getattr(product, "base_uom", None),
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    direction=direction,
                    qty=qty,
                    unit_cost=unit_cost,
                    note=raw_line.get("note") or "",
                )
            )
            im_inputs.append(
                IMInput(
                    product_id=product.id,
                    qty=qty,
                    base_qty=qty,
                    uom_id=getattr(product, "base_uom_id", None),
                    base_uom_id=getattr(product, "base_uom_id", None),
                    uom_factor=Decimal("1"),
                    unit_cost=unit_cost,
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    move_type=move_type,
                    cost_source=InventoryMove.CostSource.MANUAL,
                    detail_id=idx,
                    location_id=adjustment.location_id,
                    source_location_id=adjustment.location_id,
                    destination_location_id=adjustment.location_id,
                    movement_nature=InventoryMove.MovementNature.ADJUSTMENT,
                    movement_reason=raw_line.get("note") or adjustment.narration or "inventory adjustment",
                )
            )

        InventoryAdjustmentLine.objects.bulk_create(line_objs)

        posting = PostingService(
            entity_id=adjustment.entity_id,
            entityfin_id=adjustment.entityfin_id,
            subentity_id=adjustment.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.INVENTORY_ADJUSTMENT,
            txn_id=adjustment.id,
            voucher_no=adjustment.adjustment_no,
            voucher_date=adjustment.adjustment_date,
            posting_date=adjustment.adjustment_date,
            narration=adjustment.narration or f"Inventory adjustment {adjustment.adjustment_no}",
            jl_inputs=[],
            im_inputs=im_inputs,
            use_advisory_lock=False,
            mark_posted=True,
        )

        InventoryAdjustment.objects.filter(id=adjustment.id).update(status=InventoryAdjustmentStatus.POSTED, posting_entry_id=entry.id)
        adjustment.refresh_from_db()
        return InventoryAdjustmentResult(adjustment=adjustment, entry_id=entry.id)
