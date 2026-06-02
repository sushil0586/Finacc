from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from entity.models import EntityBankAccountV2
from financial.models import AccountBankDetails, account
from posting.models import EntryStatus, JournalLine

from ..models import (
    ZERO,
    BankReconciliationAuditLog,
    BankReconciliationMatch,
    BankReconciliationMatchBankLine,
    BankReconciliationMatchBookLine,
    BankReconciliationRun,
    BankStatementImport,
    BankStatementLine,
)


ACTIVE_MATCH_STATUSES = {
    BankReconciliationMatch.Status.SUGGESTED,
    BankReconciliationMatch.Status.CONFIRMED,
    BankReconciliationMatch.Status.PARTIALLY_MATCHED,
}
FINAL_MATCH_STATUSES = {
    BankReconciliationMatch.Status.CONFIRMED,
    BankReconciliationMatch.Status.PARTIALLY_MATCHED,
}
OPEN_BANK_LINE_STATUSES = {
    BankStatementLine.ReconciliationStatus.UNMATCHED,
    BankStatementLine.ReconciliationStatus.SUGGESTED,
    BankStatementLine.ReconciliationStatus.CANCELLED,
}


@dataclass
class BankBookBinding:
    account_ids: set[int]
    ledger_ids: set[int]
    metadata: dict


@dataclass
class MatchCandidate:
    journal_line: JournalLine
    confidence_score: Decimal
    reason_codes: list[str]
    match_type: str
    safe_auto_confirm: bool


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _money(value) -> Decimal:
    return Decimal(str(value or ZERO))


def _statement_amount(line: BankStatementLine) -> Decimal:
    return _money(line.credit_amount) if _money(line.credit_amount) > ZERO else _money(line.debit_amount)


def _bank_direction(line: BankStatementLine) -> str:
    return "credit" if _money(line.credit_amount) > ZERO else "debit"


def _bank_to_book_drcr(direction: str) -> bool:
    return direction == "credit"


def bank_line_signed_amount(line: BankStatementLine) -> Decimal:
    return _statement_amount(line) if _bank_direction(line) == "credit" else (_statement_amount(line) * Decimal("-1"))


def _journal_descriptor(line: JournalLine) -> str:
    parts = [
        getattr(line, "voucher_no", "") or "",
        getattr(line.entry, "voucher_no", "") or "",
        getattr(line, "description", "") or "",
        getattr(line.entry, "narration", "") or "",
    ]
    return _normalize_text(" ".join(parts))


def _reason_append(reasons: list[str], code: str):
    if code not in reasons:
        reasons.append(code)


def resolve_bank_book_binding(*, entity, bank_account: EntityBankAccountV2, metadata: dict | None = None) -> BankBookBinding:
    metadata = metadata or {}
    account_ids: set[int] = set()
    ledger_ids: set[int] = set()

    explicit_book_ledger = getattr(bank_account, "book_ledger", None)
    explicit_book_account = getattr(explicit_book_ledger, "account_profile", None) if explicit_book_ledger else None
    if explicit_book_account is not None:
        account_ids.add(explicit_book_account.id)
    if explicit_book_ledger is not None:
        ledger_ids.add(explicit_book_ledger.id)

    explicit_account_id = metadata.get("book_account_id")
    explicit_ledger_id = metadata.get("book_ledger_id")
    if explicit_account_id:
        mapped_account = account.objects.filter(id=explicit_account_id, entity=entity, isactive=True).select_related("ledger").first()
        if mapped_account is None:
            raise ValidationError({"bank_account": "Configured bank book account does not belong to the selected entity."})
        account_ids.add(mapped_account.id)
        if mapped_account.ledger_id:
            ledger_ids.add(mapped_account.ledger_id)
    if explicit_ledger_id:
        ledger_ids.add(int(explicit_ledger_id))

    details_qs = AccountBankDetails.objects.filter(entity=entity, isactive=True).select_related("account__ledger")
    direct = details_qs.filter(
        banKAcno=bank_account.account_number,
    )
    if bank_account.ifsc_code:
        direct = direct.filter(Q(ifsc__iexact=bank_account.ifsc_code) | Q(ifsc__isnull=True) | Q(ifsc=""))
    if not direct.exists():
        direct = details_qs.filter(banKAcno__endswith=bank_account.account_number[-4:])
        if bank_account.ifsc_code:
            direct = direct.filter(Q(ifsc__iexact=bank_account.ifsc_code) | Q(ifsc__isnull=True) | Q(ifsc=""))

    for detail in direct:
        if detail.account_id:
            account_ids.add(detail.account_id)
            if getattr(detail.account, "ledger_id", None):
                ledger_ids.add(detail.account.ledger_id)

    if not account_ids and not ledger_ids:
        raise ValidationError(
            {
                "bank_account": (
                    "No matching book-side bank account/ledger mapping was found for this bank account. "
                    "Map the bank account to a financial account before reconciliation."
                )
            }
        )

    return BankBookBinding(
        account_ids=account_ids,
        ledger_ids=ledger_ids,
        metadata={
            "bank_account_id": bank_account.id,
            "resolved_account_ids": sorted(account_ids),
            "resolved_ledger_ids": sorted(ledger_ids),
        },
    )


def get_or_create_run(*, statement_import: BankStatementImport, actor=None) -> BankReconciliationRun:
    run = (
        BankReconciliationRun.objects.filter(statement_import=statement_import)
        .order_by("-created_at", "-id")
        .first()
    )
    if run:
        return run
    return BankReconciliationRun.objects.create(
        entity=statement_import.entity,
        entityfin=statement_import.entityfin,
        subentity=statement_import.subentity,
        bank_account=statement_import.bank_account,
        statement_import=statement_import,
        status=BankReconciliationRun.Status.DRAFT,
        as_of_date=statement_import.statement_to or statement_import.statement_from,
        statement_opening_balance=statement_import.opening_balance,
        statement_closing_balance=statement_import.closing_balance,
        statement_line_count=statement_import.lines.count(),
        created_by=actor,
        metadata={},
    )


def bank_lines_for_run(*, run: BankReconciliationRun):
    queryset = BankStatementLine.objects.select_related("statement_import").filter(
        statement_import__entity=run.entity,
        statement_import__bank_account=run.bank_account,
        validation_status__in=[
            BankStatementLine.ValidationStatus.VALID,
            BankStatementLine.ValidationStatus.WARNING,
        ],
    )
    if run.entityfin_id:
        queryset = queryset.filter(Q(statement_import__entityfin_id=run.entityfin_id) | Q(statement_import__entityfin_id__isnull=True))
    if run.subentity_id:
        queryset = queryset.filter(Q(statement_import__subentity_id=run.subentity_id) | Q(statement_import__subentity_id__isnull=True))
    if run.as_of_date:
        queryset = queryset.filter(
            Q(txn_date__lte=run.as_of_date)
            | Q(value_date__lte=run.as_of_date)
            | Q(txn_date__isnull=True, value_date__isnull=True)
        )
    queryset = queryset.exclude(exception_status=BankStatementLine.ExceptionStatus.IGNORED)
    return queryset.order_by("txn_date", "value_date", "statement_import__statement_from", "line_no", "id")


def get_run_bank_lines(*, run: BankReconciliationRun, bank_line_ids: list[int]):
    lines = list(bank_lines_for_run(run=run).filter(id__in=bank_line_ids))
    if len(lines) != len(set(bank_line_ids)):
        raise ValidationError({"bank_line_ids": "One or more selected bank lines are not valid for this reconciliation run."})
    return lines


def build_unmatched_bank_rows(*, run: BankReconciliationRun):
    rows = []
    current_from = run.statement_import.statement_from
    for line in bank_lines_for_run(run=run).filter(
        reconciliation_status__in=OPEN_BANK_LINE_STATUSES
    )[:400]:
        rows.append(
            {
                "id": line.id,
                "line_no": line.line_no,
                "txn_date": line.txn_date,
                "value_date": line.value_date,
                "narration": line.narration,
                "reference_no": line.reference_no,
                "cheque_no": line.cheque_no,
                "debit_amount": line.debit_amount,
                "credit_amount": line.credit_amount,
                "balance": line.balance,
                "status": line.reconciliation_status,
                "exception_status": line.exception_status,
                "exception_reason": line.exception_reason,
                "statement_import_id": line.statement_import_id,
                "statement_import_code": line.statement_import.import_code,
                "is_opening_item": bool(
                    current_from
                    and line.statement_import.statement_to
                    and line.statement_import.statement_to < current_from
                ),
                "created_voucher_id": line.created_voucher_id,
            }
        )
    return rows


def _active_match_queryset():
    return BankReconciliationMatch.objects.filter(status__in=ACTIVE_MATCH_STATUSES)


def _final_match_queryset():
    return BankReconciliationMatch.objects.filter(status__in=FINAL_MATCH_STATUSES)


def _journal_line_amount(line: JournalLine) -> Decimal:
    return _money(line.amount)


def candidate_book_lines(*, run: BankReconciliationRun, statement_line: BankStatementLine, date_tolerance_days: int = 3):
    binding = resolve_bank_book_binding(entity=run.entity, bank_account=run.bank_account, metadata=run.metadata)
    txn_date = statement_line.txn_date or statement_line.value_date
    qs = JournalLine.objects.select_related("entry", "account", "ledger").filter(
        entity=run.entity,
        amount=_statement_amount(statement_line),
        drcr=_bank_to_book_drcr(_bank_direction(statement_line)),
        entry__status=EntryStatus.POSTED,
    )
    if run.entityfin_id:
        qs = qs.filter(entityfin_id=run.entityfin_id)
    if run.subentity_id:
        qs = qs.filter(subentity_id=run.subentity_id)
    if binding.account_ids and binding.ledger_ids:
        qs = qs.filter(Q(account_id__in=binding.account_ids) | Q(ledger_id__in=binding.ledger_ids))
    elif binding.account_ids:
        qs = qs.filter(account_id__in=binding.account_ids)
    else:
        qs = qs.filter(ledger_id__in=binding.ledger_ids)
    if txn_date:
        qs = qs.filter(posting_date__range=(txn_date - timedelta(days=date_tolerance_days), txn_date + timedelta(days=date_tolerance_days)))

    active_book_line_ids = set(
        BankReconciliationMatchBookLine.objects.filter(match__status__in=ACTIVE_MATCH_STATUSES)
        .exclude(match__run=run, match__status=BankReconciliationMatch.Status.SUGGESTED)
        .values_list("journal_line_id", flat=True)
    )
    if active_book_line_ids:
        qs = qs.exclude(id__in=active_book_line_ids)
    return qs.order_by("posting_date", "id")


def _score_candidate(statement_line: BankStatementLine, journal_line: JournalLine) -> MatchCandidate | None:
    reasons: list[str] = ["amount_exact"]
    confidence = Decimal("55.00")
    match_type = BankReconciliationMatch.MatchType.POSSIBLE
    safe_auto_confirm = False

    txn_date = statement_line.txn_date or statement_line.value_date
    posting_date = journal_line.posting_date
    date_gap = abs((posting_date - txn_date).days) if posting_date and txn_date else None

    descriptor = _journal_descriptor(journal_line)
    ref_text = _normalize_text(statement_line.reference_no)
    cheque_text = _normalize_text(statement_line.cheque_no)
    narration_text = _normalize_text(statement_line.narration)

    cheque_match = bool(cheque_text and cheque_text in descriptor)
    ref_match = bool(ref_text and ref_text in descriptor)
    same_date = date_gap == 0 if date_gap is not None else False
    near_date = date_gap is not None and date_gap <= 3

    if cheque_match:
        confidence += Decimal("35.00")
        _reason_append(reasons, "cheque_match")
    if ref_match:
        confidence += Decimal("30.00")
        _reason_append(reasons, "reference_match")
    if same_date:
        confidence += Decimal("15.00")
        _reason_append(reasons, "same_date")
    elif near_date:
        confidence += Decimal("10.00")
        _reason_append(reasons, "date_tolerance")

    narration_similarity = 0.0
    if narration_text and descriptor:
        narration_similarity = SequenceMatcher(None, narration_text, descriptor).ratio()
        if narration_text in descriptor or descriptor in narration_text:
            narration_similarity = max(narration_similarity, 0.90)
        if narration_similarity >= 0.85:
            confidence += Decimal("18.00")
            _reason_append(reasons, "narration_similarity_high")
        elif narration_similarity >= 0.70:
            confidence += Decimal("10.00")
            _reason_append(reasons, "narration_similarity")

    if (ref_match or cheque_match) and same_date:
        match_type = BankReconciliationMatch.MatchType.EXACT
        confidence = max(confidence, Decimal("98.00"))
        safe_auto_confirm = True
        _reason_append(reasons, "safe_exact")
    elif ref_match or cheque_match:
        match_type = BankReconciliationMatch.MatchType.SUGGESTED
        confidence = max(confidence, Decimal("88.00"))
    elif same_date:
        match_type = BankReconciliationMatch.MatchType.SUGGESTED
        confidence = max(confidence, Decimal("82.00"))
    elif near_date:
        match_type = BankReconciliationMatch.MatchType.SUGGESTED
        confidence = max(confidence, Decimal("74.00"))
    elif narration_similarity >= 0.70:
        match_type = BankReconciliationMatch.MatchType.POSSIBLE
        confidence = max(confidence, Decimal("62.00"))

    if confidence < Decimal("55.00"):
        return None

    return MatchCandidate(
        journal_line=journal_line,
        confidence_score=min(confidence, Decimal("100.00")),
        reason_codes=reasons,
        match_type=match_type,
        safe_auto_confirm=safe_auto_confirm,
    )


def _bank_line_active_matches(bank_line_ids):
    return BankReconciliationMatch.objects.filter(
        bank_lines__statement_line_id__in=bank_line_ids,
        status__in=ACTIVE_MATCH_STATUSES,
    ).distinct()


def _book_line_active_matches(journal_line_ids):
    return BankReconciliationMatch.objects.filter(
        book_lines__journal_line_id__in=journal_line_ids,
        status__in=ACTIVE_MATCH_STATUSES,
    ).distinct()


def _cancel_existing_suggestions(*, run: BankReconciliationRun, bank_line_ids=None, journal_line_ids=None, actor=None, action="auto_suggestion_replaced", audit_context: dict | None = None):
    matches = BankReconciliationMatch.objects.filter(run=run, status=BankReconciliationMatch.Status.SUGGESTED)
    if bank_line_ids:
        matches = matches.filter(bank_lines__statement_line_id__in=list(bank_line_ids))
    if journal_line_ids:
        matches = matches.filter(book_lines__journal_line_id__in=list(journal_line_ids))
    matches = matches.distinct()
    for match in matches:
        old_status = match.status
        match.status = BankReconciliationMatch.Status.CANCELLED
        match.save(update_fields=["status", "updated_at"])
        _audit(
            action=action,
            run=run,
            statement_import=run.statement_import,
            match=match,
            actor=actor,
            old_status=old_status,
            new_status=match.status,
            metadata={"auto_cancelled": True, "request_context": audit_context or {}},
        )


def _recalculate_line_statuses_for_lines(statement_lines):
    for line in statement_lines:
        active_matches = list(
            BankReconciliationMatch.objects.filter(bank_lines__statement_line=line, status__in=ACTIVE_MATCH_STATUSES).distinct()
        )
        new_status = BankStatementLine.ReconciliationStatus.UNMATCHED
        if any(match.status == BankReconciliationMatch.Status.CONFIRMED for match in active_matches):
            new_status = BankStatementLine.ReconciliationStatus.CONFIRMED
        elif any(match.status == BankReconciliationMatch.Status.PARTIALLY_MATCHED for match in active_matches):
            new_status = BankStatementLine.ReconciliationStatus.PARTIALLY_MATCHED
        elif any(match.status == BankReconciliationMatch.Status.SUGGESTED for match in active_matches):
            new_status = BankStatementLine.ReconciliationStatus.SUGGESTED
        if line.reconciliation_status != new_status:
            line.reconciliation_status = new_status
            line.save(update_fields=["reconciliation_status", "updated_at"])


def _recalculate_run_metrics(run: BankReconciliationRun):
    import_lines = bank_lines_for_run(run=run)
    run.statement_line_count = import_lines.count()
    run.matched_line_count = import_lines.filter(reconciliation_status=BankStatementLine.ReconciliationStatus.CONFIRMED).count()
    run.suggested_line_count = import_lines.filter(reconciliation_status=BankStatementLine.ReconciliationStatus.SUGGESTED).count()
    run.exception_line_count = import_lines.exclude(exception_status=BankStatementLine.ExceptionStatus.NONE).count()
    run.matched_amount = (
        BankReconciliationMatch.objects.filter(run=run, status__in=FINAL_MATCH_STATUSES).aggregate(total=Sum("matched_amount"))["total"] or ZERO
    )
    run.unmatched_bank_amount = sum(
        (
            _statement_amount(line)
            for line in import_lines.filter(reconciliation_status=BankStatementLine.ReconciliationStatus.UNMATCHED)
            .exclude(exception_status=BankStatementLine.ExceptionStatus.IGNORED)
        ),
        ZERO,
    )
    run.unmatched_book_amount = sum(
        (row["amount"] for row in build_unmatched_book_rows(run=run)),
        ZERO,
    )
    run.difference_amount = run.statement_closing_balance - run.book_closing_balance
    if run.matched_line_count and run.unmatched_bank_amount == ZERO and run.unmatched_book_amount == ZERO:
        run.status = BankReconciliationRun.Status.RECONCILED
    elif run.suggested_line_count:
        run.status = BankReconciliationRun.Status.REVIEW
    elif run.matched_line_count:
        run.status = BankReconciliationRun.Status.MATCHING
    run.save(
        update_fields=[
            "statement_line_count",
            "matched_line_count",
            "suggested_line_count",
            "exception_line_count",
            "matched_amount",
            "unmatched_bank_amount",
            "unmatched_book_amount",
            "difference_amount",
            "status",
            "updated_at",
        ]
    )


def _audit(*, action: str, run: BankReconciliationRun, statement_import, match, actor, old_status: str | None, new_status: str | None, metadata: dict | None = None):
    BankReconciliationAuditLog.objects.create(
        run=run,
        statement_import=statement_import,
        match=match,
        action=action,
        object_type="match" if match else "run",
        object_id=str(match.id if match else run.id),
        payload={
            "old_status": old_status,
            "new_status": new_status,
            **(metadata or {}),
        },
        actor=actor,
    )


def _create_match(
    *,
    run: BankReconciliationRun,
    bank_lines: list[BankStatementLine],
    book_lines: list[JournalLine],
    status_value: str,
    match_type: str,
    match_kind: str,
    confidence_score: Decimal,
    reason_codes: list[str],
    notes: str = "",
    actor=None,
    action: str = "manual_match_confirmed",
    audit_context: dict | None = None,
):
    bank_total = sum((_statement_amount(line) for line in bank_lines), ZERO)
    book_total = sum((_journal_line_amount(line) for line in book_lines), ZERO)
    matched_amount = min(bank_total, book_total)
    difference_amount = bank_total - book_total
    match = BankReconciliationMatch.objects.create(
        run=run,
        status=status_value,
        match_type=match_type,
        match_kind=match_kind,
        confidence_score=confidence_score,
        bank_total_amount=bank_total,
        book_total_amount=book_total,
        matched_amount=matched_amount,
        difference_amount=difference_amount,
        reason_codes=reason_codes,
        notes=notes,
        suggested_by=actor if status_value == BankReconciliationMatch.Status.SUGGESTED else None,
        confirmed_by=actor if status_value in FINAL_MATCH_STATUSES else None,
        confirmed_at=timezone.now() if status_value in FINAL_MATCH_STATUSES else None,
    )

    remaining = matched_amount
    for order, line in enumerate(bank_lines, start=1):
        amount = min(_statement_amount(line), remaining)
        if amount <= ZERO and order > 1:
            continue
        BankReconciliationMatchBankLine.objects.create(
            match=match,
            statement_line=line,
            allocated_amount=amount,
            allocation_order=order,
            is_primary=(order == 1),
        )
        remaining -= amount
        if remaining <= ZERO:
            break

    remaining = matched_amount
    for order, line in enumerate(book_lines, start=1):
        amount = min(_journal_line_amount(line), remaining)
        if amount <= ZERO and order > 1:
            continue
        BankReconciliationMatchBookLine.objects.create(
            match=match,
            entry=line.entry,
            journal_line=line,
            allocated_amount=amount,
            allocation_order=order,
            is_primary=(order == 1),
        )
        remaining -= amount
        if remaining <= ZERO:
            break

    _recalculate_line_statuses_for_lines(bank_lines)
    _recalculate_run_metrics(run)
    _audit(
        action=action,
        run=run,
        statement_import=run.statement_import,
        match=match,
        actor=actor,
        old_status=None,
        new_status=status_value,
        metadata={
            "reason_codes": reason_codes,
            "match_type": match_type,
            "match_kind": match_kind,
            "bank_line_ids": [line.id for line in bank_lines],
            "journal_line_ids": [line.id for line in book_lines],
            "old_values": {"match_status": None},
            "new_values": {
                "match_status": status_value,
                "matched_amount": str(match.matched_amount),
                "difference_amount": str(match.difference_amount),
            },
            "request_context": audit_context or {},
        },
    )
    return match


@transaction.atomic
def auto_match_import(*, statement_import: BankStatementImport, actor=None, audit_context: dict | None = None):
    if statement_import.status not in {BankStatementImport.Status.VALIDATED, BankStatementImport.Status.READY}:
        raise ValidationError({"statement_import": "Validate the statement import before running auto-match."})
    run = get_or_create_run(statement_import=statement_import, actor=actor)
    _cancel_existing_suggestions(run=run, actor=actor, action="auto_suggestions_reset", audit_context=audit_context)

    results = []
    lines = bank_lines_for_run(run=run)

    for line in lines:
        if line.reconciliation_status in {
            BankStatementLine.ReconciliationStatus.CONFIRMED,
            BankStatementLine.ReconciliationStatus.PARTIALLY_MATCHED,
        }:
            continue
        if line.exception_status in {
            BankStatementLine.ExceptionStatus.IGNORED,
            BankStatementLine.ExceptionStatus.HOLD_FOR_REVIEW,
            BankStatementLine.ExceptionStatus.BANK_ERROR,
        }:
            continue

        existing_final = BankReconciliationMatch.objects.filter(
            run=run,
            bank_lines__statement_line=line,
            status__in=FINAL_MATCH_STATUSES,
        ).exists()
        if existing_final:
            continue

        candidates = []
        for journal_line in candidate_book_lines(run=run, statement_line=line):
            candidate = _score_candidate(line, journal_line)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item.confidence_score, item.journal_line.posting_date or timezone.localdate()), reverse=True)
        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        can_auto_confirm = best.safe_auto_confirm and (second is None or (best.confidence_score - second.confidence_score) >= Decimal("5.00"))
        status_value = BankReconciliationMatch.Status.CONFIRMED if can_auto_confirm else BankReconciliationMatch.Status.SUGGESTED
        match = _create_match(
            run=run,
            bank_lines=[line],
            book_lines=[best.journal_line],
            status_value=status_value,
            match_type=best.match_type,
            match_kind=BankReconciliationMatch.MatchKind.AUTO,
            confidence_score=best.confidence_score,
            reason_codes=best.reason_codes,
            notes="Auto-generated by bank reconciliation engine.",
            actor=actor,
            action="auto_suggestion_created" if status_value == BankReconciliationMatch.Status.SUGGESTED else "auto_match_confirmed",
            audit_context=audit_context,
        )
        results.append(
            {
                "match_id": match.id,
                "status": match.status,
                "match_type": match.match_type,
                "confidence_score": str(match.confidence_score),
                "reason_codes": match.reason_codes,
                "statement_line_id": line.id,
                "journal_line_id": best.journal_line.id,
            }
        )
    return run, results


def _ensure_bank_lines_available(*, run: BankReconciliationRun, bank_lines: list[BankStatementLine], actor=None, audit_context: dict | None = None):
    active_final = _bank_line_active_matches([line.id for line in bank_lines]).filter(status__in=FINAL_MATCH_STATUSES)
    if active_final.exists():
        raise ValidationError({"bank_lines": "One or more selected bank lines are already part of an active confirmed/partial match."})
    _cancel_existing_suggestions(run=run, bank_line_ids=[line.id for line in bank_lines], actor=actor, action="suggestion_cancelled_for_manual_match", audit_context=audit_context)


def _ensure_book_lines_available(*, run: BankReconciliationRun, journal_lines: list[JournalLine], actor=None, audit_context: dict | None = None):
    active_final = _book_line_active_matches([line.id for line in journal_lines]).filter(status__in=FINAL_MATCH_STATUSES)
    if active_final.exists():
        raise ValidationError({"journal_lines": "One or more selected book lines are already part of an active confirmed/partial match."})
    _cancel_existing_suggestions(run=run, journal_line_ids=[line.id for line in journal_lines], actor=actor, action="suggestion_cancelled_for_manual_match", audit_context=audit_context)


def _validate_journal_lines_for_run(*, run: BankReconciliationRun, journal_lines: list[JournalLine], bank_lines: list[BankStatementLine]):
    binding = resolve_bank_book_binding(entity=run.entity, bank_account=run.bank_account, metadata=run.metadata)
    allowed_account_ids = binding.account_ids
    allowed_ledger_ids = binding.ledger_ids
    expected_directions = {_bank_to_book_drcr(_bank_direction(line)) for line in bank_lines}
    if len(expected_directions) != 1:
        raise ValidationError({"bank_lines": "Selected bank lines must have the same debit/credit direction for one match."})
    expected_direction = list(expected_directions)[0]
    for line in journal_lines:
        if line.entity_id != run.entity_id:
            raise ValidationError({"journal_lines": "Selected book line belongs to a different entity."})
        if run.entityfin_id and line.entityfin_id != run.entityfin_id:
            raise ValidationError({"journal_lines": "Selected book line belongs to a different financial year."})
        if run.subentity_id and line.subentity_id != run.subentity_id:
            raise ValidationError({"journal_lines": "Selected book line belongs to a different subentity."})
        if line.drcr != expected_direction:
            raise ValidationError({"journal_lines": "Selected book line has the wrong debit/credit direction for the bank lines."})
        if allowed_account_ids or allowed_ledger_ids:
            if not (
                (line.account_id and line.account_id in allowed_account_ids)
                or (line.ledger_id and line.ledger_id in allowed_ledger_ids)
            ):
                raise ValidationError({"journal_lines": "Selected book line does not belong to the resolved bank ledger/account for this reconciliation run."})


@transaction.atomic
def confirm_manual_match(*, run: BankReconciliationRun, bank_lines: list[BankStatementLine], journal_lines: list[JournalLine], actor=None, notes: str = "", audit_context: dict | None = None):
    _ensure_bank_lines_available(run=run, bank_lines=bank_lines, actor=actor, audit_context=audit_context)
    _ensure_book_lines_available(run=run, journal_lines=journal_lines, actor=actor, audit_context=audit_context)
    _validate_journal_lines_for_run(run=run, journal_lines=journal_lines, bank_lines=bank_lines)

    bank_total = sum((_statement_amount(line) for line in bank_lines), ZERO)
    book_total = sum((_journal_line_amount(line) for line in journal_lines), ZERO)
    partial = bank_total != book_total

    if len(bank_lines) == 1 and len(journal_lines) == 1:
        kind = BankReconciliationMatch.MatchKind.ONE_TO_ONE
    elif len(bank_lines) == 1 and len(journal_lines) > 1:
        kind = BankReconciliationMatch.MatchKind.ONE_TO_MANY
    elif len(bank_lines) > 1 and len(journal_lines) == 1:
        kind = BankReconciliationMatch.MatchKind.MANY_TO_ONE
    else:
        kind = BankReconciliationMatch.MatchKind.MANY_TO_MANY
    status_value = BankReconciliationMatch.Status.PARTIALLY_MATCHED if partial else BankReconciliationMatch.Status.CONFIRMED
    return _create_match(
        run=run,
        bank_lines=bank_lines,
        book_lines=journal_lines,
        status_value=status_value,
        match_type=BankReconciliationMatch.MatchType.EXACT if not partial else BankReconciliationMatch.MatchType.SUGGESTED,
        match_kind=BankReconciliationMatch.MatchKind.PARTIAL if partial else kind,
        confidence_score=Decimal("100.00") if not partial else Decimal("90.00"),
        reason_codes=["manual_match", "partial_difference"] if partial else ["manual_match"],
        notes=notes,
        actor=actor,
        action="partial_match_confirmed" if partial else ("group_match_confirmed" if len(bank_lines) + len(journal_lines) > 2 else "manual_match_confirmed"),
        audit_context=audit_context,
    )


@transaction.atomic
def unmatch(*, match: BankReconciliationMatch, actor=None, notes: str = "", audit_context: dict | None = None):
    old_status = match.status
    match.status = BankReconciliationMatch.Status.CANCELLED
    if notes:
        match.notes = notes
    match.save(update_fields=["status", "notes", "updated_at"])
    bank_lines = [rel.statement_line for rel in match.bank_lines.select_related("statement_line")]
    _recalculate_line_statuses_for_lines(bank_lines)
    _recalculate_run_metrics(match.run)
    _audit(
        action="unmatched",
        run=match.run,
        statement_import=match.run.statement_import,
        match=match,
        actor=actor,
        old_status=old_status,
        new_status=match.status,
        metadata={
            "notes": notes,
            "old_values": {"match_status": old_status},
            "new_values": {"match_status": match.status},
            "request_context": audit_context or {},
        },
    )
    return match


def build_unmatched_book_rows(*, run: BankReconciliationRun):
    binding = resolve_bank_book_binding(entity=run.entity, bank_account=run.bank_account, metadata=run.metadata)
    qs = JournalLine.objects.select_related("entry", "account", "ledger").filter(entity=run.entity, entry__status=EntryStatus.POSTED)
    if run.entityfin_id:
        qs = qs.filter(entityfin_id=run.entityfin_id)
    if run.subentity_id:
        qs = qs.filter(subentity_id=run.subentity_id)
    if binding.account_ids and binding.ledger_ids:
        qs = qs.filter(Q(account_id__in=binding.account_ids) | Q(ledger_id__in=binding.ledger_ids))
    elif binding.account_ids:
        qs = qs.filter(account_id__in=binding.account_ids)
    else:
        qs = qs.filter(ledger_id__in=binding.ledger_ids)
    if run.as_of_date:
        qs = qs.filter(posting_date__lte=run.as_of_date)
    matched_ids = set(
        BankReconciliationMatchBookLine.objects.filter(match__status__in=ACTIVE_MATCH_STATUSES).values_list("journal_line_id", flat=True)
    )
    if matched_ids:
        qs = qs.exclude(id__in=matched_ids)
    rows = []
    current_from = run.statement_import.statement_from
    for line in qs.order_by("posting_date", "id")[:400]:
        rows.append(
            {
                "journal_line_id": line.id,
                "entry_id": line.entry_id,
                "voucher_no": line.voucher_no or getattr(line.entry, "voucher_no", ""),
                "posting_date": line.posting_date,
                "drcr": "dr" if line.drcr else "cr",
                "amount": _journal_line_amount(line),
                "description": line.description or getattr(line.entry, "narration", ""),
                "reference": getattr(line.entry, "narration", "") or "",
                "is_opening_item": bool(current_from and line.posting_date and line.posting_date < current_from),
            }
        )
    return rows


def build_workspace_payload(
    *,
    statement_import: BankStatementImport,
    run: BankReconciliationRun | None = None,
    filters: dict | None = None,
):
    filters = filters or {}
    run = run or BankReconciliationRun.objects.filter(statement_import=statement_import).order_by("-created_at", "-id").first()
    bank_lines = bank_lines_for_run(run=run) if run else statement_import.lines.all().order_by("txn_date", "line_no", "id")
    if filters.get("date_from"):
        bank_lines = bank_lines.filter(Q(txn_date__gte=filters["date_from"]) | Q(value_date__gte=filters["date_from"]))
    if filters.get("date_to"):
        bank_lines = bank_lines.filter(Q(txn_date__lte=filters["date_to"]) | Q(value_date__lte=filters["date_to"]))
    if filters.get("reference"):
        bank_lines = bank_lines.filter(Q(reference_no__icontains=filters["reference"]) | Q(cheque_no__icontains=filters["reference"]))
    if filters.get("narration"):
        bank_lines = bank_lines.filter(narration__icontains=filters["narration"])
    if filters.get("status"):
        bank_lines = bank_lines.filter(reconciliation_status=filters["status"])
    if filters.get("amount") is not None:
        bank_lines = bank_lines.filter(Q(debit_amount=filters["amount"]) | Q(credit_amount=filters["amount"]))

    unmatched_bank = build_unmatched_bank_rows(run=run) if run else [
        {
            "id": line.id,
            "line_no": line.line_no,
            "txn_date": line.txn_date,
            "value_date": line.value_date,
            "narration": line.narration,
            "reference_no": line.reference_no,
            "cheque_no": line.cheque_no,
            "debit_amount": line.debit_amount,
            "credit_amount": line.credit_amount,
            "balance": line.balance,
            "status": line.reconciliation_status,
            "exception_status": line.exception_status,
            "exception_reason": line.exception_reason,
            "statement_import_id": line.statement_import_id,
            "statement_import_code": statement_import.import_code,
            "is_opening_item": False,
            "created_voucher_id": line.created_voucher_id,
        }
        for line in bank_lines.filter(reconciliation_status=BankStatementLine.ReconciliationStatus.UNMATCHED)[:200]
    ]

    suggested_matches = []
    confirmed_matches = []
    counts_by_status = {}
    unmatched_book_rows = []
    if run:
        matches = run.matches.prefetch_related("bank_lines__statement_line", "book_lines__journal_line").all()
        if filters.get("status"):
            matches = matches.filter(status=filters["status"])
        for key in [
            BankReconciliationMatch.Status.SUGGESTED,
            BankReconciliationMatch.Status.CONFIRMED,
            BankReconciliationMatch.Status.PARTIALLY_MATCHED,
            BankReconciliationMatch.Status.UNMATCHED,
            BankReconciliationMatch.Status.CANCELLED,
        ]:
            counts_by_status[key] = run.matches.filter(status=key).count()
        for match in matches.order_by("-created_at", "-id")[:200]:
            row = {
                "match_id": match.id,
                "status": match.status,
                "match_type": match.match_type,
                "match_kind": match.match_kind,
                "confidence_score": match.confidence_score,
                "matched_amount": match.matched_amount,
                "difference_amount": match.difference_amount,
                "reason_codes": match.reason_codes,
                "bank_line_ids": [rel.statement_line_id for rel in match.bank_lines.all()],
                "journal_line_ids": [rel.journal_line_id for rel in match.book_lines.all()],
            }
            if match.status == BankReconciliationMatch.Status.SUGGESTED:
                suggested_matches.append(row)
            elif match.status in FINAL_MATCH_STATUSES:
                confirmed_matches.append(row)
        unmatched_book_rows = build_unmatched_book_rows(run=run)
    else:
        counts_by_status = {
            "suggested": 0,
            "confirmed": 0,
            "partially_matched": 0,
            "unmatched": bank_lines.filter(reconciliation_status=BankStatementLine.ReconciliationStatus.UNMATCHED).count(),
            "cancelled": 0,
        }
    return {
        "import": {
            "id": statement_import.id,
            "import_code": statement_import.import_code,
            "status": statement_import.status,
            "statement_from": statement_import.statement_from,
            "statement_to": statement_import.statement_to,
            "opening_balance": statement_import.opening_balance,
            "closing_balance": statement_import.closing_balance,
        },
        "run": {
            "id": run.id,
            "run_code": run.run_code,
            "status": run.status,
            "as_of_date": run.as_of_date,
        } if run else None,
        "counts_by_status": counts_by_status,
        "unmatched_bank_lines": unmatched_bank,
        "unmatched_book_lines": unmatched_book_rows,
        "suggested_matches": suggested_matches,
        "confirmed_matches": confirmed_matches,
    }
