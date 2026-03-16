from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from calendar import monthrange

from django.core.exceptions import ValidationError

from entity.models import EntityFinancialYear
from reports.selectors.financial import ensure_date


@dataclass(frozen=True)
class Gstr1FilterParams:
    entity_id: int
    entityfinid_id: int | None
    subentity_id: int | None
    month: int | None
    year: int | None
    from_date: date | None
    to_date: date | None
    include_cancelled: bool


def parse_scope_params(params) -> Gstr1FilterParams:
    entity_id = _parse_int(params.get("entity"), "entity")
    entityfinid_id = _parse_int(params.get("entityfinid"), "entityfinid", required=False)
    subentity_id = _parse_int(params.get("subentity"), "subentity", required=False)
    month = _parse_int(params.get("month"), "month", required=False)
    year = _parse_int(params.get("year"), "year", required=False)
    include_cancelled = _parse_bool(params.get("include_cancelled"), default=False)

    from_date = ensure_date(params.get("from_date"))
    to_date = ensure_date(params.get("to_date"))

    if (month or year) and not (month and year):
        raise ValidationError({"month": ["Both month and year are required when filtering by month."]})

    if not from_date and not to_date and month and year:
        start = date(int(year), int(month), 1)
        end = date(int(year), int(month), monthrange(int(year), int(month))[1])
        from_date = start
        to_date = end

    if not from_date and not to_date:
        raise ValidationError({"from_date": ["from_date/to_date or month/year is required."]})

    if entityfinid_id:
        fy = EntityFinancialYear.objects.filter(id=entityfinid_id, entity_id=entity_id).first()
        if not fy:
            raise ValidationError({"entityfinid": ["Financial year is not valid for this entity."]})
        fy_start = ensure_date(fy.finstartyear)
        fy_end = ensure_date(fy.finendyear)
        if from_date and (from_date < fy_start or from_date > fy_end):
            raise ValidationError({"from_date": ["from_date is outside the financial year."]})
        if to_date and (to_date < fy_start or to_date > fy_end):
            raise ValidationError({"to_date": ["to_date is outside the financial year."]})

    if from_date and to_date and from_date > to_date:
        raise ValidationError({"from_date": ["from_date cannot be after to_date."]})

    return Gstr1FilterParams(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        month=month,
        year=year,
        from_date=from_date,
        to_date=to_date,
        include_cancelled=include_cancelled,
    )


def _parse_int(value, field, *, required=True):
    if value in (None, "", 0, "0"):
        if required:
            raise ValidationError({field: [f"{field} is required."]})
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: [f"{field} must be an integer."]}) from exc


def _parse_bool(value, *, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
