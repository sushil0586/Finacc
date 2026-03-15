from __future__ import annotations

from payroll.models import PayrollPeriod, PayrollRun
from payroll.services.dto.payroll_rollout_results import IssueSeverity, RolloutValidationResult
from payroll.services.payroll_posting_verification_service import PayrollPostingVerificationService
from payroll.services.payroll_reconciliation_service import PayrollReconciliationService
from payroll.services.payroll_rollout_validation_service import PayrollRolloutValidationService
from payroll.services.payroll_shadow_run_service import PayrollShadowRunService


class PayrollCutoverService:
    """
    Aggregates rollout readiness signals for one scope and period.
    """

    @classmethod
    def validate_cutover(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None = None,
        period_code: str,
        payroll_run_id: int | None = None,
        expected_employee_count: int | None = None,
        legacy_frozen: bool = False,
    ) -> RolloutValidationResult:
        result = RolloutValidationResult(
            name="payroll-cutover-readiness",
            scope={
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "period_code": period_code,
                "payroll_run_id": payroll_run_id,
            },
        )

        setup_result = PayrollRolloutValidationService.validate_setup(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            period_code=period_code,
        )
        result.checks["setup_validation"] = setup_result.as_dict()
        result.issues.extend(setup_result.issues)

        period = PayrollPeriod.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            code=period_code,
        ).first()
        if not period:
            result.add_issue("missing_target_period", "Target payroll period does not exist.")
            return result
        if period.status != PayrollPeriod.Status.OPEN:
            result.add_issue("target_period_not_open", "Target payroll period is not open.")

        if not legacy_frozen:
            result.add_issue(
                "legacy_not_frozen",
                "Legacy payroll is not confirmed frozen for the target entity.",
                severity=IssueSeverity.WARNING,
            )

        if payroll_run_id:
            run = PayrollRun.objects.filter(
                id=payroll_run_id,
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
            ).first()
            if not run:
                result.add_issue("shadow_run_missing", "Shadow payroll run not found in the requested scope.")
                return result
            shadow_result = PayrollShadowRunService.validate_shadow_run(
                payroll_run=run,
                expected_employee_count=expected_employee_count,
                verify_posting=bool(run.posted_entry_id),
            )
            result.checks["shadow_validation"] = shadow_result.as_dict()
            result.issues.extend(shadow_result.issues)

            posting_result = PayrollPostingVerificationService.verify_run_posting(run=run) if run.posted_entry_id else None
            if posting_result:
                result.checks["posting_verification"] = posting_result.as_dict()
                result.issues.extend(posting_result.issues)

            result.checks["payslip_spotcheck"] = PayrollReconciliationService.build_payslip_spotcheck_payload(run=run)

        return result
