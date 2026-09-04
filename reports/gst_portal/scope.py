from __future__ import annotations

from dataclasses import dataclass

from entity.models import EntityGstRegistration, SubEntity, SubEntityGstRegistration


@dataclass(frozen=True)
class GstPortalRegistrationScope:
    gstin: str
    state_cd: str
    registration_source: str
    requested_subentity_id: int | None
    filing_subentity_id: int | None
    shared_subentity_ids: tuple[int, ...]
    warnings: tuple[dict, ...] = ()


def resolve_gst_portal_registration_scope(*, entity_id: int, subentity_id: int | None = None) -> GstPortalRegistrationScope:
    """
    Resolve the GST registration that should drive portal filing.

    GST returns are filed per GSTIN/period. If multiple Finacc branches share the
    same GSTIN, portal filing must aggregate those branches instead of silently
    using only the currently selected branch.
    """

    requested_branch_registration = None
    if subentity_id:
        requested_branch_registration = (
            SubEntityGstRegistration.objects.select_related("state", "subentity")
            .filter(subentity_id=subentity_id, subentity__entity_id=entity_id, isactive=True, is_primary=True)
            .first()
            or SubEntityGstRegistration.objects.select_related("state", "subentity")
            .filter(subentity_id=subentity_id, subentity__entity_id=entity_id, isactive=True)
            .order_by("id")
            .first()
        )

    entity_registration = (
        EntityGstRegistration.objects.select_related("state")
        .filter(entity_id=entity_id, isactive=True, is_primary=True)
        .first()
        or EntityGstRegistration.objects.select_related("state")
        .filter(entity_id=entity_id, isactive=True)
        .order_by("id")
        .first()
    )
    registration = requested_branch_registration or entity_registration
    if not registration:
        raise LookupError("No active GST registration is configured for this filing scope.")

    gstin = str(registration.gstin or "").strip().upper()
    state_cd = _state_code(getattr(registration, "state", None), gstin)
    branch_ids = tuple(
        SubEntityGstRegistration.objects.filter(
            subentity__entity_id=entity_id,
            gstin__iexact=gstin,
            isactive=True,
        )
        .values_list("subentity_id", flat=True)
        .order_by("subentity_id")
    )
    warnings = []
    filing_subentity_id = subentity_id
    if len(branch_ids) > 1:
        filing_subentity_id = None
        warnings.append(
            {
                "code": "GST_PORTAL_SHARED_GSTIN_SCOPE",
                "severity": "warning",
                "message": "Multiple branches share this GSTIN. Portal filing should aggregate all same-GSTIN branches for the return period.",
            }
        )
    elif branch_ids and subentity_id not in branch_ids:
        filing_subentity_id = branch_ids[0]

    source = "subentity" if requested_branch_registration else "entity"
    if source == "entity" and not branch_ids and subentity_id is None:
        branch_ids = tuple(SubEntity.objects.filter(entity_id=entity_id, isactive=True).values_list("id", flat=True).order_by("id"))

    return GstPortalRegistrationScope(
        gstin=gstin,
        state_cd=state_cd,
        registration_source=source,
        requested_subentity_id=subentity_id,
        filing_subentity_id=filing_subentity_id,
        shared_subentity_ids=branch_ids,
        warnings=tuple(warnings),
    )


def _state_code(state, gstin: str) -> str:
    explicit = str(getattr(state, "statecode", "") or "").strip()
    if explicit:
        return explicit.zfill(2) if explicit.isdigit() else explicit
    return gstin[:2] if gstin else ""
