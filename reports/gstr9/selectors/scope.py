from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError

from entity.models import EntityFinancialYear


@dataclass(frozen=True)
class Gstr9FilterParams:
    entity_id: int
    entityfinid_id: int | None
    subentity_id: int | None


def parse_scope_params(params) -> Gstr9FilterParams:
    entity_id = _parse_int(params.get("entity"), "entity")
    entityfinid_id = _parse_int(params.get("entityfinid"), "entityfinid", required=False)
    subentity_id = _parse_int(params.get("subentity"), "subentity", required=False)

    if entityfinid_id:
        exists = EntityFinancialYear.objects.filter(id=entityfinid_id, entity_id=entity_id).exists()
        if not exists:
            raise ValidationError({"entityfinid": ["Financial year is not valid for this entity."]})

    return Gstr9FilterParams(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
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

