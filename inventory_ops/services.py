from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

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
        for idx, raw_line in enumerate(payload["lines"], start=1):
            try:
                product = Product.objects.select_related("base_uom").get(id=raw_line["product"], entity_id=payload["entity"])
            except Product.DoesNotExist as exc:
                raise ValidationError({"lines": [f"Invalid product selected for transfer line {idx}."]}) from exc
            qty = _q4(raw_line["qty"])
            if qty <= 0:
                continue
            unit_cost = raw_line.get("unit_cost")
            if unit_cost is None:
                unit_cost = getattr(product, "purchase_rate", None) or getattr(product, "selling_price", None) or Decimal("0")
            unit_cost = _q4(unit_cost)

            line_objs.append(
                InventoryTransferLine(
                    transfer=transfer,
                    product=product,
                    uom=getattr(product, "base_uom", None),
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
        for idx, raw_line in enumerate(payload["lines"], start=1):
            try:
                product = Product.objects.select_related("base_uom").get(id=raw_line["product"], entity_id=payload["entity"])
            except Product.DoesNotExist as exc:
                raise ValidationError({"lines": [f"Invalid product selected for adjustment line {idx}."]}) from exc
            qty = _q4(raw_line["qty"])
            if qty <= 0:
                continue
            unit_cost = _q4(raw_line["unit_cost"])
            direction = raw_line["direction"]
            move_type = InventoryMove.MoveType.IN_ if direction == InventoryAdjustmentLine.Direction.INCREASE else InventoryMove.MoveType.OUT

            line_objs.append(
                InventoryAdjustmentLine(
                    adjustment=adjustment,
                    product=product,
                    uom=getattr(product, "base_uom", None),
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
