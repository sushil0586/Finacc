from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from payroll.models import PayrollRun, PayrollRunActionLog

User = get_user_model()


class PayrollRunHardeningService:
    """
    Centralizes immutability, workflow logging, and payment-state updates.
    """

    @staticmethod
    def assert_mutable(run: PayrollRun) -> None:
        if run.is_immutable:
            raise ValueError("This payroll run is immutable. Create a correction or reversal instead.")

    @staticmethod
    def log_action(
        run: PayrollRun,
        *,
        action: str,
        user_id: int | None,
        old_status: str | None = None,
        new_status: str | None = None,
        old_payment_status: str | None = None,
        new_payment_status: str | None = None,
        reason_code: str = "",
        comment: str = "",
        payload: dict | None = None,
    ) -> None:
        actor = User.objects.filter(id=user_id).only("id", "username", "email", "first_name", "last_name").first() if user_id else None
        actor_name = (
            actor.get_full_name() if actor and hasattr(actor, "get_full_name") and actor.get_full_name()
            else getattr(actor, "username", "")
            or getattr(actor, "email", "")
        ) if actor else ""
        audit_payload = {
            "run_id": run.id,
            "run_reference": run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
            "entity_id": run.entity_id,
            "entityfinid_id": run.entityfinid_id,
            "subentity_id": run.subentity_id,
            "actor_id": user_id,
            "actor_name": actor_name or None,
            "logged_at": timezone.now().isoformat(),
        }
        if run.post_reference:
            audit_payload["posting_reference"] = run.post_reference
        if run.posted_entry_id:
            audit_payload["posting_entry_id"] = run.posted_entry_id
        if run.payment_batch_ref:
            audit_payload["payment_batch_ref"] = run.payment_batch_ref
        if run.reversal_reason:
            audit_payload["reversal_reason"] = run.reversal_reason
        if payload:
            audit_payload.update(payload)
        PayrollRunActionLog.objects.create(
            payroll_run=run,
            action=action,
            old_status=old_status or run.status,
            new_status=new_status or run.status,
            old_payment_status=old_payment_status or run.payment_status,
            new_payment_status=new_payment_status or run.payment_status,
            acted_by_id=user_id,
            reason_code=reason_code,
            comment=comment,
            payload=audit_payload,
        )

    @classmethod
    @transaction.atomic
    def freeze_run(cls, run: PayrollRun, *, user_id: int | None) -> None:
        run.locked_by_id = user_id
        run.locked_at = timezone.now()
        run.is_immutable = True
        run.save(update_fields=["locked_by", "locked_at", "is_immutable"])
        run.employee_runs.update(is_frozen=True)
        run.employee_runs.all().update(payment_status=run.payment_status)
        for row in run.employee_runs.prefetch_related("components"):
            row.components.update(is_frozen=True)

    @classmethod
    @transaction.atomic
    def handoff_payment(cls, run: PayrollRun, *, user_id: int, batch_ref: str, payload: dict | None = None) -> PayrollRun:
        if run.status != PayrollRun.Status.POSTED:
            raise ValueError("Only posted payroll runs can be handed off to payments.")
        old_payment_status = run.payment_status
        run.payment_status = PayrollRun.PaymentStatus.HANDED_OFF
        run.payment_batch_ref = batch_ref
        run.payment_handoff_payload = payload or {}
        run.payment_handed_off_at = timezone.now()
        run.save(
            update_fields=[
                "payment_status",
                "payment_batch_ref",
                "payment_handoff_payload",
                "payment_handed_off_at",
            ]
        )
        run.employee_runs.update(payment_status=run.payment_status)
        cls.log_action(
            run,
            action=PayrollRunActionLog.Action.PAYMENT_HANDED_OFF,
            user_id=user_id,
            old_payment_status=old_payment_status,
            new_payment_status=run.payment_status,
            payload=payload or {},
        )
        return run

    @classmethod
    @transaction.atomic
    def reconcile_payment(cls, run: PayrollRun, *, user_id: int, payment_status: str, comment: str = "") -> PayrollRun:
        old_payment_status = run.payment_status
        run.payment_status = payment_status
        if payment_status == PayrollRun.PaymentStatus.RECONCILED:
            run.payment_reconciled_at = timezone.now()
        run.save(update_fields=["payment_status", "payment_reconciled_at"])
        run.employee_runs.update(payment_status=payment_status)
        action = (
            PayrollRunActionLog.Action.DISBURSED
            if payment_status == PayrollRun.PaymentStatus.DISBURSED
            else PayrollRunActionLog.Action.PAYMENT_FAILED
            if payment_status == PayrollRun.PaymentStatus.FAILED
            else PayrollRunActionLog.Action.RECONCILED
        )
        cls.log_action(
            run,
            action=action,
            user_id=user_id,
            old_payment_status=old_payment_status,
            new_payment_status=payment_status,
            comment=comment,
        )
        return run
