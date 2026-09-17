from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from financial.models import account

from ..models import ZERO, BankReconciliationAuditLog, BankReconciliationRun, BankStatementLine
from .matching import _bank_direction, _statement_amount, get_run_bank_lines, unmatched_bank_lines_for_run


AUTO_POSTING_SUGGESTION_KEY = "treasury_auto_posting_suggestion"


BANK_CHARGE_TERMS = ("bank charge", "charges", "bank fee", "commission", "sms charge", "debit card fee")
INTEREST_CREDIT_TERMS = ("interest credit", "interest cr", "int cr", "bank interest", "savings interest")
INTEREST_DEBIT_TERMS = ("interest debit", "interest dr", "int dr", "loan interest")


def suggestion_from_metadata(line: BankStatementLine) -> dict:
    suggestion = (line.metadata or {}).get(AUTO_POSTING_SUGGESTION_KEY) or {}
    return {
        "suggested_voucher_kind": suggestion.get("voucher_kind") or "",
        "suggested_counterpart_account_id": suggestion.get("counterpart_account_id"),
        "suggested_counterpart_account_name": suggestion.get("counterpart_account_name") or "",
        "suggestion_confidence": suggestion.get("confidence_score") or "",
        "suggestion_reason": suggestion.get("reason") or "",
        "suggestion_status": suggestion.get("status") or "",
    }


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _find_account_by_keywords(*, run: BankReconciliationRun, keywords: tuple[str, ...]):
    qs = account.objects.filter(entity=run.entity, isactive=True).select_related("ledger").order_by("id")
    for keyword in keywords:
        row = qs.filter(accountname__icontains=keyword).first()
        if row:
            return row
        row = qs.filter(ledger__name__icontains=keyword).first()
        if row:
            return row
    return None


def _resolve_configured_account(*, run: BankReconciliationRun, account_id: int | None, field_name: str):
    if account_id in (None, ""):
        return None
    row = account.objects.filter(id=account_id, entity=run.entity, isactive=True).select_related("ledger").first()
    if row is None:
        raise ValidationError({field_name: "Account is not valid for this entity."})
    return row


def _resolve_rule_accounts(*, run: BankReconciliationRun, mappings: dict) -> dict:
    return {
        "bank_charges": _resolve_configured_account(
            run=run,
            account_id=mappings.get("bank_charges_account_id"),
            field_name="bank_charges_account_id",
        )
        or _find_account_by_keywords(run=run, keywords=("bank charges", "bank charge")),
        "interest_received": _resolve_configured_account(
            run=run,
            account_id=mappings.get("interest_income_account_id"),
            field_name="interest_income_account_id",
        )
        or _find_account_by_keywords(run=run, keywords=("interest income", "interest received")),
        "interest_paid": _resolve_configured_account(
            run=run,
            account_id=mappings.get("interest_expense_account_id"),
            field_name="interest_expense_account_id",
        )
        or _find_account_by_keywords(run=run, keywords=("interest expense", "interest paid")),
        "suspense_entry": _resolve_configured_account(
            run=run,
            account_id=mappings.get("suspense_account_id"),
            field_name="suspense_account_id",
        ),
    }


def _make_suggestion(*, line: BankStatementLine, voucher_kind: str, counterpart, confidence: Decimal, reason: str, rule_code: str) -> dict:
    return {
        "status": "suggested",
        "voucher_kind": voucher_kind,
        "counterpart_account_id": counterpart.id if counterpart else None,
        "counterpart_account_name": counterpart.accountname if counterpart else "",
        "confidence_score": str(confidence),
        "reason": reason,
        "rule_code": rule_code,
        "review_required": True,
        "direct_post_allowed": False,
        "amount": str(_statement_amount(line)),
        "direction": _bank_direction(line),
    }


def classify_bank_line_for_auto_posting(*, run: BankReconciliationRun, line: BankStatementLine, accounts: dict) -> dict | None:
    if line.created_voucher_id:
        return None
    if line.reconciliation_status not in {
        BankStatementLine.ReconciliationStatus.UNMATCHED,
        BankStatementLine.ReconciliationStatus.SUGGESTED,
        BankStatementLine.ReconciliationStatus.CANCELLED,
    }:
        return None
    amount = _statement_amount(line)
    if amount <= ZERO:
        return None
    text = _normalize_text(f"{line.narration} {line.reference_no} {line.cheque_no}")
    direction = _bank_direction(line)

    if direction == "debit" and any(term in text for term in BANK_CHARGE_TERMS) and accounts.get("bank_charges"):
        return _make_suggestion(
            line=line,
            voucher_kind="bank_charges",
            counterpart=accounts["bank_charges"],
            confidence=Decimal("90.00"),
            reason="Narration looks like bank charges; review and create a bank voucher if correct.",
            rule_code="bank_charge_keyword_debit",
        )
    if direction == "credit" and any(term in text for term in INTEREST_CREDIT_TERMS) and accounts.get("interest_received"):
        return _make_suggestion(
            line=line,
            voucher_kind="interest_received",
            counterpart=accounts["interest_received"],
            confidence=Decimal("88.00"),
            reason="Narration looks like bank interest income; review and create a bank voucher if correct.",
            rule_code="interest_credit_keyword",
        )
    if direction == "debit" and any(term in text for term in INTEREST_DEBIT_TERMS) and accounts.get("interest_paid"):
        return _make_suggestion(
            line=line,
            voucher_kind="interest_paid",
            counterpart=accounts["interest_paid"],
            confidence=Decimal("84.00"),
            reason="Narration looks like bank interest paid; review and create a bank voucher if correct.",
            rule_code="interest_debit_keyword",
        )
    if accounts.get("suspense_entry"):
        return _make_suggestion(
            line=line,
            voucher_kind="suspense_entry",
            counterpart=accounts["suspense_entry"],
            confidence=Decimal("50.00"),
            reason="No strong rule matched. Park as suspense only after review.",
            rule_code="fallback_suspense_review",
        )
    return None


def _audit_suggestion(*, run: BankReconciliationRun, line: BankStatementLine, actor, suggestion: dict, audit_context: dict | None):
    BankReconciliationAuditLog.objects.create(
        run=run,
        statement_import=run.statement_import,
        action="auto_posting_suggestion_created",
        object_type="statement_line",
        object_id=str(line.id),
        payload={
            "suggestion": suggestion,
            **(audit_context or {}),
        },
        actor=actor,
    )


@transaction.atomic
def suggest_auto_posting_rules(
    *,
    run: BankReconciliationRun,
    actor,
    bank_line_ids: list[int] | None = None,
    mappings: dict | None = None,
    limit: int = 200,
    audit_context: dict | None = None,
) -> dict:
    mappings = mappings or {}
    accounts = _resolve_rule_accounts(run=run, mappings=mappings)
    if bank_line_ids:
        bank_lines = get_run_bank_lines(run=run, bank_line_ids=bank_line_ids)
    else:
        bank_lines = list(unmatched_bank_lines_for_run(run=run).select_related("statement_import").order_by("txn_date", "line_no", "id")[:limit])

    suggestions = []
    skipped_count = 0
    for line in bank_lines:
        suggestion = classify_bank_line_for_auto_posting(run=run, line=line, accounts=accounts)
        if not suggestion:
            skipped_count += 1
            continue
        metadata = dict(line.metadata or {})
        metadata[AUTO_POSTING_SUGGESTION_KEY] = suggestion
        line.metadata = metadata
        line.save(update_fields=["metadata"])
        _audit_suggestion(run=run, line=line, actor=actor, suggestion=suggestion, audit_context=audit_context)
        suggestions.append({"bank_line_id": line.id, "line_no": line.line_no, **suggestion})

    return {
        "run_id": run.id,
        "run_code": run.run_code,
        "suggested_count": len(suggestions),
        "skipped_count": skipped_count,
        "review_required": True,
        "direct_post_allowed": False,
        "suggestions": suggestions,
    }
