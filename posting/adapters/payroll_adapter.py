from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from django.db import transaction

from payroll.models import PayrollLedgerPolicy, PayrollRun
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
        debits: Dict[int, Decimal] = {}
        credits: Dict[int, Decimal] = {}
        is_reversal = bool(run.reversed_run_id)

        for employee_row in run.employee_runs.select_related("employee_profile").prefetch_related("components"):
            for component_row in employee_row.components.all():
                component = component_row.component
                posting_map = getattr(component_row, "component_posting_version", None)
                amount = q2(component_row.amount)
                if amount <= ZERO2:
                    continue

                if component.component_type in {
                    component.ComponentType.EARNING,
                    component.ComponentType.REIMBURSEMENT,
                }:
                    expense_account_id = getattr(posting_map, "expense_account_id", None)
                    payable_account_id = getattr(posting_map, "payable_account_id", None) or policy.salary_payable_account_id
                    if expense_account_id:
                        bucket = credits if is_reversal else debits
                        bucket[expense_account_id] = q2(bucket.get(expense_account_id, ZERO2) + amount)
                    payable_bucket = debits if is_reversal else credits
                    payable_bucket[payable_account_id] = q2(payable_bucket.get(payable_account_id, ZERO2) + amount)
                elif component.component_type == component.ComponentType.EMPLOYER_CONTRIBUTION:
                    expense_account_id = getattr(posting_map, "expense_account_id", None)
                    liability_account_id = (
                        getattr(posting_map, "liability_account_id", None)
                        or policy.employer_contribution_payable_account_id
                        or policy.salary_payable_account_id
                    )
                    if expense_account_id:
                        bucket = credits if is_reversal else debits
                        bucket[expense_account_id] = q2(bucket.get(expense_account_id, ZERO2) + amount)
                    liability_bucket = debits if is_reversal else credits
                    liability_bucket[liability_account_id] = q2(liability_bucket.get(liability_account_id, ZERO2) + amount)
                else:
                    liability_account_id = (
                        getattr(posting_map, "liability_account_id", None)
                        or getattr(posting_map, "payable_account_id", None)
                    )
                    if liability_account_id:
                        salary_bucket = credits if is_reversal else debits
                        liability_bucket = debits if is_reversal else credits
                        salary_bucket[policy.salary_payable_account_id] = q2(
                            salary_bucket.get(policy.salary_payable_account_id, ZERO2) + amount
                        )
                        liability_bucket[liability_account_id] = q2(
                            liability_bucket.get(liability_account_id, ZERO2) + amount
                        )

        jl_inputs: List[JLInput] = []
        for account_id, amount in sorted(debits.items()):
            jl_inputs.append(
                JLInput(
                    account_id=account_id,
                    drcr=True,
                    amount=amount,
                    description=f"Payroll run {run.run_number or run.id}",
                )
            )
        for account_id, amount in sorted(credits.items()):
            jl_inputs.append(
                JLInput(
                    account_id=account_id,
                    drcr=False,
                    amount=amount,
                    description=f"Payroll run {run.run_number or run.id}",
                )
            )
        return jl_inputs

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
            narration=f"Payroll run {run.run_number or run.id}",
            jl_inputs=PayrollPostingAdapter._aggregate_lines(run, policy),
            im_inputs=[],
            mark_posted=True,
        )
