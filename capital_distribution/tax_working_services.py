from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.concurrency import assert_expected_updated_at

from .calculations import stable_hash
from .models import (
    CapitalDistributionAuditEvent,
    CapitalDistributionRun,
    CapitalDistributionTaxWorking,
    CapitalDistributionTaxWorkingLine,
    TaxPolicyVersion,
)
from .tax_services import tax_policy_state
from .tax_formulas import evaluate_statutory_formula


MONEY = Decimal("0.01")
HUNDRED = Decimal("100")
ROUNDING_MODES = {
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "down": ROUND_DOWN,
}


def _decimal(value, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid decimal value."}) from exc


def _money(value: Decimal, rounding: str) -> Decimal:
    return value.quantize(MONEY, rounding=ROUNDING_MODES.get(rounding, ROUND_HALF_UP))


def _line_source_state(line) -> dict:
    return {
        "source_line": line.id,
        "segment": line.segment_id,
        "stakeholder": line.stakeholder_id,
        "stakeholder_name": line.stakeholder.target_name,
        "component_type": line.component_type,
        "basis_amount": str(line.basis_amount),
        "rate": str(line.rate) if line.rate is not None else None,
        "days": line.days,
        "book_amount": str(line.amount),
        "side": line.side,
        "explanation": line.explanation,
        "source_references": line.source_references,
    }


def _working_line_state(line) -> dict:
    return {
        "id": line.id,
        "source_line": line.source_line_id,
        "component_type": line.component_type,
        "stakeholder_name": line.stakeholder_name,
        "book_amount": str(line.book_amount),
        "treatment": line.treatment,
        "calculated_allowable_amount": str(line.calculated_allowable_amount),
        "calculated_disallowed_amount": str(line.calculated_disallowed_amount),
        "override_allowable_amount": (
            str(line.override_allowable_amount) if line.override_allowable_amount is not None else None
        ),
        "allowable_amount": str(line.allowable_amount),
        "disallowed_amount": str(line.disallowed_amount),
        "rule_snapshot": line.rule_snapshot,
        "source_snapshot": line.source_snapshot,
        "override_reason": line.override_reason,
        "evidence_references": line.evidence_references,
        "overridden_at": line.overridden_at.isoformat() if line.overridden_at else None,
        "overridden_by": line.overridden_by_id,
    }


def tax_working_state(working, *, include_lines=True) -> dict:
    state = {
        "id": working.id,
        "entity": working.entity_id,
        "entityfinid": working.entityfin_id,
        "subentity": working.subentity_id,
        "run": working.run_id,
        "tax_policy": working.tax_policy_id,
        "period_from": working.period_from.isoformat(),
        "period_to": working.period_to.isoformat(),
        "status": working.status,
        "idempotency_key": working.idempotency_key,
        "calculation_hash": working.calculation_hash,
        "source_snapshot": working.source_snapshot,
        "policy_snapshot": working.policy_snapshot,
        "book_amount": str(working.book_amount),
        "allowable_amount": str(working.allowable_amount),
        "disallowed_amount": str(working.disallowed_amount),
        "calculated_at": working.calculated_at.isoformat() if working.calculated_at else None,
        "calculated_by": working.calculated_by_id,
        "submitted_at": working.submitted_at.isoformat() if working.submitted_at else None,
        "submitted_by": working.submitted_by_id,
        "approved_at": working.approved_at.isoformat() if working.approved_at else None,
        "approved_by": working.approved_by_id,
        "reversed_at": working.reversed_at.isoformat() if working.reversed_at else None,
        "reversed_by": working.reversed_by_id,
        "lifecycle_reason": working.lifecycle_reason,
        "created_at": working.created_at.isoformat() if working.created_at else None,
        "updated_at": working.updated_at.isoformat() if working.updated_at else None,
    }
    if include_lines:
        state["lines"] = [_working_line_state(line) for line in working.lines.all()]
    return state


def _audit(working, actor, action, *, before=None, reason="", metadata=None) -> None:
    CapitalDistributionAuditEvent.objects.create(
        entity=working.entity,
        run=working.run,
        tax_policy=working.tax_policy,
        tax_working=working,
        actor=actor,
        action=action,
        correlation_id=uuid.uuid4().hex,
        reason=reason,
        before_state=before or {},
        after_state=tax_working_state(working),
        metadata=metadata or {},
    )


def _rule_result(*, source: dict, rule: dict, rounding: str) -> tuple[Decimal, Decimal]:
    amount = _decimal(source["book_amount"], "book_amount")
    treatment = str(rule.get("treatment") or "").strip().lower()
    if treatment in {"allowed", "informational"}:
        allowable = amount
    elif treatment == "disallowed":
        allowable = Decimal("0")
    elif treatment == "capped":
        caps = []
        if rule.get("formula_code"):
            caps.append(evaluate_statutory_formula(
                source=source,
                rule=rule,
                quantum=MONEY,
                rounding_mode=ROUNDING_MODES.get(rounding, ROUND_HALF_UP),
            ))
        if rule.get("cap_amount") not in (None, ""):
            caps.append(_decimal(rule["cap_amount"], "cap_amount"))
        if rule.get("max_rate") not in (None, ""):
            basis = _decimal(source.get("basis_amount"), "basis_amount")
            caps.append(basis * _decimal(rule["max_rate"], "max_rate") / HUNDRED)
        conditions = rule.get("conditions") or {}
        if conditions.get("evaluated_cap_amount") not in (None, ""):
            caps.append(_decimal(conditions["evaluated_cap_amount"], "evaluated_cap_amount"))
        if not caps:
            formula = str(rule.get("formula_code") or "").strip()
            raise ValidationError({
                "formula_code": (
                    f"Tax formula '{formula}' has no enabled evaluator. Supply a governed evaluated_cap_amount "
                    "or a supported rate/amount cap."
                )
            })
        allowable = min([amount, *caps])
    else:
        raise ValidationError({"treatment": f"Unsupported tax treatment: {treatment}."})
    allowable = _money(max(Decimal("0"), allowable), rounding)
    amount = _money(amount, rounding)
    return allowable, _money(amount - allowable, rounding)


def _hash_payload(working) -> dict:
    return {
        "run": working.run_id,
        "run_calculation_hash": working.source_snapshot.get("run_calculation_hash"),
        "policy": working.tax_policy_id,
        "policy_version": working.policy_snapshot.get("version_number"),
        "lines": [
            {
                "source": line.source_snapshot,
                "rule": line.rule_snapshot,
                "allowable_amount": str(line.allowable_amount),
                "disallowed_amount": str(line.disallowed_amount),
                "override_allowable_amount": (
                    str(line.override_allowable_amount) if line.override_allowable_amount is not None else None
                ),
                "override_reason": line.override_reason,
                "evidence_references": line.evidence_references,
            }
            for line in working.lines.all()
        ],
    }


def _refresh_totals_and_hash(working) -> None:
    lines = list(working.lines.all())
    working.book_amount = sum((line.book_amount for line in lines), Decimal("0"))
    working.allowable_amount = sum((line.allowable_amount for line in lines), Decimal("0"))
    working.disallowed_amount = sum((line.disallowed_amount for line in lines), Decimal("0"))
    if working.book_amount != working.allowable_amount + working.disallowed_amount:
        raise ValidationError({"reconciliation": "Book amount must equal allowable plus disallowed amount."})
    working.calculation_hash = stable_hash(_hash_payload(working))
    working.save(update_fields=(
        "book_amount", "allowable_amount", "disallowed_amount", "calculation_hash", "updated_at"
    ))


@transaction.atomic
def calculate_tax_working(*, run, tax_policy, idempotency_key, actor):
    run = (
        CapitalDistributionRun.objects.select_for_update()
        .select_related("entity", "entityfin", "formation_profile")
        .prefetch_related("lines__stakeholder")
        .get(pk=run.pk)
    )
    tax_policy = TaxPolicyVersion.objects.select_for_update().get(pk=tax_policy.pk)
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValidationError({"idempotency_key": "An idempotency key is required."})
    existing = CapitalDistributionTaxWorking.objects.filter(entity=run.entity, idempotency_key=key).first()
    if existing:
        if existing.run_id != run.id or existing.tax_policy_id != tax_policy.id:
            raise ValidationError({"idempotency_key": "This key was already used for a different tax working."})
        return existing
    existing = CapitalDistributionTaxWorking.objects.filter(run=run, tax_policy=tax_policy).first()
    if existing:
        return existing
    if run.status != run.Status.POSTED:
        raise ValidationError({"run": "Tax working requires a posted appropriation run."})
    if tax_policy.status != tax_policy.Status.APPROVED:
        raise ValidationError({"tax_policy": "Tax working requires an approved tax policy."})
    if tax_policy.entity_id != run.entity_id:
        raise ValidationError({"tax_policy": "Tax policy and book run must belong to the same entity."})
    if tax_policy.entityfin_id and tax_policy.entityfin_id != run.entityfin_id:
        raise ValidationError({"tax_policy": "Tax policy financial year does not match the book run."})
    if tax_policy.formation_type != run.formation_profile.formation_type:
        raise ValidationError({"tax_policy": "Tax policy formation does not match the book run."})
    if tax_policy.effective_from > run.period_from or (
        tax_policy.effective_to and tax_policy.effective_to < run.period_to
    ):
        raise ValidationError({"tax_policy": "Tax policy must cover the complete book-run period."})

    configuration = tax_policy.configuration or {}
    rounding = configuration.get("rounding", "half_up")
    rules = {str(rule.get("component") or "").strip().lower(): rule for rule in configuration.get("rules", [])}
    source_lines = list(run.lines.all())
    if not source_lines:
        raise ValidationError({"run": "Posted book run has no appropriation lines."})
    missing = sorted({line.component_type for line in source_lines if line.component_type not in rules})
    if missing:
        raise ValidationError({"tax_policy": f"Missing tax rules for book components: {', '.join(missing)}."})

    line_sources = {line.id: _line_source_state(line) for line in source_lines}
    remuneration_lines = [
        {"source_line": line.id, "book_amount": str(line.amount)}
        for line in source_lines if line.component_type == "remuneration"
    ]
    remuneration_context = {
        "statutory_book_profit": str(run.source_profit + run.book_adjustments),
        "aggregate_book_remuneration": str(sum(
            (line.amount for line in source_lines if line.component_type == "remuneration"), Decimal("0")
        )),
        "remuneration_lines": remuneration_lines,
        "profit_source": run.profit_source,
        "source_profit": str(run.source_profit),
        "book_adjustments": str(run.book_adjustments),
    }
    for line in source_lines:
        if line.component_type == "remuneration":
            line_sources[line.id]["formula_context"] = remuneration_context

    source_snapshot = {
        "run": run.id,
        "run_status": run.status,
        "run_calculation_hash": run.calculation_hash,
        "posting_batch": str(run.posting_batch_id) if run.posting_batch_id else None,
        "lines": [line_sources[line.id] for line in source_lines],
    }
    try:
        working = CapitalDistributionTaxWorking.objects.create(
            entity=run.entity,
            entityfin=run.entityfin,
            subentity=run.subentity,
            run=run,
            tax_policy=tax_policy,
            period_from=run.period_from,
            period_to=run.period_to,
            idempotency_key=key,
            calculation_hash="pending",
            source_snapshot=source_snapshot,
            policy_snapshot=tax_policy_state(tax_policy),
            calculated_at=timezone.now(),
            calculated_by=actor,
            createdby=actor,
        )
    except IntegrityError as exc:
        raise ValidationError({"tax_working": "A tax working already exists for this book run and policy."}) from exc

    for source_line in source_lines:
        source = line_sources[source_line.id]
        rule = rules[source_line.component_type]
        allowable, disallowed = _rule_result(source=source, rule=rule, rounding=rounding)
        CapitalDistributionTaxWorkingLine.objects.create(
            working=working,
            source_line=source_line,
            component_type=source_line.component_type,
            stakeholder_name=source_line.stakeholder.target_name,
            book_amount=_money(source_line.amount, rounding),
            treatment=str(rule["treatment"]).strip().lower(),
            calculated_allowable_amount=allowable,
            calculated_disallowed_amount=disallowed,
            allowable_amount=allowable,
            disallowed_amount=disallowed,
            rule_snapshot=rule,
            source_snapshot=source,
        )
    _refresh_totals_and_hash(working)
    _audit(working, actor, "tax_working_calculated")
    return working


def _valid_evidence_references(value) -> list:
    if not isinstance(value, list) or not value:
        raise ValidationError({"evidence_references": "At least one evidence reference is required."})
    for index, reference in enumerate(value):
        if isinstance(reference, str) and reference.strip():
            continue
        if isinstance(reference, dict) and str(reference.get("reference") or "").strip():
            continue
        raise ValidationError({
            "evidence_references": f"Evidence reference {index + 1} must be a non-empty string or object reference."
        })
    return value


@transaction.atomic
def override_tax_working_line(*, line, allowable_amount, reason, evidence_references, actor, expected_updated_at=None):
    line = CapitalDistributionTaxWorkingLine.objects.select_for_update().select_related("working").get(pk=line.pk)
    working = CapitalDistributionTaxWorking.objects.select_for_update().get(pk=line.working_id)
    assert_expected_updated_at(working, expected_updated_at)
    if working.status != working.Status.CALCULATED:
        raise ValidationError({"status": "Overrides are allowed only while the tax working is calculated."})
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "An override reason is required."})
    evidence = _valid_evidence_references(evidence_references)
    allowable = _decimal(allowable_amount, "allowable_amount")
    if allowable < 0 or allowable > line.book_amount:
        raise ValidationError({"allowable_amount": "Override must be between zero and the source book amount."})
    rounding = working.policy_snapshot.get("configuration", {}).get("rounding", "half_up")
    before = tax_working_state(working)
    line.override_allowable_amount = _money(allowable, rounding)
    line.allowable_amount = line.override_allowable_amount
    line.disallowed_amount = _money(line.book_amount - line.allowable_amount, rounding)
    line.override_reason = reason
    line.evidence_references = evidence
    line.overridden_at = timezone.now()
    line.overridden_by = actor
    line.save(update_fields=(
        "override_allowable_amount", "allowable_amount", "disallowed_amount", "override_reason",
        "evidence_references", "overridden_at", "overridden_by", "updated_at",
    ))
    _refresh_totals_and_hash(working)
    _audit(working, actor, "tax_working_line_overridden", before=before, reason=reason, metadata={"line": line.id})
    return working


def reproduce_tax_working(working) -> dict:
    rounding = working.policy_snapshot.get("configuration", {}).get("rounding", "half_up")
    expected = []
    for line in working.lines.all():
        calculated_allowable, calculated_disallowed = _rule_result(
            source=line.source_snapshot,
            rule=line.rule_snapshot,
            rounding=rounding,
        )
        allowable = line.override_allowable_amount if line.override_allowable_amount is not None else calculated_allowable
        expected.append({
            "line": line.id,
            "calculated_allowable_amount": str(calculated_allowable),
            "calculated_disallowed_amount": str(calculated_disallowed),
            "allowable_amount": str(allowable),
            "disallowed_amount": str(_money(line.book_amount - allowable, rounding)),
        })
    stored = [
        {
            "line": line.id,
            "calculated_allowable_amount": str(line.calculated_allowable_amount),
            "calculated_disallowed_amount": str(line.calculated_disallowed_amount),
            "allowable_amount": str(line.allowable_amount),
            "disallowed_amount": str(line.disallowed_amount),
        }
        for line in working.lines.all()
    ]
    reproduced_hash = stable_hash(_hash_payload(working))
    return {
        "matches": expected == stored and reproduced_hash == working.calculation_hash,
        "stored_hash": working.calculation_hash,
        "reproduced_hash": reproduced_hash,
        "expected_lines": expected,
    }


def _assert_reproducible(working) -> None:
    result = reproduce_tax_working(working)
    if not result["matches"]:
        raise ValidationError({"reproduction": "Stored tax working no longer reproduces from its frozen snapshots."})


@transaction.atomic
def submit_tax_working(*, working, actor, reason="", expected_updated_at=None):
    working = CapitalDistributionTaxWorking.objects.select_for_update().select_related("run").get(pk=working.pk)
    assert_expected_updated_at(working, expected_updated_at)
    if working.status != working.Status.CALCULATED:
        raise ValidationError({"status": "Only a calculated tax working can be submitted."})
    if working.run.status != working.run.Status.POSTED:
        raise ValidationError({"run": "The source book run is no longer posted."})
    _assert_reproducible(working)
    before = tax_working_state(working)
    working.status = working.Status.SUBMITTED
    working.submitted_at = timezone.now()
    working.submitted_by = actor
    working.lifecycle_reason = str(reason or "").strip()
    working.save(update_fields=("status", "submitted_at", "submitted_by", "lifecycle_reason", "updated_at"))
    _audit(working, actor, "tax_working_submitted", before=before, reason=reason)
    return working


@transaction.atomic
def approve_tax_working(*, working, actor, reason="", expected_updated_at=None):
    working = CapitalDistributionTaxWorking.objects.select_for_update().get(pk=working.pk)
    assert_expected_updated_at(working, expected_updated_at)
    if working.status != working.Status.SUBMITTED:
        raise ValidationError({"status": "Only a submitted tax working can be approved."})
    if working.submitted_by_id == getattr(actor, "id", None):
        raise ValidationError({"approver": "The submitter cannot approve the same tax working."})
    _assert_reproducible(working)
    before = tax_working_state(working)
    working.status = working.Status.APPROVED
    working.approved_at = timezone.now()
    working.approved_by = actor
    working.lifecycle_reason = str(reason or "").strip()
    working.save(update_fields=("status", "approved_at", "approved_by", "lifecycle_reason", "updated_at"))
    _audit(working, actor, "tax_working_approved", before=before, reason=reason)
    return working


@transaction.atomic
def reverse_tax_working(*, working, actor, reason, expected_updated_at=None):
    working = CapitalDistributionTaxWorking.objects.select_for_update().get(pk=working.pk)
    assert_expected_updated_at(working, expected_updated_at)
    if working.status != working.Status.APPROVED:
        raise ValidationError({"status": "Only an approved tax working can be reversed."})
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "A reversal reason is required."})
    before = tax_working_state(working)
    working.status = working.Status.REVERSED
    working.reversed_at = timezone.now()
    working.reversed_by = actor
    working.lifecycle_reason = reason
    working.save(update_fields=("status", "reversed_at", "reversed_by", "lifecycle_reason", "updated_at"))
    _audit(working, actor, "tax_working_reversed", before=before, reason=reason)
    return working
