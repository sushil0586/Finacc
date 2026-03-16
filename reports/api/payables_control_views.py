from __future__ import annotations

"""HTTP and export views for payable control and close-validation reports."""

from django.http import HttpResponse
from rest_framework.response import Response

from reports.api.payables_views import (
    PAYABLE_DEFAULTS,
    _BasePayableAPIView,
    _BasePayableExportAPIView,
    _attach_payable_actions,
    _filtered_querydict,
    _payable_scope_filters,
)
from reports.api.receivables_views import _write_csv, _write_excel, _write_pdf
from reports.schemas.common import build_report_envelope
from reports.services.payables_config import resolve_report_columns
from reports.schemas.payables_reports import (
    PayableCloseValidationScopeSerializer,
    PayableControlScopeSerializer,
    PayableExceptionScopeSerializer,
)
from reports.services.payables_control import (
    build_ap_gl_reconciliation_report,
    build_payables_close_readiness_summary,
    build_payables_close_validation,
    build_vendor_balance_exception_report,
)




class ApGlReconciliationReportAPIView(_BasePayableAPIView):
    serializer_class = PayableControlScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_ap_gl_reconciliation_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            include_trace=scope.get("include_trace", True),
        )
        response = build_report_envelope(
            report_code="ap_gl_reconciliation",
            report_name="AP to GL Reconciliation Report",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path="/api/reports/payables/reconciliation/"))


class VendorBalanceExceptionReportAPIView(_BasePayableAPIView):
    serializer_class = PayableExceptionScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_vendor_balance_exception_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            search=scope.get("search"),
            min_amount=scope.get("min_amount"),
            overdue_days_gt=scope.get("overdue_days_gt"),
            stale_days_gt=scope.get("stale_days_gt"),
            include_negative_balances=(True if "include_negative_balances" not in scope else scope.get("include_negative_balances")),
            include_old_advances=(True if "include_old_advances" not in scope else scope.get("include_old_advances")),
            include_stale_vendors=(True if "include_stale_vendors" not in scope else scope.get("include_stale_vendors")),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
        )
        response = build_report_envelope(
            report_code="vendor_balance_exceptions",
            report_name="Vendor Balance Exception Report",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path="/api/reports/payables/exceptions/"))


class PayablesCloseValidationAPIView(_BasePayableAPIView):
    serializer_class = PayableCloseValidationScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_payables_close_validation(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
        )
        response = build_report_envelope(
            report_code="payables_close_validation",
            report_name="Payables Close Validation",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        response["actions"].update({
            "can_export_excel": False,
            "can_export_pdf": False,
            "can_export_csv": False,
            "can_print": False,
        })
        return Response(response)


class PayablesCloseReadinessSummaryAPIView(_BasePayableAPIView):
    serializer_class = PayableControlScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_payables_close_readiness_summary(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
        )
        response = build_report_envelope(
            report_code="payables_close_readiness_summary",
            report_name="Payables Close Readiness Summary",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        response["actions"].update({
            "can_export_excel": False,
            "can_export_pdf": False,
            "can_export_csv": False,
            "can_print": False,
        })
        return Response(response)


class _BasePayableControlExportAPIView(_BasePayableExportAPIView):
    def export_payload(self, request):
        raise NotImplementedError

    def export_query(self, request):
        return _filtered_querydict(request, exclude=["page", "page_size"])

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


class _ApGlReconciliationExportMixin(_BasePayableControlExportAPIView):
    serializer_class = PayableControlScopeSerializer

    def export_payload(self, request):
        scope = self.get_scope(request)
        data = build_ap_gl_reconciliation_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
            include_trace=scope.get("include_trace", True),
        )
        rows = [
            [
                row["vendor_name"],
                row["vendor_code"],
                row["open_invoice_balance"],
                row["unapplied_advance"],
                row["subledger_balance"],
                row["gl_balance"],
                row["difference_amount"],
                row["reconciliation_status"],
            ]
            for row in data["rows"]
        ]
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')}"
        headers = [column["label"] for column in resolve_report_columns("ap_gl_reconciliation", export=True)]
        return scope, data, headers, rows, subtitle


class ApGlReconciliationExcelAPIView(_ApGlReconciliationExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.export_payload(request)
        content = _write_excel("AP to GL Reconciliation", subtitle, headers, rows, numeric_columns={2, 3, 4, 5, 6})
        return self.export_response(
            filename=f"ApGlReconciliation_Entity{scope['entity']}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ApGlReconciliationCSVAPIView(_ApGlReconciliationExportMixin):
    def get(self, request):
        scope, _data, headers, rows, _subtitle = self.export_payload(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"ApGlReconciliation_Entity{scope['entity']}.csv",
            content=content,
            content_type="text/csv",
        )


class ApGlReconciliationPDFAPIView(_ApGlReconciliationExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.export_payload(request)
        content = _write_pdf("AP to GL Reconciliation Report", subtitle, headers, rows)
        return self.export_response(
            filename=f"ApGlReconciliation_Entity{scope['entity']}.pdf",
            content=content,
            content_type="application/pdf",
        )


class ApGlReconciliationPrintAPIView(ApGlReconciliationPDFAPIView):
    export_mode = "inline"


class _VendorBalanceExceptionsExportMixin(_BasePayableControlExportAPIView):
    serializer_class = PayableExceptionScopeSerializer

    def export_payload(self, request):
        scope = self.get_scope(request)
        data = build_vendor_balance_exception_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            vendor_id=scope.get("vendor"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            search=scope.get("search"),
            min_amount=scope.get("min_amount"),
            overdue_days_gt=scope.get("overdue_days_gt"),
            stale_days_gt=scope.get("stale_days_gt"),
            include_negative_balances=(True if "include_negative_balances" not in scope else scope.get("include_negative_balances")),
            include_old_advances=(True if "include_old_advances" not in scope else scope.get("include_old_advances")),
            include_stale_vendors=(True if "include_stale_vendors" not in scope else scope.get("include_stale_vendors")),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
        )
        rows = [
            [
                row["vendor_name"],
                row["vendor_code"],
                row["exception_type"],
                row["severity"],
                row["document_number"],
                row["amount"],
                row["age_days"],
                row["message"],
            ]
            for row in data["rows"]
        ]
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')}"
        headers = [column["label"] for column in resolve_report_columns("vendor_balance_exceptions", export=True)]
        return scope, data, headers, rows, subtitle


class VendorBalanceExceptionExcelAPIView(_VendorBalanceExceptionsExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.export_payload(request)
        content = _write_excel("Vendor Balance Exceptions", subtitle, headers, rows, numeric_columns={5, 6})
        return self.export_response(
            filename=f"VendorBalanceExceptions_Entity{scope['entity']}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class VendorBalanceExceptionCSVAPIView(_VendorBalanceExceptionsExportMixin):
    def get(self, request):
        scope, _data, headers, rows, _subtitle = self.export_payload(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"VendorBalanceExceptions_Entity{scope['entity']}.csv",
            content=content,
            content_type="text/csv",
        )


class VendorBalanceExceptionPDFAPIView(_VendorBalanceExceptionsExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.export_payload(request)
        content = _write_pdf("Vendor Balance Exception Report", subtitle, headers, rows)
        return self.export_response(
            filename=f"VendorBalanceExceptions_Entity{scope['entity']}.pdf",
            content=content,
            content_type="application/pdf",
        )


class VendorBalanceExceptionPrintAPIView(VendorBalanceExceptionPDFAPIView):
    export_mode = "inline"
