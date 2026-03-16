from __future__ import annotations

import csv
from typing import Iterable

from django.http import HttpResponse

from payroll.models import PayrollRun, PayrollRunEmployee
from payroll.services.payroll_traceability_service import PayrollTraceabilityService


class PayrollExportService:
    @staticmethod
    def _response(*, filename: str) -> tuple[HttpResponse, csv.writer]:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response, csv.writer(response)

    @staticmethod
    def export_run_register(*, runs: Iterable[PayrollRun]) -> HttpResponse:
        response, writer = PayrollExportService._response(filename="payroll_run_register.csv")
        writer.writerow(
            [
                "run_id",
                "run_reference",
                "entity_id",
                "entity_name",
                "entityfinid_id",
                "subentity_id",
                "period_code",
                "status",
                "payment_status",
                "employee_count",
                "gross_amount",
                "deduction_amount",
                "employer_contribution_amount",
                "reimbursement_amount",
                "net_pay_amount",
                "post_reference",
                "payment_batch_ref",
                "reversal_reason",
                "created_at",
                "posted_at",
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.id,
                    run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    run.entity_id,
                    getattr(run.entity, "entityname", ""),
                    run.entityfinid_id,
                    run.subentity_id or "",
                    getattr(run.payroll_period, "code", ""),
                    run.status,
                    run.payment_status,
                    run.employee_count,
                    run.gross_amount,
                    run.deduction_amount,
                    run.employer_contribution_amount,
                    run.reimbursement_amount,
                    run.net_pay_amount,
                    run.post_reference,
                    run.payment_batch_ref,
                    run.reversal_reason,
                    run.created_at,
                    run.posted_at,
                ]
            )
        return response

    @staticmethod
    def export_employee_rows(*, rows: Iterable[PayrollRunEmployee]) -> HttpResponse:
        response, writer = PayrollExportService._response(filename="payroll_run_employee_rows.csv")
        writer.writerow(
            [
                "row_id",
                "run_id",
                "run_reference",
                "employee_profile_id",
                "employee_code",
                "employee_name",
                "status",
                "payment_status",
                "gross_amount",
                "deduction_amount",
                "employer_contribution_amount",
                "reimbursement_amount",
                "payable_amount",
                "salary_structure_id",
                "salary_structure_version_id",
            ]
        )
        for row in rows:
            run = row.payroll_run
            writer.writerow(
                [
                    row.id,
                    run.id,
                    run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    row.employee_profile_id,
                    row.employee_profile.employee_code,
                    row.employee_profile.full_name,
                    row.status,
                    row.payment_status,
                    row.gross_amount,
                    row.deduction_amount,
                    row.employer_contribution_amount,
                    row.reimbursement_amount,
                    row.payable_amount,
                    row.salary_structure_id or "",
                    row.salary_structure_version_id or "",
                ]
            )
        return response

    @staticmethod
    def export_component_totals(*, runs: Iterable[PayrollRun]) -> HttpResponse:
        response, writer = PayrollExportService._response(filename="payroll_component_totals.csv")
        writer.writerow(
            [
                "run_id",
                "run_reference",
                "component_id",
                "component_code",
                "component_name",
                "category",
                "amount",
                "employee_count",
            ]
        )
        for run in runs:
            run_ref = run.run_number or f"{run.doc_code}-{run.doc_no or run.id}"
            for total in PayrollTraceabilityService.build_component_totals(run=run):
                writer.writerow(
                    [
                        run.id,
                        run_ref,
                        total["component_id"] or "",
                        total["component_code"],
                        total["component_name"],
                        total["category"] or "",
                        total["amount"],
                        total["employee_count"],
                    ]
                )
        return response

    @staticmethod
    def export_deduction_summary(*, runs: Iterable[PayrollRun]) -> HttpResponse:
        response, writer = PayrollExportService._response(filename="payroll_deduction_summary.csv")
        writer.writerow(
            [
                "run_id",
                "run_reference",
                "employee_count",
                "deduction_amount",
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.id,
                    run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    run.employee_count,
                    run.deduction_amount,
                ]
            )
        return response
