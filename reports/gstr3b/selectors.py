from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError

from entity.models import EntityFinancialYear
from reports.selectors.financial import ensure_date


@dataclass(frozen=True)
class Gstr3bScope:
    entity_id: int
    entityfinid_id: int | None
    subentity_id: int | None
    month: int | None
    year: int | None
    from_date: date | None
    to_date: date | None


def parse_scope_params(params) -> Gstr3bScope:
    entity_id = _parse_int(params.get("entity"), "entity")
    entityfinid_id = _parse_int(params.get("entityfinid"), "entityfinid", required=False)
    subentity_id = _parse_int(params.get("subentity"), "subentity", required=False)
    month = _parse_int(params.get("month"), "month", required=False)
    year = _parse_int(params.get("year"), "year", required=False)

    from_date = ensure_date(params.get("from_date"))
    to_date = ensure_date(params.get("to_date"))

    if (month or year) and not (month and year):
        raise ValidationError({"month": ["Both month and year are required when filtering by month."]})

    if month and year and not from_date and not to_date:
        from_date = date(year, month, 1)
        to_date = date(year, month, monthrange(year, month)[1])

    if not from_date and not to_date:
        raise ValidationError({"from_date": ["from_date/to_date or month/year is required."]})

    if from_date and to_date and from_date > to_date:
        raise ValidationError({"from_date": ["from_date cannot be after to_date."]})

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

    return Gstr3bScope(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        month=month,
        year=year,
        from_date=from_date,
        to_date=to_date,
    )


def scope_filters(scope: Gstr3bScope) -> dict:
    return {
        "entity": scope.entity_id,
        "entityfinid": scope.entityfinid_id,
        "subentity": scope.subentity_id,
        "month": scope.month,
        "year": scope.year,
        "from_date": scope.from_date,
        "to_date": scope.to_date,
    }


def _parse_int(value, field, *, required=True):
    if value in (None, "", 0, "0"):
        if required:
            raise ValidationError({field: [f"{field} is required."]})
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: [f"{field} must be an integer."]}) from exc

