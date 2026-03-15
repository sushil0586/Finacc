from __future__ import annotations

from django.utils import timezone

from payroll.models import Payslip, PayrollRunEmployee


class PayslipService:
    """
    Payslip generation stays in payroll because it is an operational document,
    not an accounting source of truth.
    """

    @staticmethod
    def build_for_run_employee(run_employee: PayrollRunEmployee) -> Payslip:
        payload = {
            "employee_code": run_employee.employee_profile.employee_code,
            "employee_name": run_employee.employee_profile.full_name,
            "payable_amount": str(run_employee.payable_amount),
            "components": [
                {
                    "code": row.component_code,
                    "name": row.component_name,
                    "type": row.component_type,
                    "amount": str(row.amount),
                }
                for row in run_employee.components.all()
            ],
        }
        payslip, _ = Payslip.objects.update_or_create(
            payroll_run_employee=run_employee,
            defaults={
                "payslip_number": f"PSL-{run_employee.payroll_run_id}-{run_employee.id}",
                "generated_at": timezone.now(),
                "payload": payload,
            },
        )
        return payslip
