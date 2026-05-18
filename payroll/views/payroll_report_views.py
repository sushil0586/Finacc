from __future__ import annotations

from django.utils.dateparse import parse_date
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from payroll.services.payroll_export_service import PayrollExportService
from payroll.services.payroll_report_service import PayrollComplianceReportService, PayrollReportFilters
from payroll.views.scoped import PayrollScopedAPIView


class _PayrollReportBaseAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]
    report_type = ""
    file_stem = "payroll_report"

    def _parse_optional_int(self, raw_value: str | None, field_name: str) -> int | None:
        return self._parse_int(raw_value, field_name, required=False)

    def _parse_optional_date(self, raw_value: str | None, field_name: str):
        if raw_value in (None, "", "null", "None"):
            return None
        parsed = parse_date(raw_value)
        if parsed is None:
            raise ValidationError({field_name: f"{field_name} must be in YYYY-MM-DD format."})
        return parsed

    def _filters_from_query(self, request) -> PayrollReportFilters:
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(request, require_entity=True, require_entityfinid=False)
        return PayrollReportFilters(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            payroll_period_id=self._parse_optional_int(request.query_params.get("payroll_period") or request.query_params.get("period"), "payroll_period"),
            department_id=self._parse_optional_int(request.query_params.get("department"), "department"),
            org_unit_id=self._parse_optional_int(request.query_params.get("org_unit"), "org_unit"),
            employee_id=self._parse_optional_int(request.query_params.get("employee"), "employee"),
            contract_id=self._parse_optional_int(request.query_params.get("contract"), "contract"),
            status=(request.query_params.get("status") or "").strip() or None,
            statutory_scheme_id=(request.query_params.get("statutory_scheme") or "").strip() or None,
            from_date=self._parse_optional_date(request.query_params.get("from_date"), "from_date"),
            to_date=self._parse_optional_date(request.query_params.get("to_date"), "to_date"),
        )

    def get(self, request):
        filters = self._filters_from_query(request)
        self._assert_entity_permission(
            request,
            entity_id=filters.entity_id,
            permission_codes={"reports.payroll.view", "payroll.run.view", "payroll.run.manage"},
            label="view payroll reports",
        )
        payload = PayrollComplianceReportService.build_report(report_type=self.report_type, filters=filters)
        return Response(payload)


class PayrollRegisterReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_PAYROLL_REGISTER
    file_stem = "payroll_register"


class SalarySheetReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_SALARY_SHEET
    file_stem = "salary_sheet"


class PFSummaryReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_PF_SUMMARY
    file_stem = "pf_summary"


class ESISummaryReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_ESI_SUMMARY
    file_stem = "esi_summary"


class PTSummaryReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_PT_SUMMARY
    file_stem = "pt_summary"


class LWFSummaryReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_LWF_SUMMARY
    file_stem = "lwf_summary"


class FnFSettlementRegisterReportAPIView(_PayrollReportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_FNF_REGISTER
    file_stem = "fnf_settlement_register"


class _PayrollReportExportBaseAPIView(_PayrollReportBaseAPIView):
    allowed_formats = {"csv", "xlsx"}

    def _parse_format(self, request) -> str:
        export_format = (request.query_params.get("format") or "xlsx").strip().lower()
        if export_format not in self.allowed_formats:
            raise ValidationError({"format": f"format must be one of {', '.join(sorted(self.allowed_formats))}."})
        return export_format

    def get(self, request):
        filters = self._filters_from_query(request)
        self._assert_entity_permission(
            request,
            entity_id=filters.entity_id,
            permission_codes={"reports.payroll.export"},
            label="export payroll reports",
        )
        payload = PayrollComplianceReportService.build_report(report_type=self.report_type, filters=filters)
        metadata = {
            "entity": filters.entity_id,
            "payroll_period_or_range": filters.payroll_period_id or (
                f"{filters.from_date.isoformat() if filters.from_date else ''}..{filters.to_date.isoformat() if filters.to_date else ''}".strip(".")
            ),
            "generated_by": getattr(request.user, "email", None) or getattr(request.user, "username", None) or f"user:{request.user.pk}",
            "generated_at": payload.get("generated_at"),
            "filters_applied": payload.get("filters") or {},
            "source_snapshot_note": "Export rendered from payroll report payload and stored payroll snapshots only.",
        }
        return PayrollExportService.export_report_payload(
            payload=payload,
            metadata=metadata,
            file_stem=self.file_stem,
            export_format=self._parse_format(request),
        )


class PayrollRegisterReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_PAYROLL_REGISTER
    file_stem = "payroll_register"


class SalarySheetReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_SALARY_SHEET
    file_stem = "salary_sheet"


class PFSummaryReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_PF_SUMMARY
    file_stem = "pf_summary"


class ESISummaryReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_ESI_SUMMARY
    file_stem = "esi_summary"


class PTSummaryReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_PT_SUMMARY
    file_stem = "pt_summary"


class LWFSummaryReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_LWF_SUMMARY
    file_stem = "lwf_summary"


class FnFSettlementRegisterReportExportAPIView(_PayrollReportExportBaseAPIView):
    report_type = PayrollComplianceReportService.REPORT_FNF_REGISTER
    file_stem = "fnf_settlement_register"
