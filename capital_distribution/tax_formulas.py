from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError


REMUNERATION_FORMULA = "india_partnership_remuneration_v1"
CAPITAL_INTEREST_FORMULA = "india_partnership_interest_v1"


def partnership_remuneration_ceiling(book_profit: Decimal) -> Decimal:
    """Return the aggregate section 40(b) remuneration ceiling before actual-pay restriction."""
    first_band = Decimal("600000")
    minimum = Decimal("300000")
    if book_profit <= 0:
        return minimum
    first_allowance = max(minimum, min(book_profit, first_band) * Decimal("0.90"))
    balance_allowance = max(Decimal("0"), book_profit - first_band) * Decimal("0.60")
    return first_allowance + balance_allowance


def allocate_pro_rata(total: Decimal, rows: list[dict], quantum: Decimal, rounding_mode) -> dict[int, Decimal]:
    """Allocate a positive amount exactly, assigning residual paise by largest remainder then id."""
    ordered = sorted(rows, key=lambda row: int(row["source_line"]))
    weights = [max(Decimal("0"), Decimal(str(row["book_amount"]))) for row in ordered]
    weight_total = sum(weights, Decimal("0"))
    if total <= 0 or weight_total <= 0:
        return {int(row["source_line"]): Decimal("0") for row in ordered}

    rounded_total = total.quantize(quantum, rounding=rounding_mode)
    units = int((rounded_total / quantum).to_integral_value(rounding=ROUND_DOWN))
    raw_units = [Decimal(units) * weight / weight_total for weight in weights]
    base_units = [int(value.to_integral_value(rounding=ROUND_DOWN)) for value in raw_units]
    residual = units - sum(base_units)
    ranking = sorted(
        range(len(ordered)),
        key=lambda index: (-(raw_units[index] - base_units[index]), int(ordered[index]["source_line"])),
    )
    for index in ranking[:residual]:
        base_units[index] += 1
    return {
        int(row["source_line"]): Decimal(base_units[index]) * quantum
        for index, row in enumerate(ordered)
    }


def evaluate_statutory_formula(*, source: dict, rule: dict, quantum: Decimal, rounding_mode) -> Decimal:
    formula = str(rule.get("formula_code") or "").strip()
    conditions = rule.get("conditions") or {}
    context = source.get("formula_context") or {}

    if formula == REMUNERATION_FORMULA:
        if source.get("component_type") != "remuneration":
            raise ValidationError({"formula_code": "The partnership remuneration formula applies only to remuneration."})
        if conditions.get("deed_authorized") is not True or conditions.get("working_partners_only") is not True:
            raise ValidationError({
                "conditions": "Confirm deed authorization and working-partner eligibility before calculating remuneration."
            })
        book_profit = Decimal(str(context.get("statutory_book_profit")))
        actual = Decimal(str(context.get("aggregate_book_remuneration")))
        allowable_total = min(max(Decimal("0"), actual), partnership_remuneration_ceiling(book_profit))
        allocation = allocate_pro_rata(
            allowable_total,
            context.get("remuneration_lines") or [],
            quantum,
            rounding_mode,
        )
        return allocation.get(int(source["source_line"]), Decimal("0"))

    if formula == CAPITAL_INTEREST_FORMULA:
        if source.get("component_type") != "capital_interest":
            raise ValidationError({"formula_code": "The partnership interest formula applies only to capital interest."})
        if conditions.get("deed_authorized") is not True:
            raise ValidationError({"conditions": "Confirm deed authorization before calculating partner interest."})
        basis = max(Decimal("0"), Decimal(str(source.get("basis_amount") or "0")))
        year_fraction = Decimal(str((source.get("explanation") or {}).get("year_fraction") or "0"))
        return basis * Decimal("0.12") * year_fraction

    raise ValidationError({
        "formula_code": (
            f"Tax formula '{formula}' has no enabled evaluator. Supply a governed evaluated_cap_amount "
            "or use a supported statutory formula."
        )
    })
