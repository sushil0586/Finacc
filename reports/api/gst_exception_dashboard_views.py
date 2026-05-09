from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.receivables_views import _write_csv, _write_excel
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr3b.services import Gstr3bSummaryService
from reports.schemas.common import build_report_envelope
from reports.services.gst_exception_dashboard import build_gst_exception_dashboard
from reports.services.gst_reconciliation import build_gstr1_vs_gstr3b_reconciliation
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class GstExceptionDashboardAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        gstr1_service = Gstr1ReportService()
        gstr3b_service = Gstr3bSummaryService()
        try:
            gstr1_scope = gstr1_service.build_scope(request.query_params)
            gstr3b_scope = gstr3b_service.build_scope(request.query_params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)

        self.enforce_scope(
            request,
            entity_id=gstr1_scope.entity_id,
            entityfinid_id=gstr1_scope.entityfinid_id,
            subentity_id=gstr1_scope.subentity_id,
        )
        gstr1_warnings = gstr1_service.validations(gstr1_scope)
        gstr3b_warnings = gstr3b_service.validations(gstr3b_scope)
        reconciliation = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
        )
        payload = build_gst_exception_dashboard(
            gstr1_warnings=gstr1_warnings,
            gstr3b_warnings=gstr3b_warnings,
            reconciliation_payload=reconciliation,
        )
        response = build_report_envelope(
            report_code="gst-exception-dashboard",
            report_name="GST Exception Dashboard",
            payload=payload,
            filters={
                "entity": gstr1_scope.entity_id,
                "entityfinid": gstr1_scope.entityfinid_id,
                "subentity": gstr1_scope.subentity_id,
                "month": gstr1_scope.month,
                "year": gstr1_scope.year,
                "from_date": gstr1_scope.from_date,
                "to_date": gstr1_scope.to_date,
            },
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": False,
            },
        )
        query = request.GET.copy()
        query.pop("page", None)
        query.pop("page_size", None)
        encoded = query.urlencode()
        response["actions"]["export_urls"] = {
            "excel": f"/api/reports/gst-exception-dashboard/export/?format=xlsx&{encoded}",
            "csv": f"/api/reports/gst-exception-dashboard/export/?format=csv&{encoded}",
            "json": f"/api/reports/gst-exception-dashboard/export/?format=json&{encoded}",
        }
        response["available_exports"] = ["excel", "csv", "json"]
        return Response(response)


class GstExceptionDashboardExportAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        export_format = (request.query_params.get("format") or "json").lower()
        gstr1_service = Gstr1ReportService()
        gstr3b_service = Gstr3bSummaryService()
        params = request.query_params.copy()
        params.pop("format", None)
        try:
            gstr1_scope = gstr1_service.build_scope(params)
            gstr3b_scope = gstr3b_service.build_scope(params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)

        self.enforce_scope(
            request,
            entity_id=gstr1_scope.entity_id,
            entityfinid_id=gstr1_scope.entityfinid_id,
            subentity_id=gstr1_scope.subentity_id,
        )
        gstr1_warnings = gstr1_service.validations(gstr1_scope)
        gstr3b_warnings = gstr3b_service.validations(gstr3b_scope)
        reconciliation = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
        )
        payload = build_gst_exception_dashboard(
            gstr1_warnings=gstr1_warnings,
            gstr3b_warnings=gstr3b_warnings,
            reconciliation_payload=reconciliation,
        )
        if export_format == "json":
            return Response(payload)

        headers = ["Source", "Severity", "Category", "Code / Label", "Affected Rows", "Reference", "Message / Note"]
        rows = []
        for row in payload["gstr1_exception_rows"]:
            rows.append(["GSTR-1", row["severity"], row["category"], row["code"], row["affected_rows"], row["sample_references"], row["message"]])
        for row in payload["gstr3b_exception_rows"]:
            rows.append(["GSTR-3B", row["severity"], row["category"], row["code"], row["affected_rows"], row["sample_references"], row["message"]])
        for row in payload["reconciliation_rows"]:
            rows.append([
                "Reconciliation",
                "error",
                "Reconciliation Gaps",
                row["label"],
                1,
                "-",
                f"Taxable diff {row['difference_taxable_value']}; Tax diff {row['difference_total_tax']}. {row['note']}".strip(),
            ])

        subtitle = f"Period: {gstr1_scope.from_date} to {gstr1_scope.to_date}"
        if export_format == "csv":
            return _file_response("GST_Exception_Dashboard.csv", _write_csv(headers, rows), "text/csv")
        if export_format == "xlsx":
            content = _write_excel(
                "GST Exception Dashboard",
                subtitle,
                headers,
                rows,
                numeric_columns={4},
            )
            return _file_response(
                "GST_Exception_Dashboard.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return Response({"detail": "Unsupported export format."}, status=400)


def _file_response(filename, content, content_type):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
