from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import Sum
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Product
from numbering.services import DocumentNumberService, ensure_document_type, ensure_series
from posting.common.location_resolver import resolve_posting_location_id
from posting.models import Entry, EntryStatus, InventoryMove, TxnType
from posting.services.posting_service import IMInput, PostingService

from .models import (
    ManufacturingRoute,
    ManufacturingRouteStep,
    ManufacturingBOM,
    ManufacturingBOMMaterial,
    ManufacturingSettings,
    ManufacturingOperationStatus,
    ManufacturingBatchTraceLink,
    ManufacturingWorkOrder,
    ManufacturingWorkOrderOperation,
    ManufacturingWorkOrderMaterial,
    ManufacturingWorkOrderAdditionalCost,
    ManufacturingWorkOrderOutput,
    ManufacturingWorkOrderStatus,
)


def _q4(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0000"))


def _q4_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return _q4(value)


def _clean_batch_number(value) -> str:
    return str(value or "").strip()


def _reference_batch_number(*, reference_no: str, fallback: str) -> str:
    value = _clean_batch_number(reference_no) or _clean_batch_number(fallback)
    if not value:
        return ""
    return value[:80]


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
    rows = InventoryMove.objects.filter(entity_id=entity_id, product_id=product_id, location_id=location_id)
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
    rows = InventoryMove.objects.filter(entity_id=entity_id, product_id=product_id, location_id=location_id)
    if batch_number:
        rows = rows.filter(batch_number=batch_number)
    summary = rows.values("move_type").annotate(qty_total=Sum("base_qty"), value_total=Sum("ext_cost"))
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


def _default_unit_cost(product: Product) -> Decimal:
    price = getattr(product, "purchase_rate", None)
    if price in (None, ""):
        price = getattr(product, "selling_price", None)
    return _q4(price or 0)


def _derive_issue_unit_cost(*, entity_id: int, product: Product, location_id: int, batch_number: str) -> Decimal:
    available_qty, available_value = _available_value_totals(
        entity_id=entity_id,
        product_id=product.id,
        location_id=location_id,
        batch_number=batch_number,
    )
    if available_qty > Decimal("0.0000") and available_value > Decimal("0.0000"):
        return _q4(available_value / available_qty)
    return _default_unit_cost(product)


def _policy_value(settings_obj: ManufacturingSettings, key: str, default):
    return (settings_obj.policy_controls or {}).get(key, default)


def _get_settings(*, entity_id: int, subentity_id: int | None) -> ManufacturingSettings:
    settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
    return settings_obj


def _doc_type_for_work_order(*, settings_obj: ManufacturingSettings):
    doc_code = settings_obj.default_doc_code_work_order or "MWO"
    doc_type = ensure_document_type(
        module="manufacturing",
        doc_key="MANUFACTURING_WORK_ORDER",
        name="Manufacturing Work Order",
        default_code=doc_code,
    )
    return doc_type, doc_code


def _allocate_work_order_no(
    *,
    settings_obj: ManufacturingSettings,
    entity_id: int,
    entityfinid_id: int | None,
    subentity_id: int | None,
    on_date,
) -> str:
    on_date = _normalize_doc_date(on_date)
    _, doc_code = _doc_type_for_work_order(settings_obj=settings_obj)
    if not entityfinid_id:
        return f"{doc_code}-{uuid4().hex[:8].upper()}"

    doc_type, doc_code = _doc_type_for_work_order(settings_obj=settings_obj)
    ensure_series(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        doc_type_id=doc_type.id,
        doc_code=doc_code,
        prefix=doc_code,
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


def _load_product_for_scope(*, entity_id: int, product_id: int, field_name: str, line_no: int | None = None) -> Product:
    try:
        return Product.objects.select_related("base_uom").get(id=product_id, entity_id=entity_id)
    except Product.DoesNotExist as exc:
        label = f"{field_name} line {line_no}" if line_no is not None else field_name
        raise ValidationError({field_name: [f"Invalid product selected for {label}."]}) from exc


def _extract_batch_fields(
    *,
    product: Product,
    raw_line: dict,
    line_kind: str,
    line_no: int,
    settings_obj: ManufacturingSettings,
) -> tuple[str, object | None, object | None]:
    batch_number = _clean_batch_number(raw_line.get("batch_number"))
    manufacture_date = raw_line.get("manufacture_date")
    expiry_date = raw_line.get("expiry_date")
    require_batch = bool(_policy_value(settings_obj, "require_batch_for_batch_managed_items", True))
    require_expiry = bool(_policy_value(settings_obj, "require_expiry_when_expiry_tracked", True))
    if getattr(product, "is_batch_managed", False):
        if require_batch and not batch_number:
            raise ValidationError({"lines": [f"Batch number is required for batch-managed {line_kind} line {line_no}."]})
        if require_expiry and getattr(product, "is_expiry_tracked", False) and not expiry_date:
            raise ValidationError({"lines": [f"Expiry date is required for expiry-tracked {line_kind} line {line_no}."]})
    elif batch_number or manufacture_date or expiry_date:
        raise ValidationError({"lines": [f"Batch details are only allowed for batch-managed items on {line_kind} line {line_no}."]})
    if manufacture_date and expiry_date and expiry_date < manufacture_date:
        raise ValidationError({"lines": [f"Expiry date cannot be earlier than manufacture date on {line_kind} line {line_no}."]})
    return batch_number, manufacture_date, expiry_date


def _assert_stock_available(
    *,
    entity_id: int,
    product: Product,
    location_id: int,
    required_qty: Decimal,
    batch_number: str,
    reserved_by_key: dict[tuple[int, int, str], Decimal],
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
        raise ValidationError(
            {
                "materials": [
                    f"Insufficient stock for material line {line_no}. Available: {effective_available}, required: {required_qty}."
                ]
            }
        )
    reserved_by_key[reservation_key] = _q4(already_reserved + required_qty)


def _load_bom(*, entity_id: int, subentity_id: int | None, bom_id: int | None) -> ManufacturingBOM | None:
    if not bom_id:
        return None
    qs = ManufacturingBOM.objects.filter(entity_id=entity_id, id=bom_id).select_related("finished_product", "output_uom", "route")
    if subentity_id is None:
        qs = qs.filter(subentity_id__isnull=True)
    else:
        qs = qs.filter(subentity_id=subentity_id)
    bom = qs.first()
    if bom is None:
        raise ValidationError({"bom": "Invalid BOM selected for this scope."})
    return bom


def _explode_bom_materials(*, bom: ManufacturingBOM, target_output_qty: Decimal) -> list[dict]:
    if bom.output_qty <= Decimal("0.0000"):
        raise ValidationError({"bom": "BOM output quantity must be greater than zero."})
    scale = _q4(target_output_qty / Decimal(bom.output_qty))
    rows: list[dict] = []
    for line in bom.materials.all().select_related("material_product", "uom").order_by("line_no", "id"):
        required_qty = _q4(Decimal(line.qty) * scale)
        rows.append(
            {
                "material_product": line.material_product_id,
                "required_qty": required_qty,
                "actual_qty": required_qty,
                "unit_cost": None,
                "batch_number": "",
                "manufacture_date": None,
                "expiry_date": None,
                "waste_qty": Decimal("0.0000"),
                "note": line.note or "",
            }
        )
    return rows


@dataclass
class ManufacturingWorkOrderResult:
    work_order: ManufacturingWorkOrder
    entry_id: int | None


class ManufacturingWorkOrderService:
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
        if source_location_id is None:
            raise ValidationError({"source_location": "A source location is required."})
        if destination_location_id is None:
            raise ValidationError({"destination_location": "A destination location is required."})
        return source_location_id, destination_location_id

    @staticmethod
    def _normalize_outputs(*, payload: dict, bom: ManufacturingBOM | None) -> list[dict]:
        outputs = [dict(row) for row in (payload.get("outputs") or [])]
        if outputs:
            return outputs
        if bom is None:
            raise ValidationError({"outputs": "At least one output line is required."})
        planned_qty = _q4(payload.get("planned_output_qty") or bom.output_qty)
        return [
            {
                "finished_product": bom.finished_product_id,
                "output_type": ManufacturingWorkOrderOutput.OutputType.MAIN,
                "planned_qty": planned_qty,
                "actual_qty": planned_qty,
                "estimated_recovery_unit_value": Decimal("0.0000"),
                "batch_number": "",
                "manufacture_date": None,
                "expiry_date": None,
                "note": "",
            }
        ]

    @staticmethod
    def _default_output_batch_fields(*, payload: dict, settings_obj: ManufacturingSettings, product: Product, raw_line: dict) -> dict:
        batch_number = _clean_batch_number(raw_line.get("batch_number"))
        manufacture_date = raw_line.get("manufacture_date")
        expiry_date = raw_line.get("expiry_date")
        if not getattr(product, "is_batch_managed", False):
            return {
                "batch_number": batch_number,
                "manufacture_date": manufacture_date,
                "expiry_date": expiry_date,
            }
        if not batch_number and _policy_value(settings_obj, "default_output_batch_mode", "manual") == "copy_from_reference":
            batch_number = _reference_batch_number(
                reference_no=payload.get("reference_no") or "",
                fallback=payload.get("work_order_no") or "",
            )
        if not manufacture_date:
            manufacture_date = payload.get("production_date")
        return {
            "batch_number": batch_number,
            "manufacture_date": manufacture_date,
            "expiry_date": expiry_date,
        }

    @staticmethod
    def _normalize_materials(*, payload: dict, bom: ManufacturingBOM | None, output_qty: Decimal) -> list[dict]:
        materials = [dict(row) for row in (payload.get("materials") or [])]
        if materials:
            return materials
        if bom is None:
            raise ValidationError({"materials": "At least one material line is required when BOM is not selected."})
        return _explode_bom_materials(bom=bom, target_output_qty=output_qty)

    @staticmethod
    def _build_operations(
        *,
        work_order: ManufacturingWorkOrder,
        bom: ManufacturingBOM | None,
        default_qty: Decimal,
    ) -> list[ManufacturingWorkOrderOperation]:
        if bom is None or bom.route_id is None:
            return []
        steps = list(
            ManufacturingRouteStep.objects.filter(route_id=bom.route_id).order_by("sequence_no", "id")
        )
        default_qty = _q4(default_qty)
        operations: list[ManufacturingWorkOrderOperation] = []
        for index, step in enumerate(steps, start=1):
            operations.append(
                ManufacturingWorkOrderOperation(
                    work_order=work_order,
                    route_step=step,
                    sequence_no=step.sequence_no or index,
                    step_code=step.step_code or "",
                    step_name=step.step_name,
                    description=step.description or "",
                    status=ManufacturingOperationStatus.READY if index == 1 else ManufacturingOperationStatus.PENDING,
                    requires_qc=step.requires_qc,
                    input_qty=default_qty,
                    output_qty=default_qty,
                    scrap_qty=Decimal("0.0000"),
                    remarks="",
                )
            )
        return operations

    @staticmethod
    def _sync_traceability_links(*, work_order: ManufacturingWorkOrder) -> None:
        ManufacturingBatchTraceLink.objects.filter(work_order=work_order).delete()
        materials = list(
            work_order.materials.all().select_related("material_product").order_by("line_no", "id")
        )
        outputs = list(
            work_order.outputs.all().select_related("finished_product").order_by("line_no", "id")
        )
        if not materials or not outputs:
            return
        links: list[ManufacturingBatchTraceLink] = []
        for output_line in outputs:
            for material_line in materials:
                links.append(
                    ManufacturingBatchTraceLink(
                        work_order=work_order,
                        material_line=material_line,
                        output_line=output_line,
                        input_product=material_line.material_product,
                        input_batch_number=material_line.batch_number or "",
                        input_manufacture_date=material_line.manufacture_date,
                        input_expiry_date=material_line.expiry_date,
                        input_qty=_q4(material_line.actual_qty),
                        output_product=output_line.finished_product,
                        output_batch_number=output_line.batch_number or "",
                        output_manufacture_date=output_line.manufacture_date,
                        output_expiry_date=output_line.expiry_date,
                        output_qty=_q4(output_line.actual_qty),
                    )
                )
        if links:
            ManufacturingBatchTraceLink.objects.bulk_create(links)

    @staticmethod
    def _calculate_cost_snapshot(
        *,
        materials: list[ManufacturingWorkOrderMaterial],
        outputs: list[ManufacturingWorkOrderOutput],
        additional_costs: list[ManufacturingWorkOrderAdditionalCost] | None = None,
    ) -> dict[str, Decimal]:
        main_outputs = [line for line in outputs if line.output_type == ManufacturingWorkOrderOutput.OutputType.MAIN]
        secondary_outputs = [line for line in outputs if line.output_type != ManufacturingWorkOrderOutput.OutputType.MAIN]
        additional_cost_rows = additional_costs or []

        standard_material_cost = sum(
            ((_q4(line.required_qty) * _q4(line.unit_cost)) for line in materials),
            Decimal("0.0000"),
        )
        actual_material_cost = sum(
            ((_q4(line.actual_qty) * _q4(line.unit_cost)) for line in materials),
            Decimal("0.0000"),
        )
        total_additional_cost = sum((_q4(line.amount) for line in additional_cost_rows), Decimal("0.0000"))
        standard_recovery_value = sum(
            ((_q4(line.planned_qty) * _q4(line.estimated_recovery_unit_value)) for line in secondary_outputs),
            Decimal("0.0000"),
        )
        actual_recovery_value = sum(
            ((_q4(line.actual_qty) * _q4(line.estimated_recovery_unit_value)) for line in secondary_outputs),
            Decimal("0.0000"),
        )
        standard_output_qty = sum((_q4(line.planned_qty) for line in main_outputs), Decimal("0.0000"))
        actual_output_qty = sum((_q4(line.actual_qty) for line in main_outputs), Decimal("0.0000"))

        standard_net_cost = max(standard_material_cost - standard_recovery_value, Decimal("0.0000"))
        actual_net_cost = max(actual_material_cost + total_additional_cost - actual_recovery_value, Decimal("0.0000"))
        standard_unit_cost = _q4(standard_net_cost / standard_output_qty) if standard_output_qty > Decimal("0.0000") else Decimal("0.0000")
        actual_unit_cost = _q4(actual_net_cost / actual_output_qty) if actual_output_qty > Decimal("0.0000") else Decimal("0.0000")
        material_variance_value = _q4(actual_material_cost - standard_material_cost)
        yield_variance_qty = _q4(actual_output_qty - standard_output_qty)
        yield_variance_percent = _q4((yield_variance_qty / standard_output_qty) * Decimal("100.0000")) if standard_output_qty > Decimal("0.0000") else Decimal("0.0000")

        return {
            "standard_material_cost_snapshot": _q4(standard_material_cost),
            "actual_material_cost_snapshot": _q4(actual_material_cost),
            "total_additional_cost_snapshot": _q4(total_additional_cost),
            "standard_recovery_value_snapshot": _q4(standard_recovery_value),
            "actual_recovery_value_snapshot": _q4(actual_recovery_value),
            "net_production_cost_snapshot": _q4(actual_net_cost),
            "standard_output_qty_snapshot": _q4(standard_output_qty),
            "actual_output_qty_snapshot": _q4(actual_output_qty),
            "standard_unit_cost_snapshot": standard_unit_cost,
            "actual_unit_cost_snapshot": actual_unit_cost,
            "material_variance_value_snapshot": material_variance_value,
            "yield_variance_qty_snapshot": yield_variance_qty,
            "yield_variance_percent_snapshot": yield_variance_percent,
        }

    @staticmethod
    def _persist_cost_snapshot(
        *,
        work_order: ManufacturingWorkOrder,
        materials: list[ManufacturingWorkOrderMaterial],
        outputs: list[ManufacturingWorkOrderOutput],
        additional_costs: list[ManufacturingWorkOrderAdditionalCost] | None = None,
    ) -> None:
        snapshot = ManufacturingWorkOrderService._calculate_cost_snapshot(materials=materials, outputs=outputs, additional_costs=additional_costs)
        for field_name, value in snapshot.items():
            setattr(work_order, field_name, value)
        work_order.save(update_fields=[*snapshot.keys(), "updated_at"])

    @staticmethod
    def _build_work_order_lines(*, work_order: ManufacturingWorkOrder, payload: dict, settings_obj: ManufacturingSettings) -> tuple[list[ManufacturingWorkOrderMaterial], list[ManufacturingWorkOrderOutput], list[ManufacturingWorkOrderOperation]]:
        bom = _load_bom(entity_id=payload["entity"], subentity_id=payload.get("subentity"), bom_id=payload.get("bom"))
        outputs_raw = ManufacturingWorkOrderService._normalize_outputs(payload=payload, bom=bom)
        main_output_raw = next(
            (row for row in outputs_raw if (row.get("output_type") or ManufacturingWorkOrderOutput.OutputType.MAIN) == ManufacturingWorkOrderOutput.OutputType.MAIN),
            outputs_raw[0] if outputs_raw else None,
        )
        main_output_qty = _q4(main_output_raw.get("planned_qty") or main_output_raw.get("actual_qty") or 0) if main_output_raw else Decimal("0.0000")
        if main_output_qty <= Decimal("0.0000"):
            raise ValidationError({"outputs": "Main output quantity must be greater than zero."})
        materials_raw = ManufacturingWorkOrderService._normalize_materials(payload=payload, bom=bom, output_qty=main_output_qty)

        material_objs: list[ManufacturingWorkOrderMaterial] = []
        for idx, raw_line in enumerate(materials_raw, start=1):
            product = _load_product_for_scope(entity_id=payload["entity"], product_id=raw_line["material_product"], field_name="materials", line_no=idx)
            required_qty = _q4(raw_line.get("required_qty") or raw_line.get("actual_qty") or 0)
            actual_qty = _q4(raw_line.get("actual_qty") or required_qty)
            waste_qty = _q4(raw_line.get("waste_qty") or 0)
            if actual_qty <= Decimal("0.0000"):
                raise ValidationError({"materials": [f"Actual quantity must be greater than zero for line {idx}."]})
            if waste_qty > actual_qty:
                raise ValidationError({"materials": [f"Waste quantity cannot exceed actual quantity for line {idx}."]})
            batch_number, manufacture_date, expiry_date = _extract_batch_fields(
                product=product,
                raw_line=raw_line,
                line_kind="material",
                line_no=idx,
                settings_obj=settings_obj,
            )
            unit_cost = _q4_or_none(raw_line.get("unit_cost")) or Decimal("0.0000")
            if unit_cost < Decimal("0.0000"):
                raise ValidationError({"materials": [f"Unit cost cannot be negative for line {idx}."]})
            material_objs.append(
                ManufacturingWorkOrderMaterial(
                    work_order=work_order,
                    line_no=idx,
                    material_product=product,
                    uom=getattr(product, "base_uom", None),
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    required_qty=required_qty,
                    actual_qty=actual_qty,
                    waste_qty=waste_qty,
                    unit_cost=unit_cost,
                    note=raw_line.get("note") or "",
                )
            )

        output_objs: list[ManufacturingWorkOrderOutput] = []
        for idx, raw_line in enumerate(outputs_raw, start=1):
            product = _load_product_for_scope(entity_id=payload["entity"], product_id=raw_line["finished_product"], field_name="outputs", line_no=idx)
            output_type = raw_line.get("output_type") or ManufacturingWorkOrderOutput.OutputType.MAIN
            if bom and output_type == ManufacturingWorkOrderOutput.OutputType.MAIN and product.id != bom.finished_product_id:
                raise ValidationError({"outputs": "Main output product must match the selected BOM finished product."})
            planned_qty = _q4(raw_line.get("planned_qty") or raw_line.get("actual_qty") or main_output_qty)
            actual_qty = _q4(raw_line.get("actual_qty") or planned_qty)
            if actual_qty <= Decimal("0.0000"):
                raise ValidationError({"outputs": [f"Actual quantity must be greater than zero for line {idx}."]})
            output_defaults = ManufacturingWorkOrderService._default_output_batch_fields(
                payload=payload,
                settings_obj=settings_obj,
                product=product,
                raw_line=raw_line,
            )
            batch_number, manufacture_date, expiry_date = _extract_batch_fields(
                product=product,
                raw_line=output_defaults,
                line_kind="output",
                line_no=idx,
                settings_obj=settings_obj,
            )
            output_objs.append(
                ManufacturingWorkOrderOutput(
                    work_order=work_order,
                    line_no=idx,
                    finished_product=product,
                    uom=getattr(product, "base_uom", None),
                    output_type=output_type,
                    batch_number=batch_number,
                    manufacture_date=manufacture_date,
                    expiry_date=expiry_date,
                    planned_qty=planned_qty,
                    actual_qty=actual_qty,
                    estimated_recovery_unit_value=_q4(raw_line.get("estimated_recovery_unit_value") or 0),
                    unit_cost=Decimal("0.0000"),
                    note=raw_line.get("note") or "",
                )
            )
        operation_objs = ManufacturingWorkOrderService._build_operations(
            work_order=work_order,
            bom=bom,
            default_qty=main_output_qty,
        )
        additional_cost_objs: list[ManufacturingWorkOrderAdditionalCost] = []
        for idx, raw_line in enumerate(payload.get("additional_costs") or [], start=1):
            amount = _q4(raw_line.get("amount") or 0)
            if amount <= Decimal("0.0000"):
                raise ValidationError({"additional_costs": [f"Amount must be greater than zero for line {idx}."]})
            additional_cost_objs.append(
                ManufacturingWorkOrderAdditionalCost(
                    work_order=work_order,
                    line_no=idx,
                    cost_type=raw_line.get("cost_type") or ManufacturingWorkOrderAdditionalCost.CostType.OTHER,
                    amount=amount,
                    note=raw_line.get("note") or "",
                )
            )
        return material_objs, output_objs, operation_objs, additional_cost_objs

    @staticmethod
    def _replace_lines(
        *,
        work_order: ManufacturingWorkOrder,
        materials: list[ManufacturingWorkOrderMaterial],
        outputs: list[ManufacturingWorkOrderOutput],
        operations: list[ManufacturingWorkOrderOperation],
        additional_costs: list[ManufacturingWorkOrderAdditionalCost],
    ) -> None:
        work_order.materials.all().delete()
        work_order.outputs.all().delete()
        work_order.operations.all().delete()
        work_order.additional_costs.all().delete()
        work_order.trace_links.all().delete()
        if materials:
            ManufacturingWorkOrderMaterial.objects.bulk_create(materials)
        if outputs:
            ManufacturingWorkOrderOutput.objects.bulk_create(outputs)
        if operations:
            ManufacturingWorkOrderOperation.objects.bulk_create(operations)
        if additional_costs:
            ManufacturingWorkOrderAdditionalCost.objects.bulk_create(additional_costs)
        ManufacturingWorkOrderService._sync_traceability_links(work_order=work_order)

    @staticmethod
    def _get_work_order_for_update(*, work_order_id: int) -> ManufacturingWorkOrder:
        locked = ManufacturingWorkOrder.objects.select_for_update().get(id=work_order_id)
        return (
            ManufacturingWorkOrder.objects
            .select_related("bom", "bom__route", "source_location", "destination_location")
            .prefetch_related(
                "materials__material_product",
                "outputs__finished_product",
                "additional_costs",
                "operations__route_step",
                "trace_links__input_product",
                "trace_links__output_product",
            )
            .get(id=locked.id)
        )

    @staticmethod
    def _advance_next_operation(*, work_order: ManufacturingWorkOrder) -> None:
        next_operation = work_order.operations.filter(status=ManufacturingOperationStatus.PENDING).order_by("sequence_no", "id").first()
        if next_operation:
            next_operation.status = ManufacturingOperationStatus.READY
            next_operation.save(update_fields=["status"])

    @staticmethod
    def _post_work_order(*, work_order: ManufacturingWorkOrder, im_inputs: list[IMInput], user_id: int | None, narration_prefix: str = "") -> Entry:
        posting_service = PostingService(
            entity_id=work_order.entity_id,
            entityfin_id=work_order.entityfin_id,
            subentity_id=work_order.subentity_id,
            user_id=user_id,
        )
        narration = " ".join(part for part in [narration_prefix.strip(), work_order.narration.strip()] if part).strip()
        return posting_service.post(
            txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            txn_id=work_order.id,
            voucher_no=work_order.work_order_no,
            voucher_date=work_order.production_date,
            posting_date=work_order.production_date,
            narration=narration,
            jl_inputs=[],
            im_inputs=im_inputs,
            mark_posted=True,
        )

    @staticmethod
    @transaction.atomic
    def create_work_order(*, payload: dict, user_id: int | None) -> ManufacturingWorkOrderResult:
        settings_obj = _get_settings(entity_id=payload["entity"], subentity_id=payload.get("subentity"))
        source_location_id, destination_location_id = ManufacturingWorkOrderService._resolve_locations(payload=payload)
        work_order = ManufacturingWorkOrder.objects.create(
            entity_id=payload["entity"],
            entityfin_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
            work_order_no=_allocate_work_order_no(
                settings_obj=settings_obj,
                entity_id=payload["entity"],
                entityfinid_id=payload.get("entityfinid"),
                subentity_id=payload.get("subentity"),
                on_date=payload["production_date"],
            ),
            production_date=payload["production_date"],
            bom_id=payload.get("bom"),
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            reference_no=payload.get("reference_no") or "",
            narration=payload.get("narration") or "",
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        material_objs, output_objs, operation_objs, additional_cost_objs = ManufacturingWorkOrderService._build_work_order_lines(
            work_order=work_order,
            payload=payload,
            settings_obj=settings_obj,
        )
        ManufacturingWorkOrderService._replace_lines(work_order=work_order, materials=material_objs, outputs=output_objs, operations=operation_objs, additional_costs=additional_cost_objs)
        ManufacturingWorkOrderService._persist_cost_snapshot(work_order=work_order, materials=material_objs, outputs=output_objs, additional_costs=additional_cost_objs)

        if settings_obj.default_workflow_action == ManufacturingSettings.DefaultWorkflowAction.POST:
            return ManufacturingWorkOrderService.post_work_order(work_order_id=work_order.id, user_id=user_id)

        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def update_work_order(*, work_order_id: int, payload: dict, user_id: int | None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status != ManufacturingWorkOrderStatus.DRAFT:
            raise ValidationError("Only draft work orders can be edited.")
        settings_obj = _get_settings(entity_id=work_order.entity_id, subentity_id=work_order.subentity_id)
        source_location_id, destination_location_id = ManufacturingWorkOrderService._resolve_locations(payload=payload)
        work_order.entityfin_id = payload.get("entityfinid")
        work_order.subentity_id = payload.get("subentity")
        work_order.production_date = payload["production_date"]
        work_order.bom_id = payload.get("bom")
        work_order.source_location_id = source_location_id
        work_order.destination_location_id = destination_location_id
        work_order.reference_no = payload.get("reference_no") or ""
        work_order.narration = payload.get("narration") or ""
        work_order.updated_by_id = user_id
        work_order.save(
            update_fields=[
                "entityfin",
                "subentity",
                "production_date",
                "bom",
                "source_location",
                "destination_location",
                "reference_no",
                "narration",
                "updated_by",
                "updated_at",
            ]
        )
        material_objs, output_objs, operation_objs, additional_cost_objs = ManufacturingWorkOrderService._build_work_order_lines(
            work_order=work_order,
            payload=payload,
            settings_obj=settings_obj,
        )
        ManufacturingWorkOrderService._replace_lines(work_order=work_order, materials=material_objs, outputs=output_objs, operations=operation_objs, additional_costs=additional_cost_objs)
        ManufacturingWorkOrderService._persist_cost_snapshot(work_order=work_order, materials=material_objs, outputs=output_objs, additional_costs=additional_cost_objs)
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def post_work_order(*, work_order_id: int, user_id: int | None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status == ManufacturingWorkOrderStatus.CANCELLED:
            raise ValidationError("Cancelled work order cannot be posted.")
        if work_order.status == ManufacturingWorkOrderStatus.POSTED:
            return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)

        settings_obj = _get_settings(entity_id=work_order.entity_id, subentity_id=work_order.subentity_id)
        reserved_stock: dict[tuple[int, int, str], Decimal] = {}
        im_inputs: list[IMInput] = []
        total_issue_value = Decimal("0.00")

        materials = list(work_order.materials.all().select_related("material_product"))
        outputs = list(work_order.outputs.all().select_related("finished_product"))
        additional_costs = list(work_order.additional_costs.all())
        open_operations = work_order.operations.exclude(status__in=[ManufacturingOperationStatus.COMPLETED, ManufacturingOperationStatus.SKIPPED])
        if not materials:
            raise ValidationError({"materials": "At least one material line is required."})
        if not outputs:
            raise ValidationError({"outputs": "At least one output line is required."})
        main_outputs = [line for line in outputs if line.output_type == ManufacturingWorkOrderOutput.OutputType.MAIN]
        if len(main_outputs) != 1:
            raise ValidationError({"outputs": "Exactly one main output line is required."})
        if open_operations.exists():
            raise ValidationError({"operations": "Complete all manufacturing operations before posting the work order."})

        for line in materials:
            qty = _q4(line.actual_qty)
            if qty <= Decimal("0.0000"):
                raise ValidationError({"materials": [f"Material line {line.line_no} must have actual quantity greater than zero."]})
            if bool(_policy_value(settings_obj, "block_negative_stock", True)):
                _assert_stock_available(
                    entity_id=work_order.entity_id,
                    product=line.material_product,
                    location_id=work_order.source_location_id,
                    required_qty=qty,
                    batch_number=line.batch_number or "",
                    reserved_by_key=reserved_stock,
                    line_no=line.line_no,
                )
            unit_cost = _q4(line.unit_cost) if _q4(line.unit_cost) > Decimal("0.0000") else _derive_issue_unit_cost(
                entity_id=work_order.entity_id,
                product=line.material_product,
                location_id=work_order.source_location_id,
                batch_number=line.batch_number or "",
            )
            line.unit_cost = unit_cost
            total_issue_value += qty * unit_cost
            im_inputs.append(
                IMInput(
                    product_id=line.material_product_id,
                    qty=qty,
                    base_qty=qty,
                    uom_id=getattr(line.material_product, "base_uom_id", None),
                    base_uom_id=getattr(line.material_product, "base_uom_id", None),
                    uom_factor=Decimal("1"),
                    unit_cost=unit_cost,
                    batch_number=line.batch_number or "",
                    manufacture_date=line.manufacture_date,
                    expiry_date=line.expiry_date,
                    move_type=InventoryMove.MoveType.OUT,
                    cost_source=InventoryMove.CostSource.AVG,
                    detail_id=line.line_no,
                    location_id=work_order.source_location_id,
                    source_location_id=work_order.source_location_id,
                    destination_location_id=work_order.destination_location_id,
                    movement_nature=InventoryMove.MovementNature.PRODUCTION,
                    movement_group=uuid4(),
                    movement_reason="manufacturing issue",
                )
            )

        secondary_outputs = [line for line in outputs if line.output_type != ManufacturingWorkOrderOutput.OutputType.MAIN]
        byproduct_credit_total = sum(
            ((_q4(line.actual_qty) * _q4(line.estimated_recovery_unit_value)) for line in secondary_outputs),
            Decimal("0.0000"),
        )
        total_additional_cost = sum((_q4(line.amount) for line in additional_costs), Decimal("0.0000"))
        if byproduct_credit_total > (total_issue_value + total_additional_cost):
            raise ValidationError({"outputs": "Total byproduct recovery value cannot exceed consumed material plus additional production cost."})

        total_main_output_qty = sum((Decimal(line.actual_qty or 0) for line in main_outputs), Decimal("0"))
        if total_main_output_qty <= Decimal("0.0000"):
            raise ValidationError({"outputs": "Main output quantity must be greater than zero."})

        main_output_cost_pool = total_issue_value + total_additional_cost - byproduct_credit_total
        main_output_unit_cost = _q4(main_output_cost_pool / total_main_output_qty) if main_output_cost_pool > Decimal("0.00") else Decimal("0.0000")

        for line in outputs:
            if line.output_type == ManufacturingWorkOrderOutput.OutputType.MAIN:
                line.unit_cost = main_output_unit_cost
            else:
                line.unit_cost = _q4(line.estimated_recovery_unit_value)
            qty = _q4(line.actual_qty)
            im_inputs.append(
                IMInput(
                    product_id=line.finished_product_id,
                    qty=qty,
                    base_qty=qty,
                    uom_id=getattr(line.finished_product, "base_uom_id", None),
                    base_uom_id=getattr(line.finished_product, "base_uom_id", None),
                    uom_factor=Decimal("1"),
                    unit_cost=line.unit_cost,
                    batch_number=line.batch_number or "",
                    manufacture_date=line.manufacture_date,
                    expiry_date=line.expiry_date,
                    move_type=InventoryMove.MoveType.IN_,
                    cost_source=InventoryMove.CostSource.AVG,
                    detail_id=1000 + line.line_no,
                    location_id=work_order.destination_location_id,
                    source_location_id=work_order.source_location_id,
                    destination_location_id=work_order.destination_location_id,
                    movement_nature=InventoryMove.MovementNature.PRODUCTION,
                    movement_group=uuid4(),
                    movement_reason="manufacturing receipt" if line.output_type == ManufacturingWorkOrderOutput.OutputType.MAIN else f"{line.output_type.lower()} receipt",
                )
            )

        ManufacturingWorkOrderMaterial.objects.bulk_update(materials, ["unit_cost"])
        ManufacturingWorkOrderOutput.objects.bulk_update(outputs, ["unit_cost"])
        ManufacturingWorkOrderService._persist_cost_snapshot(work_order=work_order, materials=materials, outputs=outputs, additional_costs=additional_costs)
        entry = ManufacturingWorkOrderService._post_work_order(work_order=work_order, im_inputs=im_inputs, user_id=user_id)
        work_order.status = ManufacturingWorkOrderStatus.POSTED
        work_order.posting_entry_id = entry.id
        work_order.updated_by_id = user_id
        work_order.save(update_fields=["status", "posting_entry_id", "updated_by", "updated_at"])
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=entry.id)

    @staticmethod
    @transaction.atomic
    def unpost_work_order(*, work_order_id: int, user_id: int | None, reason: str | None = None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status != ManufacturingWorkOrderStatus.POSTED:
            raise ValidationError("Only posted work orders can be unposted.")

        entry = ManufacturingWorkOrderService._post_work_order(
            work_order=work_order,
            im_inputs=[],
            user_id=user_id,
            narration_prefix=f"Reversal for {work_order.work_order_no}: {(reason or '').strip()}".strip(),
        )
        Entry.objects.filter(
            entity_id=work_order.entity_id,
            entityfin_id=work_order.entityfin_id,
            subentity_id=work_order.subentity_id,
            txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            txn_id=work_order.id,
        ).update(
            status=EntryStatus.REVERSED,
            narration=f"Reversed: {(reason or '').strip()}".strip(),
        )
        work_order.status = ManufacturingWorkOrderStatus.DRAFT
        work_order.posting_entry_id = entry.id
        work_order.updated_by_id = user_id
        work_order.save(update_fields=["status", "posting_entry_id", "updated_by", "updated_at"])
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=entry.id)

    @staticmethod
    @transaction.atomic
    def cancel_work_order(*, work_order_id: int, user_id: int | None, reason: str | None = None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status == ManufacturingWorkOrderStatus.POSTED:
            raise ValidationError("Posted work order must be unposted before cancellation.")
        if work_order.status == ManufacturingWorkOrderStatus.CANCELLED:
            return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)
        work_order.status = ManufacturingWorkOrderStatus.CANCELLED
        suffix = f" | Cancelled: {reason.strip()}" if reason and reason.strip() else ""
        work_order.narration = f"{work_order.narration or ''}{suffix}".strip(" |")
        work_order.updated_by_id = user_id
        work_order.save(update_fields=["status", "narration", "updated_by", "updated_at"])
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def start_operation(*, work_order_id: int, operation_id: int, user_id: int | None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status != ManufacturingWorkOrderStatus.DRAFT:
            raise ValidationError("Operations can only be progressed on draft work orders.")
        operation = work_order.operations.filter(id=operation_id).first()
        if operation is None:
            raise ValidationError({"operation": "Operation not found for this work order."})
        if operation.status not in [ManufacturingOperationStatus.READY, ManufacturingOperationStatus.IN_PROGRESS]:
            raise ValidationError({"operation": f"Operation cannot be started from status {operation.status}."})
        if operation.status == ManufacturingOperationStatus.READY:
            operation.status = ManufacturingOperationStatus.IN_PROGRESS
            operation.started_at = timezone.now()
            operation.save(update_fields=["status", "started_at"])
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def complete_operation(*, work_order_id: int, operation_id: int, payload: dict, user_id: int | None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status != ManufacturingWorkOrderStatus.DRAFT:
            raise ValidationError("Operations can only be progressed on draft work orders.")
        operation = work_order.operations.filter(id=operation_id).first()
        if operation is None:
            raise ValidationError({"operation": "Operation not found for this work order."})
        if operation.status not in [ManufacturingOperationStatus.READY, ManufacturingOperationStatus.IN_PROGRESS]:
            raise ValidationError({"operation": f"Operation cannot be completed from status {operation.status}."})
        operation.input_qty = _q4(payload.get("input_qty") if payload.get("input_qty") is not None else operation.input_qty)
        operation.output_qty = _q4(payload.get("output_qty") if payload.get("output_qty") is not None else operation.output_qty)
        operation.scrap_qty = _q4(payload.get("scrap_qty") if payload.get("scrap_qty") is not None else operation.scrap_qty)
        if operation.scrap_qty > operation.input_qty and operation.input_qty > Decimal("0.0000"):
            raise ValidationError({"scrap_qty": "Scrap quantity cannot exceed input quantity."})
        operation.remarks = (payload.get("remarks") or operation.remarks or "").strip()
        if operation.started_at is None:
            operation.started_at = timezone.now()
        operation.completed_at = timezone.now()
        operation.status = ManufacturingOperationStatus.COMPLETED
        operation.save(update_fields=["input_qty", "output_qty", "scrap_qty", "remarks", "started_at", "completed_at", "status"])
        ManufacturingWorkOrderService._advance_next_operation(work_order=work_order)
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)

    @staticmethod
    @transaction.atomic
    def skip_operation(*, work_order_id: int, operation_id: int, payload: dict, user_id: int | None) -> ManufacturingWorkOrderResult:
        work_order = ManufacturingWorkOrderService._get_work_order_for_update(work_order_id=work_order_id)
        if work_order.status != ManufacturingWorkOrderStatus.DRAFT:
            raise ValidationError("Operations can only be progressed on draft work orders.")
        operation = work_order.operations.filter(id=operation_id).first()
        if operation is None:
            raise ValidationError({"operation": "Operation not found for this work order."})
        if operation.status not in [ManufacturingOperationStatus.READY, ManufacturingOperationStatus.IN_PROGRESS]:
            raise ValidationError({"operation": f"Operation cannot be skipped from status {operation.status}."})
        operation.status = ManufacturingOperationStatus.SKIPPED
        operation.remarks = (payload.get("remarks") or operation.remarks or "").strip()
        if operation.started_at is None:
            operation.started_at = timezone.now()
        operation.completed_at = timezone.now()
        operation.save(update_fields=["status", "remarks", "started_at", "completed_at"])
        ManufacturingWorkOrderService._advance_next_operation(work_order=work_order)
        work_order.refresh_from_db()
        return ManufacturingWorkOrderResult(work_order=work_order, entry_id=work_order.posting_entry_id)
