from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import BankReconciliationAuditLog, BankReconciliationRun
from .matching import _recalculate_run_metrics


RUN_ACTION_TARGET_STATUS = {
    "mark_review": BankReconciliationRun.Status.REVIEW,
    "mark_reconciled": BankReconciliationRun.Status.RECONCILED,
    "lock_run": BankReconciliationRun.Status.LOCKED,
    "unlock_run": BankReconciliationRun.Status.REVIEW,
}


def ensure_run_mutable(*, run: BankReconciliationRun):
    if run.status == BankReconciliationRun.Status.LOCKED:
        raise ValidationError(
            {
                "run_id": (
                    f"Run {run.run_code} is locked. Unlock it before applying further reconciliation, voucher, or exception actions."
                )
            }
        )


def _audit(*, run: BankReconciliationRun, actor, action: str, old_status: str, new_status: str, notes: str, audit_context: dict | None = None):
    BankReconciliationAuditLog.objects.create(
        run=run,
        statement_import=run.statement_import,
        action=action,
        object_type="reconciliation_run",
        object_id=str(run.id),
        payload={
            "old_status": old_status,
            "new_status": new_status,
            "notes": notes,
            "old_values": {
                "status": old_status,
                "locked_by_id": run.locked_by_id,
                "locked_at": run.locked_at.isoformat() if run.locked_at else None,
            },
            "new_values": {
                "status": new_status,
                "locked_by_id": run.locked_by_id,
                "locked_at": run.locked_at.isoformat() if run.locked_at else None,
            },
            "request_context": audit_context or {},
        },
        actor=actor,
    )


@transaction.atomic
def apply_run_action(*, run: BankReconciliationRun, action: str, actor, notes: str = "", audit_context: dict | None = None):
    if action not in RUN_ACTION_TARGET_STATUS:
        raise ValidationError({"action": "Unsupported run action."})

    _recalculate_run_metrics(run)
    old_status = run.status

    if action == "mark_reconciled":
        if run.unmatched_bank_amount != 0 or run.unmatched_book_amount != 0 or run.suggested_line_count != 0:
            raise ValidationError(
                {
                    "action": (
                        "Run cannot be marked reconciled while unmatched bank amounts, unmatched book amounts, or suggested matches still remain."
                    )
                }
            )
    if action == "lock_run":
        run.locked_by = actor
        run.locked_at = timezone.now()
    elif action == "unlock_run":
        run.locked_by = None
        run.locked_at = None

    run.status = RUN_ACTION_TARGET_STATUS[action]
    if notes.strip():
        run.notes = notes.strip()
    run.save(update_fields=["status", "locked_by", "locked_at", "notes", "updated_at"])
    _audit(
        run=run,
        actor=actor,
        action=action,
        old_status=old_status,
        new_status=run.status,
        notes=notes.strip(),
        audit_context=audit_context,
    )
    return run
