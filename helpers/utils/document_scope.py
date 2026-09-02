from __future__ import annotations

from typing import Any

from rest_framework import serializers


DOCUMENT_BRANCH_IMMUTABLE_MESSAGE = "Document branch cannot be changed after save. Create a new document for another branch."


def normalize_optional_pk(value: Any) -> int | None:
    if value in (None, "", "null", "None", 0, "0"):
        return None
    pk = getattr(value, "pk", None)
    if pk is None:
        pk = getattr(value, "id", value)
    return int(pk) if pk not in (None, "", "null", "None", 0, "0") else None


def assert_document_subentity_unchanged(instance: Any, attrs: dict[str, Any]) -> None:
    if instance is None or "subentity" not in attrs:
        return
    saved_subentity_id = normalize_optional_pk(getattr(instance, "subentity_id", None))
    incoming_subentity_id = normalize_optional_pk(attrs.get("subentity"))
    if incoming_subentity_id != saved_subentity_id:
        raise serializers.ValidationError({"subentity": DOCUMENT_BRANCH_IMMUTABLE_MESSAGE})
