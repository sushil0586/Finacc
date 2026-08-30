from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db.models import Q

from manufacturing.models import (
    ManufacturingSettings,
    ManufacturingWorkOrder,
    ManufacturingWorkOrderAdditionalCost,
    ManufacturingWorkOrderOutput,
    ManufacturingWorkOrderStatus,
)
from manufacturing.services import ManufacturingWorkOrderService
from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntityStaticAccountMap, Entry, EntryStatus, InventoryMove, JournalLine, TxnType


ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")


@dataclass(frozen=True)
class ManufacturingReportCorrectnessIssue:
    work_order_id: int
    work_order_no: str
    area: str
    field: str
    expected: str
    actual: str
    message: str


def _q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _money(value) -> str:
    return str(_q2(value))


def _qty(value) -> str:
    return str(_q4(value))


def _issue(
    *,
    work_order: ManufacturingWorkOrder,
    area: str,
    field: str,
    expected,
    actual,
    message: str,
) -> ManufacturingReportCorrectnessIssue:
    return ManufacturingReportCorrectnessIssue(
        work_order_id=work_order.id,
        work_order_no=work_order.work_order_no or f"#{work_order.id}",
        area=area,
        field=field,
        expected=str(expected),
        actual=str(actual),
        message=message,
    )


def _compare_money(
    issues: list[ManufacturingReportCorrectnessIssue],
    *,
    work_order: ManufacturingWorkOrder,
    area: str,
    field: str,
    expected,
    actual,
) -> None:
    if _q2(expected) != _q2(actual):
        issues.append(
            _issue(
                work_order=work_order,
                area=area,
                field=field,
                expected=_money(expected),
                actual=_money(actual),
                message=f"{area}.{field} does not reconcile.",
            )
        )


def _compare_qty(
    issues: list[ManufacturingReportCorrectnessIssue],
    *,
    work_order: ManufacturingWorkOrder,
    area: str,
    field: str,
    expected,
    actual,
) -> None:
    if _q4(expected) != _q4(actual):
        issues.append(
            _issue(
                work_order=work_order,
                area=area,
                field=field,
                expected=_qty(expected),
                actual=_qty(actual),
                message=f"{area}.{field} does not reconcile.",
            )
        )


def _mapped_account_ids_by_code(entity_id: int) -> dict[str, set[int]]:
    rows = (
        EntityStaticAccountMap.objects
        .filter(entity_id=entity_id, is_active=True, account_id__isnull=False)
        .select_related("static_account")
        .values_list("static_account__code", "account_id")
    )
    mapped: dict[str, set[int]] = {}
    for code, account_id in rows:
        mapped.setdefault(code, set()).add(account_id)
    return mapped


def _journal_total(lines: Iterable[JournalLine], account_ids: set[int], *, drcr: bool) -> Decimal:
    return sum(
        (_q2(line.amount) for line in lines if line.drcr is drcr and line.account_id in account_ids),
        ZERO2,
    )


def _has_variance_journal_lines(lines: Iterable[JournalLine], account_ids_by_code: dict[str, set[int]]) -> bool:
    variance_account_ids = (
        account_ids_by_code.get(StaticAccountCodes.MANUFACTURING_MATERIAL_VARIANCE, set())
        | account_ids_by_code.get(StaticAccountCodes.MANUFACTURING_YIELD_VARIANCE, set())
    )
    return any(line.account_id in variance_account_ids and _q2(line.amount) != ZERO2 for line in lines)


def _expected_journal_totals(
    *,
    work_order: ManufacturingWorkOrder,
    settings_obj: ManufacturingSettings,
    additional_costs: list[ManufacturingWorkOrderAdditionalCost],
    output_valuation_basis: str | None = None,
) -> dict[tuple[str, bool], Decimal]:
    total_issue_value = _q2(work_order.actual_material_cost_snapshot)
    capitalized_costs, expensed_costs = ManufacturingWorkOrderService._split_additional_costs(
        settings_obj=settings_obj,
        additional_costs=additional_costs,
    )
    total_capitalized_additional_cost = _q2(sum((_q4(line.amount) for line in capitalized_costs), ZERO4))
    total_expensed_additional_cost = _q2(sum((_q4(line.amount) for line in expensed_costs), ZERO4))
    total_wip_value = _q2(total_issue_value + total_capitalized_additional_cost)
    output_valuation_basis = output_valuation_basis or ManufacturingWorkOrderService._output_valuation_basis(settings_obj)
    total_fg_capitalized = total_wip_value
    material_variance_amount = ZERO2
    yield_variance_amount = ZERO2

    if output_valuation_basis == ManufacturingWorkOrderService.OUTPUT_VALUATION_STANDARD_COST:
        total_fg_capitalized = _q2(
            sum(
                (_q4(line.actual_qty) * _q4(line.unit_cost) for line in work_order.outputs.all()),
                ZERO4,
            )
        )
        total_variance_amount = _q2(total_wip_value - total_fg_capitalized)
        material_variance_amount = _q2(
            _q4(work_order.actual_material_cost_snapshot) - _q4(work_order.standard_material_cost_snapshot)
        )
        yield_variance_amount = _q2(total_variance_amount - material_variance_amount)

    expected: dict[tuple[str, bool], Decimal] = {
        (StaticAccountCodes.MANUFACTURING_WIP, True): total_wip_value,
        (StaticAccountCodes.MANUFACTURING_WIP, False): total_wip_value,
        (StaticAccountCodes.MANUFACTURING_CONSUMPTION, False): total_issue_value,
        (StaticAccountCodes.MANUFACTURING_OVERHEAD_ABSORPTION, False): _q2(
            total_capitalized_additional_cost + total_expensed_additional_cost
        ),
        (StaticAccountCodes.MANUFACTURING_FINISHED_GOODS, True): total_fg_capitalized,
        (StaticAccountCodes.MANUFACTURING_ADDITIONAL_COST_EXPENSE, True): total_expensed_additional_cost,
        (StaticAccountCodes.MANUFACTURING_MATERIAL_VARIANCE, True): max(material_variance_amount, ZERO2),
        (StaticAccountCodes.MANUFACTURING_MATERIAL_VARIANCE, False): max(-material_variance_amount, ZERO2),
        (StaticAccountCodes.MANUFACTURING_YIELD_VARIANCE, True): max(yield_variance_amount, ZERO2),
        (StaticAccountCodes.MANUFACTURING_YIELD_VARIANCE, False): max(-yield_variance_amount, ZERO2),
    }
    return expected


def audit_manufacturing_report_correctness(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    from_date=None,
    to_date=None,
    limit: int | None = None,
) -> list[ManufacturingReportCorrectnessIssue]:
    work_orders = ManufacturingWorkOrder.objects.filter(
        entity_id=entity_id,
        status=ManufacturingWorkOrderStatus.POSTED,
    )
    if entityfin_id is not None:
        work_orders = work_orders.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        work_orders = work_orders.filter(subentity_id=subentity_id)
    if from_date:
        work_orders = work_orders.filter(production_date__gte=from_date)
    if to_date:
        work_orders = work_orders.filter(production_date__lte=to_date)

    work_orders = work_orders.prefetch_related("materials", "outputs", "additional_costs").order_by("-production_date", "-id")
    if limit:
        work_orders = work_orders[:limit]

    account_ids_by_code = _mapped_account_ids_by_code(entity_id)
    issues: list[ManufacturingReportCorrectnessIssue] = []

    for work_order in work_orders:
        materials = list(work_order.materials.all())
        outputs = list(work_order.outputs.all())
        additional_costs = list(work_order.additional_costs.all())
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity_id=entity_id, subentity_id=work_order.subentity_id)
        snapshot = ManufacturingWorkOrderService._calculate_cost_snapshot(
            materials=materials,
            outputs=outputs,
            settings_obj=settings_obj,
            additional_costs=additional_costs,
        )

        for field_name, expected_value in snapshot.items():
            comparator = _compare_qty if field_name.endswith("_qty_snapshot") or field_name.endswith("_percent_snapshot") or field_name.endswith("_unit_cost_snapshot") else _compare_money
            comparator(
                issues,
                work_order=work_order,
                area="snapshot",
                field=field_name,
                expected=expected_value,
                actual=getattr(work_order, field_name),
            )

        entry = Entry.objects.filter(
            id=work_order.posting_entry_id,
            entity_id=entity_id,
            txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            txn_id=work_order.id,
            status=EntryStatus.POSTED,
        ).first()
        if not entry:
            issues.append(
                _issue(
                    work_order=work_order,
                    area="posting",
                    field="entry",
                    expected="posted entry",
                    actual=str(work_order.posting_entry_id),
                    message="Posted work order does not have a matching posted journal entry.",
                )
            )
            continue

        journal_lines = list(
            JournalLine.objects.filter(
                entry_id=entry.id,
                entity_id=entity_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
                txn_id=work_order.id,
            )
        )
        debit_total = sum((_q2(line.amount) for line in journal_lines if line.drcr), ZERO2)
        credit_total = sum((_q2(line.amount) for line in journal_lines if not line.drcr), ZERO2)
        _compare_money(issues, work_order=work_order, area="journal", field="debits_equal_credits", expected=debit_total, actual=credit_total)

        posted_output_valuation_basis = (
            ManufacturingWorkOrderService.OUTPUT_VALUATION_STANDARD_COST
            if _has_variance_journal_lines(journal_lines, account_ids_by_code)
            else ManufacturingWorkOrderService._output_valuation_basis(settings_obj)
        )

        for (code, drcr), expected_amount in _expected_journal_totals(
            work_order=work_order,
            settings_obj=settings_obj,
            additional_costs=additional_costs,
            output_valuation_basis=posted_output_valuation_basis,
        ).items():
            if expected_amount == ZERO2:
                continue
            account_ids = account_ids_by_code.get(code, set())
            actual_amount = _journal_total(journal_lines, account_ids, drcr=drcr)
            _compare_money(
                issues,
                work_order=work_order,
                area="journal",
                field=f"{code}.{'debit' if drcr else 'credit'}",
                expected=expected_amount,
                actual=actual_amount,
            )

        moves = list(
            InventoryMove.objects.filter(
                entry_id=entry.id,
                entity_id=entity_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
                txn_id=work_order.id,
                movement_nature=InventoryMove.MovementNature.PRODUCTION,
            )
        )
        expected_move_count = len(materials) + len(outputs)
        if len(moves) != expected_move_count:
            issues.append(
                _issue(
                    work_order=work_order,
                    area="inventory",
                    field="move_count",
                    expected=expected_move_count,
                    actual=len(moves),
                    message="Production inventory move count does not match material plus output lines.",
                )
            )

        material_moves = [move for move in moves if move.move_type == InventoryMove.MoveType.OUT]
        output_moves = [move for move in moves if move.move_type == InventoryMove.MoveType.IN_]
        _compare_qty(
            issues,
            work_order=work_order,
            area="inventory",
            field="material_out_qty",
            expected=sum((_q4(line.actual_qty) for line in materials), ZERO4),
            actual=sum((_q4(move.base_qty) for move in material_moves), ZERO4),
        )
        _compare_money(
            issues,
            work_order=work_order,
            area="inventory",
            field="material_out_value",
            expected=sum((_q4(line.actual_qty) * _q4(line.unit_cost) for line in materials), ZERO4),
            actual=sum((_q2(move.ext_cost) for move in material_moves), ZERO2),
        )
        _compare_qty(
            issues,
            work_order=work_order,
            area="inventory",
            field="output_in_qty",
            expected=sum((_q4(line.actual_qty) for line in outputs), ZERO4),
            actual=sum((_q4(move.base_qty) for move in output_moves), ZERO4),
        )
        _compare_money(
            issues,
            work_order=work_order,
            area="inventory",
            field="output_in_value",
            expected=sum((_q4(line.actual_qty) * _q4(line.unit_cost) for line in outputs), ZERO4),
            actual=sum((_q2(move.ext_cost) for move in output_moves), ZERO2),
        )

    return issues
