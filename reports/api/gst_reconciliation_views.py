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
from reports.services.gst_reconciliation import build_gstr1_vs_gstr3b_reconciliation
from reports.schemas.common import build_report_envelope
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class Gstr1VsGstr3bReconciliationAPIView(ScopedEntitlementMixin, APIView):
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
        payload = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
        )
        response = build_report_envelope(
            report_code="gstr1-vs-gstr3b-reconciliation",
            report_name="GSTR-1 vs GSTR-3B Reconciliation",
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
            "excel": f"/api/reports/gst-reconciliation/export/?format=xlsx&{encoded}",
            "csv": f"/api/reports/gst-reconciliation/export/?format=csv&{encoded}",
            "json": f"/api/reports/gst-reconciliation/export/?format=json&{encoded}",
        }
        response["available_exports"] = ["excel", "csv", "json"]
        return Response(response)


class Gstr1VsGstr3bReconciliationExportAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        export_format = (request.query_params.get("format") or "json").lower()
        gstr1_service = Gstr1ReportService()
        gstr3b_service = Gstr3bSummaryService()
        params = request.query_params.copy()
        if "format" in params:
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
        payload = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
        )
        if export_format == "json":
            return Response(payload)

        headers = [
            "Check",
            "Status",
            "GSTR-1 Taxable",
            "GSTR-3B Taxable",
            "Taxable Difference",
            "GSTR-1 Total Tax",
            "GSTR-3B Total Tax",
            "Tax Difference",
            "Note",
        ]
        rows = [
            [
                row["label"],
                row["status"],
                row["gstr1_taxable_value"],
                row["gstr3b_taxable_value"],
                row["difference_taxable_value"],
                row["gstr1_total_tax"],
                row["gstr3b_total_tax"],
                row["difference_total_tax"],
                row.get("note") or "",
            ]
            for row in payload["rows"]
        ]
        subtitle = f"Period: {gstr1_scope.from_date} to {gstr1_scope.to_date}"
        if export_format == "csv":
            return _file_response("GSTR1_vs_GSTR3B_Reconciliation.csv", _write_csv(headers, rows), "text/csv")
        if export_format == "xlsx":
            content = _write_excel(
                "GSTR-1 vs GSTR-3B Reconciliation",
                subtitle,
                headers,
                rows,
                numeric_columns={2, 3, 4, 5, 6, 7},
            )
            return _file_response(
                "GSTR1_vs_GSTR3B_Reconciliation.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return Response({"detail": "Unsupported export format."}, status=400)


def _file_response(filename, content, content_type):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
