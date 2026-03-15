from __future__ import annotations

from posting.adapters.payroll_adapter import PayrollPostingAdapter
from payroll.models import PayrollRun


class PayrollPostingService:
    """
    Payroll owns the workflow gate; posting owns accounting persistence.
    """

    @staticmethod
    def post_run(run: PayrollRun, *, user_id: int):
        return PayrollPostingAdapter.post_payroll_run(run=run, user_id=user_id)
