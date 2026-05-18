from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from Authentication.models import User
from entity.notification_service import NotificationService
from payroll.models import Payslip, PayrollRunEmployee


class PayslipService:
    """
    Payslip generation stays in payroll because it is an operational document,
    not an accounting source of truth.
    """

    @staticmethod
    def _string_decimal(value) -> str:
        try:
            return str(Decimal(str(value or "0")).quantize(Decimal("0.01")))
        except Exception:
            return "0.00"

    @staticmethod
    def build_for_run_employee(run_employee: PayrollRunEmployee) -> Payslip:
        existing = getattr(run_employee, "payslip", None)
        if existing and (
            run_employee.is_frozen
            or run_employee.payroll_run.is_immutable
            or run_employee.payroll_run.status in {
                run_employee.payroll_run.Status.APPROVED,
                run_employee.payroll_run.Status.POSTED,
                run_employee.payroll_run.Status.REVERSED,
            }
        ):
            return existing

        calculation_payload = run_employee.calculation_payload or {}
        contract_snapshot = calculation_payload.get("contract_payroll_profile_snapshot") or {}
        attendance_snapshot = calculation_payload.get("attendance_snapshot") or {}
        payable_days_snapshot = calculation_payload.get("payable_days_snapshot") or {}
        tax_projection_snapshot = calculation_payload.get("tax_projection_snapshot") or {}
        source_markers = calculation_payload.get("source_markers") or {}
        policy_snapshot = contract_snapshot.get("payroll_policy") or {}
        recurring_items = contract_snapshot.get("recurring_items") or []
        one_time_items = contract_snapshot.get("one_time_items") or []
        payload = {
            "employee_code": run_employee.employee_code,
            "employee_name": run_employee.employee_name,
            "contract_payroll_profile_id": str(run_employee.contract_payroll_profile_id),
            "contract_code": contract_snapshot.get("contract_code"),
            "payroll_run_id": run_employee.payroll_run_id,
            "payroll_period_code": calculation_payload.get("period_code"),
            "payable_amount": str(run_employee.payable_amount),
            "gross_amount": str(run_employee.gross_amount),
            "deduction_amount": str(run_employee.deduction_amount),
            "employer_contribution_amount": str(run_employee.employer_contribution_amount),
            "reimbursement_amount": str(run_employee.reimbursement_amount),
            "salary_structure": calculation_payload.get("salary_structure_snapshot") or {},
            "attendance": {
                "attendance_days": attendance_snapshot.get("attendance_days"),
                "payable_days": attendance_snapshot.get("payable_days") or payable_days_snapshot.get("payable_days"),
                "lop_days": attendance_snapshot.get("lop_days") or payable_days_snapshot.get("lop_days"),
                "overtime_hours": attendance_snapshot.get("overtime_hours"),
                "late_count": attendance_snapshot.get("late_count"),
                "half_days": attendance_snapshot.get("half_days") or payable_days_snapshot.get("half_days"),
                "source": source_markers.get("attendance_source"),
            },
            "tax_projection_snapshot": tax_projection_snapshot,
            "tds_projection_trace": tax_projection_snapshot.get("tds_trace") or {},
            "policy_snapshot": policy_snapshot,
            "source_markers": source_markers,
            "recurring_pay_items": recurring_items,
            "one_time_pay_items": one_time_items,
            "components": [
                {
                    "code": row.component_code,
                    "name": row.component_name,
                    "type": row.component_type,
                    "amount": str(row.amount),
                    "source": (
                        (row.calculation_basis_snapshot or {}).get("contract_native_source")
                        or ((row.metadata or {}).get("source_type"))
                        or "structure_line"
                    ),
                    "calculation_basis_snapshot": row.calculation_basis_snapshot or {},
                }
                for row in run_employee.components.all()
            ],
            "section_totals": {
                "earnings": PayslipService._string_decimal(
                    sum(
                        (
                            row.amount
                            for row in run_employee.components.all()
                            if row.component_type in {"EARNING", "REIMBURSEMENT"}
                        ),
                        Decimal("0.00"),
                    )
                ),
                "deductions": PayslipService._string_decimal(
                    sum(
                        (
                            row.amount
                            for row in run_employee.components.all()
                            if row.component_type in {"DEDUCTION", "RECOVERY"}
                        ),
                        Decimal("0.00"),
                    )
                ),
                "employer_contributions": PayslipService._string_decimal(
                    sum(
                        (
                            row.amount
                            for row in run_employee.components.all()
                            if row.component_type == "EMPLOYER_CONTRIBUTION"
                        ),
                        Decimal("0.00"),
                    )
                ),
            },
        }
        payslip, created = Payslip.objects.update_or_create(
            payroll_run_employee=run_employee,
            defaults={
                "payslip_number": f"PSL-{run_employee.payroll_run_id}-{run_employee.id}",
                "generated_at": timezone.now(),
                "payload": payload,
            },
        )
        employee_user_id = run_employee.employee_user_id
        if created and employee_user_id:
            NotificationService.emit(
                instance=run_employee.payroll_run,
                workflow_key="payroll_run",
                event_code="PAYSLIP_RELEASED",
                title="Payslip Released",
                message=f"Payslip {payslip.payslip_number} is ready for {run_employee.employee_name or run_employee.employee_code}.",
                users=User.objects.filter(pk=employee_user_id),
                target_url=f"/payroll/runs/{run_employee.payroll_run_id}",
                payload={
                    "payslip_id": payslip.id,
                    "payslip_number": payslip.payslip_number,
                    "payroll_run_employee_id": run_employee.id,
                },
            )
        return payslip
