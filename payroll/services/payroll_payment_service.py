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
                    "contract_payroll_profile_id": str(row.contract_payroll_profile_id),
                    "hrms_contract_id": str(row.contract_payroll_profile.hrms_contract_id) if row.contract_payroll_profile_id else None,
                    "contract_code": getattr(row.contract_payroll_profile.hrms_contract, "contract_code", None)
                    if row.contract_payroll_profile_id
                    else None,
                    "employee_code": row.employee_code,
                    "employee_name": row.employee_name,
                    "work_email": getattr(row.contract_payroll_profile.hrms_contract.employee, "work_email", None)
                    if row.contract_payroll_profile_id
                    else None,
                    "amount": str(row.payable_amount),
                    "payment_account_id": row.payment_account_id,
                }
                for row in run.employee_runs.select_related(
                    "contract_payroll_profile__hrms_contract__employee"
                )
                if row.payable_amount > 0
            ],
        }
