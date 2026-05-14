from __future__ import annotations

from rest_framework.response import Response

from reports.api.payables_views import (
    PAYABLE_DEFAULTS,
    _BasePayableAPIView,
    _BasePayableExportAPIView,
    _attach_payable_actions,
    _payable_scope_filters,
)
from reports.api.receivables_views import _write_csv, _write_excel, _write_pdf
from reports.schemas.common import build_report_envelope
from reports.schemas.payables_reports import PayableReportScopeSerializer
from reports.services.payables_advanced import (
    build_ap_compliance_aging_report,
    build_ap_payment_forecast_report,
    build_duplicate_anomalous_bill_detection_report,
    build_grn_invoice_posting_exceptions_report,
    build_vendor_reconciliation_statement_report,
)


def _columns_and_rows(payload):
    meta = payload.get("_meta", {})
    columns = meta.get("available_columns") if isinstance(meta, dict) else []
    effective = set(meta.get("effective_columns") or [])
    selected = [column for column in columns if column.get("key") in effective] if columns and effective else columns
    if not selected:
        selected = [{"key": key, "label": key.replace("_", " ").title()} for key in (payload.get("rows", [{}])[0].keys() if payload.get("rows") else [])]
    headers = [column.get("label", column.get("key")) for column in selected]
    keys = [column.get("key") for column in selected]
    rows = [[row.get(key) for key in keys] for row in payload.get("rows", [])]
    return headers, rows


class _BaseAdvancedPayableReportAPIView(_BasePayableAPIView):
    serializer_class = PayableReportScopeSerializer
    report_code = ""
    report_name = ""
    export_base_path = ""

    def build_payload(self, request, scope):
        raise NotImplementedError

    def get(self, request):
        scope = self.get_scope(request)
        self.assert_report_permission(request, scope, self.report_code)
        payload = self.build_payload(request, scope)
        response = build_report_envelope(
            report_code=self.report_code,
            report_name=self.report_name,
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path=self.export_base_path))


class ApPaymentForecastAPIView(_BaseAdvancedPayableReportAPIView):
    report_code = "ap_payment_forecast"
    report_name = "AP Payment Forecast"
    export_base_path = "/api/reports/payables/ap-payment-forecast/"

    def build_payload(self, request, scope):
        return build_ap_payment_forecast_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            user=request.user,
        )


class VendorReconciliationStatementAPIView(_BaseAdvancedPayableReportAPIView):
    report_code = "vendor_reconciliation_statement"
    report_name = "Vendor Reconciliation Statement"
    export_base_path = "/api/reports/payables/vendor-reconciliation-statement/"

    def build_payload(self, request, scope):
        return build_vendor_reconciliation_statement_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            user=request.user,
        )


class GrnInvoicePostingExceptionsAPIView(_BaseAdvancedPayableReportAPIView):
    report_code = "grn_invoice_posting_exceptions"
    report_name = "GRN vs Invoice vs Posting Exceptions"
    export_base_path = "/api/reports/payables/grn-invoice-posting-exceptions/"

    def build_payload(self, request, scope):
        return build_grn_invoice_posting_exceptions_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            user=request.user,
        )


class ApComplianceAgingAPIView(_BaseAdvancedPayableReportAPIView):
    report_code = "ap_compliance_aging"
    report_name = "AP Compliance Aging"
    export_base_path = "/api/reports/payables/ap-compliance-aging/"

    def build_payload(self, request, scope):
        return build_ap_compliance_aging_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            user=request.user,
        )


class DuplicateAnomalousBillDetectionAPIView(_BaseAdvancedPayableReportAPIView):
    report_code = "duplicate_anomalous_bill_detection"
    report_name = "Duplicate / Anomalous Bill Detection"
    export_base_path = "/api/reports/payables/duplicate-anomalous-bill-detection/"

    def build_payload(self, request, scope):
        return build_duplicate_anomalous_bill_detection_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            user=request.user,
        )


class _BaseAdvancedPayableExportAPIView(_BasePayableExportAPIView):
    serializer_class = PayableReportScopeSerializer
    file_report_title = "Payables Report"

    def get_payload(self, request, scope):
        raise NotImplementedError

    def render_file(self, request, scope, payload):
        raise NotImplementedError

    def get(self, request):
        scope = self.get_scope(request)
        payload = self.get_payload(request, scope)
        return self.render_file(request, scope, payload)


class _AdvancedPayableExportMixin(_BaseAdvancedPayableExportAPIView):
    report_code = ""
    file_report_title = ""

    def get_payload(self, request, scope):
        raise NotImplementedError

    def _headers_rows(self, payload):
        return _columns_and_rows(payload)


def _build_export_classes(prefix, report_code, title, payload_builder):
    class Excel(_AdvancedPayableExportMixin):
        def get_payload(self, request, scope):
            return payload_builder(request, scope)

        def render_file(self, request, scope, payload):
            headers, rows = self._headers_rows(payload)
            content = _write_excel(title, title, headers, rows)
            return self.export_response(filename=f"{prefix}.xlsx", content=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    class CSV(_AdvancedPayableExportMixin):
        def get_payload(self, request, scope):
            return payload_builder(request, scope)

        def render_file(self, request, scope, payload):
            headers, rows = self._headers_rows(payload)
            content = _write_csv(headers, rows)
            return self.export_response(filename=f"{prefix}.csv", content=content, content_type="text/csv")

    class PDF(_AdvancedPayableExportMixin):
        def get_payload(self, request, scope):
            return payload_builder(request, scope)

        def render_file(self, request, scope, payload):
            headers, rows = self._headers_rows(payload)
            content = _write_pdf(title, title, headers, rows)
            return self.export_response(filename=f"{prefix}.pdf", content=content, content_type="application/pdf")

    class PRINT(PDF):
        export_mode = "inline"

    return Excel, CSV, PDF, PRINT


_ApPaymentForecastExcelAPIView, _ApPaymentForecastCSVAPIView, _ApPaymentForecastPDFAPIView, _ApPaymentForecastPrintAPIView = _build_export_classes(
    "ap_payment_forecast",
    "ap_payment_forecast",
    "AP Payment Forecast",
    lambda request, scope: build_ap_payment_forecast_report(
        entity_id=scope["entity"],
        entityfin_id=scope.get("entityfinid"),
        subentity_id=scope.get("subentity"),
        from_date=scope.get("from_date"),
        to_date=scope.get("to_date"),
        as_of_date=scope.get("as_of_date"),
        sort_by=scope.get("sort_by"),
        sort_order=scope.get("sort_order", "asc"),
        page=1,
        page_size=100000,
        user=request.user,
    ),
)
ApPaymentForecastExcelAPIView = _ApPaymentForecastExcelAPIView
ApPaymentForecastCSVAPIView = _ApPaymentForecastCSVAPIView
ApPaymentForecastPDFAPIView = _ApPaymentForecastPDFAPIView
ApPaymentForecastPrintAPIView = _ApPaymentForecastPrintAPIView


_VendorReconciliationStatementExcelAPIView, _VendorReconciliationStatementCSVAPIView, _VendorReconciliationStatementPDFAPIView, _VendorReconciliationStatementPrintAPIView = _build_export_classes(
    "vendor_reconciliation_statement",
    "vendor_reconciliation_statement",
    "Vendor Reconciliation Statement",
    lambda request, scope: build_vendor_reconciliation_statement_report(
        entity_id=scope["entity"],
        entityfin_id=scope.get("entityfinid"),
        subentity_id=scope.get("subentity"),
        from_date=scope.get("from_date"),
        to_date=scope.get("to_date"),
        as_of_date=scope.get("as_of_date"),
        search=scope.get("search"),
        sort_by=scope.get("sort_by"),
        sort_order=scope.get("sort_order", "desc"),
        page=1,
        page_size=100000,
        user=request.user,
    ),
)
VendorReconciliationStatementExcelAPIView = _VendorReconciliationStatementExcelAPIView
VendorReconciliationStatementCSVAPIView = _VendorReconciliationStatementCSVAPIView
VendorReconciliationStatementPDFAPIView = _VendorReconciliationStatementPDFAPIView
VendorReconciliationStatementPrintAPIView = _VendorReconciliationStatementPrintAPIView


_GrnInvoicePostingExceptionsExcelAPIView, _GrnInvoicePostingExceptionsCSVAPIView, _GrnInvoicePostingExceptionsPDFAPIView, _GrnInvoicePostingExceptionsPrintAPIView = _build_export_classes(
    "grn_invoice_posting_exceptions",
    "grn_invoice_posting_exceptions",
    "GRN vs Invoice vs Posting Exceptions",
    lambda request, scope: build_grn_invoice_posting_exceptions_report(
        entity_id=scope["entity"],
        entityfin_id=scope.get("entityfinid"),
        subentity_id=scope.get("subentity"),
        from_date=scope.get("from_date"),
        to_date=scope.get("to_date"),
        search=scope.get("search"),
        sort_by=scope.get("sort_by"),
        sort_order=scope.get("sort_order", "desc"),
        page=1,
        page_size=100000,
        user=request.user,
    ),
)
GrnInvoicePostingExceptionsExcelAPIView = _GrnInvoicePostingExceptionsExcelAPIView
GrnInvoicePostingExceptionsCSVAPIView = _GrnInvoicePostingExceptionsCSVAPIView
GrnInvoicePostingExceptionsPDFAPIView = _GrnInvoicePostingExceptionsPDFAPIView
GrnInvoicePostingExceptionsPrintAPIView = _GrnInvoicePostingExceptionsPrintAPIView


_ApComplianceAgingExcelAPIView, _ApComplianceAgingCSVAPIView, _ApComplianceAgingPDFAPIView, _ApComplianceAgingPrintAPIView = _build_export_classes(
    "ap_compliance_aging",
    "ap_compliance_aging",
    "AP Compliance Aging",
    lambda request, scope: build_ap_compliance_aging_report(
        entity_id=scope["entity"],
        entityfin_id=scope.get("entityfinid"),
        subentity_id=scope.get("subentity"),
        as_of_date=scope.get("as_of_date") or scope.get("to_date"),
        search=scope.get("search"),
        sort_by=scope.get("sort_by"),
        sort_order=scope.get("sort_order", "desc"),
        page=1,
        page_size=100000,
        user=request.user,
    ),
)
ApComplianceAgingExcelAPIView = _ApComplianceAgingExcelAPIView
ApComplianceAgingCSVAPIView = _ApComplianceAgingCSVAPIView
ApComplianceAgingPDFAPIView = _ApComplianceAgingPDFAPIView
ApComplianceAgingPrintAPIView = _ApComplianceAgingPrintAPIView


_DuplicateAnomalousBillDetectionExcelAPIView, _DuplicateAnomalousBillDetectionCSVAPIView, _DuplicateAnomalousBillDetectionPDFAPIView, _DuplicateAnomalousBillDetectionPrintAPIView = _build_export_classes(
    "duplicate_anomalous_bill_detection",
    "duplicate_anomalous_bill_detection",
    "Duplicate / Anomalous Bill Detection",
    lambda request, scope: build_duplicate_anomalous_bill_detection_report(
        entity_id=scope["entity"],
        entityfin_id=scope.get("entityfinid"),
        subentity_id=scope.get("subentity"),
        from_date=scope.get("from_date"),
        to_date=scope.get("to_date"),
        search=scope.get("search"),
        sort_by=scope.get("sort_by"),
        sort_order=scope.get("sort_order", "desc"),
        page=1,
        page_size=100000,
        user=request.user,
    ),
)
DuplicateAnomalousBillDetectionExcelAPIView = _DuplicateAnomalousBillDetectionExcelAPIView
DuplicateAnomalousBillDetectionCSVAPIView = _DuplicateAnomalousBillDetectionCSVAPIView
DuplicateAnomalousBillDetectionPDFAPIView = _DuplicateAnomalousBillDetectionPDFAPIView
DuplicateAnomalousBillDetectionPrintAPIView = _DuplicateAnomalousBillDetectionPrintAPIView

