from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from core.concurrency import assert_expected_updated_at
from entity.models import Entity

from .models import (
    CapitalDistributionAuditEvent,
    CapitalDistributionLine,
    EntityFormationProfile,
    TaxPolicyVersion,
    WAVE_ONE_FORMATIONS,
)
from .tax_formulas import CAPITAL_INTEREST_FORMULA, REMUNERATION_FORMULA


ALLOWED_CONFIGURATION_KEYS = {"currency", "rounding", "rules", "metadata"}
ALLOWED_RULE_KEYS = {
    "component",
    "treatment",
    "max_rate",
    "cap_amount",
    "formula_code",
    "conditions",
    "notes",
}
ALLOWED_TREATMENTS = {"allowed", "disallowed", "capped", "informational"}
ALLOWED_ROUNDING = {"half_up", "half_even", "down"}


def _normal_code(value) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _decimal(value, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "Enter a valid decimal value."})


def tax_policy_state(policy: TaxPolicyVersion) -> dict:
    return {
        "id": policy.id,
        "entity": policy.entity_id,
        "entityfinid": policy.entityfin_id,
        "formation_profile": policy.formation_profile_id,
        "formation_type": policy.formation_type,
        "tax_type": policy.tax_type,
        "policy_code": policy.policy_code,
        "version_number": policy.version_number,
        "status": policy.status,
        "jurisdiction_country": policy.jurisdiction_country,
        "jurisdiction_state": policy.jurisdiction_state,
        "effective_from": policy.effective_from.isoformat(),
        "effective_to": policy.effective_to.isoformat() if policy.effective_to else None,
        "statutory_reference": policy.statutory_reference,
        "source_url": policy.source_url,
        "source_published_on": policy.source_published_on.isoformat() if policy.source_published_on else None,
        "configuration": policy.configuration,
        "schema_version": policy.schema_version,
        "notes": policy.notes,
        "submitted_at": policy.submitted_at.isoformat() if policy.submitted_at else None,
        "submitted_by": policy.submitted_by_id,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
        "approved_by": policy.approved_by_id,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def _audit(policy, actor, action, *, before=None, reason="") -> None:
    CapitalDistributionAuditEvent.objects.create(
        entity=policy.entity,
        tax_policy=policy,
        actor=actor,
        action=action,
        correlation_id=uuid.uuid4().hex,
        reason=reason,
        before_state=before or {},
        after_state=tax_policy_state(policy),
    )


def validate_tax_policy(
    policy: TaxPolicyVersion,
    *,
    require_complete: bool = False,
    enforce_approved_overlap: bool = False,
) -> None:
    errors = {}
    configuration = policy.configuration or {}
    if not policy.policy_code:
        errors["policy_code"] = "A stable tax policy code is required."
    if len(policy.jurisdiction_country or "") != 2 or not policy.jurisdiction_country.isalpha():
        errors["jurisdiction_country"] = "Jurisdiction country must be a two-letter ISO code."
    if not isinstance(configuration, dict):
        raise ValidationError({"configuration": "Tax policy configuration must be an object."})

    unknown = sorted(set(configuration) - ALLOWED_CONFIGURATION_KEYS)
    if unknown:
        errors["configuration"] = f"Unsupported tax policy settings: {', '.join(unknown)}."

    currency = str(configuration.get("currency") or "INR").upper()
    if len(currency) != 3 or not currency.isalpha():
        errors["currency"] = "Currency must be a three-letter ISO code."
    if configuration.get("rounding", "half_up") not in ALLOWED_ROUNDING:
        errors["rounding"] = "Rounding must be half_up, half_even, or down."

    rules = configuration.get("rules", [])
    if not isinstance(rules, list):
        errors["rules"] = "Tax policy rules must be a list."
        rules = []
    if require_complete and not rules:
        errors["rules"] = "At least one tax treatment rule is required."

    seen_components = set()
    supported_components = set(CapitalDistributionLine.Component.values)
    for index, rule in enumerate(rules):
        key = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors[key] = "Each tax treatment rule must be an object."
            continue
        unknown_rule_keys = sorted(set(rule) - ALLOWED_RULE_KEYS)
        if unknown_rule_keys:
            errors[key] = f"Unsupported rule settings: {', '.join(unknown_rule_keys)}."
            continue
        component = _normal_code(rule.get("component"))
        treatment = _normal_code(rule.get("treatment"))
        if component not in supported_components:
            errors[f"{key}.component"] = "Select a supported appropriation component."
        elif component in seen_components:
            errors[f"{key}.component"] = "Each component can have only one tax treatment rule."
        else:
            seen_components.add(component)
        if treatment not in ALLOWED_TREATMENTS:
            errors[f"{key}.treatment"] = "Treatment must be allowed, disallowed, capped, or informational."
        if "max_rate" in rule and rule["max_rate"] is not None:
            rate = _decimal(rule["max_rate"], f"{key}.max_rate")
            if rate < 0 or rate > 100:
                errors[f"{key}.max_rate"] = "Maximum rate must be between 0 and 100."
        if "cap_amount" in rule and rule["cap_amount"] is not None:
            cap = _decimal(rule["cap_amount"], f"{key}.cap_amount")
            if cap < 0:
                errors[f"{key}.cap_amount"] = "Cap amount cannot be negative."
        if treatment == "capped" and not any(
            rule.get(field) not in (None, "") for field in ("max_rate", "cap_amount", "formula_code")
        ):
            errors[key] = "A capped rule requires a maximum rate, cap amount, or formula code."
        if rule.get("conditions") is not None and not isinstance(rule["conditions"], dict):
            errors[f"{key}.conditions"] = "Rule conditions must be an object."
        if require_complete and rule.get("formula_code") == REMUNERATION_FORMULA:
            conditions = rule.get("conditions") or {}
            if component != CapitalDistributionLine.Component.REMUNERATION:
                errors[f"{key}.formula_code"] = "The partnership remuneration formula requires remuneration."
            elif conditions.get("deed_authorized") is not True or conditions.get("working_partners_only") is not True:
                errors[f"{key}.conditions"] = (
                    "Confirm deed authorization and that remuneration is limited to working partners."
                )
        if require_complete and rule.get("formula_code") == CAPITAL_INTEREST_FORMULA:
            conditions = rule.get("conditions") or {}
            if component != CapitalDistributionLine.Component.CAPITAL_INTEREST:
                errors[f"{key}.formula_code"] = "The partnership interest formula requires capital interest."
            elif conditions.get("deed_authorized") is not True:
                errors[f"{key}.conditions"] = "Confirm that partner interest is authorized by the deed."

    if require_complete:
        if policy.formation_type not in WAVE_ONE_FORMATIONS:
            errors["formation_type"] = "Tax working is enabled only for Wave 1 formations."
        if policy.formation_profile.status != EntityFormationProfile.Status.VERIFIED:
            errors["formation_profile"] = "A verified formation profile is required."
        if not policy.statutory_reference:
            errors["statutory_reference"] = "A statutory section, notification, or circular reference is required."

    if enforce_approved_overlap:
        overlaps = TaxPolicyVersion.objects.filter(
            entity=policy.entity,
            policy_code=policy.policy_code,
            jurisdiction_country=policy.jurisdiction_country,
            jurisdiction_state=policy.jurisdiction_state,
            formation_type=policy.formation_type,
            tax_type=policy.tax_type,
            status=TaxPolicyVersion.Status.APPROVED,
            isactive=True,
        ).exclude(pk=policy.pk).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=policy.effective_from)
        )
        if policy.effective_to:
            overlaps = overlaps.filter(effective_from__lte=policy.effective_to)
        if overlaps.exists():
            errors["effective_from"] = "Policy period overlaps an approved tax policy for this scope."

    if errors:
        raise ValidationError(errors)


@transaction.atomic
def create_tax_policy(*, entity: Entity, formation_profile: EntityFormationProfile, payload: dict, actor) -> TaxPolicyVersion:
    payload = dict(payload)
    EntityFormationProfile.objects.select_for_update().get(pk=formation_profile.pk)
    if formation_profile.entity_id != entity.id:
        raise ValidationError({"formation_profile": "Formation profile must belong to the selected entity."})
    if formation_profile.status != EntityFormationProfile.Status.VERIFIED:
        raise ValidationError({"formation_profile": "A verified formation profile is required."})

    policy_code = _normal_code(payload.pop("policy_code"))
    country = str(payload.pop("jurisdiction_country", "IN") or "IN").strip().upper()
    state = str(payload.pop("jurisdiction_state", "") or "").strip().upper()
    version = (
        TaxPolicyVersion.objects.select_for_update()
        .filter(
            entity=entity,
            policy_code=policy_code,
            jurisdiction_country=country,
            jurisdiction_state=state,
        )
        .aggregate(value=Max("version_number"))["value"]
        or 0
    ) + 1
    policy = TaxPolicyVersion.objects.create(
        entity=entity,
        formation_profile=formation_profile,
        formation_type=formation_profile.formation_type,
        policy_code=policy_code,
        jurisdiction_country=country,
        jurisdiction_state=state,
        version_number=version,
        createdby=actor,
        **payload,
    )
    validate_tax_policy(policy)
    _audit(policy, actor, "tax_policy_created")
    return policy


@transaction.atomic
def update_draft_tax_policy(*, policy: TaxPolicyVersion, payload: dict, actor, expected_updated_at=None) -> TaxPolicyVersion:
    policy = TaxPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != TaxPolicyVersion.Status.DRAFT:
        raise ValidationError({"status": "Only a draft tax policy can be edited."})
    before = tax_policy_state(policy)
    for field in (
        "entityfin",
        "tax_type",
        "effective_from",
        "effective_to",
        "statutory_reference",
        "source_url",
        "source_published_on",
        "configuration",
        "schema_version",
        "notes",
    ):
        if field in payload:
            setattr(policy, field, payload[field])
    policy.save()
    validate_tax_policy(policy)
    _audit(policy, actor, "tax_policy_updated", before=before)
    return policy


@transaction.atomic
def submit_tax_policy(*, policy, actor, reason="", expected_updated_at=None) -> TaxPolicyVersion:
    policy = TaxPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != TaxPolicyVersion.Status.DRAFT:
        raise ValidationError({"status": "Only a draft tax policy can be submitted."})
    validate_tax_policy(policy, require_complete=True)
    before = tax_policy_state(policy)
    policy.status = TaxPolicyVersion.Status.SUBMITTED
    policy.submitted_at = timezone.now()
    policy.submitted_by = actor
    policy.save(update_fields=("status", "submitted_at", "submitted_by", "updated_at"))
    _audit(policy, actor, "tax_policy_submitted", before=before, reason=reason)
    return policy


@transaction.atomic
def approve_tax_policy(*, policy, actor, reason="", expected_updated_at=None) -> TaxPolicyVersion:
    policy = TaxPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != TaxPolicyVersion.Status.SUBMITTED:
        raise ValidationError({"status": "Only a submitted tax policy can be approved."})
    if policy.submitted_by_id == getattr(actor, "id", None):
        raise ValidationError({"approved_by": "The maker cannot approve their own tax policy."})
    validate_tax_policy(policy, require_complete=True, enforce_approved_overlap=True)
    before = tax_policy_state(policy)
    policy.status = TaxPolicyVersion.Status.APPROVED
    policy.approved_at = timezone.now()
    policy.approved_by = actor
    policy.save(update_fields=("status", "approved_at", "approved_by", "updated_at"))
    _audit(policy, actor, "tax_policy_approved", before=before, reason=reason)
    return policy


@transaction.atomic
def reject_tax_policy(*, policy, actor, reason, expected_updated_at=None) -> TaxPolicyVersion:
    policy = TaxPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != TaxPolicyVersion.Status.SUBMITTED:
        raise ValidationError({"status": "Only a submitted tax policy can be rejected."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "A rejection reason is required."})
    before = tax_policy_state(policy)
    policy.status = TaxPolicyVersion.Status.REJECTED
    policy.save(update_fields=("status", "updated_at"))
    _audit(policy, actor, "tax_policy_rejected", before=before, reason=reason)
    return policy


@transaction.atomic
def supersede_tax_policy(*, policy, actor, reason, expected_updated_at=None) -> TaxPolicyVersion:
    policy = TaxPolicyVersion.objects.select_for_update().get(pk=policy.pk)
    assert_expected_updated_at(policy, expected_updated_at)
    if policy.status != TaxPolicyVersion.Status.APPROVED:
        raise ValidationError({"status": "Only an approved tax policy can be superseded."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "A supersession reason is required."})
    before = tax_policy_state(policy)
    policy.status = TaxPolicyVersion.Status.SUPERSEDED
    policy.save(update_fields=("status", "updated_at"))
    _audit(policy, actor, "tax_policy_superseded", before=before, reason=reason)
    return policy
