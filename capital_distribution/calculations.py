from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from .models import CapitalDistributionLine


MONEY = Decimal("0.01")
HUNDRED = Decimal("100")


def decimal_value(value, default="0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def stable_hash(payload: dict | list) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def inclusive_days(period_from: date, period_to: date) -> int:
    return (period_to - period_from).days + 1


def day_denominator(convention: str, period_from: date) -> Decimal:
    convention = (convention or "actual_365").lower()
    if convention == "actual_actual":
        year = period_from.year
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return Decimal("366" if leap else "365")
    if convention == "actual_360":
        return Decimal("360")
    if convention != "actual_365":
        raise ValidationError({"day_count_convention": f"Unsupported day-count convention: {convention}."})
    return Decimal("365")


def proration_fraction(convention: str, period_from: date, period_to: date) -> Decimal:
    convention = (convention or "actual_365").lower()
    if convention != "actual_actual":
        return Decimal(inclusive_days(period_from, period_to)) / day_denominator(convention, period_from)
    fraction = Decimal("0")
    year = period_from.year
    while year <= period_to.year:
        segment_from = max(period_from, date(year, 1, 1))
        segment_to = min(period_to, date(year, 12, 31))
        fraction += Decimal(inclusive_days(segment_from, segment_to)) / day_denominator("actual_actual", segment_from)
        year += 1
    return fraction


@dataclass(frozen=True)
class CalculatedLine:
    stakeholder_id: int
    component_type: str
    basis_amount: Decimal
    rate: Decimal | None
    days: int
    amount: Decimal
    side: str
    explanation: dict


@dataclass(frozen=True)
class SegmentCalculation:
    source_profit: Decimal
    distributable_result: Decimal
    lines: tuple[CalculatedLine, ...]


def validate_stakeholder_calculation_configuration(configuration: dict) -> None:
    configuration = configuration or {}
    allowed = {"seeded_from_ownership", "remainder_priority", "remuneration", "capital_interest", "drawing_interest"}
    unknown = sorted(set(configuration) - allowed)
    if unknown:
        raise ValidationError({"configuration": f"Unsupported stakeholder settings: {', '.join(unknown)}."})

    remuneration = configuration.get("remuneration") or {}
    if remuneration.get("enabled"):
        method = remuneration.get("method", "fixed")
        if method not in {"fixed", "percentage_of_book_profit"}:
            raise ValidationError({"configuration": "Remuneration method must be fixed or percentage_of_book_profit."})
        value_key = "amount" if method == "fixed" else "rate"
        if remuneration.get(value_key) in (None, ""):
            raise ValidationError({"configuration": f"Remuneration {value_key} is required when enabled."})
        value = decimal_value(remuneration[value_key])
        if value < 0 or (value_key == "rate" and value > 100):
            raise ValidationError({"configuration": "Remuneration amount must be non-negative and percentage rate must be between 0 and 100."})
        if remuneration.get("cap") not in (None, "") and decimal_value(remuneration["cap"]) < 0:
            raise ValidationError({"configuration": "Remuneration cap cannot be negative."})

    for key, label in (("capital_interest", "Capital interest"), ("drawing_interest", "Drawing interest")):
        config = configuration.get(key) or {}
        if config.get("enabled"):
            if config.get("rate") in (None, ""):
                raise ValidationError({"configuration": f"{label} rate is required when enabled."})
            rate = decimal_value(config["rate"])
            if rate < 0 or rate > 100:
                raise ValidationError({"configuration": f"{label} rate must be between 0 and 100."})


def _remuneration(*, config: dict, source_profit: Decimal, fraction: Decimal) -> tuple[Decimal, Decimal]:
    if not config.get("enabled"):
        return Decimal("0"), Decimal("0")
    method = config.get("method", "fixed")
    if method == "percentage_of_book_profit":
        basis = max(source_profit, Decimal("0"))
        rate = decimal_value(config.get("rate"))
        amount = basis * rate / HUNDRED
    else:
        basis = decimal_value(config.get("amount"))
        rate = Decimal("0")
        amount = basis
    if method == "fixed" and config.get("prorate", True):
        amount = amount * fraction
    if config.get("cap") not in (None, ""):
        amount = min(amount, decimal_value(config["cap"]))
    return money(basis), money(amount)


def _annual_interest(*, balance: Decimal, config: dict, fraction: Decimal) -> tuple[Decimal, Decimal]:
    if not config.get("enabled"):
        return Decimal("0"), Decimal("0")
    basis = max(balance, Decimal("0"))
    rate = decimal_value(config.get("rate"))
    return money(basis), money(basis * rate / HUNDRED * fraction)


def calculate_segment(
    *,
    source_profit: Decimal,
    book_adjustments: Decimal,
    period_from: date,
    period_to: date,
    stakeholder_rows: list,
    balances: dict[int, dict],
    day_count_convention: str = "actual_365",
) -> SegmentCalculation:
    days = inclusive_days(period_from, period_to)
    denominator = day_denominator(day_count_convention, period_from)
    fraction = proration_fraction(day_count_convention, period_from, period_to)
    lines: list[CalculatedLine] = []
    remuneration_total = Decimal("0")
    capital_interest_total = Decimal("0")
    drawing_interest_total = Decimal("0")

    for row in stakeholder_rows:
        config = row.configuration or {}
        validate_stakeholder_calculation_configuration(config)
        balance = balances.get(row.id, {})
        remuneration_basis, remuneration = _remuneration(
            config=config.get("remuneration") or {},
            source_profit=source_profit,
            fraction=fraction,
        )
        capital_basis, capital_interest = _annual_interest(
            balance=decimal_value(balance.get("capital_balance")),
            config=config.get("capital_interest") or {},
            fraction=fraction,
        )
        drawing_basis, drawing_interest = _annual_interest(
            balance=decimal_value(balance.get("drawing_balance")),
            config=config.get("drawing_interest") or {},
            fraction=fraction,
        )
        for component, basis, rate, amount, side in (
            (CapitalDistributionLine.Component.REMUNERATION, remuneration_basis, (config.get("remuneration") or {}).get("rate"), remuneration, CapitalDistributionLine.Side.CREDIT),
            (CapitalDistributionLine.Component.CAPITAL_INTEREST, capital_basis, (config.get("capital_interest") or {}).get("rate"), capital_interest, CapitalDistributionLine.Side.CREDIT),
            (CapitalDistributionLine.Component.DRAWING_INTEREST, drawing_basis, (config.get("drawing_interest") or {}).get("rate"), drawing_interest, CapitalDistributionLine.Side.DEBIT),
        ):
            if amount:
                lines.append(CalculatedLine(
                    stakeholder_id=row.id,
                    component_type=component,
                    basis_amount=basis,
                    rate=decimal_value(rate) if rate not in (None, "") else None,
                    days=days,
                    amount=amount,
                    side=side,
                    explanation={"formula": component, "day_count": day_count_convention, "denominator": str(denominator), "year_fraction": str(fraction)},
                ))
        remuneration_total += remuneration
        capital_interest_total += capital_interest
        drawing_interest_total += drawing_interest

    distributable = money(source_profit + book_adjustments - remuneration_total - capital_interest_total + drawing_interest_total)
    component = (
        CapitalDistributionLine.Component.RESIDUAL_PROFIT
        if distributable >= 0
        else CapitalDistributionLine.Component.RESIDUAL_LOSS
    )
    side = CapitalDistributionLine.Side.CREDIT if distributable >= 0 else CapitalDistributionLine.Side.DEBIT
    allocation_total = abs(distributable)
    allocated = Decimal("0")
    ordered = sorted(stakeholder_rows, key=lambda row: (bool((row.configuration or {}).get("remainder_priority")), row.sort_order, row.id))
    for index, row in enumerate(ordered):
        percentage = row.profit_percentage if distributable >= 0 else (row.loss_percentage or row.profit_percentage)
        if index == len(ordered) - 1:
            amount = money(allocation_total - allocated)
        else:
            amount = money(allocation_total * decimal_value(percentage) / HUNDRED)
            allocated += amount
        lines.append(CalculatedLine(
            stakeholder_id=row.id,
            component_type=component,
            basis_amount=allocation_total,
            rate=decimal_value(percentage),
            days=days,
            amount=amount,
            side=side,
            explanation={"formula": "remainder_to_final_priority_row" if index == len(ordered) - 1 else "percentage"},
        ))
    return SegmentCalculation(source_profit=money(source_profit), distributable_result=distributable, lines=tuple(lines))
