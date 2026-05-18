from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from django.db import transaction

from payroll.models import PayrollLedgerPolicy, PayrollRun
from payroll.services.payroll_posting_finalization_service import PayrollPostingFinalizationService
from posting.common.journal_descriptions import payroll_prefix
from posting.models import TxnType
from posting.services.posting_service import JLInput, PostingService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollPostingAdapter:
    """
    Converts an approved payroll run into normalized posting journal lines.

    Payroll remains the owner of run calculation and approval. Posting remains
    the owner of accounting truth and journal persistence.
    """

    @staticmethod
    def _policy_for_run(run: PayrollRun) -> PayrollLedgerPolicy:
        if run.ledger_policy_version_id:
            return run.ledger_policy_version
        return PayrollLedgerPolicy.objects.get(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            is_active=True,
        )

    @staticmethod
    def _aggregate_lines(run: PayrollRun, policy: PayrollLedgerPolicy) -> List[JLInput]:
        preview = PayrollPostingFinalizationService.preview_run(run)
        PayrollPostingFinalizationService._raise_for_blocking_issues(preview)
        return preview["posting"]["jl_inputs"]

    @staticmethod
    @transaction.atomic
    def post_payroll_run(*, run: PayrollRun, user_id: int):
        policy = PayrollPostingAdapter._policy_for_run(run)
        posting_service = PostingService(
            entity_id=run.entity_id,
            entityfin_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            user_id=user_id,
        )
        return posting_service.post(
            txn_type=TxnType.PAYROLL,
            txn_id=run.id,
            voucher_no=run.run_number or (str(run.doc_no) if run.doc_no else None),
            voucher_date=run.payroll_period.period_end,
            posting_date=run.posting_date,
            narration=payroll_prefix(run),
            jl_inputs=PayrollPostingAdapter._aggregate_lines(run, policy),
            im_inputs=[],
            mark_posted=True,
        )
