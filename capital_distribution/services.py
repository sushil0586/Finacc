from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from core.concurrency import assert_expected_updated_at
from entity.models import Entity, EntityFinancialYear, EntityOwnershipV2, SubEntity
from financial.models import account
from posting.models import JournalLine, TxnType

from .calculations import (
    calculate_segment,
    decimal_value,
    inclusive_days,
    money,
    stable_hash,
    validate_stakeholder_calculation_configuration,
)

from .models import (
    CapitalDistributionAuditEvent,
    CapitalDistributionAccountMapping,
    CapitalDistributionLine,
    CapitalDistributionRun,
    CapitalDistributionSegment,
    DistributionBalanceSnapshot,
    DistributionPolicyStakeholder,
    DistributionPolicyVersion,
    EntityFormationProfile,
    FormationType,
    WAVE_ONE_FORMATIONS,
)
from .observability import current_correlation_id, operation_metadata
from .posting import CapitalDistributionPostingAdapter


STRATEGY_BY_FORMATION = {
    FormationType.PROPRIETORSHIP: "proprietor_capital_v1",
    FormationType.PARTNERSHIP: "partnership_appropriation_v1",
    FormationType.LLP: "llp_appropriation_v1",
    FormationType.COMPANY: "company_equity_dividend_v1",
    FormationType.OPC: "opc_equity_dividend_v1",
    FormationType.HUF: "huf_capital_v1",
    FormationType.TRUST: "trust_fund_allocation_v1",
    FormationType.SOCIETY: "society_fund_allocation_v1",
    FormationType.NGO: "ngo_fund_allocation_v1",
    FormationType.SECTION_8: "section_8_fund_allocation_v1",
    FormationType.COOPERATIVE: "cooperative_distribution_v1",
    FormationType.GOVERNMENT: "government_capital_transfer_v1",
    FormationType.PSU: "psu_capital_transfer_v1",
}


@dataclass(frozen=True)
class FormationResolution:
    formation_type: str
    strategy_code: str
    status: str
    supported: bool
    evidence: dict
    readiness_issues: list[dict]
    resolution_hash: str

    def as_dict(self) -> dict:
        return {
            "formation_type": self.formation_type,
            "strategy_code": self.strategy_code,
            "status": self.status,
            "supported": self.supported,
            "evidence": self.evidence,
            "readiness_issues": self.readiness_issues,
            "resolution_hash": self.resolution_hash,
        }


def _normal(value) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def _formation_from_text(value) -> str | None:
    text = _normal(value)
    if not text:
        return None
    checks = (
        (FormationType.SECTION_8, ("section 8", "section eight")),
        (FormationType.OPC, ("one person company", "opc")),
        (FormationType.LLP, ("limited liability partnership", "llp")),
        (FormationType.HUF, ("hindu undivided family", "huf")),
        (FormationType.COOPERATIVE, ("cooperative", "co operative")),
        (FormationType.PSU, ("public sector undertaking", "psu")),
        (FormationType.GOVERNMENT, ("government", "govt")),
        (FormationType.PROPRIETORSHIP, ("proprietorship", "proprietor", "sole owner")),
        (FormationType.PARTNERSHIP, ("partnership", "partner")),
        (FormationType.COMPANY, ("private limited", "public limited", "company", "pvt ltd", "ltd")),
        (FormationType.TRUST, ("trust",)),
        (FormationType.SOCIETY, ("society",)),
        (FormationType.NGO, ("ngo", "non government organisation", "non government organization")),
    )
    for formation, tokens in checks:
        if any(token in text for token in tokens):
            return formation
    return None


def _resolution_hash(payload: dict) -> str:
    stable = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def resolve_entity_formation(entity: Entity) -> FormationResolution:
    tax_profile = getattr(entity, "tax_profile", None)
    cin_no = str(getattr(tax_profile, "cin_no", "") or "").strip().upper()
    llpin_no = str(getattr(tax_profile, "llpin_no", "") or "").strip().upper()
    constitution_rows = list(
        entity.constitutions_v2.filter(isactive=True)
        .order_by("id")
        .values("id", "constitution_code", "constitution_name", "effective_from", "effective_to")
    )
    ownership_rows = list(
        entity.ownerships_v2.filter(isactive=True)
        .order_by("id")
        .values("id", "ownership_type", "name", "share_percentage", "effective_from", "effective_to")
    )

    identifier_signals = []
    if cin_no:
        identifier_signals.append(FormationType.COMPANY)
    if llpin_no:
        identifier_signals.append(FormationType.LLP)

    constitution_signals = {
        signal
        for row in constitution_rows
        for signal in (
            _formation_from_text(row.get("constitution_code")),
            _formation_from_text(row.get("constitution_name")),
        )
        if signal
    }
    ownership_types = {str(row.get("ownership_type") or "").strip().lower() for row in ownership_rows}
    ownership_signals = set()
    if "proprietor" in ownership_types:
        ownership_signals.add(FormationType.PROPRIETORSHIP)
    if "partner" in ownership_types:
        ownership_signals.add(FormationType.PARTNERSHIP)
    if ownership_types & {"director", "shareholder"}:
        ownership_signals.add(FormationType.COMPANY)
    if "trustee" in ownership_types:
        ownership_signals.add(FormationType.TRUST)

    business_signal = None
    if entity.business_type == Entity.BusinessType.NGO:
        business_signal = FormationType.NGO
    elif entity.business_type == Entity.BusinessType.GOVERNMENT:
        business_signal = FormationType.GOVERNMENT

    evidence = {
        "identifiers": {"cin_no": cin_no or None, "llpin_no": llpin_no or None},
        "constitution_rows": [
            {
                **row,
                "effective_from": row["effective_from"].isoformat() if row["effective_from"] else None,
                "effective_to": row["effective_to"].isoformat() if row["effective_to"] else None,
            }
            for row in constitution_rows
        ],
        "ownership_rows": [
            {
                **row,
                "share_percentage": str(row["share_percentage"]) if row["share_percentage"] is not None else None,
                "effective_from": row["effective_from"].isoformat() if row["effective_from"] else None,
                "effective_to": row["effective_to"].isoformat() if row["effective_to"] else None,
            }
            for row in ownership_rows
        ],
        "business_type": entity.business_type,
        "signals": {
            "identifier": sorted(identifier_signals),
            "constitution": sorted(constitution_signals),
            "ownership": sorted(ownership_signals),
            "business": business_signal,
        },
    }

    issues = []
    identifier_set = set(identifier_signals)
    if len(identifier_set) > 1:
        issues.append({
            "code": "conflicting_registration_identifiers",
            "severity": "error",
            "message": "CIN and LLPIN evidence conflict. Correct the entity registration profile before setup.",
        })

    selected = None
    if identifier_set:
        selected = next(iter(identifier_set))
        incompatible_constitutions = {
            value for value in constitution_signals if value != selected and not (
                selected == FormationType.COMPANY and value in {FormationType.OPC, FormationType.SECTION_8}
            )
        }
        if incompatible_constitutions:
            issues.append({
                "code": "identifier_constitution_conflict",
                "severity": "error",
                "message": "Registration identifiers conflict with constitution details.",
                "details": sorted(incompatible_constitutions),
            })
        if selected == FormationType.COMPANY:
            if FormationType.SECTION_8 in constitution_signals:
                selected = FormationType.SECTION_8
            elif FormationType.OPC in constitution_signals:
                selected = FormationType.OPC
    elif len(constitution_signals) == 1:
        selected = next(iter(constitution_signals))
    elif len(constitution_signals) > 1:
        issues.append({
            "code": "multiple_constitution_signals",
            "severity": "error",
            "message": "Multiple active constitution types were found.",
            "details": sorted(constitution_signals),
        })
    elif len(ownership_signals) == 1:
        selected = next(iter(ownership_signals))
    elif len(ownership_signals) > 1:
        issues.append({
            "code": "mixed_ownership_signals",
            "severity": "error",
            "message": "Ownership rows imply more than one organization formation.",
            "details": sorted(ownership_signals),
        })
    elif business_signal:
        selected = business_signal
        issues.append({
            "code": "business_type_only",
            "severity": "warning",
            "message": "Formation is inferred only from business type and requires verification.",
        })

    selected = selected or FormationType.UNCONFIGURED
    if selected == FormationType.LLP and FormationType.PARTNERSHIP in ownership_signals:
        # LLP partners are represented by partner ownership rows and are compatible.
        ownership_signals.discard(FormationType.PARTNERSHIP)
    incompatible_ownership = {
        value for value in ownership_signals if value != selected and not (
            selected in {FormationType.OPC, FormationType.SECTION_8} and value == FormationType.COMPANY
        )
    }
    if incompatible_ownership:
        issues.append({
            "code": "formation_ownership_conflict",
            "severity": "error",
            "message": "Ownership rows conflict with the resolved organization formation.",
            "details": sorted(incompatible_ownership),
        })

    has_error = any(issue["severity"] == "error" for issue in issues)
    supported = selected in WAVE_ONE_FORMATIONS and not has_error
    if selected == FormationType.UNCONFIGURED and has_error:
        status = EntityFormationProfile.Status.CONTRADICTORY
        issues.append({
            "code": "formation_unconfigured",
            "severity": "error",
            "message": "Organization formation cannot be resolved until conflicting evidence is corrected.",
        })
    elif selected == FormationType.UNCONFIGURED:
        status = EntityFormationProfile.Status.DRAFT
        issues.append({
            "code": "formation_unconfigured",
            "severity": "error",
            "message": "Organization formation is not configured.",
        })
    elif has_error:
        status = EntityFormationProfile.Status.CONTRADICTORY
    elif supported:
        status = EntityFormationProfile.Status.VERIFIED
    else:
        status = EntityFormationProfile.Status.UNSUPPORTED
        issues.append({
            "code": "strategy_not_enabled",
            "severity": "warning",
            "message": "This formation is recognized but its distribution strategy is not enabled in Wave 1.",
        })

    strategy_code = STRATEGY_BY_FORMATION.get(selected, "")
    hash_payload = {
        "formation_type": selected,
        "strategy_code": strategy_code,
        "evidence": evidence,
        "issues": issues,
    }
    return FormationResolution(
        formation_type=selected,
        strategy_code=strategy_code,
        status=status,
        supported=supported,
        evidence=evidence,
        readiness_issues=issues,
        resolution_hash=_resolution_hash(hash_payload),
    )


@transaction.atomic
def materialize_formation_profile(*, entity: Entity, actor, effective_from=None) -> EntityFormationProfile:
    resolution = resolve_entity_formation(entity)
    latest = (
        EntityFormationProfile.objects.select_for_update()
        .filter(entity=entity)
        .order_by("-version_number", "-id")
        .first()
    )
    if latest and latest.resolution_hash == resolution.resolution_hash and latest.isactive:
        return latest

    version = (latest.version_number if latest else 0) + 1
    profile = EntityFormationProfile.objects.create(
        entity=entity,
        formation_type=resolution.formation_type,
        strategy_code=resolution.strategy_code,
        version_number=version,
        status=resolution.status,
        effective_from=effective_from,
        source="resolved",
        evidence=resolution.evidence,
        readiness_issues=resolution.readiness_issues,
        resolution_hash=resolution.resolution_hash,
        verified_at=timezone.now() if resolution.status == EntityFormationProfile.Status.VERIFIED else None,
        verified_by=actor if resolution.status == EntityFormationProfile.Status.VERIFIED else None,
        createdby=actor,
    )
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        actor=actor,
        action="formation_resolved",
        correlation_id=current_correlation_id(),
        after_state=serialize_formation_profile(profile),
    )
    return profile


def _policy_state(policy: DistributionPolicyVersion) -> dict:
    return {
        "id": policy.id,
        "version_number": policy.version_number,
        "status": policy.status,
        "formation_type": policy.formation_type,
        "effective_from": policy.effective_from.isoformat(),
        "effective_to": policy.effective_to.isoformat() if policy.effective_to else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def serialize_formation_profile(profile: EntityFormationProfile) -> dict:
    return {
        "id": profile.id,
        "entity": profile.entity_id,
        "formation_type": profile.formation_type,
        "strategy_code": profile.strategy_code,
        "policy_schema_version": profile.policy_schema_version,
        "version_number": profile.version_number,
        "status": profile.status,
        "supported": profile.formation_type in WAVE_ONE_FORMATIONS and profile.status == profile.Status.VERIFIED,
        "effective_from": profile.effective_from.isoformat() if profile.effective_from else None,
        "effective_to": profile.effective_to.isoformat() if profile.effective_to else None,
        "source": profile.source,
        "evidence": profile.evidence,
        "readiness_issues": profile.readiness_issues,
        "resolution_hash": profile.resolution_hash,
        "verified_at": profile.verified_at.isoformat() if profile.verified_at else None,
    }


def validate_policy(policy: DistributionPolicyVersion) -> None:
    errors = {}
    policy_configuration = policy.configuration or {}
    allowed_policy_settings = {"run_cadence", "rounding", "day_count_convention", "allow_day_weighted"}
    unknown_policy_settings = sorted(set(policy_configuration) - allowed_policy_settings)
    if unknown_policy_settings:
        errors["configuration"] = f"Unsupported policy settings: {', '.join(unknown_policy_settings)}."
    if policy_configuration.get("day_count_convention", "actual_365") not in {"actual_365", "actual_360", "actual_actual"}:
        errors["day_count_convention"] = "Day-count convention must be actual_365, actual_360, or actual_actual."
    if policy.formation_type not in WAVE_ONE_FORMATIONS:
        errors["formation_type"] = "This formation strategy is not enabled in Wave 1."
    if policy.formation_profile.status != EntityFormationProfile.Status.VERIFIED:
        errors["formation_profile"] = "A verified formation profile is required."

    overlaps = DistributionPolicyVersion.objects.filter(
        entity=policy.entity,
        formation_type=policy.formation_type,
        status=DistributionPolicyVersion.Status.APPROVED,
        isactive=True,
    ).exclude(pk=policy.pk).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=policy.effective_from),
    )
    if policy.effective_to:
        overlaps = overlaps.filter(effective_from__lte=policy.effective_to)
    if overlaps.exists():
        errors["effective_from"] = "Policy period overlaps an approved policy."

    rows = list(policy.stakeholders.filter(isactive=True).select_related("ownership"))
    for row in rows:
        try:
            validate_stakeholder_calculation_configuration(row.configuration)
        except ValidationError as exc:
            errors[f"stakeholder_{row.ownership_id}_configuration"] = exc.messages
    invalid_ownership_rows = []
    for row in rows:
        ownership = row.ownership
        if ownership is None or not ownership.isactive:
            invalid_ownership_rows.append(row.target_name)
            continue
        if ownership.effective_from and ownership.effective_from > policy.effective_from:
            invalid_ownership_rows.append(row.target_name)
            continue
        if ownership.effective_to and ownership.effective_to < policy.effective_from:
            invalid_ownership_rows.append(row.target_name)
            continue
        if policy.effective_to and ownership.effective_to and ownership.effective_to < policy.effective_to:
            invalid_ownership_rows.append(row.target_name)
    if invalid_ownership_rows:
        errors["ownership"] = (
            "Stakeholders must be active for the complete policy period: "
            + ", ".join(invalid_ownership_rows)
            + "."
        )
    if policy.formation_type == FormationType.PROPRIETORSHIP:
        if len(rows) != 1 or rows[0].target_type != DistributionPolicyStakeholder.TargetType.PROPRIETOR:
            errors["stakeholders"] = "A proprietorship requires exactly one proprietor row."
        elif rows[0].profit_percentage != Decimal("100.0000"):
            errors["profit_percentage"] = "The proprietor share must be exactly 100%."
        elif ((rows[0].configuration or {}).get("remuneration") or {}).get("enabled"):
            errors["remuneration"] = "Proprietor remuneration is not an appropriation and cannot be enabled."
    elif policy.formation_type in {FormationType.PARTNERSHIP, FormationType.LLP}:
        if not rows or any(row.target_type != DistributionPolicyStakeholder.TargetType.PARTNER for row in rows):
            errors["stakeholders"] = "Partnership and LLP policies require partner rows only."
        profit_total = sum((row.profit_percentage or Decimal("0")) for row in rows)
        if profit_total != Decimal("100.0000"):
            errors["profit_percentage"] = f"Partner profit shares total {profit_total:.4f}%; expected 100.0000%."
        configured_loss_rows = [row for row in rows if row.loss_percentage is not None]
        if configured_loss_rows:
            if len(configured_loss_rows) != len(rows):
                errors["loss_percentage"] = "Set loss percentage for every partner or leave all loss percentages blank."
            else:
                loss_total = sum(row.loss_percentage for row in configured_loss_rows)
                if loss_total != Decimal("100.0000"):
                    errors["loss_percentage"] = f"Partner loss shares total {loss_total:.4f}%; expected 100.0000%."
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def create_policy(*, entity: Entity, formation_profile: EntityFormationProfile, payload: dict, actor) -> DistributionPolicyVersion:
    payload = dict(payload)
    EntityFormationProfile.objects.select_for_update().get(pk=formation_profile.pk)
    if formation_profile.entity_id != entity.id:
        raise ValidationError({"formation_profile": "Formation profile must belong to the selected entity."})
    if formation_profile.status != EntityFormationProfile.Status.VERIFIED:
        raise ValidationError({"formation_profile": "A verified formation profile is required."})
    if formation_profile.formation_type not in WAVE_ONE_FORMATIONS:
        raise ValidationError({"formation_type": "This formation strategy is not enabled in Wave 1."})

    version = (
        DistributionPolicyVersion.objects.select_for_update()
        .filter(entity=entity)
        .aggregate(value=Max("version_number"))["value"]
        or 0
    ) + 1
    stakeholders = payload.pop("stakeholders", [])
    policy = DistributionPolicyVersion.objects.create(
        entity=entity,
        formation_profile=formation_profile,
        formation_type=formation_profile.formation_type,
        version_number=version,
        createdby=actor,
        **payload,
    )
    for index, stakeholder in enumerate(stakeholders):
        row = dict(stakeholder)
        DistributionPolicyStakeholder.objects.create(
            policy=policy,
            createdby=actor,
            sort_order=row.pop("sort_order", (index + 1) * 10),
            **row,
        )
    validate_policy(policy)
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        policy=policy,
        actor=actor,
        action="policy_created",
        correlation_id=current_correlation_id(),
        after_state=_policy_state(policy),
    )
    return policy


def _ownership_rows_for_policy(*, entity: Entity, formation_type: str, effective_from):
    ownership_type = (
        EntityOwnershipV2.OwnershipType.PROPRIETOR
        if formation_type == FormationType.PROPRIETORSHIP
        else EntityOwnershipV2.OwnershipType.PARTNER
    )
    return list(
        EntityOwnershipV2.objects.filter(
            entity=entity,
            ownership_type=ownership_type,
            isactive=True,
        )
        .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=effective_from))
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=effective_from))
        .order_by("id")
    )


@transaction.atomic
def seed_policy_from_ownership(
    *,
    entity: Entity,
    formation_profile: EntityFormationProfile,
    payload: dict,
    actor,
) -> DistributionPolicyVersion:
    effective_from = payload["effective_from"]
    owners = _ownership_rows_for_policy(
        entity=entity,
        formation_type=formation_profile.formation_type,
        effective_from=effective_from,
    )
    if formation_profile.formation_type == FormationType.PROPRIETORSHIP:
        if len(owners) != 1:
            raise ValidationError({
                "ownership": "Exactly one active proprietor is required on the policy effective date."
            })
    elif formation_profile.formation_type in {FormationType.PARTNERSHIP, FormationType.LLP}:
        if not owners:
            raise ValidationError({"ownership": "At least one active partner is required on the policy effective date."})
        missing_shares = [owner.name for owner in owners if owner.share_percentage is None]
        if missing_shares:
            raise ValidationError({
                "ownership": f"Profit share is missing for: {', '.join(missing_shares)}."
            })
    else:
        raise ValidationError({"formation_type": "This formation strategy is not enabled in Wave 1."})

    target_type = (
        DistributionPolicyStakeholder.TargetType.PROPRIETOR
        if formation_profile.formation_type == FormationType.PROPRIETORSHIP
        else DistributionPolicyStakeholder.TargetType.PARTNER
    )
    stakeholders = []
    for owner in owners:
        percentage = Decimal("100.0000") if target_type == "proprietor" else owner.share_percentage
        account_preference = owner.account_preference
        if account_preference == EntityOwnershipV2.AccountPreference.AUTO:
            account_preference = EntityOwnershipV2.AccountPreference.CURRENT
        stakeholders.append({
            "ownership": owner,
            "target_type": target_type,
            "target_name": owner.name,
            "profit_percentage": percentage,
            "loss_percentage": percentage,
            "destination_account_preference": account_preference,
            "configuration": {"seeded_from_ownership": True},
        })
    create_payload = dict(payload)
    create_payload["stakeholders"] = stakeholders
    policy = create_policy(
        entity=entity,
        formation_profile=formation_profile,
        payload=create_payload,
        actor=actor,
    )
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        policy=policy,
        actor=actor,
        action="policy_seeded_from_ownership",
        correlation_id=current_correlation_id(),
        after_state=_policy_state(policy),
        metadata={"ownership_ids": [owner.id for owner in owners]},
    )
    return policy


@transaction.atomic
def update_draft_policy(
    *, policy: DistributionPolicyVersion, payload: dict, actor, expected_updated_at=None
) -> DistributionPolicyVersion:
    policy = DistributionPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != DistributionPolicyVersion.Status.DRAFT:
        raise ValidationError({"status": "Only a draft policy can be edited."})
    payload = dict(payload)
    before = _policy_state(policy)
    stakeholders = payload.pop("stakeholders", None)
    for field in (
        "entityfin",
        "subentity",
        "effective_from",
        "effective_to",
        "governing_document_reference",
        "configuration",
        "schema_version",
        "notes",
    ):
        if field in payload:
            setattr(policy, field, payload[field])
    policy.save()
    if stakeholders is not None:
        policy.stakeholders.all().delete()
        for index, stakeholder in enumerate(stakeholders):
            row = dict(stakeholder)
            DistributionPolicyStakeholder.objects.create(
                policy=policy,
                createdby=actor,
                sort_order=row.pop("sort_order", (index + 1) * 10),
                **row,
            )
    validate_policy(policy)
    CapitalDistributionAuditEvent.objects.create(
        entity=policy.entity,
        policy=policy,
        actor=actor,
        action="policy_updated",
        correlation_id=current_correlation_id(),
        before_state=before,
        after_state=_policy_state(policy),
    )
    return policy


@transaction.atomic
def submit_policy(
    *, policy: DistributionPolicyVersion, actor, reason="", expected_updated_at=None
) -> DistributionPolicyVersion:
    policy = DistributionPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != DistributionPolicyVersion.Status.DRAFT:
        raise ValidationError({"status": "Only a draft policy can be submitted."})
    validate_policy(policy)
    before = _policy_state(policy)
    policy.status = DistributionPolicyVersion.Status.SUBMITTED
    policy.submitted_at = timezone.now()
    policy.submitted_by = actor
    policy.save(update_fields=("status", "submitted_at", "submitted_by", "updated_at"))
    CapitalDistributionAuditEvent.objects.create(
        entity=policy.entity,
        policy=policy,
        actor=actor,
        action="policy_submitted",
        correlation_id=current_correlation_id(),
        reason=reason,
        before_state=before,
        after_state=_policy_state(policy),
    )
    return policy


@transaction.atomic
def approve_policy(
    *, policy: DistributionPolicyVersion, actor, reason="", expected_updated_at=None
) -> DistributionPolicyVersion:
    policy = DistributionPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != DistributionPolicyVersion.Status.SUBMITTED:
        raise ValidationError({"status": "Only a submitted policy can be approved."})
    if policy.submitted_by_id == getattr(actor, "id", None):
        raise ValidationError({"approved_by": "The maker cannot approve their own policy."})
    validate_policy(policy)
    before = _policy_state(policy)
    policy.status = DistributionPolicyVersion.Status.APPROVED
    policy.approved_at = timezone.now()
    policy.approved_by = actor
    policy.save(update_fields=("status", "approved_at", "approved_by", "updated_at"))
    CapitalDistributionAuditEvent.objects.create(
        entity=policy.entity,
        policy=policy,
        actor=actor,
        action="policy_approved",
        correlation_id=current_correlation_id(),
        reason=reason,
        before_state=before,
        after_state=_policy_state(policy),
    )
    return policy


@transaction.atomic
def reject_policy(
    *, policy: DistributionPolicyVersion, actor, reason, expected_updated_at=None
) -> DistributionPolicyVersion:
    policy = DistributionPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != DistributionPolicyVersion.Status.SUBMITTED:
        raise ValidationError({"status": "Only a submitted policy can be rejected."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "A rejection reason is required."})
    before = _policy_state(policy)
    policy.status = DistributionPolicyVersion.Status.REJECTED
    policy.save(update_fields=("status", "updated_at"))
    CapitalDistributionAuditEvent.objects.create(
        entity=policy.entity,
        policy=policy,
        actor=actor,
        action="policy_rejected",
        correlation_id=current_correlation_id(),
        reason=reason,
        before_state=before,
        after_state=_policy_state(policy),
    )
    return policy


@transaction.atomic
def supersede_policy(
    *, policy: DistributionPolicyVersion, actor, reason, expected_updated_at=None
) -> DistributionPolicyVersion:
    policy = DistributionPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != DistributionPolicyVersion.Status.APPROVED:
        raise ValidationError({"status": "Only an approved policy can be superseded."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "A supersession reason is required."})
    before = _policy_state(policy)
    policy.status = DistributionPolicyVersion.Status.SUPERSEDED
    policy.save(update_fields=("status", "updated_at"))
    CapitalDistributionAuditEvent.objects.create(
        entity=policy.entity,
        policy=policy,
        actor=actor,
        action="policy_superseded",
        correlation_id=current_correlation_id(),
        reason=reason,
        before_state=before,
        after_state=_policy_state(policy),
    )
    return policy


def _as_date(value):
    return value.date() if hasattr(value, "date") else value


def _approved_policy_segments(*, entity, entityfin, subentity, period_from, period_to):
    policies = list(
        DistributionPolicyVersion.objects.filter(
            entity=entity,
            formation_type__in=WAVE_ONE_FORMATIONS,
            status=DistributionPolicyVersion.Status.APPROVED,
            isactive=True,
            effective_from__lte=period_to,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period_from))
        .filter(Q(entityfin__isnull=True) | Q(entityfin=entityfin))
        .filter(Q(subentity__isnull=True) | Q(subentity=subentity))
        .select_related("formation_profile")
        .prefetch_related("stakeholders")
        .order_by("effective_from", "version_number", "id")
    )
    if not policies:
        raise ValidationError({"policy": "No approved Wave 1 distribution policy covers this period."})
    formation_types = {policy.formation_type for policy in policies}
    if len(formation_types) != 1:
        raise ValidationError({
            "policy": "Approved policies from different organization formations cannot be combined in one run."
        })

    segments = []
    cursor = period_from
    for policy in policies:
        start = max(cursor, policy.effective_from, period_from)
        end = min(period_to, policy.effective_to or period_to)
        if start > end:
            continue
        if start != cursor:
            raise ValidationError({"policy": f"Approved policy coverage has a gap beginning {cursor.isoformat()}."})
        segments.append((start, end, policy))
        cursor = end + timedelta(days=1)
        if cursor > period_to:
            break
    if cursor <= period_to:
        raise ValidationError({"policy": f"Approved policy coverage ends before {period_to.isoformat()}."})
    return segments


def _segment_book_profit(*, entity, entityfin, subentity, period_from, period_to):
    from reports.services.financial.statements import build_profit_and_loss

    report = build_profit_and_loss(
        entity_id=entity.id,
        entityfin_id=entityfin.id,
        subentity_id=subentity.id if subentity else None,
        from_date=period_from,
        to_date=period_to,
        posted_only=True,
        include_disclosures=False,
        page_size=1,
    )
    value = money(decimal_value(report["totals"]["net_profit"]))
    snapshot = {
        "source": "profit_loss_report",
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "net_profit": str(value),
        "report_totals": report["totals"],
    }
    return value, snapshot


def _account_balance_snapshot(*, mapped_account, entityfin, subentity, cutoff_date) -> dict:
    ledger = mapped_account.ledger
    rows = JournalLine.objects.filter(
        entity_id=mapped_account.entity_id,
        entityfin_id=entityfin.id,
        ledger_id=ledger.id,
        posting_date__lte=cutoff_date,
        posting_batch__is_active=True,
    ).exclude(txn_type=TxnType.CAPITAL_DISTRIBUTION)
    if subentity:
        rows = rows.filter(subentity=subentity)
    totals = rows.aggregate(
        debit=Sum("amount", filter=Q(drcr=True)),
        credit=Sum("amount", filter=Q(drcr=False)),
        latest=Max("posted_at"),
    )
    debit = money(decimal_value(ledger.openingbdr) + decimal_value(totals["debit"]))
    credit = money(decimal_value(ledger.openingbcr) + decimal_value(totals["credit"]))
    return {
        "account": mapped_account.id,
        "ledger": ledger.id,
        "debit": debit,
        "credit": credit,
        "net_debit": money(max(debit - credit, Decimal("0"))),
        "net_credit": money(max(credit - debit, Decimal("0"))),
        "movement_count": rows.count(),
        "latest_posted_at": totals["latest"].isoformat() if totals["latest"] else None,
    }


def collect_distribution_balances(*, policy_segments, entity, entityfin, subentity, period_to) -> list[dict]:
    stakeholder_rows = {}
    for _, _, policy in policy_segments:
        for row in policy.stakeholders.filter(isactive=True).select_related("ownership"):
            stakeholder_rows[row.ownership_id] = row
    mappings = {
        row.ownership_id: row
        for row in CapitalDistributionAccountMapping.objects.filter(
            entity=entity,
            ownership_id__in=stakeholder_rows,
            isactive=True,
        ).select_related("capital_account__ledger", "current_account__ledger", "drawings_account__ledger")
    }
    missing = [row.target_name for owner_id, row in stakeholder_rows.items() if owner_id not in mappings]
    if missing:
        raise ValidationError({"account_mappings": f"Posting account mappings are missing for: {', '.join(missing)}."})

    balances = []
    for ownership_id, stakeholder in stakeholder_rows.items():
        mapping = mappings[ownership_id]
        destination = mapping.destination_account(stakeholder.destination_account_preference)
        if not destination:
            raise ValidationError({"account_mappings": f"No destination account is mapped for {stakeholder.target_name}."})
        capital_source = mapping.capital_account or destination
        capital = _account_balance_snapshot(
            mapped_account=capital_source,
            entityfin=entityfin,
            subentity=subentity,
            cutoff_date=period_to,
        )
        drawings = (
            _account_balance_snapshot(
                mapped_account=mapping.drawings_account,
                entityfin=entityfin,
                subentity=subentity,
                cutoff_date=period_to,
            )
            if mapping.drawings_account_id
            else None
        )
        balances.append({
            "ownership": ownership_id,
            "capital_balance": str(capital["net_credit"]),
            "drawing_balance": str(drawings["net_debit"] if drawings else Decimal("0")),
            "movements": [{
                "source": "posted_ledger",
                "mapping": mapping.id,
                "capital": {key: str(value) if isinstance(value, Decimal) else value for key, value in capital.items()},
                "drawings": (
                    {key: str(value) if isinstance(value, Decimal) else value for key, value in drawings.items()}
                    if drawings else None
                ),
            }],
            "source_references": [
                f"mapping:{mapping.id}",
                f"account:{capital_source.id}",
                f"ledger:{capital_source.ledger_id}",
                *([f"account:{mapping.drawings_account_id}", f"ledger:{mapping.drawings_account.ledger_id}"] if mapping.drawings_account_id else []),
            ],
        })
    return balances


def distribution_mapping_readiness(*, entity, policy=None, period_from=None, period_to=None) -> dict:
    ownership_ids = set()
    if policy:
        ownership_ids = set(policy.stakeholders.filter(isactive=True).values_list("ownership_id", flat=True))
    else:
        ownership_ids = set(entity.ownerships_v2.filter(isactive=True).values_list("id", flat=True))
    mappings = list(
        CapitalDistributionAccountMapping.objects.filter(entity=entity, ownership_id__in=ownership_ids, isactive=True)
        .select_related("ownership", "capital_account__ledger", "current_account__ledger", "drawings_account__ledger")
    )
    mapped_ids = {row.ownership_id for row in mappings}
    missing_ids = sorted(owner_id for owner_id in ownership_ids if owner_id not in mapped_ids)
    invalid_ids = []
    mapping_by_owner = {row.ownership_id: row for row in mappings}
    if policy:
        for stakeholder in policy.stakeholders.filter(isactive=True).select_related("ownership"):
            mapping = mapping_by_owner.get(stakeholder.ownership_id)
            mapping_covers_period = bool(mapping) and (
                not period_from or not mapping.effective_from or mapping.effective_from <= period_from
            ) and (
                not period_to or not mapping.effective_to or mapping.effective_to >= period_to
            )
            destination = mapping.destination_account(stakeholder.destination_account_preference) if mapping_covers_period else None
            if not destination or not destination.isactive or not destination.ledger_id or not destination.ledger.isactive:
                invalid_ids.append(stakeholder.ownership_id)
                continue
            drawing_config = (stakeholder.configuration or {}).get("drawing_interest") or {}
            if drawing_config.get("enabled") and (
                not mapping.drawings_account_id
                or not mapping.drawings_account.isactive
                or not mapping.drawings_account.ledger_id
                or not mapping.drawings_account.ledger.isactive
            ):
                invalid_ids.append(stakeholder.ownership_id)

    from posting.common.static_accounts import StaticAccountCodes
    from posting.models import EntityStaticAccountMap

    appropriation_ready = EntityStaticAccountMap.objects.filter(
        entity=entity,
        sub_entity__isnull=True,
        static_account__code=StaticAccountCodes.PROFIT_LOSS_APPROPRIATION,
        static_account__is_active=True,
        is_active=True,
        account__isactive=True,
        account__ledger__isactive=True,
        ledger__isactive=True,
    ).exists()
    issues = []
    if missing_ids:
        issues.append({"code": "missing_partner_mappings", "ownership_ids": missing_ids})
    if invalid_ids:
        issues.append({"code": "invalid_partner_mappings", "ownership_ids": sorted(set(invalid_ids))})
    if not appropriation_ready:
        issues.append({"code": "missing_appropriation_mapping"})
    return {
        "ready": not issues,
        "appropriation_ready": appropriation_ready,
        "mapped_ownership_ids": sorted(mapped_ids),
        "missing_ownership_ids": missing_ids,
        "invalid_ownership_ids": sorted(set(invalid_ids)),
        "issues": issues,
    }


def serialize_distribution_run(run: CapitalDistributionRun) -> dict:
    segments = run.segments.prefetch_related("lines__stakeholder").order_by("sequence")
    return {
        "id": run.id,
        "entity": run.entity_id,
        "entityfinid": run.entityfin_id,
        "subentity": run.subentity_id,
        "formation_type": run.formation_profile.formation_type,
        "policy": run.policy_id,
        "period_from": run.period_from.isoformat(),
        "period_to": run.period_to.isoformat(),
        "cadence": run.cadence,
        "status": run.status,
        "profit_source": run.profit_source,
        "source_profit": str(run.source_profit),
        "book_adjustments": str(run.book_adjustments),
        "distributable_result": str(run.distributable_result),
        "calculation_hash": run.calculation_hash,
        "idempotency_key": run.idempotency_key,
        "source_snapshot": run.source_snapshot,
        "calculated_at": run.calculated_at.isoformat() if run.calculated_at else None,
        "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
        "submitted_by": run.submitted_by_id,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "approved_by": run.approved_by_id,
        "posted_at": run.posted_at.isoformat() if run.posted_at else None,
        "posted_by": run.posted_by_id,
        "reversed_at": run.reversed_at.isoformat() if run.reversed_at else None,
        "reversed_by": run.reversed_by_id,
        "lifecycle_reason": run.lifecycle_reason,
        "posting_batch": str(run.posting_batch_id) if run.posting_batch_id else None,
        "reversal_batch": str(run.reversal_batch_id) if run.reversal_batch_id else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "segments": [
            {
                "id": segment.id,
                "sequence": segment.sequence,
                "policy": segment.policy_id,
                "policy_version": segment.policy.version_number,
                "period_from": segment.period_from.isoformat(),
                "period_to": segment.period_to.isoformat(),
                "days": segment.days,
                "source_profit": str(segment.source_profit),
                "allocation_basis": segment.allocation_basis,
                "lines": [
                    {
                        "id": line.id,
                        "stakeholder": line.stakeholder_id,
                        "stakeholder_name": line.stakeholder.target_name,
                        "component_type": line.component_type,
                        "basis_amount": str(line.basis_amount),
                        "rate": str(line.rate) if line.rate is not None else None,
                        "days": line.days,
                        "amount": str(line.amount),
                        "side": line.side,
                        "explanation": line.explanation,
                    }
                    for line in segment.lines.all()
                ],
            }
            for segment in segments
        ],
    }


@transaction.atomic
def calculate_distribution_run(
    *,
    entity: Entity,
    entityfin: EntityFinancialYear,
    subentity: SubEntity | None,
    period_from,
    period_to,
    cadence: str,
    profit_source: str,
    supplied_profit: Decimal | None,
    book_adjustments: Decimal,
    balance_inputs: list[dict],
    idempotency_key: str,
    actor,
) -> CapitalDistributionRun:
    from .migration_services import assert_wave_one_activation

    fy_start = _as_date(entityfin.finstartyear)
    fy_end = _as_date(entityfin.finendyear)
    if period_from < fy_start or period_to > fy_end:
        raise ValidationError({"period": "Calculation period must be inside the selected financial year."})
    if entityfin.entity_id != entity.id or (subentity and subentity.entity_id != entity.id):
        raise ValidationError({"scope": "Financial year and branch must belong to the selected entity."})
    assert_wave_one_activation(entity=entity)

    policy_segments = _approved_policy_segments(
        entity=entity,
        entityfin=entityfin,
        subentity=subentity,
        period_from=period_from,
        period_to=period_to,
    )
    supplied_balance_rows = [
        {
            "ownership": int(row["ownership"]),
            "capital_balance": str(row.get("capital_balance", "0")),
            "drawing_balance": str(row.get("drawing_balance", "0")),
            "movements": row.get("movements", []),
            "source_references": row.get("source_references", []),
        }
        for row in balance_inputs
    ]
    has_account_mappings = CapitalDistributionAccountMapping.objects.filter(entity=entity, isactive=True).exists()
    balance_mode = "manual" if supplied_balance_rows else ("posted_ledger" if has_account_mappings else "unmapped_zero")
    request_payload = {
        "entity": entity.id,
        "entityfin": entityfin.id,
        "subentity": subentity.id if subentity else None,
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "cadence": cadence,
        "profit_source": profit_source,
        "supplied_profit": str(supplied_profit) if supplied_profit is not None else None,
        "book_adjustments": str(book_adjustments),
        "balance_mode": balance_mode,
        "balances": supplied_balance_rows,
    }
    request_hash = stable_hash(request_payload)
    existing = CapitalDistributionRun.objects.select_for_update().filter(
        entity=entity, idempotency_key=idempotency_key
    ).first()
    if existing:
        if existing.source_snapshot.get("request_hash") != request_hash:
            raise ValidationError({"idempotency_key": "This key was already used for different calculation inputs."})
        return existing

    normalized_balances = supplied_balance_rows
    if balance_mode == "posted_ledger":
        normalized_balances = collect_distribution_balances(
            policy_segments=policy_segments,
            entity=entity,
            entityfin=entityfin,
            subentity=subentity,
            period_to=period_to,
        )
    if profit_source == CapitalDistributionRun.ProfitSource.DAY_WEIGHTED:
        disabled = [
            policy.version_number
            for _, _, policy in policy_segments
            if not (policy.configuration or {}).get("allow_day_weighted", False)
        ]
        if disabled:
            raise ValidationError({
                "profit_source": "Day-weighted fallback is not enabled by policy version(s): "
                + ", ".join(str(version) for version in disabled)
                + "."
            })
    total_days = inclusive_days(period_from, period_to)
    balance_by_ownership = {int(row["ownership"]): row for row in normalized_balances}
    first_policy = policy_segments[0][2]
    run = CapitalDistributionRun.objects.create(
        entity=entity,
        entityfin=entityfin,
        subentity=subentity,
        formation_profile=first_policy.formation_profile,
        policy=first_policy,
        period_from=period_from,
        period_to=period_to,
        cadence=cadence,
        status=CapitalDistributionRun.Status.DRAFT,
        profit_source=profit_source,
        book_adjustments=money(book_adjustments),
        idempotency_key=idempotency_key,
        source_snapshot={
            "request_hash": request_hash,
            "request": request_payload,
            "balance_mode": balance_mode,
            "collected_balances": normalized_balances,
        },
        createdby=actor,
    )

    source_total = Decimal("0")
    distributable_total = Decimal("0")
    supplied_profit_allocated = Decimal("0")
    adjustment_allocated = Decimal("0")
    hash_segments = []
    snapshot_seen = set()
    for sequence, (segment_from, segment_to, policy) in enumerate(policy_segments, start=1):
        rows = list(policy.stakeholders.filter(isactive=True).select_related("ownership").order_by("sort_order", "id"))
        validate_policy(policy)
        segment_days = inclusive_days(segment_from, segment_to)
        if profit_source == CapitalDistributionRun.ProfitSource.POSTED_BOOKS:
            segment_profit, source_snapshot = _segment_book_profit(
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                period_from=segment_from,
                period_to=segment_to,
            )
            allocation_basis = "actual_segment"
        else:
            if supplied_profit is None:
                raise ValidationError({"source_profit": "A source profit is required for this calculation mode."})
            if sequence == len(policy_segments):
                segment_profit = money(supplied_profit - supplied_profit_allocated)
            else:
                segment_profit = money(supplied_profit * Decimal(segment_days) / Decimal(total_days))
                supplied_profit_allocated += segment_profit
            source_snapshot = {"source": profit_source, "supplied_profit": str(supplied_profit)}
            allocation_basis = "day_weighted"
        if sequence == len(policy_segments):
            segment_adjustment = money(book_adjustments - adjustment_allocated)
        else:
            segment_adjustment = money(book_adjustments * Decimal(segment_days) / Decimal(total_days))
            adjustment_allocated += segment_adjustment
        balances_by_stakeholder = {}
        for row in rows:
            balance = balance_by_ownership.get(row.ownership_id, {})
            balances_by_stakeholder[row.id] = balance
            if row.id not in snapshot_seen:
                snapshot_payload = {
                    "ownership": row.ownership_id,
                    "capital_balance": str(balance.get("capital_balance", "0")),
                    "drawing_balance": str(balance.get("drawing_balance", "0")),
                    "movements": balance.get("movements", []),
                    "source_references": balance.get("source_references", []),
                }
                DistributionBalanceSnapshot.objects.create(
                    run=run,
                    stakeholder=row,
                    cutoff_date=segment_to,
                    capital_balance=decimal_value(balance.get("capital_balance")),
                    drawing_balance=decimal_value(balance.get("drawing_balance")),
                    movements=balance.get("movements", []),
                    source_references=balance.get("source_references", []),
                    snapshot_hash=stable_hash(snapshot_payload),
                )
                snapshot_seen.add(row.id)
        result = calculate_segment(
            source_profit=segment_profit,
            book_adjustments=segment_adjustment,
            period_from=segment_from,
            period_to=segment_to,
            stakeholder_rows=rows,
            balances=balances_by_stakeholder,
            day_count_convention=(policy.configuration or {}).get("day_count_convention", "actual_365"),
        )
        segment = CapitalDistributionSegment.objects.create(
            run=run,
            policy=policy,
            sequence=sequence,
            period_from=segment_from,
            period_to=segment_to,
            days=segment_days,
            source_profit=result.source_profit,
            allocation_basis=allocation_basis,
            source_snapshot=source_snapshot,
        )
        for line in result.lines:
            CapitalDistributionLine.objects.create(
                run=run,
                segment=segment,
                stakeholder_id=line.stakeholder_id,
                component_type=line.component_type,
                basis_amount=line.basis_amount,
                rate=line.rate,
                days=line.days,
                amount=line.amount,
                side=line.side,
                explanation=line.explanation,
            )
        source_total += result.source_profit
        distributable_total += result.distributable_result
        hash_segments.append({
            "policy": policy.id,
            "from": segment_from.isoformat(),
            "to": segment_to.isoformat(),
            "source_profit": str(result.source_profit),
            "distributable": str(result.distributable_result),
            "lines": [line.__dict__ for line in result.lines],
        })

    run.source_profit = money(source_total)
    run.distributable_result = money(distributable_total)
    source_control = {
        "balances": normalized_balances,
        "segments": [
            {"policy": segment.policy_id, "source": segment.source_snapshot}
            for segment in run.segments.order_by("sequence")
        ],
    }
    run.source_snapshot["source_control_hash"] = stable_hash(source_control)
    run.calculation_hash = stable_hash({"request": request_payload, "segments": hash_segments})
    run.status = CapitalDistributionRun.Status.CALCULATED
    run.calculated_at = timezone.now()
    run.calculated_by = actor
    run.save(update_fields=(
        "source_profit", "distributable_result", "source_snapshot", "calculation_hash", "status",
        "calculated_at", "calculated_by", "updated_at",
    ))
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        policy=first_policy,
        run=run,
        actor=actor,
        action="run_calculated",
        correlation_id=current_correlation_id(),
        after_state={"run": run.id, "calculation_hash": run.calculation_hash, "status": run.status},
        metadata=operation_metadata(operation="run_calculated"),
    )
    return run


def serialize_account_mapping(mapping: CapitalDistributionAccountMapping) -> dict:
    def account_value(selected):
        if not selected:
            return None
        return {
            "id": selected.id,
            "name": selected.effective_accounting_name,
            "ledger": selected.ledger_id,
            "ledger_code": selected.effective_accounting_code,
        }

    return {
        "id": mapping.id,
        "entity": mapping.entity_id,
        "ownership": mapping.ownership_id,
        "ownership_name": mapping.ownership.name,
        "capital_account": account_value(mapping.capital_account),
        "current_account": account_value(mapping.current_account),
        "drawings_account": account_value(mapping.drawings_account),
        "effective_from": mapping.effective_from.isoformat() if mapping.effective_from else None,
        "effective_to": mapping.effective_to.isoformat() if mapping.effective_to else None,
        "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
    }


@transaction.atomic
def upsert_account_mapping(*, entity, ownership, capital_account, current_account, drawings_account, effective_from, effective_to, actor):
    mapping = CapitalDistributionAccountMapping.objects.select_for_update().filter(
        entity=entity,
        ownership=ownership,
        isactive=True,
    ).first()
    before = serialize_account_mapping(mapping) if mapping else {}
    if mapping is None:
        mapping = CapitalDistributionAccountMapping(entity=entity, ownership=ownership, createdby=actor)
    mapping.capital_account = capital_account
    mapping.current_account = current_account
    mapping.drawings_account = drawings_account
    mapping.effective_from = effective_from
    mapping.effective_to = effective_to
    mapping.save()
    CapitalDistributionAuditEvent.objects.create(
        entity=entity,
        actor=actor,
        action="account_mapping_saved",
        correlation_id=current_correlation_id(),
        before_state=before,
        after_state=serialize_account_mapping(mapping),
    )
    return mapping


def _current_source_control(run: CapitalDistributionRun) -> dict:
    segments = list(run.segments.select_related("policy").order_by("sequence"))
    policy_segments = [(row.period_from, row.period_to, row.policy) for row in segments]
    if run.source_snapshot.get("balance_mode") == "posted_ledger":
        balances = collect_distribution_balances(
            policy_segments=policy_segments,
            entity=run.entity,
            entityfin=run.entityfin,
            subentity=run.subentity,
            period_to=run.period_to,
        )
    else:
        balances = run.source_snapshot.get("collected_balances", [])
    source_segments = []
    for segment in segments:
        source = segment.source_snapshot
        if run.profit_source == CapitalDistributionRun.ProfitSource.POSTED_BOOKS:
            _, source = _segment_book_profit(
                entity=run.entity,
                entityfin=run.entityfin,
                subentity=run.subentity,
                period_from=segment.period_from,
                period_to=segment.period_to,
            )
        source_segments.append({"policy": segment.policy_id, "source": source})
    return {"balances": balances, "segments": source_segments}


def assert_run_sources_current(run: CapitalDistributionRun) -> None:
    captured_hash = run.source_snapshot.get("source_control_hash")
    if not captured_hash or stable_hash(_current_source_control(run)) != captured_hash:
        raise ValidationError({"source": "Underlying posted books or mapped balances changed. Recalculate the run before approval or posting."})


def _run_state(run):
    return {
        "id": run.id,
        "status": run.status,
        "calculation_hash": run.calculation_hash,
        "posting_batch": str(run.posting_batch_id) if run.posting_batch_id else None,
        "reversal_batch": str(run.reversal_batch_id) if run.reversal_batch_id else None,
    }


def _audit_run(run, actor, action, before, reason=""):
    CapitalDistributionAuditEvent.objects.create(
        entity=run.entity,
        policy=run.policy,
        run=run,
        actor=actor,
        action=action,
        correlation_id=current_correlation_id(),
        reason=reason,
        before_state=before,
        after_state=_run_state(run),
        metadata=operation_metadata(operation=action),
    )


@transaction.atomic
def submit_distribution_run(*, run, actor, expected_updated_at=None, reason=""):
    run = CapitalDistributionRun.objects.select_for_update().select_related("entity", "entityfin").get(pk=run.pk)
    assert_expected_updated_at(run, expected_updated_at)
    if run.status != CapitalDistributionRun.Status.CALCULATED:
        raise ValidationError({"status": "Only a calculated run can be submitted."})
    assert_run_sources_current(run)
    readiness = distribution_mapping_readiness(
        entity=run.entity, policy=run.policy, period_from=run.period_from, period_to=run.period_to
    )
    if not readiness["ready"]:
        raise ValidationError({"readiness": readiness["issues"]})
    overlap = CapitalDistributionRun.objects.filter(
        entity=run.entity,
        entityfin=run.entityfin,
        subentity=run.subentity,
        isactive=True,
        period_from__lte=run.period_to,
        period_to__gte=run.period_from,
        status__in=(run.Status.SUBMITTED, run.Status.APPROVED, run.Status.POSTED),
    ).exclude(pk=run.pk).exists()
    if overlap:
        raise ValidationError({"period": "Another submitted, approved, or posted run overlaps this period and scope."})
    before = _run_state(run)
    run.status = run.Status.SUBMITTED
    run.submitted_at = timezone.now()
    run.submitted_by = actor
    run.lifecycle_reason = reason
    run.save(update_fields=("status", "submitted_at", "submitted_by", "lifecycle_reason", "updated_at"))
    _audit_run(run, actor, "run_submitted", before, reason)
    return run


@transaction.atomic
def approve_distribution_run(*, run, actor, expected_updated_at=None, reason=""):
    run = CapitalDistributionRun.objects.select_for_update().select_related("entity", "entityfin").get(pk=run.pk)
    assert_expected_updated_at(run, expected_updated_at)
    if run.status != CapitalDistributionRun.Status.SUBMITTED:
        raise ValidationError({"status": "Only a submitted run can be approved."})
    if run.submitted_by_id and run.submitted_by_id == getattr(actor, "id", None):
        raise ValidationError({"approver": "The submitter cannot approve the same run."})
    assert_run_sources_current(run)
    before = _run_state(run)
    run.status = run.Status.APPROVED
    run.approved_at = timezone.now()
    run.approved_by = actor
    run.lifecycle_reason = reason
    run.save(update_fields=("status", "approved_at", "approved_by", "lifecycle_reason", "updated_at"))
    _audit_run(run, actor, "run_approved", before, reason)
    return run


@transaction.atomic
def post_distribution_run(*, run, actor, expected_updated_at=None, reason=""):
    run = CapitalDistributionRun.objects.select_for_update().select_related("entity", "entityfin").get(pk=run.pk)
    if run.status == CapitalDistributionRun.Status.POSTED:
        return run
    assert_expected_updated_at(run, expected_updated_at)
    if run.status != CapitalDistributionRun.Status.APPROVED:
        raise ValidationError({"status": "Only an approved run can be posted."})
    assert_run_sources_current(run)
    readiness = distribution_mapping_readiness(
        entity=run.entity, policy=run.policy, period_from=run.period_from, period_to=run.period_to
    )
    if not readiness["ready"]:
        raise ValidationError({"readiness": readiness["issues"]})
    before = _run_state(run)
    try:
        entry = CapitalDistributionPostingAdapter.post(run=run, user_id=getattr(actor, "id", None))
    except ValueError as exc:
        raise ValidationError({"posting": str(exc)}) from exc
    run.status = run.Status.POSTED
    run.posting_batch = entry.posting_batch
    run.posted_at = timezone.now()
    run.posted_by = actor
    run.lifecycle_reason = reason
    run.save(update_fields=("status", "posting_batch", "posted_at", "posted_by", "lifecycle_reason", "updated_at"))
    _audit_run(run, actor, "run_posted", before, reason)
    return run


@transaction.atomic
def reverse_distribution_run(*, run, actor, expected_updated_at=None, reason=""):
    run = CapitalDistributionRun.objects.select_for_update().select_related("entity", "entityfin").get(pk=run.pk)
    assert_expected_updated_at(run, expected_updated_at)
    if run.status != CapitalDistributionRun.Status.POSTED:
        raise ValidationError({"status": "Only a posted run can be reversed."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "A reversal reason is required."})
    before = _run_state(run)
    try:
        entry = CapitalDistributionPostingAdapter.reverse(run=run, user_id=getattr(actor, "id", None))
    except ValueError as exc:
        raise ValidationError({"posting": str(exc)}) from exc
    run.status = run.Status.REVERSED
    run.reversal_batch = entry.posting_batch
    run.reversed_at = timezone.now()
    run.reversed_by = actor
    run.lifecycle_reason = reason
    run.save(update_fields=("status", "reversal_batch", "reversed_at", "reversed_by", "lifecycle_reason", "updated_at"))
    _audit_run(run, actor, "run_reversed", before, reason)
    return run
