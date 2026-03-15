from __future__ import annotations

from payroll.models import PayrollRun
from payroll.services.dto.payroll_rollout_results import IssueSeverity, ShadowRunValidationResult
from payroll.services.payroll_posting_verification_service import PayrollPostingVerificationService
from payroll.services.payroll_reconciliation_service import PayrollReconciliationService
from payroll.services.payroll_run_service import PayrollRunService


class PayrollShadowRunService:
    """
    Runs rollout-safe validations against a non-live payroll run.
    """

    @staticmethod
    def validate_shadow_run(
        *,
        payroll_run: PayrollRun,
        expected_employee_count: int | None = None,
        verify_posting: bool = False,
    ) -> ShadowRunValidationResult:
        scope = {
            "entity_id": payroll_run.entity_id,
            "entityfinid_id": payroll_run.entityfinid_id,
            "subentity_id": payroll_run.subentity_id,
            "payroll_run_id": payroll_run.id,
        }
        result = ShadowRunValidationResult(name="payroll-shadow-run", scope=scope, payroll_run_id=payroll_run.id)

        employee_rows = payroll_run.employee_runs.select_related("employee_profile")
        employee_count = employee_rows.count()
        result.summary = {
            "status": payroll_run.status,
            "employee_count": employee_count,
            "gross_amount": str(payroll_run.gross_amount),
            "deduction_amount": str(payroll_run.deduction_amount),
            "net_pay_amount": str(payroll_run.net_pay_amount),
        }

        if expected_employee_count is not None and employee_count != expected_employee_count:
            result.add_issue(
                "employee_count_mismatch",
                "Shadow run employee count does not match expected count.",
                detail={"expected": expected_employee_count, "actual": employee_count},
            )

        cross_scope = employee_rows.exclude(employee_profile__entity_id=payroll_run.entity_id)
        if cross_scope.exists():
            result.add_issue(
                "cross_scope_employee_leakage",
                "Shadow run contains employee profiles from another entity.",
                detail={"employee_run_ids": list(cross_scope.values_list("id", flat=True)[:20])},
            )

        missing_versions = employee_rows.filter(salary_structure_version__isnull=True).count()
        result.checks["employee_rows_missing_structure_version"] = missing_versions
        if missing_versions:
            result.add_issue(
                "missing_structure_versions",
                "Some shadow employee rows do not contain a frozen salary structure version.",
                severity=IssueSeverity.WARNING,
                detail={"count": missing_versions},
            )

        rec = PayrollReconciliationService.build_run_self_consistency(run=payroll_run)
        result.checks["self_consistency"] = rec.as_dict()
        if not rec.passed:
            for issue in rec.issues:
                result.issues.append(issue)

        if verify_posting and payroll_run.posted_entry_id:
            post_result = PayrollPostingVerificationService.verify_run_posting(run=payroll_run)
            result.checks["posting_verification"] = post_result.as_dict()
            if not post_result.passed:
                result.add_issue("posting_verification_failed", "Payroll posting verification failed.", detail=post_result.as_dict())

        return result
