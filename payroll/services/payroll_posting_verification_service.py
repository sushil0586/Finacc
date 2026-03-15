from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Sum

from payroll.models import PayrollRun
from payroll.services.dto.payroll_rollout_results import (
    IssueSeverity,
    MetricComparison,
    ReconciliationBlock,
    ReconciliationResult,
)
from posting.models import Entry, EntryStatus, JournalLine, TxnType

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollPostingVerificationService:
    @classmethod
    def verify_run_posting(cls, *, run: PayrollRun) -> ReconciliationResult:
        result = ReconciliationResult(
            name="payroll-posting-verification",
            scope={
                "entity_id": run.entity_id,
                "entityfinid_id": run.entityfinid_id,
                "subentity_id": run.subentity_id,
                "payroll_run_id": run.id,
            },
        )
        if not run.posted_entry_id:
            result.add_issue("missing_posted_entry_id", "Payroll run has no posted entry reference.")
            return result

        entry = Entry.objects.filter(
            id=run.posted_entry_id,
            entity_id=run.entity_id,
            entityfin_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            txn_type=TxnType.PAYROLL,
            txn_id=run.id,
        ).first()
        if not entry:
            result.add_issue("missing_posting_entry", "Referenced posting entry does not exist in the expected scope.")
            return result

        journal_qs = JournalLine.objects.filter(entry_id=entry.id)
        sums = journal_qs.aggregate(
            dr_total=Sum("amount", filter=models.Q(drcr=True)),
            cr_total=Sum("amount", filter=models.Q(drcr=False)),
        )
        dr_total = q2(sums.get("dr_total"))
        cr_total = q2(sums.get("cr_total"))
        block = ReconciliationBlock(
            key="posting_quality",
            status="pass",
            metrics=[],
        )

        if entry.status != EntryStatus.POSTED:
            result.add_issue("entry_not_posted", "Posting entry exists but is not in POSTED status.")
            block.status = "fail"
        if dr_total != cr_total:
            result.add_issue(
                "unbalanced_journal",
                "Payroll posting journal is not balanced.",
                detail={"dr_total": str(dr_total), "cr_total": str(cr_total)},
            )
            block.status = "fail"
        if journal_qs.count() == 0:
            result.add_issue("missing_journal_lines", "Posting entry exists but contains no journal lines.")
            block.status = "fail"

        liability_hit = journal_qs.filter(account_id=run.ledger_policy_version.salary_payable_account_id).exists() if run.ledger_policy_version_id else False
        if run.ledger_policy_version_id and not liability_hit:
            result.add_issue(
                "salary_payable_not_hit",
                "Payroll salary payable ledger was not hit by posting.",
                severity=IssueSeverity.WARNING,
            )

        block.metrics.extend(
            [
                cls._metric("gross_amount", run.gross_amount, dr_total),
                cls._metric("net_pay_amount", run.net_pay_amount, cr_total),
            ]
        )
        if any(not metric.passed for metric in block.metrics):
            block.status = "warn" if block.status == "pass" else block.status
        result.blocks.append(block)
        return result

    @staticmethod
    def _metric(name: str, expected, actual):
        expected_value = q2(expected)
        actual_value = q2(actual)
        difference = q2(actual_value - expected_value)
        tolerance = Decimal("0.05")
        return MetricComparison(
            name=name,
            legacy_value=expected_value,
            new_value=actual_value,
            difference=difference,
            tolerance=tolerance,
            passed=abs(difference) <= tolerance,
        )
