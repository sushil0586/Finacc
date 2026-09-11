from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from entity.models import Entity, EntityFinancialYear, EntityOwnershipV2

from .calculations import stable_hash
from .models import (
    CapitalDistributionActivation,
    CapitalDistributionAuditEvent,
    DistributionPolicyVersion,
    EntityFormationProfile,
    FormationType,
    WAVE_ONE_FORMATIONS,
)
from .observability import current_correlation_id, operation_metadata
from .services import (
    distribution_mapping_readiness,
    materialize_formation_profile,
    resolve_entity_formation,
    seed_policy_from_ownership,
)


def _as_date(value):
    return value.date() if hasattr(value, "date") else value


def _issue(code: str, message: str, *, severity: str = "error", details=None) -> dict:
    row = {"code": code, "severity": severity, "message": message}
    if details:
        row["details"] = details
    return row


def _active_owners(*, entity, formation_type, period_from, period_to):
    owner_type = (
        EntityOwnershipV2.OwnershipType.PROPRIETOR
        if formation_type == FormationType.PROPRIETORSHIP
        else EntityOwnershipV2.OwnershipType.PARTNER
    )
    return list(
        entity.ownerships_v2.filter(ownership_type=owner_type, isactive=True)
        .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=period_from))
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period_to))
        .order_by("id")
    )


def assess_wave_one_migration(*, entity: Entity, entityfin: EntityFinancialYear) -> dict:
    if entityfin.entity_id != entity.id:
        raise ValidationError({"entityfinid": "Financial year must belong to the selected entity."})
    period_from = _as_date(entityfin.finstartyear)
    period_to = _as_date(entityfin.finendyear)
    resolution = resolve_entity_formation(entity)
    issues = [dict(row) for row in resolution.readiness_issues]
    formation_type = resolution.formation_type

    if formation_type not in WAVE_ONE_FORMATIONS:
        issues.append(_issue(
            "wave_one_formation_required",
            "Wave 1 migration supports proprietorship, partnership, and LLP entities only.",
        ))

    owners = _active_owners(
        entity=entity,
        formation_type=formation_type,
        period_from=period_from,
        period_to=period_to,
    ) if formation_type in WAVE_ONE_FORMATIONS else []
    if formation_type == FormationType.PROPRIETORSHIP:
        if len(owners) != 1:
            issues.append(_issue(
                "invalid_proprietor_count",
                "Exactly one active proprietor must cover the complete financial year.",
                details=[str(row.id) for row in owners],
            ))
        elif owners[0].share_percentage not in (None, Decimal("100.00")):
            issues.append(_issue(
                "invalid_proprietor_share",
                "A proprietor share, when supplied, must be exactly 100%.",
                details=[f"{owners[0].name}: {owners[0].share_percentage}%"],
            ))
    elif formation_type in {FormationType.PARTNERSHIP, FormationType.LLP}:
        if not owners:
            issues.append(_issue(
                "missing_partners",
                "At least one active partner must cover the complete financial year.",
            ))
        else:
            missing_shares = [row.name for row in owners if row.share_percentage is None]
            if missing_shares:
                issues.append(_issue(
                    "missing_profit_share",
                    "Every active partner requires a profit-sharing percentage.",
                    details=missing_shares,
                ))
            else:
                total = sum((row.share_percentage for row in owners), Decimal("0"))
                if total != Decimal("100.00"):
                    issues.append(_issue(
                        "invalid_profit_share_total",
                        f"Active partner shares total {total:.2f}%; expected 100.00%.",
                    ))

    missing_pan = [row.name for row in owners if not row.pan_number]
    if missing_pan:
        issues.append(_issue(
            "missing_owner_pan",
            "PAN is missing for one or more owners. Complete it before production certification.",
            severity="warning",
            details=missing_pan,
        ))
    missing_reference = [row.name for row in owners if not row.agreement_reference]
    if missing_reference:
        issues.append(_issue(
            "missing_governing_reference",
            "A deed or ownership reference is missing and must be reviewed before policy approval.",
            severity="warning",
            details=missing_reference,
        ))

    profile = (
        EntityFormationProfile.objects.filter(entity=entity, isactive=True)
        .order_by("-version_number", "-id")
        .first()
    )
    profile_ready = bool(
        profile
        and profile.status == EntityFormationProfile.Status.VERIFIED
        and profile.formation_type == formation_type
        and profile.resolution_hash == resolution.resolution_hash
    )
    if profile and not profile_ready:
        issues.append(_issue(
            "formation_profile_stale",
            "The saved formation profile no longer matches the current ownership and constitution evidence.",
        ))

    policies = DistributionPolicyVersion.objects.filter(
        entity=entity,
        entityfin=entityfin,
        formation_type=formation_type,
        isactive=True,
    )
    approved_policy = (
        policies.filter(
            status=DistributionPolicyVersion.Status.APPROVED,
            effective_from__lte=period_from,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period_to))
        .order_by("-version_number", "-id")
        .first()
    )
    mapping = distribution_mapping_readiness(
        entity=entity,
        policy=approved_policy,
        period_from=period_from,
        period_to=period_to,
    ) if approved_policy else {
        "ready": False,
        "appropriation_ready": False,
        "mapped_ownership_ids": [],
        "missing_ownership_ids": [row.id for row in owners],
        "invalid_ownership_ids": [],
        "issues": [{"code": "approved_policy_required"}],
    }
    blockers = [row for row in issues if row.get("severity", "error") == "error"]
    activation_ready = not blockers and profile_ready and bool(approved_policy) and mapping["ready"]
    if not profile_ready:
        activation_issue = _issue("verified_profile_required", "Resolve and verify the formation profile.")
    elif not approved_policy:
        activation_issue = _issue("approved_policy_required", "Approve a complete distribution policy for this financial year.")
    elif not mapping["ready"]:
        activation_issue = _issue("posting_mappings_required", "Complete owner and appropriation posting mappings.")
    else:
        activation_issue = None

    activation = CapitalDistributionActivation.objects.filter(entity=entity, isactive=True).first()
    planned_actions = []
    if not profile_ready:
        planned_actions.append("create_verified_formation_profile")
    if not policies.exists():
        planned_actions.append("create_initial_draft_policy")
    if not activation:
        planned_actions.append("create_disabled_activation_gate")

    payload = {
        "entity": entity.id,
        "entity_name": entity.entityname,
        "entityfinid": entityfin.id,
        "financial_year": entityfin.desc,
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "formation_type": formation_type,
        "strategy_code": resolution.strategy_code,
        "migration_ready": not blockers,
        "activation_ready": activation_ready,
        "activation": {
            "status": activation.status if activation else "not_created",
            "enabled": bool(activation and activation.status == CapitalDistributionActivation.Status.ENABLED),
        },
        "owners": [
            {
                "id": row.id,
                "name": row.name,
                "ownership_type": row.ownership_type,
                "share_percentage": str(row.share_percentage) if row.share_percentage is not None else None,
                "pan_present": bool(row.pan_number),
                "reference_present": bool(row.agreement_reference),
            }
            for row in owners
        ],
        "profile": {
            "id": profile.id if profile else None,
            "ready": profile_ready,
            "status": profile.status if profile else "missing",
        },
        "policy": {
            "count": policies.count(),
            "approved_id": approved_policy.id if approved_policy else None,
        },
        "mapping_readiness": mapping,
        "issues": issues + ([activation_issue] if activation_issue and activation_issue not in issues else []),
        "planned_actions": planned_actions,
    }
    payload["readiness_hash"] = stable_hash({
        key: value
        for key, value in payload.items()
        if key not in {"activation", "planned_actions"}
    })
    return payload


@transaction.atomic
def apply_wave_one_migration(*, entity: Entity, entityfin: EntityFinancialYear, actor) -> dict:
    Entity.objects.select_for_update().get(pk=entity.pk)
    report = assess_wave_one_migration(entity=entity, entityfin=entityfin)
    blocking = [row for row in report["issues"] if row.get("severity", "error") == "error"]
    blocking = [row for row in blocking if row["code"] not in {
        "formation_profile_stale", "verified_profile_required", "approved_policy_required",
        "posting_mappings_required",
    }]
    if blocking:
        raise ValidationError({"readiness": blocking})

    profile = materialize_formation_profile(
        entity=entity,
        actor=actor,
        effective_from=_as_date(entityfin.finstartyear),
    )
    policies = DistributionPolicyVersion.objects.filter(
        entity=entity,
        entityfin=entityfin,
        formation_type=profile.formation_type,
        isactive=True,
    )
    created_policy = None
    if not policies.exists():
        created_policy = seed_policy_from_ownership(
            entity=entity,
            formation_profile=profile,
            payload={
                "entityfin": entityfin,
                "subentity": None,
                "effective_from": _as_date(entityfin.finstartyear),
                "effective_to": _as_date(entityfin.finendyear),
                "governing_document_reference": "",
                "configuration": {"run_cadence": "annual", "rounding": "half_up", "day_count_convention": "actual_365"},
                "notes": "Initial Wave 1 draft generated from the ownership master.",
            },
            actor=actor,
        )

    activation = CapitalDistributionActivation.objects.select_for_update().filter(
        entity=entity,
        isactive=True,
    ).first()
    if activation is None:
        activation = CapitalDistributionActivation.objects.create(entity=entity, createdby=actor)
    refreshed = assess_wave_one_migration(entity=entity, entityfin=entityfin)
    activation.status = (
        CapitalDistributionActivation.Status.READY
        if refreshed["activation_ready"]
        else CapitalDistributionActivation.Status.PENDING
    )
    refreshed["activation"] = {
        "status": activation.status,
        "enabled": activation.status == CapitalDistributionActivation.Status.ENABLED,
    }
    activation.readiness_hash = refreshed["readiness_hash"]
    activation.readiness_snapshot = refreshed
    activation.assessed_at = timezone.now()
    activation.save(update_fields=(
        "status", "readiness_hash", "readiness_snapshot", "assessed_at", "updated_at"
    ))
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        policy=created_policy,
        actor=actor,
        action="wave_one_migration_applied",
        correlation_id=current_correlation_id(),
        after_state={
            "activation": activation.status,
            "formation_profile": profile.id,
            "created_policy": created_policy.id if created_policy else None,
            "readiness_hash": refreshed["readiness_hash"],
        },
        metadata=operation_metadata(operation="apply_wave_one_migration"),
    )
    return refreshed


@transaction.atomic
def set_wave_one_activation(*, entity: Entity, entityfin: EntityFinancialYear, enabled: bool, actor) -> dict:
    Entity.objects.select_for_update().get(pk=entity.pk)
    report = assess_wave_one_migration(entity=entity, entityfin=entityfin)
    activation = CapitalDistributionActivation.objects.select_for_update().filter(
        entity=entity,
        isactive=True,
    ).first()
    if enabled and activation is None:
        raise ValidationError({
            "activation": "Prepare the Wave 1 migration before enabling capital distribution."
        })
    if activation is None:
        activation = CapitalDistributionActivation.objects.create(entity=entity, createdby=actor)
    if enabled and not report["activation_ready"]:
        raise ValidationError({"readiness": report["issues"] + report["mapping_readiness"]["issues"]})
    before = {"status": activation.status, "enabled_at": activation.enabled_at.isoformat() if activation.enabled_at else None}
    activation.status = (
        CapitalDistributionActivation.Status.ENABLED
        if enabled
        else CapitalDistributionActivation.Status.DISABLED
    )
    report["activation"] = {"status": activation.status, "enabled": enabled}
    activation.readiness_hash = report["readiness_hash"]
    activation.readiness_snapshot = report
    activation.assessed_at = timezone.now()
    activation.enabled_at = timezone.now() if enabled else None
    activation.enabled_by = actor if enabled else None
    activation.save()
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        actor=actor,
        action="wave_one_activation_enabled" if enabled else "wave_one_activation_disabled",
        correlation_id=current_correlation_id(),
        before_state=before,
        after_state={"status": activation.status, "readiness_hash": report["readiness_hash"]},
        metadata=operation_metadata(operation="set_wave_one_activation"),
    )
    return report


def assert_wave_one_activation(*, entity: Entity) -> None:
    activation = CapitalDistributionActivation.objects.filter(entity=entity, isactive=True).first()
    if activation and activation.status != CapitalDistributionActivation.Status.ENABLED:
        raise ValidationError({
            "activation": "Capital and distribution is not enabled for this migrated entity. Complete readiness and enable it first."
        })
