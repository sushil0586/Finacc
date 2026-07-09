from __future__ import annotations

import csv
from io import StringIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from reports.api.receivables_views import _write_excel
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
        assert_any_report_permission(
            user=request.user,
            entity_id=gstr1_scope.entity_id,
            required_permissions=("reports.gstr1_gstr3b_reconciliation.view",),
            message="You do not have permission to access the GSTR-1 vs GSTR-3B reconciliation report.",
        )
        payload = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
            scope_params={
                "entityfinid": gstr1_scope.entityfinid_id,
                "subentity": gstr1_scope.subentity_id,
                "from_date": gstr1_scope.from_date,
                "to_date": gstr1_scope.to_date,
            },
            gstr1_scope=gstr1_scope,
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
        assert_any_report_permission(
            user=request.user,
            entity_id=gstr1_scope.entity_id,
            required_permissions=("reports.gstr1_gstr3b_reconciliation.view",),
            message="You do not have permission to access the GSTR-1 vs GSTR-3B reconciliation report.",
        )
        payload = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
            scope_params={
                "entityfinid": gstr1_scope.entityfinid_id,
                "subentity": gstr1_scope.subentity_id,
                "from_date": gstr1_scope.from_date,
                "to_date": gstr1_scope.to_date,
            },
            gstr1_scope=gstr1_scope,
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
                _format_export_number(row["gstr1_taxable_value"]),
                _format_export_number(row["gstr3b_taxable_value"]),
                _format_export_number(row["difference_taxable_value"]),
                _format_export_number(row["gstr1_total_tax"]),
                _format_export_number(row["gstr3b_total_tax"]),
                _format_export_number(row["difference_total_tax"]),
                row.get("note") or "",
            ]
            for row in payload["rows"]
        ]
        total_row = _reconciliation_total_row(payload.get("rows") or [])
        generated_on = timezone.localtime().strftime("%d %b %Y %I:%M %p")
        subtitle = (
            f"Period: {_format_export_date(gstr1_scope.from_date)} to "
            f"{_format_export_date(gstr1_scope.to_date)} | "
            f"Generated on {generated_on}"
        )
        if export_format == "csv":
            stream = StringIO()
            writer = csv.writer(stream)
            writer.writerow(["Report", "GSTR-1 vs GSTR-3B Reconciliation"])
            writer.writerow(["Period", f"{_format_export_date(gstr1_scope.from_date)} to {_format_export_date(gstr1_scope.to_date)}"])
            writer.writerow(["Generated On", generated_on])
            writer.writerow([])
            writer.writerow(headers)
            writer.writerows(rows)
            if total_row:
                writer.writerow(total_row)
            return _file_response("GSTR1_vs_GSTR3B_Reconciliation.csv", stream.getvalue().encode("utf-8"), "text/csv")
        if export_format == "xlsx":
            content = _write_excel(
                "GSTR-1 vs GSTR-3B Reconciliation",
                subtitle,
                headers,
                rows,
                numeric_columns={2, 3, 4, 5, 6, 7},
                total_row=total_row,
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


def _format_export_date(value):
    if not value:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _format_export_number(value):
    try:
        return f"{float(value or 0):.2f}"
    except Exception:
        return "0.00"


def _reconciliation_total_row(rows: list[dict]) -> list[str] | None:
    if not rows:
        return None
    totals = {
        "gstr1_taxable_value": 0.0,
        "gstr3b_taxable_value": 0.0,
        "difference_taxable_value": 0.0,
        "gstr1_total_tax": 0.0,
        "gstr3b_total_tax": 0.0,
        "difference_total_tax": 0.0,
    }
    for row in rows:
        totals["gstr1_taxable_value"] += float(row.get("gstr1_taxable_value") or 0)
        totals["gstr3b_taxable_value"] += float(row.get("gstr3b_taxable_value") or 0)
        totals["difference_taxable_value"] += float(row.get("difference_taxable_value") or 0)
        totals["gstr1_total_tax"] += float(row.get("gstr1_total_tax") or 0)
        totals["gstr3b_total_tax"] += float(row.get("gstr3b_total_tax") or 0)
        totals["difference_total_tax"] += float(row.get("difference_total_tax") or 0)
    return [
        "Report Total",
        "",
        _format_export_number(totals["gstr1_taxable_value"]),
        _format_export_number(totals["gstr3b_taxable_value"]),
        _format_export_number(totals["difference_taxable_value"]),
        _format_export_number(totals["gstr1_total_tax"]),
        _format_export_number(totals["gstr3b_total_tax"]),
        _format_export_number(totals["difference_total_tax"]),
        "",
    ]
