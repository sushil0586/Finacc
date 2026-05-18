from __future__ import annotations

from posting.adapters.payroll_adapter import PayrollPostingAdapter
from payroll.models import FnFSettlement, PayrollRun
from payroll.services.payroll_posting_finalization_service import PayrollPostingFinalizationService


class PayrollPostingService:
    """
    Payroll owns the workflow gate; posting owns accounting persistence.
    """

    @staticmethod
    def post_run(run: PayrollRun, *, user_id: int):
        return PayrollPostingAdapter.post_payroll_run(run=run, user_id=user_id)

    @staticmethod
    def preview_run(run: PayrollRun) -> dict:
        return PayrollPostingFinalizationService.preview_run(run)

    @staticmethod
    def validate_run(run: PayrollRun) -> dict:
        return PayrollPostingFinalizationService.validate_run(run)

    @staticmethod
    def posting_status_for_run(run: PayrollRun) -> dict:
        return PayrollPostingFinalizationService.posting_status_for_run(run)

    @staticmethod
    def preview_fnf(settlement: FnFSettlement) -> dict:
        return PayrollPostingFinalizationService.preview_fnf(settlement)

    @staticmethod
    def validate_fnf(settlement: FnFSettlement) -> dict:
        return PayrollPostingFinalizationService.validate_fnf(settlement)

    @staticmethod
    def post_fnf(settlement: FnFSettlement, *, user_id: int):
        return PayrollPostingFinalizationService.post_fnf(settlement, user_id=user_id)

    @staticmethod
    def posting_status_for_fnf(settlement: FnFSettlement) -> dict:
        return PayrollPostingFinalizationService.posting_status_for_fnf(settlement)
