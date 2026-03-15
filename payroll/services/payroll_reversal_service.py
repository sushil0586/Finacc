from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from payroll.models import PayrollRun, PayrollRunActionLog
from payroll.services.payroll_posting_service import PayrollPostingService
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService


class PayrollReversalService:
    """
    Build explicit reversal lineage instead of mutating posted payroll runs.
    """

    @classmethod
    @transaction.atomic
    def reverse_run(cls, run: PayrollRun, *, user_id: int, reason: str) -> PayrollRun:
        if run.status != PayrollRun.Status.POSTED:
            raise ValueError("Only posted payroll runs can be reversed.")
        if run.reversal_runs.exists():
            raise ValueError("This payroll run already has a reversal run.")

        reversal = PayrollRun.objects.create(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            payroll_period_id=run.payroll_period_id,
            run_type=PayrollRun.RunType.ADJUSTMENT,
            posting_date=timezone.localdate(),
            payout_date=run.payout_date,
            status=PayrollRun.Status.APPROVED,
            payment_status=PayrollRun.PaymentStatus.NOT_READY,
            employee_count=run.employee_count,
            gross_amount=run.gross_amount,
            deduction_amount=run.deduction_amount,
            employer_contribution_amount=run.employer_contribution_amount,
            reimbursement_amount=run.reimbursement_amount,
            net_pay_amount=run.net_pay_amount,
            config_snapshot=run.config_snapshot,
            ledger_policy_version_id=run.ledger_policy_version_id,
            statutory_policy_version_ref=run.statutory_policy_version_ref,
            correction_of_run=None,
            reversed_run=run,
            reversal_reason=reason,
            created_by_id=user_id,
            approved_by_id=user_id,
            approved_at=timezone.now(),
            status_reason_code="REVERSAL",
            status_comment=reason,
            is_immutable=True,
        )

        entry = PayrollPostingService.post_run(reversal, user_id=user_id)
        reversal.status = PayrollRun.Status.POSTED
        reversal.posted_by_id = user_id
        reversal.posted_at = timezone.now()
        reversal.posted_entry_id = entry.id
        reversal.post_reference = entry.voucher_no or ""
        reversal.reversal_posting_entry_id = entry.id
        reversal.save(
            update_fields=[
                "status",
                "posted_by",
                "posted_at",
                "posted_entry_id",
                "post_reference",
                "reversal_posting_entry_id",
            ]
        )

        old_status = run.status
        run.status = PayrollRun.Status.REVERSED
        run.reversed_by_id = user_id
        run.reversed_at = timezone.now()
        run.reversal_reason = reason
        run.save(update_fields=["status", "reversed_by", "reversed_at", "reversal_reason"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.REVERSED,
            user_id=user_id,
            old_status=old_status,
            new_status=run.status,
            comment=reason,
            payload={"reversal_run_id": reversal.id},
        )
        return reversal
