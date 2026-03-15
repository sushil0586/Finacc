from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from payroll.models import (
    PayrollAdjustment,
    PayrollEmployeeProfile,
    PayrollPeriod,
    PayrollRun,
    PayrollRunActionLog,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    SalaryStructureLine,
    SalaryStructureVersion,
)
from payroll.services.payroll_config_resolver import PayrollConfigResolver
from payroll.services.payroll_posting_service import PayrollPostingService
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


@dataclass(frozen=True)
class PayrollRunResult:
    run: PayrollRun
    message: str


class PayrollRunService:
    """
    Orchestrates payroll run lifecycle.

    Payroll calculations stay inside payroll. Accounting handoff is explicit and
    happens only through the posting adapter once the run is approved.
    """

    @staticmethod
    def _doc_type_id() -> Optional[int]:
        row = DocumentType.objects.filter(module="payroll", default_code="PRUN", is_active=True).first()
        return row.id if row else None

    @classmethod
    def _assign_number(cls, run: PayrollRun) -> None:
        if run.doc_no:
            return
        doc_type_id = cls._doc_type_id()
        if not doc_type_id:
            run.run_number = run.run_number or f"{run.doc_code}-{run.id}"
            return
        number = DocumentNumberService.allocate_final(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            doc_type_id=doc_type_id,
            doc_code=run.doc_code,
            on_date=run.posting_date,
        )
        run.doc_no = number.doc_no
        run.run_number = number.display_no

    @staticmethod
    def _active_profiles(run: PayrollRun):
        qs = PayrollEmployeeProfile.objects.filter(
            entity_id=run.entity_id,
            status=PayrollEmployeeProfile.Status.ACTIVE,
            blocked_for_payroll=False,
        )
        qs = qs.filter(models.Q(entityfinid_id__isnull=True) | models.Q(entityfinid_id=run.entityfinid_id))
        if run.subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=run.subentity_id)
        return qs.select_related("salary_structure", "salary_structure_version")

    @staticmethod
    def _scope_check(run: PayrollRun, *, profile: PayrollEmployeeProfile) -> None:
        if profile.entity_id != run.entity_id:
            raise ValueError("Employee payroll profile entity does not match payroll run.")
        if profile.subentity_id != run.subentity_id:
            raise ValueError("Employee payroll profile subentity does not match payroll run.")

    @staticmethod
    def _resolve_structure_version(*, run: PayrollRun, profile: PayrollEmployeeProfile) -> SalaryStructureVersion | None:
        return PayrollConfigResolver.resolve_salary_structure_version(profile=profile, on_date=run.payroll_period.period_end)

    @staticmethod
    def _approved_adjustments(run: PayrollRun):
        qs = PayrollAdjustment.objects.filter(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            status=PayrollAdjustment.Status.APPROVED,
            effective_date__lte=run.payroll_period.period_end,
        )
        if run.subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=run.subentity_id)
        return qs.select_related("component", "employee_profile")

    @staticmethod
    def _line_amount(*, line: SalaryStructureLine, ctc_annual: Decimal, resolved: Dict[int, Decimal]) -> Decimal:
        basis = line.calculation_basis
        if basis == SalaryStructureLine.CalculationBasis.FIXED:
            return q2(line.fixed_amount)
        if basis == SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC:
            return q2(q2(ctc_annual) / Decimal("12.00") * q2(line.rate) / Decimal("100.00"))
        if basis == SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT and line.basis_component_id:
            return q2(q2(resolved.get(line.basis_component_id, ZERO2)) * q2(line.rate) / Decimal("100.00"))
        return ZERO2

    @classmethod
    @transaction.atomic
    def create_run(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        payroll_period_id: int,
        subentity_id: Optional[int],
        run_type: str,
        posting_date,
        payout_date,
        created_by_id: Optional[int],
    ) -> PayrollRunResult:
        period = PayrollPeriod.objects.select_for_update().get(
            id=payroll_period_id,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id != period.subentity_id:
            raise ValueError("Payroll period scope does not match the requested run scope.")
        if period.status != PayrollPeriod.Status.OPEN:
            raise ValueError("Payroll period must be open before a run can be created.")

        run = PayrollRun.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            payroll_period=period,
            run_type=run_type,
            posting_date=posting_date or period.period_end,
            payout_date=payout_date or period.payout_date,
            created_by_id=created_by_id,
        )
        cls._assign_number(run)
        run.save(update_fields=["doc_no", "run_number"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.CREATED,
            user_id=created_by_id,
            comment="Payroll run created.",
        )
        return PayrollRunResult(run=run, message="Payroll run created.")

    @classmethod
    @transaction.atomic
    def calculate_run(cls, run: PayrollRun, *, force: bool = False) -> PayrollRunResult:
        PayrollRunHardeningService.assert_mutable(run)
        if run.status not in {PayrollRun.Status.DRAFT, PayrollRun.Status.CALCULATED}:
            raise ValueError("Only draft or calculated payroll runs can be recalculated.")
        if run.status == PayrollRun.Status.CALCULATED and not force:
            raise ValueError("Payroll run is already calculated. Use force=true to recalculate.")

        ledger_policy = PayrollConfigResolver.resolve_ledger_policy(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            on_date=run.payroll_period.period_end,
        )
        if not ledger_policy:
            raise ValueError("No active payroll ledger policy found for the payroll run scope.")

        run.employee_runs.all().delete()

        adjustments_by_employee: Dict[int, list[PayrollAdjustment]] = {}
        for adjustment in cls._approved_adjustments(run):
            adjustments_by_employee.setdefault(adjustment.employee_profile_id, []).append(adjustment)

        employee_count = 0
        gross_total = ZERO2
        deduction_total = ZERO2
        employer_total = ZERO2
        reimbursement_total = ZERO2
        net_total = ZERO2

        for profile in cls._active_profiles(run):
            cls._scope_check(run, profile=profile)
            structure = profile.salary_structure
            structure_version = cls._resolve_structure_version(run=run, profile=profile)
            if not structure or structure.status != structure.Status.ACTIVE or not structure_version:
                continue

            lines = list(
                SalaryStructureLine.objects.filter(
                    salary_structure_version=structure_version,
                    is_active=True,
                )
                .select_related("component", "basis_component")
                .order_by("sequence", "id")
            )
            resolved: Dict[int, Decimal] = {}
            gross_amount = ZERO2
            deduction_amount = ZERO2
            employer_amount = ZERO2
            reimbursement_amount = ZERO2

            run_employee = PayrollRunEmployee.objects.create(
                payroll_run=run,
                employee_profile=profile,
                salary_structure=structure,
                salary_structure_version=structure_version,
                ledger_policy_version=ledger_policy,
                statutory_policy_version_ref=run.statutory_policy_version_ref,
            )

            for line in lines:
                amount = cls._line_amount(line=line, ctc_annual=q2(profile.ctc_annual), resolved=resolved)
                resolved[line.component_id] = amount
                component_posting = PayrollConfigResolver.resolve_component_posting(
                    entity_id=run.entity_id,
                    entityfinid_id=run.entityfinid_id,
                    subentity_id=run.subentity_id,
                    component_id=line.component_id,
                    on_date=run.payroll_period.period_end,
                )
                PayrollRunEmployeeComponent.objects.create(
                    payroll_run_employee=run_employee,
                    component=line.component,
                    component_code=line.component.code,
                    component_name=line.component.name,
                    component_type=line.component.component_type,
                    posting_behavior=line.component.posting_behavior,
                    component_posting_version=component_posting,
                    source_structure_line=line,
                    sequence=line.sequence,
                    amount=amount,
                    taxable_amount=amount if line.component.is_taxable else ZERO2,
                    is_employer_cost=line.component.component_type == line.component.ComponentType.EMPLOYER_CONTRIBUTION,
                    calculation_basis_snapshot={
                        "basis": line.calculation_basis,
                        "rate": str(line.rate),
                        "fixed_amount": str(line.fixed_amount),
                    },
                )
                if line.component.component_type == line.component.ComponentType.DEDUCTION:
                    deduction_amount = q2(deduction_amount + amount)
                elif line.component.component_type == line.component.ComponentType.EMPLOYER_CONTRIBUTION:
                    employer_amount = q2(employer_amount + amount)
                elif line.component.component_type == line.component.ComponentType.REIMBURSEMENT:
                    reimbursement_amount = q2(reimbursement_amount + amount)
                    gross_amount = q2(gross_amount + amount)
                elif line.component.component_type == line.component.ComponentType.RECOVERY:
                    deduction_amount = q2(deduction_amount + amount)
                else:
                    gross_amount = q2(gross_amount + amount)

            for adjustment in adjustments_by_employee.get(profile.id, []):
                component = adjustment.component
                component_type = component.component_type if component else PayrollAdjustment.Kind.MANUAL
                posting_behavior = component.posting_behavior if component else "MANUAL"
                component_posting = (
                    PayrollConfigResolver.resolve_component_posting(
                        entity_id=run.entity_id,
                        entityfinid_id=run.entityfinid_id,
                        subentity_id=run.subentity_id,
                        component_id=component.id,
                        on_date=run.payroll_period.period_end,
                    )
                    if component
                    else None
                )
                PayrollRunEmployeeComponent.objects.create(
                    payroll_run_employee=run_employee,
                    component=component,
                    payroll_adjustment=adjustment,
                    component_code=component.code if component else adjustment.kind,
                    component_name=component.name if component else adjustment.kind.replace("_", " ").title(),
                    component_type=component_type,
                    posting_behavior=posting_behavior,
                    component_posting_version=component_posting,
                    sequence=900,
                    amount=q2(adjustment.amount),
                    taxable_amount=q2(adjustment.amount) if component and component.is_taxable else ZERO2,
                    is_employer_cost=component_type == PayrollAdjustment.Kind.REIMBURSEMENT,
                    metadata={"adjustment_kind": adjustment.kind},
                    calculation_basis_snapshot={"adjustment_kind": adjustment.kind},
                )
                if adjustment.kind in {PayrollAdjustment.Kind.LOAN_RECOVERY, PayrollAdjustment.Kind.ADVANCE_RECOVERY}:
                    deduction_amount = q2(deduction_amount + adjustment.amount)
                elif adjustment.kind == PayrollAdjustment.Kind.REIMBURSEMENT:
                    reimbursement_amount = q2(reimbursement_amount + adjustment.amount)
                    gross_amount = q2(gross_amount + adjustment.amount)
                else:
                    gross_amount = q2(gross_amount + adjustment.amount)

            payable_amount = q2(gross_amount - deduction_amount)
            run_employee.gross_amount = gross_amount
            run_employee.deduction_amount = deduction_amount
            run_employee.employer_contribution_amount = employer_amount
            run_employee.reimbursement_amount = reimbursement_amount
            run_employee.payable_amount = payable_amount
            run_employee.calculation_payload = {
                "structure_code": structure.code,
                "structure_version": structure_version.version_no,
                "period_code": run.payroll_period.code,
            }
            run_employee.calculation_assumptions = {
                "ctc_annual": str(profile.ctc_annual),
                "pay_frequency": profile.pay_frequency,
                "period_end": str(run.payroll_period.period_end),
            }
            run_employee.save(
                update_fields=[
                    "gross_amount",
                    "deduction_amount",
                    "employer_contribution_amount",
                    "reimbursement_amount",
                    "payable_amount",
                    "calculation_payload",
                    "calculation_assumptions",
                ]
            )

            employee_count += 1
            gross_total = q2(gross_total + gross_amount)
            deduction_total = q2(deduction_total + deduction_amount)
            employer_total = q2(employer_total + employer_amount)
            reimbursement_total = q2(reimbursement_total + reimbursement_amount)
            net_total = q2(net_total + payable_amount)

        run.status = PayrollRun.Status.CALCULATED
        run.employee_count = employee_count
        run.gross_amount = gross_total
        run.deduction_amount = deduction_total
        run.employer_contribution_amount = employer_total
        run.reimbursement_amount = reimbursement_total
        run.net_pay_amount = net_total
        run.calculation_payload = {
            "calculated_at": timezone.now().isoformat(),
            "employee_count": employee_count,
        }
        run.ledger_policy_version = ledger_policy
        run.config_snapshot = {
            "ledger_policy_id": ledger_policy.id,
            "ledger_policy_version": ledger_policy.version_no,
            "structure_versions": [
                {
                    "employee_profile_id": row.employee_profile_id,
                    "salary_structure_version_id": row.salary_structure_version_id,
                }
                for row in run.employee_runs.all()
            ],
        }
        run.save(
            update_fields=[
                "status",
                "employee_count",
                "gross_amount",
                "deduction_amount",
                "employer_contribution_amount",
                "reimbursement_amount",
                "net_pay_amount",
                "calculation_payload",
                "ledger_policy_version",
                "config_snapshot",
            ]
        )
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.CALCULATED,
            user_id=None,
            old_status=PayrollRun.Status.DRAFT if not force else PayrollRun.Status.CALCULATED,
            new_status=run.status,
            payload={"employee_count": employee_count},
        )
        return PayrollRunResult(run=run, message="Payroll run calculated.")

    @staticmethod
    @transaction.atomic
    def submit_run(run: PayrollRun, *, submitted_by_id: int, note: str = "", reason_code: str = "") -> PayrollRunResult:
        if run.status != PayrollRun.Status.CALCULATED:
            raise ValueError("Only calculated payroll runs can be submitted.")
        old_status = run.status
        run.submitted_by_id = submitted_by_id
        run.submitted_at = timezone.now()
        run.status_comment = note or run.status_comment
        run.status_reason_code = reason_code or run.status_reason_code
        run.save(update_fields=["submitted_by", "submitted_at", "status_comment", "status_reason_code"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.SUBMITTED,
            user_id=submitted_by_id,
            old_status=old_status,
            new_status=run.status,
            reason_code=reason_code,
            comment=note,
        )
        return PayrollRunResult(run=run, message="Payroll run submitted.")

    @staticmethod
    @transaction.atomic
    def approve_run(run: PayrollRun, *, approved_by_id: int, note: str = "") -> PayrollRunResult:
        if run.status != PayrollRun.Status.CALCULATED:
            raise ValueError("Only calculated payroll runs can be approved.")
        if not run.employee_runs.exists():
            raise ValueError("Payroll run has no employee rows to approve.")
        old_status = run.status
        run.status = PayrollRun.Status.APPROVED
        run.approved_by_id = approved_by_id
        run.approved_at = timezone.now()
        run.approval_note = note or ""
        run.save(update_fields=["status", "approved_by", "approved_at", "approval_note"])
        PayrollRunHardeningService.freeze_run(run, user_id=approved_by_id)
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.APPROVED,
            user_id=approved_by_id,
            old_status=old_status,
            new_status=run.status,
            comment=note,
        )
        return PayrollRunResult(run=run, message="Payroll run approved.")

    @staticmethod
    @transaction.atomic
    def post_run(run: PayrollRun, *, posted_by_id: int) -> PayrollRunResult:
        if run.status != PayrollRun.Status.APPROVED:
            raise ValueError("Only approved payroll runs can be posted.")
        if not run.is_immutable:
            raise ValueError("Payroll run must be locked before posting.")
        old_status = run.status
        entry = PayrollPostingService.post_run(run, user_id=posted_by_id)
        run.status = PayrollRun.Status.POSTED
        run.posted_by_id = posted_by_id
        run.posted_at = timezone.now()
        run.posted_entry_id = entry.id
        run.post_reference = entry.voucher_no or ""
        run.save(update_fields=["status", "posted_by", "posted_at", "posted_entry_id", "post_reference"])
        PayrollRunHardeningService.log_action(
            run,
            action=PayrollRunActionLog.Action.POSTED,
            user_id=posted_by_id,
            old_status=old_status,
            new_status=run.status,
            payload={"entry_id": entry.id},
        )
        return PayrollRunResult(run=run, message="Payroll run posted.")

    @staticmethod
    def summary(run: PayrollRun) -> dict:
        rows = run.employee_runs.aggregate(
            gross_amount=Sum("gross_amount"),
            deduction_amount=Sum("deduction_amount"),
            employer_contribution_amount=Sum("employer_contribution_amount"),
            reimbursement_amount=Sum("reimbursement_amount"),
            payable_amount=Sum("payable_amount"),
        )
        return {
            "run_id": run.id,
            "employee_count": run.employee_count,
            "gross_amount": q2(rows.get("gross_amount")),
            "deduction_amount": q2(rows.get("deduction_amount")),
            "employer_contribution_amount": q2(rows.get("employer_contribution_amount")),
            "reimbursement_amount": q2(rows.get("reimbursement_amount")),
            "payable_amount": q2(rows.get("payable_amount")),
            "status": run.status,
        }
