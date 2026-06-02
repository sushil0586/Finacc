from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from financial.models import FinancialCodeSeries, FinancialCodeSeriesAudit, FinancialMasterRule


PARTY_MANAGED = "party_managed"
LEDGER_ONLY = "ledger_only"


def normalize_party_type(value):
    party_type = str(value or "").strip()
    if not party_type:
        return ""
    return next(
        (choice for choice, _label in FinancialMasterRule._meta.get_field("party_type").choices if choice.lower() == party_type.lower()),
        party_type,
    )


def _rule_match_score(*, rule, partytype="", account_type_id=None, debit_head_id=None, credit_head_id=None):
    score = 0
    normalized_partytype = normalize_party_type(partytype)

    if rule.party_type:
        if rule.party_type != normalized_partytype:
            return None
        score += 1
    if rule.account_type_id:
        if rule.account_type_id != account_type_id:
            return None
        score += 2
    if rule.debit_head_id:
        if rule.debit_head_id != debit_head_id:
            return None
        score += 4
    if rule.credit_head_id:
        if rule.credit_head_id != credit_head_id:
            return None
        score += 8
    return score


def resolve_financial_master_rule(*, entity=None, template_code=None, partytype="", account_type_id=None, debit_head_id=None, credit_head_id=None):
    filters = Q(isactive=True)
    entity_id = getattr(entity, "id", entity)
    if entity_id is not None:
        filters &= Q(entity_id=entity_id) | Q(entity__isnull=True)
    elif template_code:
        filters &= Q(template_code=template_code) | Q(template_code__isnull=True)

    candidates = (
        FinancialMasterRule.objects.select_related(
            "entity",
            "account_type",
            "debit_head",
            "credit_head",
            "suggested_account_type",
            "suggested_debit_head",
            "suggested_credit_head",
        )
        .filter(filters)
        .order_by("priority", "id")
    )
    best_rule = None
    best_tuple = None
    for rule in candidates:
        match_score = _rule_match_score(
            rule=rule,
            partytype=partytype,
            account_type_id=account_type_id,
            debit_head_id=debit_head_id,
            credit_head_id=credit_head_id,
        )
        if match_score is None:
            continue
        scope_weight = 0 if entity_id is not None and rule.entity_id == entity_id else 1
        candidate_tuple = (scope_weight, rule.priority, -match_score, rule.id)
        if best_tuple is None or candidate_tuple < best_tuple:
            best_tuple = candidate_tuple
            best_rule = rule
    return best_rule


def resolve_management_mode(*, entity=None, template_code=None, partytype="", account_type_id=None, debit_head_id=None, credit_head_id=None, fallback=None):
    rule = resolve_financial_master_rule(
        entity=entity,
        template_code=template_code,
        partytype=partytype,
        account_type_id=account_type_id,
        debit_head_id=debit_head_id,
        credit_head_id=credit_head_id,
    )
    if rule:
        return rule.management_mode
    return fallback


def resolve_series_rule(*, entity=None, template_code=None, partytype="", account_type_id=None, debit_head_id=None, credit_head_id=None):
    filters = Q(isactive=True)
    entity_id = getattr(entity, "id", entity)
    if entity_id is not None:
        filters &= Q(entity_id=entity_id) | Q(entity__isnull=True)
    elif template_code:
        filters &= Q(template_code=template_code) | Q(template_code__isnull=True)

    candidates = FinancialCodeSeries.objects.filter(filters).order_by("priority", "id")
    best_series = None
    best_tuple = None
    normalized_partytype = normalize_party_type(partytype)
    for series in candidates:
        score = 0
        if series.party_type:
            if series.party_type != normalized_partytype:
                continue
            score += 1
        if series.account_type_id:
            if series.account_type_id != account_type_id:
                continue
            score += 2
        if series.debit_head_id:
            if series.debit_head_id != debit_head_id:
                continue
            score += 4
        if series.credit_head_id:
            if series.credit_head_id != credit_head_id:
                continue
            score += 8
        scope_weight = 0 if entity_id is not None and series.entity_id == entity_id else 1
        candidate_tuple = (scope_weight, series.priority, -score, series.id)
        if best_tuple is None or candidate_tuple < best_tuple:
            best_tuple = candidate_tuple
            best_series = series
    return best_series


@transaction.atomic
def allocate_from_series(*, entity, ledger=None, account=None, allocated_by=None, partytype="", account_type_id=None, debit_head_id=None, credit_head_id=None, allocation_reason="create"):
    series = resolve_series_rule(
        entity=entity,
        partytype=partytype,
        account_type_id=account_type_id,
        debit_head_id=debit_head_id,
        credit_head_id=credit_head_id,
    )
    if not series:
        return None

    locked_series = FinancialCodeSeries.objects.select_for_update().get(pk=series.pk)
    code = locked_series.next_code
    if code > locked_series.range_end:
        raise ValueError(f"Code series {locked_series.series_key} is exhausted.")

    locked_series.next_code = code + locked_series.increment_step
    locked_series.save(update_fields=["next_code"])
    FinancialCodeSeriesAudit.objects.create(
        entity_id=getattr(entity, "id", entity),
        series=locked_series,
        allocated_code=code,
        ledger=ledger,
        account=account,
        allocated_by=allocated_by,
        allocation_reason=allocation_reason,
    )
    return code
