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
from reports.services.payables import (
    build_ap_aging_report,
    build_payables_dashboard_summary,
    build_upcoming_payments_calendar_report,
    build_vendor_outstanding_report,
)
from reports.services.payables_config import PAYABLE_REPORT_DEFAULTS, get_payables_report_config, resolve_report_columns
from reports.services.payables_meta import build_payables_report_meta
from reports.services.report_preferences import list_user_report_preferences
from reports.selectors.financial import resolve_scope_names
from rbac.services import EffectivePermissionService


PAYABLE_DEFAULTS = PAYABLE_REPORT_DEFAULTS


def _export_headers(report_code, *, view=None, feature_state=None):
    headers = [
        column["label"]
        for column in resolve_report_columns(
            report_code,
            view=view,
            enabled_features=feature_state,
            export=True,
        )
    ]
    if headers:
        return headers

    if report_code == "vendor_outstanding":
        return [
            "Vendor Code",
            "Vendor Name",
            "Outstanding",
            "Not Due",
            "0-30",
            "31-60",
            "61-90",
            "91-180",
            "181+",
            "Oldest Due Date",
            "GSTIN",
            "Opening Balance",
            "Bill Amount",
            "Payment Amount",
            "Last Bill Date",
            "Last Payment Date",
        ]
    if report_code == "ap_aging" and (view or "summary") == "invoice":
        return ["Vendor", "Vendor Code", "Bill Number", "Bill Date", "Due Date", "Balance", "Current", "1-30", "31-60", "61-90", "90+"]
    if report_code == "ap_aging":
        return ["Vendor", "Vendor Code", "Outstanding", "Overdue", "Current", "1-30", "31-60", "61-90", "90+", "Unapplied Advance"]
    return ["Details"]


def _export_columns_from_report_meta(payload, *, fallback_keys):
    meta = payload.get("_meta") if isinstance(payload, dict) else {}
    available = meta.get("available_columns") if isinstance(meta, dict) else None
    effective = meta.get("effective_columns") if isinstance(meta, dict) else None
    if isinstance(available, list) and isinstance(effective, list):
        labels_by_key = {
            str(column.get("key")): str(column.get("label") or column.get("key"))
            for column in available
            if isinstance(column, dict) and column.get("key")
        }
        selected = [str(key) for key in effective if str(key) in labels_by_key]
        if selected:
            return [(key, labels_by_key[key]) for key in selected]
    return [(key, key.replace("_", " ").title()) for key in fallback_keys]


def _payable_scope_filters(scope):
    return {
        "entityfinid": scope.get("entityfinid"),
        "subentity": scope.get("subentity"),
        "from_date": scope.get("from_date"),
        "to_date": scope.get("to_date"),
        "as_of_date": scope.get("as_of_date"),
        "vendor": scope.get("vendor"),
        "vendor_ids": scope.get("vendor_ids"),
        "vendor_group": scope.get("vendor_group"),
        "region": scope.get("region"),
        "currency": scope.get("currency"),
        "gst_registered": scope.get("gst_registered"),
        "msme": scope.get("msme"),
        "voucher_type": scope.get("voucher_type"),
        "aging_basis": scope.get("aging_basis"),
        "overdue_only": scope.get("overdue_only", False),
        "show_overdue_only": scope.get("show_overdue_only", False),
        "show_not_due": scope.get("show_not_due", False),
        "include_zero_balance": scope.get("include_zero_balance", False),
        "include_credit_balances": scope.get("include_credit_balances", False),
        "include_advances_separately": scope.get("include_advances_separately", False),
        "show_settled": scope.get("show_settled", False),
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

    def get_permission_codes(self, request, scope):
        return EffectivePermissionService.permission_codes_for_user(request.user, scope["entity"])

    def assert_report_permission(self, request, scope, report_code, *, view=None):
        report = get_payables_report_config(report_code, view=view)
        if not report:
            return
        required_permission = report.get("required_permission")
        if not required_permission:
            return
        permission_codes = self.get_permission_codes(request, scope)
        if required_permission not in permission_codes:
            raise PermissionDenied("You do not have permission to access this report.")

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
        self.assert_report_permission(request, scope, "vendor_outstanding")
        data = build_vendor_outstanding_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            vendor_id=scope.get("vendor"),
            vendor_ids=scope.get("vendor_ids"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            gst_registered=scope.get("gst_registered"),
            msme=scope.get("msme"),
            voucher_type=scope.get("voucher_type"),
            aging_basis=scope.get("aging_basis") or "due_date",
            overdue_only=scope.get("overdue_only", False),
            show_overdue_only=scope.get("show_overdue_only", False),
            show_not_due=scope.get("show_not_due", False),
            include_zero_balance=scope.get("include_zero_balance", False),
            include_credit_balances=scope.get("include_credit_balances", False),
            include_advances_separately=scope.get("include_advances_separately", False),
            show_settled=scope.get("show_settled", False),
            outstanding_gt=scope.get("outstanding_gt"),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            view=scope.get("view") or "summary",
            reconcile_gl=scope.get("reconcile_gl", False),
            include_trace=scope.get("include_trace", True),
            user=request.user,
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
        self.assert_report_permission(request, scope, "ap_aging", view=scope.get("view") or "summary")
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
            user=request.user,
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
        permission_codes = self.get_permission_codes(request, scope)
        payload = build_payables_report_meta(
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            permission_codes=permission_codes,
        )
        if not payload.get("reports"):
            raise PermissionDenied("You do not have permission to access payables reports.")
        payload["user_preferences"] = list_user_report_preferences(
            user=request.user,
            entity_id=scope["entity"],
            report_codes=[row["code"] for row in payload["reports"]],
        )
        return Response(payload)


class PayablesDashboardSummaryAPIView(_BasePayableAPIView):
    serializer_class = PayableReportScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        self.assert_report_permission(request, scope, "payables_dashboard_summary")
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
            user=request.user,
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


class UpcomingPaymentsCalendarAPIView(_BasePayableAPIView):
    serializer_class = PayableReportScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        self.assert_report_permission(request, scope, "upcoming_payments_calendar")
        payload = build_upcoming_payments_calendar_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            vendor_id=scope.get("vendor"),
            vendor_ids=scope.get("vendor_ids"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            outstanding_gt=scope.get("outstanding_gt"),
            overdue_only=scope.get("overdue_only", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
            include_trace=scope.get("include_trace", True),
            user=request.user,
        )
        return Response(
            self.build_envelope(
                report_code="upcoming_payments_calendar",
                report_name="Upcoming Payments Calendar",
                payload=payload,
                scope=scope,
                request=request,
                export_base_path="/api/reports/payables/upcoming-payments-calendar/",
            )
        )


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
        self.assert_report_permission(request, scope, "vendor_outstanding")
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
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
            user=request.user,
        )
        fallback_keys = [
            "vendor_code",
            "vendor_name",
            "outstanding",
            "not_due",
            "bucket_0_30",
            "bucket_31_60",
            "bucket_61_90",
            "bucket_91_180",
            "bucket_181_plus",
            "oldest_due_date",
            "gstin",
            "opening_balance",
            "bill_amount",
            "payment_amount",
            "last_bill_date",
            "last_payment_date",
        ]
        columns = _export_columns_from_report_meta(data, fallback_keys=fallback_keys)
        rows = [[row.get(key, "") for key, _label in columns] for row in data["rows"]]
        subtitle = (
            f"Entity: {scope_names['entity_name'] or 'Selected entity'} | "
            f"Subentity: {scope_names['subentity_name'] or 'All subentities'} | "
            f"As of: {scope.get('as_of_date') or scope.get('to_date') or ''}"
        )
        headers = [label for _key, label in columns]
        return scope, data, headers, rows, subtitle


class VendorOutstandingExcelAPIView(_VendorOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.report_data(request)
        content = _write_excel(
            "Vendor Outstanding",
            subtitle,
            headers,
            rows,
            numeric_columns={2, 3, 4, 5, 6, 7, 8, 11, 12, 13},
        )
        return self.export_response(
            filename=f"VendorOutstanding_{scope.get('as_of_date') or scope.get('to_date') or 'report'}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class VendorOutstandingCSVAPIView(_VendorOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"VendorOutstanding_{scope.get('as_of_date') or scope.get('to_date') or 'report'}.csv",
            content=content,
            content_type="text/csv",
        )


class VendorOutstandingPDFAPIView(_VendorOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Vendor Outstanding Report", subtitle, headers, rows)
        return self.export_response(
            filename=f"VendorOutstanding_{scope.get('as_of_date') or scope.get('to_date') or 'report'}.pdf",
            content=content,
            content_type="application/pdf",
        )


class VendorOutstandingPrintAPIView(VendorOutstandingPDFAPIView):
    export_mode = "inline"


class _ApAgingExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableAgingScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        self.assert_report_permission(request, scope, "ap_aging", view=scope.get("view") or "summary")
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
            user=request.user,
        )
        if (scope.get("view") or "summary") == "invoice":
            fallback_keys = [
                "vendor_name",
                "vendor_code",
                "bill_number",
                "bill_date",
                "due_date",
                "credit_days",
                "bill_amount",
                "paid_amount",
                "balance",
                "current",
                "bucket_1_30",
                "bucket_31_60",
                "bucket_61_90",
                "bucket_90_plus",
                "currency",
            ]
            columns = _export_columns_from_report_meta(data, fallback_keys=fallback_keys)
            rows = [[row.get(key, "") for key, _label in columns] for row in data["rows"]]
            title = "AP Aging Invoice Report"
            headers = [label for _key, label in columns]
            numeric_fields = {"credit_days", "bill_amount", "paid_amount", "balance", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus"}
            numeric_columns = {index for index, (key, _label) in enumerate(columns) if key in numeric_fields}
        else:
            fallback_keys = [
                "vendor_name",
                "vendor_code",
                "outstanding",
                "overdue_amount",
                "current",
                "bucket_1_30",
                "bucket_31_60",
                "bucket_61_90",
                "bucket_90_plus",
                "unapplied_advance",
                "credit_limit",
                "credit_days",
                "last_payment_date",
                "currency",
            ]
            columns = _export_columns_from_report_meta(data, fallback_keys=fallback_keys)
            rows = [[row.get(key, "") for key, _label in columns] for row in data["rows"]]
            title = "AP Aging Summary Report"
            headers = [label for _key, label in columns]
            numeric_fields = {"outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_advance", "credit_limit", "credit_days"}
            numeric_columns = {index for index, (key, _label) in enumerate(columns) if key in numeric_fields}
        subtitle = f"As of: {scope.get('as_of_date') or scope.get('to_date')} | View: {scope.get('view') or 'summary'}"
        return scope, headers, rows, subtitle, title, numeric_columns


class ApAgingExcelAPIView(_ApAgingExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle, title, numeric_columns = self.report_data(request)
        content = _write_excel(title, subtitle, headers, rows, numeric_columns=numeric_columns)
        return self.export_response(
            filename=f"ApAging_{scope.get('view') or 'summary'}_{scope.get('as_of_date') or scope.get('to_date') or 'report'}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ApAgingCSVAPIView(_ApAgingExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle, _title, _numeric_columns = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"ApAging_{scope.get('view') or 'summary'}_{scope.get('as_of_date') or scope.get('to_date') or 'report'}.csv",
            content=content,
            content_type="text/csv",
        )


class ApAgingPDFAPIView(_ApAgingExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle, title, _numeric_columns = self.report_data(request)
        content = _write_pdf(title, subtitle, headers, rows)
        return self.export_response(
            filename=f"ApAging_{scope.get('view') or 'summary'}_{scope.get('as_of_date') or scope.get('to_date') or 'report'}.pdf",
            content=content,
            content_type="application/pdf",
        )


class ApAgingPrintAPIView(ApAgingPDFAPIView):
    export_mode = "inline"


class _UpcomingPaymentsCalendarExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableReportScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        self.assert_report_permission(request, scope, "upcoming_payments_calendar")
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        data = build_upcoming_payments_calendar_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            vendor_id=scope.get("vendor"),
            vendor_ids=scope.get("vendor_ids"),
            vendor_group=scope.get("vendor_group"),
            region_id=scope.get("region"),
            currency=scope.get("currency"),
            outstanding_gt=scope.get("outstanding_gt"),
            overdue_only=scope.get("overdue_only", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=1,
            page_size=100000,
            include_trace=scope.get("include_trace", True),
            user=request.user,
        )
        fallback_keys = [
            "vendor_name",
            "vendor_code",
            "bill_number",
            "bill_date",
            "due_date",
            "days_to_due",
            "payment_status",
            "balance",
            "currency",
            "branch",
            "reference",
        ]
        columns = _export_columns_from_report_meta(data, fallback_keys=fallback_keys)
        headers = [label for _key, label in columns]
        rows = [[row.get(key, "") for key, _label in columns] for row in data["rows"]]
        subtitle = (
            f"Entity: {scope_names['entity_name'] or 'Selected entity'} | "
            f"Subentity: {scope_names['subentity_name'] or 'All subentities'} | "
            f"Window: {data.get('from_date') or scope.get('from_date') or scope.get('as_of_date') or ''} to "
            f"{data.get('to_date') or scope.get('to_date') or ''}"
        )
        return scope, headers, rows, subtitle


class UpcomingPaymentsCalendarExcelAPIView(_UpcomingPaymentsCalendarExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_excel(
            "Upcoming Payments Calendar",
            subtitle,
            headers,
            rows,
            numeric_columns={5, 7},
        )
        return self.export_response(
            filename=f"UpcomingPaymentsCalendar_{scope.get('to_date') or scope.get('as_of_date') or 'report'}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class UpcomingPaymentsCalendarCSVAPIView(_UpcomingPaymentsCalendarExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"UpcomingPaymentsCalendar_{scope.get('to_date') or scope.get('as_of_date') or 'report'}.csv",
            content=content,
            content_type="text/csv",
        )


class UpcomingPaymentsCalendarPDFAPIView(_UpcomingPaymentsCalendarExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Upcoming Payments Calendar", subtitle, headers, rows)
        return self.export_response(
            filename=f"UpcomingPaymentsCalendar_{scope.get('to_date') or scope.get('as_of_date') or 'report'}.pdf",
            content=content,
            content_type="application/pdf",
        )


class UpcomingPaymentsCalendarPrintAPIView(UpcomingPaymentsCalendarPDFAPIView):
    export_mode = "inline"
