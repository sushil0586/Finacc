from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from ..models import BankReconciliationAuditLog, BankReconciliationMatch, BankReconciliationRun, BankStatementLine
from .matching import (
    ACTIVE_MATCH_STATUSES,
    FINAL_MATCH_STATUSES,
    _cancel_existing_suggestions,
    get_run_bank_lines,
    _recalculate_run_metrics,
)


EXCEPTION_ACTION_TO_STATUS = {
    "mark_as_bank_error": BankStatementLine.ExceptionStatus.BANK_ERROR,
    "mark_as_book_error": BankStatementLine.ExceptionStatus.BOOK_ERROR,
    "ignore": BankStatementLine.ExceptionStatus.IGNORED,
    "hold_for_review": BankStatementLine.ExceptionStatus.HOLD_FOR_REVIEW,
    "mark_as_pending_clearance": BankStatementLine.ExceptionStatus.PENDING_CLEARANCE,
    "clear_exception": BankStatementLine.ExceptionStatus.NONE,
}


def _audit(*, run: BankReconciliationRun, bank_line: BankStatementLine, actor, action: str, old_status: str, new_status: str, reason: str, audit_context: dict | None = None):
    BankReconciliationAuditLog.objects.create(
        run=run,
        statement_import=run.statement_import,
        action=action,
        object_type="statement_line",
        object_id=str(bank_line.id),
        payload={
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
            "old_values": {
                "exception_status": old_status,
            },
            "new_values": {
                "exception_status": new_status,
                "exception_reason": reason,
                "reconciliation_status": bank_line.reconciliation_status,
            },
            "request_context": audit_context or {},
        },
        actor=actor,
    )


@transaction.atomic
def apply_exception_action(*, run: BankReconciliationRun, bank_line_id: int, action: str, reason: str, actor, audit_context: dict | None = None):
    if action not in EXCEPTION_ACTION_TO_STATUS:
        raise ValidationError({"action": "Unsupported exception action."})
    bank_line = get_run_bank_lines(run=run, bank_line_ids=[bank_line_id])[0]
    active_final = BankReconciliationMatch.objects.filter(
        run=run,
        bank_lines__statement_line=bank_line,
        status__in=FINAL_MATCH_STATUSES,
    ).exists()
    if active_final:
        raise ValidationError({"bank_line_id": "Exception action cannot be applied to a bank line that is already finally matched."})

    _cancel_existing_suggestions(run=run, bank_line_ids=[bank_line.id], actor=actor, action="suggestion_cancelled_for_exception_action")
    old_status = bank_line.exception_status
    bank_line.exception_status = EXCEPTION_ACTION_TO_STATUS[action]
    cleaned_reason = (reason or "").strip()
    bank_line.exception_reason = "" if action == "clear_exception" else cleaned_reason
    bank_line.metadata = {
        **(bank_line.metadata or {}),
        "exception_action": action,
    }
    if action == "ignore":
        bank_line.reconciliation_status = BankStatementLine.ReconciliationStatus.CANCELLED
    elif action == "clear_exception" and bank_line.reconciliation_status == BankStatementLine.ReconciliationStatus.CANCELLED:
        bank_line.reconciliation_status = BankStatementLine.ReconciliationStatus.UNMATCHED
    elif bank_line.reconciliation_status == BankStatementLine.ReconciliationStatus.CANCELLED:
        bank_line.reconciliation_status = BankStatementLine.ReconciliationStatus.UNMATCHED
    bank_line.save(
        update_fields=[
            "exception_status",
            "exception_reason",
            "reconciliation_status",
            "metadata",
            "updated_at",
        ]
    )
    _audit(
        run=run,
        bank_line=bank_line,
        actor=actor,
        action=action,
        old_status=old_status,
        new_status=bank_line.exception_status,
        reason=bank_line.exception_reason,
        audit_context=audit_context,
    )
    _recalculate_run_metrics(run)
    return bank_line
