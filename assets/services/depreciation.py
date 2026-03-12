from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from math import pow

from assets.models import AssetSettings
from assets.models import DepreciationRun, DepreciationRunLine, FixedAsset

Q2 = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass
class DepreciationPreviewLine:
    asset_id: int
    opening_gross_block: Decimal
    depreciation_amount: Decimal
    opening_accumulated_depreciation: Decimal
    closing_accumulated_depreciation: Decimal
    closing_net_book_value: Decimal
    method: str
    days_in_period: int
    annual_rate: Decimal


def monthly_slm_amount(asset: FixedAsset) -> Decimal:
    depreciable_base = max(q2(asset.gross_block) - q2(asset.residual_value), ZERO)
    if not asset.useful_life_months:
        return ZERO
    return q2(depreciable_base / Decimal(asset.useful_life_months))


def _asset_days_in_period(asset: FixedAsset, period_from: date, period_to: date) -> int:
    start = max(period_from, asset.depreciation_start_date or asset.put_to_use_date or asset.capitalization_date or asset.acquisition_date)
    end = period_to
    if asset.disposal_date:
        end = min(end, asset.disposal_date)
    if start > end:
        return 0
    return (end - start).days + 1


def _period_factor(asset: FixedAsset, period_from: date, period_to: date, proration_mode: str) -> Decimal:
    days = _asset_days_in_period(asset, period_from, period_to)
    if days <= 0:
        return ZERO
    if proration_mode == "none":
        return Decimal("1.000000")
    if proration_mode == "monthly":
        return Decimal("1.000000")
    year_days = Decimal("366" if period_from.year % 4 == 0 else "365")
    return (Decimal(days) / year_days).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _wdv_annual_rate(asset: FixedAsset) -> Decimal:
    if q2(asset.depreciation_rate) > ZERO:
        return q2(asset.depreciation_rate)
    gross = q2(asset.gross_block)
    residual = q2(asset.residual_value)
    years = max(Decimal(asset.useful_life_months or 0) / Decimal("12"), Decimal("1"))
    if gross <= ZERO or residual >= gross:
        return ZERO
    residual_ratio = max(float((gross - residual) / gross), 0.0001)
    annual = Decimal(str((1 - pow(1 - residual_ratio, float(1 / years))) * 100))
    return q2(annual)


def _depreciation_amount(asset: FixedAsset, *, period_from: date, period_to: date, proration_mode: str) -> tuple[Decimal, Decimal]:
    if asset.depreciation_method == FixedAsset.DepreciationMethod.SLM:
        base_amount = monthly_slm_amount(asset)
        if proration_mode == "daily":
            days = _asset_days_in_period(asset, period_from, period_to)
            amount = q2((base_amount * Decimal(days)) / Decimal("30")) if days > 0 else ZERO
        else:
            amount = base_amount if _asset_days_in_period(asset, period_from, period_to) > 0 else ZERO
        return amount, ZERO

    annual_rate = _wdv_annual_rate(asset)
    opening_nbv = max(q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount), ZERO)
    factor = _period_factor(asset, period_from, period_to, proration_mode)
    if annual_rate <= ZERO or opening_nbv <= ZERO or factor <= ZERO:
        return ZERO, annual_rate
    amount = q2(opening_nbv * (annual_rate / Decimal("100.00")) * factor)
    cap = max(opening_nbv - q2(asset.residual_value), ZERO)
    return q2(min(amount, cap)), annual_rate


def preview_run(*, assets_qs, period_from: date, period_to: date) -> list[DepreciationPreviewLine]:
    settings_cache: dict[tuple[int, int | None], AssetSettings] = {}
    lines: list[DepreciationPreviewLine] = []
    for asset in assets_qs:
        if asset.status != FixedAsset.AssetStatus.ACTIVE:
            continue
        if asset.depreciation_start_date and asset.depreciation_start_date > period_to:
            continue
        scope_key = (asset.entity_id, asset.subentity_id)
        if scope_key not in settings_cache:
            settings_cache[scope_key] = AssetSettings.objects.filter(entity_id=asset.entity_id, subentity_id=asset.subentity_id).first() or AssetSettings.objects.filter(entity_id=asset.entity_id, subentity_id__isnull=True).first()
        proration_mode = ((settings_cache[scope_key].policy_controls or {}).get("depreciation_proration") if settings_cache[scope_key] else "daily") or "daily"
        amount, annual_rate = _depreciation_amount(asset, period_from=period_from, period_to=period_to, proration_mode=proration_mode)
        if amount <= ZERO:
            continue
        opening_acc = q2(asset.accumulated_depreciation)
        closing_acc = q2(opening_acc + amount)
        closing_nbv = q2(max(q2(asset.gross_block) - closing_acc - q2(asset.impairment_amount), q2(asset.residual_value)))
        days = _asset_days_in_period(asset, period_from, period_to)
        lines.append(
            DepreciationPreviewLine(
                asset_id=asset.id,
                opening_gross_block=q2(asset.gross_block),
                depreciation_amount=amount,
                opening_accumulated_depreciation=opening_acc,
                closing_accumulated_depreciation=closing_acc,
                closing_net_book_value=closing_nbv,
                method=asset.depreciation_method,
                days_in_period=days,
                annual_rate=annual_rate,
            )
        )
    return lines


def attach_preview_lines(run: DepreciationRun, preview_lines: list[DepreciationPreviewLine]) -> None:
    DepreciationRunLine.objects.filter(run=run).delete()
    DepreciationRunLine.objects.bulk_create(
        [
            DepreciationRunLine(
                run=run,
                asset_id=line.asset_id,
                period_from=run.period_from,
                period_to=run.period_to,
                opening_gross_block=line.opening_gross_block,
                opening_accumulated_depreciation=line.opening_accumulated_depreciation,
                depreciation_amount=line.depreciation_amount,
                closing_accumulated_depreciation=line.closing_accumulated_depreciation,
                closing_net_book_value=line.closing_net_book_value,
                calculation_meta={"method": line.method, "days_in_period": line.days_in_period, "annual_rate": f"{line.annual_rate:.2f}"},
            )
            for line in preview_lines
        ]
    )
