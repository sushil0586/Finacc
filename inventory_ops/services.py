from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from django.db.models import Sum
from django.db import transaction
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from catalog.models import Product
from numbering.services import DocumentNumberService, ensure_document_type, ensure_series
from posting.common.location_resolver import resolve_posting_location_id
from posting.models import Entry, EntryStatus, InventoryMove, TxnType
from posting.services.posting_service import IMInput, PostingService

from .models import (
    InventoryAdjustment,
    InventoryAdjustmentLine,
    InventoryAdjustmentStatus,
    InventoryOpsSettings,
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


def _normalize_doc_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    parsed = parse_date(text)
    if parsed:
        return parsed
    if text:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise ValidationError({"date": ["Use YYYY-MM-DD format."]})


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


def _available_value_totals(*, entity_id: int, product_id: int, location_id: int, batch_number: str = "") -> tuple[Decimal, Decimal]:
    rows = InventoryMove.objects.filter(
        entity_id=entity_id,
        product_id=product_id,
        location_id=location_id,
    )
    if batch_number:
        rows = rows.filter(batch_number=batch_number)
    summary = rows.values("move_type").annotate(
        qty_total=Sum("base_qty"),
        value_total=Sum("ext_cost"),
    )
    in_qty = Decimal("0")
    out_qty = Decimal("0")
    in_value = Decimal("0")
    out_value = Decimal("0")
    for row in summary:
        if row["move_type"] == InventoryMove.MoveType.IN_:
            in_qty += Decimal(row["qty_total"] or 0)
            in_value += Decimal(row["value_total"] or 0)
        elif row["move_type"] == InventoryMove.MoveType.OUT:
            out_qty += Decimal(row["qty_total"] or 0)
            out_value += Decimal(row["value_total"] or 0)
    return _q4(in_qty - out_qty), _q4(in_value - out_value)


def _load_product_for_line(*, entity_id: int, product_id: int, line_kind: str, line_no: int) -> Product:
    try:
        return Product.objects.select_related("base_uom").get(id=product_id, entity_id=entity_id)
    except Product.DoesNotExist as exc:
        raise ValidationError({"lines": [f"Invalid product selected for {line_kind} line {line_no}."]}) from exc


def _resolve_unit_cost_for_line(*, product: Product, raw_line: dict, line_kind: str, line_no: int, require_mode: str) -> Decimal:
    explicit_cost = _q4_or_none(raw_line.get("unit_cost"))
    if explicit_cost is not None:
        if explicit_cost < 0:
            raise ValidationError({"lines": [f"Unit cost cannot be negative for {line_kind} line {line_no}."]})
        if require_mode == "always_required" and explicit_cost <= Decimal("0.0000"):
            raise ValidationError({"lines": [f"Unit cost is required for {line_kind} line {line_no}."]})
        return explicit_cost
    default_cost = _default_unit_cost(product)
    if require_mode == "always_required":
        raise ValidationError({"lines": [f"Unit cost is required for {line_kind} line {line_no}."]})
    if require_mode == "required_if_no_default" and default_cost <= Decimal("0.0000"):
        raise ValidationError(
            {"lines": [f"Unit cost is required for {line_kind} line {line_no} because stock value is being introduced."]}
        )
    return default_cost


def _get_inventory_ops_settings(*, entity_id: int, subentity_id: int | None) -> InventoryOpsSettings:
    settings_obj, _ = InventoryOpsSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
    return settings_obj


def _policy_value(settings_obj: InventoryOpsSettings, key: str, default):
    return (settings_obj.policy_controls or {}).get(key, default)


def _doc_type_for_inventory(*, settings_obj: InventoryOpsSettings, series_key: str):
    cfg = {
        "inventory_transfer": {
            "doc_key": "INVENTORY_TRANSFER",
            "label": "Inventory Transfer",
            "default_code": settings_obj.default_doc_code_transfer or "ITF",
            "prefix": settings_obj.default_doc_code_transfer or "ITF",
        },
        "inventory_adjustment": {
            "doc_key": "INVENTORY_ADJUSTMENT",
            "label": "Inventory Adjustment",
            "default_code": settings_obj.default_doc_code_adjustment or "IAD",
            "prefix": settings_obj.default_doc_code_adjustment or "IAD",
        },
    }[series_key]
    doc_type = ensure_document_type(module="inventory_ops", doc_key=cfg["doc_key"], name=cfg["label"], default_code=cfg["default_code"])
    return doc_type, cfg


def _allocate_inventory_doc_number(
    *,
    settings_obj: InventoryOpsSettings,
    entity_id: int,
    entityfinid_id: int | None,
    subentity_id: int | None,
    series_key: str,
    on_date,
) -> str:
    on_date = _normalize_doc_date(on_date)
    _, cfg = _doc_type_for_inventory(settings_obj=settings_obj, series_key=series_key)
    doc_code = cfg["default_code"]
    if not entityfinid_id:
        return f"{doc_code}-{uuid4().hex[:8].upper()}"

    doc_type, cfg = _doc_type_for_inventory(settings_obj=settings_obj, series_key=series_key)
    ensure_series(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        doc_type_id=doc_type.id,
        doc_code=doc_code,
        prefix=cfg["prefix"],
        start=1,
        padding=4,
        reset="yearly",
        include_year=False,
        include_month=False,
    )
    res = DocumentNumberService.allocate_final(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        doc_type_id=doc_type.id,
        doc_code=doc_code,
        on_date=on_date,
    )
    return res.display_no


def _derive_transfer_unit_cost(*, entity_id: int, product: Product, source_location_id: int, batch_number: str) -> Decimal:
    available_qty, available_value = _available_value_totals(
        entity_id=entity_id,
        product_id=product.id,
        location_id=source_location_id,
        batch_number=batch_number,
    )
    if available_qty > Decimal("0.0000") and available_value > Decimal("0.0000"):
        return _q4(available_value / available_qty)

    last_known = InventoryMove.objects.filter(
        entity_id=entity_id,
        product_id=product.id,
        location_id=source_location_id,
    ).exclude(unit_cost__lte=0)
    if batch_number:
        last_known = last_known.filter(batch_number=batch_number)
    last_known = last_known.order_by("-posting_date", "-id").values_list("unit_cost", flat=True).first()
    if last_known not in (None, ""):
        return _q4(last_known)
    return _default_unit_cost(product)


def _extract_batch_fields(
    *,
    product: Product,
    raw_line: dict,
    line_kind: str,
    line_no: int,
    require_batch: bool = True,
    require_expiry: bool = False,
) -> tuple[str, object | None, object | None]:
    batch_number = _clean_batch_number(raw_line.get("batch_number"))
    manufacture_date = raw_line.get("manufacture_date")
    expiry_date = raw_line.get("expiry_date")
    if getattr(product, "is_batch_managed", False):
        if require_batch and not batch_number:
            raise ValidationError({"lines": [f"Batch number is required for batch-managed {line_kind} line {line_no}."]})
        if require_expiry and getattr(product, "is_expiry_tracked", False) and not expiry_date:
            raise ValidationError({"lines": [f"Expiry date is required for expiry-tracked {line_kind} line {line_no}."]})
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
    entry_id: int | None


class InventoryTransferService:
    @staticmethod
    def _resolve_locations(*, payload: dict) -> tuple[int, int]:
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
        return source_location_id, destination_location_id

    @staticmethod
    def _build_transfer_lines_and_inputs(
        *,
        transfer: InventoryTransfer,
        payload: dict,
        source_location_id: int,
        destination_location_id: int,
        settings_obj: InventoryOpsSettings | None = None,
    ) -> tuple[list[InventoryTransferLine], list[IMInput]]:
        line_objs: list[InventoryTransferLine] = []
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
                require_batch=bool(_policy_value(settings_obj, "require_batch_for_batch_managed_items", True)) if settings_obj else True,
                require_expiry=bool(_policy_value(settings_obj, "require_expiry_when_expiry_tracked", True)) if settings_obj else False,
            )
            explicit_cost = _q4_or_none(raw_line.get("unit_cost"))
            if explicit_cost is not None and explicit_cost < 0:
                raise ValidationError({"lines": [f"Unit cost cannot be negative for transfer line {idx}."]})
            allow_manual_cost = bool(_policy_value(settings_obj, "allow_manual_transfer_cost_override", False)) if settings_obj else False
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
            if explicit_cost is None or explicit_cost <= Decimal("0.0000") or not allow_manual_cost:
                unit_cost = _derive_transfer_unit_cost(
                    entity_id=payload["entity"],
                    product=product,
                    source_location_id=source_location_id,
                    batch_number=batch_number,
                )
            else:
                unit_cost = explicit_cost

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
                    cost_source=InventoryMove.CostSource.AVG,
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
                    cost_source=InventoryMove.CostSource.AVG,
                    detail_id=idx,
                    location_id=transfer.destination_location_id,
                    source_location_id=transfer.source_location_id,
                    destination_location_id=transfer.destination_location_id,
                    movement_nature=InventoryMove.MovementNature.TRANSFER,
                    movement_group=group,
                    movement_reason="inventory transfer in",
                )
            )
        if not line_objs:
            raise ValidationError({"lines": ["At least one valid transfer line is required."]})
        return line_objs, im_inputs

    @staticmethod
    def _replace_transfer_lines(*, transfer: InventoryTransfer, line_objs: list[InventoryTransferLine]) -> None:
        transfer.lines.all().delete()
        InventoryTransferLine.objects.bulk_create(line_objs)

    @staticmethod
    def _post_transfer(*, transfer: InventoryTransfer, im_inputs: list[IMInput], user_id: int | None, narration_prefix: str | None = None):
        posting = PostingService(
            entity_id=transfer.entity_id,
            entityfin_id=transfer.entityfin_id,
            subentity_id=transfer.subentity_id,
            user_id=user_id,
        )
        return posting.post(
            txn_type=TxnType.INVENTORY_TRANSFER,
            txn_id=transfer.id,
            voucher_no=transfer.transfer_no,
            voucher_date=transfer.transfer_date,
            posting_date=transfer.transfer_date,
            narration=(narration_prefix or transfer.narration or f"Inventory transfer {transfer.transfer_no}"),
            jl_inputs=[],
            im_inputs=im_inputs,
            use_advisory_lock=False,
            mark_posted=True,
        )

    @staticmethod
    def _get_transfer_for_update(*, transfer_id: int) -> InventoryTransfer:
        try:
            return InventoryTransfer.objects.select_for_update().get(id=transfer_id)
        except InventoryTransfer.DoesNotExist as exc:
            raise ValidationError("Inventory transfer not found.") from exc

    @staticmethod
    @transaction.atomic
    def create_transfer(*, payload: dict, user_id: int | None) -> InventoryTransferResult:
        source_location_id, destination_location_id = InventoryTransferService._resolve_locations(payload=payload)
        settings_obj = _get_inventory_ops_settings(entity_id=payload["entity"], subentity_id=payload.get("subentity"))

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
        transfer.transfer_no = _allocate_inventory_doc_number(
            settings_obj=settings_obj,
            entity_id=transfer.entity_id,
            entityfinid_id=transfer.entityfin_id,
            subentity_id=transfer.subentity_id,
            series_key="inventory_transfer",
            on_date=transfer.transfer_date,
        )
        transfer.save(update_fields=["transfer_no"])
        line_objs, _ = InventoryTransferService._build_transfer_lines_and_inputs(
            transfer=transfer,
            payload=payload,
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            settings_obj=settings_obj,
        )
        InventoryTransferService._replace_transfer_lines(transfer=transfer, line_objs=line_objs)
        transfer.refresh_from_db()
        return InventoryTransferResult(transfer=transfer, entry_id=transfer.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def update_transfer(*, transfer_id: int, payload: dict, user_id: int | None) -> InventoryTransferResult:
        transfer = InventoryTransferService._get_transfer_for_update(transfer_id=transfer_id)
        if transfer.status != InventoryTransferStatus.DRAFT:
            raise ValidationError("Only draft transfers can be edited.")
        source_location_id, destination_location_id = InventoryTransferService._resolve_locations(payload=payload)
        transfer.entityfin_id = payload.get("entityfinid")
        transfer.subentity_id = payload.get("subentity")
        transfer.transfer_date = payload["transfer_date"]
        transfer.source_location_id = source_location_id
        transfer.destination_location_id = destination_location_id
        transfer.reference_no = payload.get("reference_no") or ""
        transfer.narration = payload.get("narration") or ""
        transfer.updated_by_id = user_id
        transfer.save(
            update_fields=[
                "entityfin",
                "subentity",
                "transfer_date",
                "source_location",
                "destination_location",
                "reference_no",
                "narration",
                "updated_by",
                "updated_at",
            ]
        )
        line_objs, _ = InventoryTransferService._build_transfer_lines_and_inputs(
            transfer=transfer,
            payload=payload,
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            settings_obj=_get_inventory_ops_settings(entity_id=transfer.entity_id, subentity_id=transfer.subentity_id),
        )
        InventoryTransferService._replace_transfer_lines(transfer=transfer, line_objs=line_objs)
        transfer.refresh_from_db()
        return InventoryTransferResult(transfer=transfer, entry_id=transfer.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def post_transfer(*, transfer_id: int, user_id: int | None) -> InventoryTransferResult:
        transfer = InventoryTransferService._get_transfer_for_update(transfer_id=transfer_id)
        if transfer.status == InventoryTransferStatus.CANCELLED:
            raise ValidationError("Cancelled transfer cannot be posted.")
        if transfer.status == InventoryTransferStatus.POSTED:
            return InventoryTransferResult(transfer=transfer, entry_id=transfer.posting_entry_id)

        payload = {
            "entity": transfer.entity_id,
            "entityfinid": transfer.entityfin_id,
            "subentity": transfer.subentity_id,
            "transfer_date": transfer.transfer_date,
            "source_location": transfer.source_location_id,
            "destination_location": transfer.destination_location_id,
            "reference_no": transfer.reference_no,
            "narration": transfer.narration,
            "lines": [
                {
                    "product": line.product_id,
                    "qty": line.qty,
                    "unit_cost": line.unit_cost,
                    "batch_number": line.batch_number,
                    "manufacture_date": line.manufacture_date,
                    "expiry_date": line.expiry_date,
                    "note": line.note,
                }
                for line in transfer.lines.all().select_related("product")
            ],
        }
        _, im_inputs = InventoryTransferService._build_transfer_lines_and_inputs(
            transfer=transfer,
            payload=payload,
            source_location_id=transfer.source_location_id,
            destination_location_id=transfer.destination_location_id,
            settings_obj=_get_inventory_ops_settings(entity_id=transfer.entity_id, subentity_id=transfer.subentity_id),
        )
        entry = InventoryTransferService._post_transfer(
            transfer=transfer,
            im_inputs=im_inputs,
            user_id=user_id,
        )
        transfer.status = InventoryTransferStatus.POSTED
        transfer.posting_entry_id = entry.id
        transfer.updated_by_id = user_id
        transfer.save(update_fields=["status", "posting_entry_id", "updated_by", "updated_at"])
        transfer.refresh_from_db()
        return InventoryTransferResult(transfer=transfer, entry_id=entry.id)

    @staticmethod
    @transaction.atomic
    def unpost_transfer(*, transfer_id: int, user_id: int | None, reason: str | None = None) -> InventoryTransferResult:
        transfer = InventoryTransferService._get_transfer_for_update(transfer_id=transfer_id)
        if transfer.status != InventoryTransferStatus.POSTED:
            raise ValidationError("Only posted transfers can be unposted.")

        entry = InventoryTransferService._post_transfer(
            transfer=transfer,
            im_inputs=[],
            user_id=user_id,
            narration_prefix=f"Reversal for {transfer.transfer_no}: {(reason or '').strip()}".strip(),
        )
        Entry.objects.filter(
            entity_id=transfer.entity_id,
            entityfin_id=transfer.entityfin_id,
            subentity_id=transfer.subentity_id,
            txn_type=TxnType.INVENTORY_TRANSFER,
            txn_id=transfer.id,
        ).update(
            status=EntryStatus.REVERSED,
            narration=f"Reversed: {(reason or '').strip()}".strip(),
        )
        transfer.status = InventoryTransferStatus.DRAFT
        transfer.posting_entry_id = entry.id
        transfer.updated_by_id = user_id
        transfer.save(update_fields=["status", "posting_entry_id", "updated_by", "updated_at"])
        transfer.refresh_from_db()
        return InventoryTransferResult(transfer=transfer, entry_id=entry.id)

    @staticmethod
    @transaction.atomic
    def cancel_transfer(*, transfer_id: int, user_id: int | None, reason: str | None = None) -> InventoryTransferResult:
        transfer = InventoryTransferService._get_transfer_for_update(transfer_id=transfer_id)
        if transfer.status == InventoryTransferStatus.POSTED:
            raise ValidationError("Posted transfer must be unposted before cancellation.")
        if transfer.status == InventoryTransferStatus.CANCELLED:
            return InventoryTransferResult(transfer=transfer, entry_id=transfer.posting_entry_id)
        transfer.status = InventoryTransferStatus.CANCELLED
        suffix = f" | Cancelled: {reason.strip()}" if reason and reason.strip() else ""
        transfer.narration = f"{transfer.narration or ''}{suffix}".strip(" |")
        transfer.updated_by_id = user_id
        transfer.save(update_fields=["status", "narration", "updated_by", "updated_at"])
        transfer.refresh_from_db()
        return InventoryTransferResult(transfer=transfer, entry_id=transfer.posting_entry_id)


@dataclass
class InventoryAdjustmentResult:
    adjustment: InventoryAdjustment
    entry_id: int


class InventoryAdjustmentService:
    @staticmethod
    @transaction.atomic
    def create_adjustment(*, payload: dict, user_id: int | None) -> InventoryAdjustmentResult:
        settings_obj = _get_inventory_ops_settings(entity_id=payload["entity"], subentity_id=payload.get("subentity"))
        location_id = resolve_posting_location_id(
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
            godown_id=payload.get("location"),
            location_id=payload.get("location"),
        )
        if location_id is None:
            raise ValidationError("A stock location is required for inventory adjustment.")
        require_reason = bool(_policy_value(settings_obj, "require_reason_on_adjustment", True))
        if require_reason:
            header_reason = str(payload.get("narration") or "").strip()
            line_reason_present = any(str((line or {}).get("note") or "").strip() for line in payload.get("lines", []))
            if not header_reason and not line_reason_present:
                raise ValidationError({"narration": "Narration or line note is required for inventory adjustment."})

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
        adjustment.adjustment_no = _allocate_inventory_doc_number(
            settings_obj=settings_obj,
            entity_id=adjustment.entity_id,
            entityfinid_id=adjustment.entityfin_id,
            subentity_id=adjustment.subentity_id,
            series_key="inventory_adjustment",
            on_date=adjustment.adjustment_date,
        )
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
                require_batch=bool(_policy_value(settings_obj, "require_batch_for_batch_managed_items", True)),
                require_expiry=bool(_policy_value(settings_obj, "require_expiry_when_expiry_tracked", True)),
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
                require_mode=(
                    str(_policy_value(settings_obj, "positive_adjustment_cost_mode", "required_if_no_default"))
                    if direction == InventoryAdjustmentLine.Direction.INCREASE
                    else "auto_if_available"
                ),
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
