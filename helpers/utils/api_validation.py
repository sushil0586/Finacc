from __future__ import annotations

from rest_framework.exceptions import ValidationError


def raise_structured_validation_error(payload) -> None:
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"non_field_errors": [str(payload)]})


def require_query_scope(entity, entityfinid):
    errors = {}
    if not entity:
        errors["entity"] = "This query param is required."
    if not entityfinid:
        errors["entityfinid"] = "This query param is required."
    if errors:
        raise ValidationError(errors)


def raise_scope_type_error() -> None:
    raise ValidationError(
        {
            "entity": "Must be an integer.",
            "entityfinid": "Must be an integer.",
            "subentity": "Must be an integer when provided.",
        }
    )
