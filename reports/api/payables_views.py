from __future__ import annotations

"""HTTP and export views for AP outstanding and aging reports."""

from django.http import HttpResponse
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.api.receivables_views import _write_csv, _write_excel, _write_pdf
from reports.schemas.common import build_report_envelope
from reports.schemas.payables_reports import PayableAgingScopeSerializer, PayableReportScopeSerializer
from reports.services.payables import build_ap_aging_report, build_payables_dashboard_summary, build_vendor_outstanding_report
from reports.services.payables_config import PAYABLE_REPORT_DEFAULTS, resolve_report_columns
from reports.services.payables_meta import build_payables_report_meta
from rbac.services import EffectivePermissionService


PAYABLE_DEFAULTS = PAYABLE_REPORT_DEFAULTS


def _export_headers(report_code, *, view=None, feature_state=None):
    return [
        column["label"]
        for column in resolve_report_columns(
            report_code,
            view=view,
            enabled_features=feature_state,
            export=True,
        )
    ]


def _payable_scope_filters(scope):
    return {
        "entity": scope["entity"],
        "entityfinid": scope.get("entityfinid"),
        "subentity": scope.get("subentity"),
        "from_date": scope.get("from_date"),
        "to_date": scope.get("to_date"),
        "as_of_date": scope.get("as_of_date"),
        "vendor": scope.get("vendor"),
        "vendor_group": scope.get("vendor_group"),
        "region": scope.get("region"),
        "currency": scope.get("currency"),
        "overdue_only": scope.get("overdue_only", False),
        "credit_limit_exceeded": scope.get("credit_limit_exceeded", False),
        "outstanding_gt": scope.get("outstanding_gt"),
        "reconcile_gl": scope.get("reconcile_gl", False),
        "search": scope.get("search"),
        "sort_by": scope.get("sort_by"),
        "sort_order": scope.get("sort_order", "desc"),
        "page": scope.get("page", 1),
        "page_size": scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
        "view": scope.get("view"),
        "settlement_type": scope.get("settlement_type"),
        "include_unapplied": scope.get("include_unapplied"),
        "note_type": scope.get("note_type"),
        "status": scope.get("status"),
        "include_trace": scope.get("include_trace", True),
    }


def _filtered_querydict(request, *, overrides=None, exclude=None):
    params = request.GET.copy()
    for key in exclude or []:
        params.pop(key, None)
    for key, value in (overrides or {}).items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    return params.urlencode()


def _attach_payable_actions(payload, request, *, export_base_path):
    query = _filtered_querydict(request, exclude=["page", "page_size"])
    payload["actions"]["can_print"] = True
    payload["actions"]["export_urls"] = {
        "excel": f"{export_base_path}excel/?{query}",
        "pdf": f"{export_base_path}pdf/?{query}",
        "csv": f"{export_base_path}csv/?{query}",
        "print": f"{export_base_path}print/?{query}",
    }
    payload["available_exports"] = ["excel", "pdf", "csv", "print"]
    return payload


class _BasePayableAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayableReportScopeSerializer

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = EffectivePermissionService.entity_for_user(request.user, scope["entity"])
        if not entity:
            raise PermissionDenied("You do not have access to this entity.")
        return scope

    def build_envelope(self, *, report_code, report_name, payload, scope, request, export_base_path):
        response = build_report_envelope(
            report_code=report_code,
            report_name=report_name,
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return _attach_payable_actions(response, request, export_base_path=export_base_path)


class VendorOutstandingReportAPIView(_BasePayableAPIView):
    serializer_class = PayableReportScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        data = build_vendor_outstanding_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            outstanding_gt=scope.get("outstanding_gt"),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            reconcile_gl=scope.get("reconcile_gl", False),
            include_trace=scope.get("include_trace", True),
        )
        return Response(
            self.build_envelope(
                report_code="vendor_outstanding",
                report_name="Vendor Outstanding Report",
                payload=data,
                scope=scope,
                request=request,
                export_base_path="/api/reports/payables/vendor-outstanding/",
            )
        )


class ApAgingReportAPIView(_BasePayableAPIView):
    serializer_class = PayableAgingScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        data = build_ap_aging_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            view=scope.get("view") or "summary",
            include_trace=scope.get("include_trace", True),
        )
        return Response(
            self.build_envelope(
                report_code="ap_aging",
                report_name="AP Aging Report",
                payload=data,
                scope=scope,
                request=request,
                export_base_path="/api/reports/payables/aging/",
            )
        )


class PayablesReportsMetaAPIView(_BasePayableAPIView):
    serializer_class = PayableReportScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        return Response(
            build_payables_report_meta(
                entity_id=scope["entity"],
                entityfinid_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )


class PayablesDashboardSummaryAPIView(_BasePayableAPIView):
    serializer_class = PayableReportScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_payables_dashboard_summary(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            search=scope.get("search"),
        )
        response = build_report_envelope(
            report_code="payables_dashboard_summary",
            report_name="Payables Dashboard Summary",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        response["actions"].update(
            {
                "can_export_excel": False,
                "can_export_pdf": False,
                "can_export_csv": False,
                "can_print": False,
            }
        )
        return Response(response)


class _BasePayableExportAPIView(_BasePayableAPIView):
    file_type = None
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


class _VendorOutstandingExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableReportScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_vendor_outstanding_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            outstanding_gt=scope.get("outstanding_gt"),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
            reconcile_gl=scope.get("reconcile_gl", False),
            include_trace=scope.get("include_trace", True),
        )
        rows = [
            [
                row["vendor_name"],
                row["vendor_code"],
                row["opening_balance"],
                row["bill_amount"],
                row["payment_amount"],
                row["credit_note"],
                row["net_outstanding"],
                row["overdue_amount"],
                row["unapplied_advance"],
                row["credit_limit"],
                row["credit_days"],
                row["last_bill_date"],
                row["last_payment_date"],
                row["currency"],
                row["gstin"],
            ]
            for row in data["rows"]
        ]
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')}"
        headers = _export_headers("vendor_outstanding")
        return scope, data, headers, rows, subtitle


class VendorOutstandingExcelAPIView(_VendorOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Vendor Outstanding", subtitle, headers, rows, numeric_columns=set(range(3, 12)))
        return self.export_response(
            filename=f"VendorOutstanding_Entity{scope['entity']}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class VendorOutstandingCSVAPIView(_VendorOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"VendorOutstanding_Entity{scope['entity']}.csv",
            content=content,
            content_type="text/csv",
        )


class VendorOutstandingPDFAPIView(_VendorOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Vendor Outstanding Report", subtitle, headers, rows)
        return self.export_response(
            filename=f"VendorOutstanding_Entity{scope['entity']}.pdf",
            content=content,
            content_type="application/pdf",
        )


class VendorOutstandingPrintAPIView(VendorOutstandingPDFAPIView):
    export_mode = "inline"


class _ApAgingExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableAgingScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_ap_aging_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
            view=scope.get("view") or "summary",
            include_trace=scope.get("include_trace", True),
        )
        if (scope.get("view") or "summary") == "invoice":
            rows = [
                [
                    row["vendor_name"],
                    row["vendor_code"],
                    row["bill_number"],
                    row["bill_date"],
                    row["due_date"],
                    row["credit_days"],
                    row["bill_amount"],
                    row["paid_amount"],
                    row["balance"],
                    row["current"],
                    row["bucket_1_30"],
                    row["bucket_31_60"],
                    row["bucket_61_90"],
                    row["bucket_90_plus"],
                    row["currency"],
                ]
                for row in data["rows"]
            ]
            title = "AP Aging Invoice Report"
            headers = _export_headers("ap_aging", view="invoice", feature_state={"view": "invoice"})
            numeric_columns = set(range(6, 15))
        else:
            rows = [
                [
                    row["vendor_name"],
                    row["vendor_code"],
                    row["outstanding"],
                    row["overdue_amount"],
                    row["current"],
                    row["bucket_1_30"],
                    row["bucket_31_60"],
                    row["bucket_61_90"],
                    row["bucket_90_plus"],
                    row["unapplied_advance"],
                    row["credit_limit"],
                    row["credit_days"],
                    row["last_payment_date"],
                    row["currency"],
                ]
                for row in data["rows"]
            ]
            title = "AP Aging Summary Report"
            headers = _export_headers("ap_aging", view="summary", feature_state={"view": "summary"})
            numeric_columns = set(range(3, 12))
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')} | View: {scope.get('view') or 'summary'}"
        return scope, headers, rows, subtitle, title, numeric_columns


class ApAgingExcelAPIView(_ApAgingExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle, title, numeric_columns = self.report_data(request)
        content = _write_excel(title, subtitle, headers, rows, numeric_columns=numeric_columns)
        return self.export_response(
            filename=f"ApAging_Entity{scope['entity']}_{scope.get('view') or 'summary'}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ApAgingCSVAPIView(_ApAgingExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle, _title, _numeric_columns = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"ApAging_Entity{scope['entity']}_{scope.get('view') or 'summary'}.csv",
            content=content,
            content_type="text/csv",
        )


class ApAgingPDFAPIView(_ApAgingExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle, title, _numeric_columns = self.report_data(request)
        content = _write_pdf(title, subtitle, headers, rows)
        return self.export_response(
            filename=f"ApAging_Entity{scope['entity']}_{scope.get('view') or 'summary'}.pdf",
            content=content,
            content_type="application/pdf",
        )


class ApAgingPrintAPIView(ApAgingPDFAPIView):
    export_mode = "inline"
