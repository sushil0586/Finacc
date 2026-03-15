from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Sum

from payroll.models import PayrollRun
from payroll.services.dto.payroll_rollout_results import (
    IssueRecord,
    IssueSeverity,
    MetricComparison,
    ReconciliationBlock,
    ReconciliationResult,
)

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollReconciliationService:
    @staticmethod
    def _metric(name: str, legacy_value, new_value, tolerance: Decimal) -> MetricComparison:
        legacy_decimal = q2(legacy_value)
        new_decimal = q2(new_value)
        difference = q2(new_decimal - legacy_decimal)
        passed = abs(difference) <= tolerance
        return MetricComparison(
            name=name,
            legacy_value=legacy_decimal,
            new_value=new_decimal,
            difference=difference,
            tolerance=tolerance,
            passed=passed,
        )

    @classmethod
    def reconcile_legacy_snapshot(
        cls,
        *,
        payroll_run: PayrollRun,
        legacy_snapshot: dict,
        tolerance: Decimal = Decimal("0.05"),
    ) -> ReconciliationResult:
        scope = {
            "entity_id": payroll_run.entity_id,
            "entityfinid_id": payroll_run.entityfinid_id,
            "subentity_id": payroll_run.subentity_id,
            "payroll_run_id": payroll_run.id,
        }
        result = ReconciliationResult(name="payroll-legacy-reconciliation", scope=scope)

        new_component_totals = cls._component_totals(run=payroll_run)
        legacy_component_totals = legacy_snapshot.get("component_totals", {})

        summary_block = ReconciliationBlock(
            key="summary",
            status="pass",
            metrics=[
                cls._metric("employee_count", legacy_snapshot.get("employee_count", 0), payroll_run.employee_count, Decimal("0")),
                cls._metric("gross_amount", legacy_snapshot.get("gross_amount", ZERO2), payroll_run.gross_amount, tolerance),
                cls._metric("deduction_amount", legacy_snapshot.get("deduction_amount", ZERO2), payroll_run.deduction_amount, tolerance),
                cls._metric("net_pay_amount", legacy_snapshot.get("net_pay_amount", ZERO2), payroll_run.net_pay_amount, tolerance),
            ],
        )
        if not all(metric.passed for metric in summary_block.metrics):
            summary_block.status = "fail"
        result.blocks.append(summary_block)

        component_rows = []
        component_metrics = []
        all_codes = sorted(set(legacy_component_totals.keys()) | set(new_component_totals.keys()))
        for code in all_codes:
            metric = cls._metric(
                f"component:{code}",
                legacy_component_totals.get(code, ZERO2),
                new_component_totals.get(code, ZERO2),
                tolerance,
            )
            component_metrics.append(metric)
            if not metric.passed:
                component_rows.append(metric.as_dict())
        component_block = ReconciliationBlock(
            key="component_totals",
            status="pass" if not component_rows else "fail",
            metrics=component_metrics,
            drilldown_rows=component_rows,
        )
        result.blocks.append(component_block)

        if summary_block.status == "fail" or component_block.status == "fail":
            result.add_issue("reconciliation_mismatch", "Payroll reconciliation found mismatched values.")

        return result

    @classmethod
    def build_run_self_consistency(cls, *, run: PayrollRun, tolerance: Decimal = Decimal("0.05")) -> ReconciliationResult:
        scope = {
            "entity_id": run.entity_id,
            "entityfinid_id": run.entityfinid_id,
            "subentity_id": run.subentity_id,
            "payroll_run_id": run.id,
        }
        result = ReconciliationResult(name="payroll-run-self-consistency", scope=scope)

        row_sums = run.employee_runs.aggregate(
            employee_count=Count("id"),
            gross_amount=Sum("gross_amount"),
            deduction_amount=Sum("deduction_amount"),
            employer_contribution_amount=Sum("employer_contribution_amount"),
            reimbursement_amount=Sum("reimbursement_amount"),
            payable_amount=Sum("payable_amount"),
        )
        block = ReconciliationBlock(
            key="self_consistency",
            status="pass",
            metrics=[
                cls._metric("employee_count", run.employee_count, row_sums.get("employee_count", 0), Decimal("0")),
                cls._metric("gross_amount", run.gross_amount, row_sums.get("gross_amount", ZERO2), tolerance),
                cls._metric("deduction_amount", run.deduction_amount, row_sums.get("deduction_amount", ZERO2), tolerance),
                cls._metric("reimbursement_amount", run.reimbursement_amount, row_sums.get("reimbursement_amount", ZERO2), tolerance),
                cls._metric("net_pay_amount", run.net_pay_amount, row_sums.get("payable_amount", ZERO2), tolerance),
            ],
        )
        if not all(metric.passed for metric in block.metrics):
            block.status = "fail"
            result.add_issue("run_self_consistency_failed", "Run header totals do not match employee row totals.")
        result.blocks.append(block)
        return result

    @staticmethod
    def _component_totals(*, run: PayrollRun) -> dict[str, Decimal]:
        rows = (
            run.employee_runs.values("components__component_code")
            .annotate(total_amount=Sum("components__amount"))
            .order_by()
        )
        return {
            row["components__component_code"]: q2(row["total_amount"])
            for row in rows
            if row["components__component_code"]
        }

    @staticmethod
    def build_payslip_spotcheck_payload(*, run: PayrollRun, limit: int = 10) -> dict:
        rows = run.employee_runs.select_related("employee_profile").prefetch_related("components")[:limit]
        return {
            "sample_size": len(rows),
            "rows": [
                {
                    "employee_code": row.employee_profile.employee_code,
                    "employee_name": row.employee_profile.full_name,
                    "gross_amount": str(row.gross_amount),
                    "deduction_amount": str(row.deduction_amount),
                    "payable_amount": str(row.payable_amount),
                    "components": [
                        {"code": comp.component_code, "amount": str(comp.amount)}
                        for comp in row.components.all()
                    ],
                }
                for row in rows
            ],
        }
