from __future__ import annotations

from payroll.models import PayrollRun


class PayrollPaymentService:
    """
    Placeholder payments boundary helper.
    Payroll prepares payment handoff payloads; payments owns execution.
    """

    @staticmethod
    def build_handoff_payload(*, run: PayrollRun) -> dict:
        return {
            "source_module": "payroll",
            "source_document": "payroll_run",
            "source_id": run.id,
            "entity_id": run.entity_id,
            "entityfinid_id": run.entityfinid_id,
            "subentity_id": run.subentity_id,
            "payout_date": run.payout_date.isoformat() if run.payout_date else None,
            "payment_batch_ref": run.payment_batch_ref,
            "employees": [
                {
                    "employee_profile_id": row.employee_profile_id,
                    "employee_code": row.employee_profile.employee_code,
                    "amount": str(row.payable_amount),
                    "payment_account_id": row.employee_profile.payment_account_id,
                }
                for row in run.employee_runs.select_related("employee_profile")
                if row.payable_amount > 0
            ],
        }
