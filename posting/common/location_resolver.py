from __future__ import annotations

from entity.models import Godown


def resolve_posting_location_id(*, entity_id: int, subentity_id: int | None = None, godown_id: int | None = None, location_id: int | None = None) -> int | None:
    """
    Resolve a posting location in the new entity -> subentity -> godown hierarchy.

    Rules:
    - If an explicit godown/location is supplied, use it if it belongs to the entity
      and, when subentity is supplied, it either belongs to that subentity or is
      entity-wide.
    - If no explicit location is supplied, prefer a godown tied to the subentity.
    - Otherwise fall back to any entity-wide active godown.
    - If nothing exists, return None so the posting can still proceed at entity/subentity level.
    """

    explicit_id = int(godown_id or location_id or 0) or None
    if explicit_id:
        godown = Godown.objects.filter(id=explicit_id, entity_id=entity_id, is_active=True).first()
        if not godown:
            raise ValueError("Selected location does not belong to the entity/subentity scope.")
        if subentity_id is not None and godown.subentity_id not in (None, subentity_id):
            raise ValueError("Selected location does not belong to the entity/subentity scope.")
        return godown.id

    if subentity_id is not None:
        godown = (
            Godown.objects.filter(entity_id=entity_id, subentity_id=subentity_id, is_active=True)
            .order_by("-is_default", "id")
            .first()
        )
        if godown:
            return godown.id

    godown = (
        Godown.objects.filter(entity_id=entity_id, subentity__isnull=True, is_active=True)
        .order_by("-is_default", "id")
        .first()
    )
    if godown:
        return godown.id

    godown = Godown.objects.filter(entity_id=entity_id, is_active=True).order_by("-is_default", "id").first()
    return godown.id if godown else None
