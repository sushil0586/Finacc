from __future__ import annotations

from rest_framework.response import Response

from reports.api.payables_views import (
    PAYABLE_DEFAULTS,
    _BasePayableAPIView,
    _BasePayableExportAPIView,
    _attach_payable_actions,
    _export_headers,
    _payable_scope_filters,
)
from reports.api.receivables_views import _write_csv, _write_excel, _write_pdf
from reports.schemas.common import build_report_envelope
from reports.schemas.payables_reports import (
    PayableClosePackScopeSerializer,
    PayableNoteRegisterScopeSerializer,
    PayableSettlementHistoryScopeSerializer,
    PayableVendorLedgerScopeSerializer,
)
from reports.services.payables_config import resolve_report_column_keys, resolve_report_columns
from reports.services.payables_operational import (
    build_payables_close_pack,
    build_vendor_ledger_statement,
    build_vendor_note_register,
    build_vendor_settlement_history_report,
    close_pack_export_rows,
)


def _column_values(row, keys):
    return [row.get(key) for key in keys]


class VendorLedgerStatementAPIView(_BasePayableAPIView):
    serializer_class = PayableVendorLedgerScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_vendor_ledger_statement(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            vendor_id=scope["vendor"],
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            include_opening=scope.get("include_opening", True),
            include_running_balance=scope.get("include_running_balance", True),
            include_settlement_drilldowns=scope.get("include_settlement_drilldowns", True),
            include_related_reports=scope.get("include_related_reports", True),
            include_trace=scope.get("include_trace", True),
        )
        response = build_report_envelope(
            report_code="vendor_ledger_statement",
            report_name="Vendor Ledger Statement",
            payload=payload,
            filters={**_payable_scope_filters(scope), "include_opening": scope.get("include_opening", True)},
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path="/api/reports/payables/vendor-ledger/"))


class VendorSettlementHistoryAPIView(_BasePayableAPIView):
    serializer_class = PayableSettlementHistoryScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_vendor_settlement_history_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            vendor_id=scope.get("vendor"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            settlement_type=scope.get("settlement_type"),
            include_unapplied=scope.get("include_unapplied", True),
            include_trace=scope.get("include_trace", True),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
        )
        response = build_report_envelope(
            report_code="vendor_settlement_history",
            report_name="Vendor Settlement History",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path="/api/reports/payables/settlement-history/"))


class VendorNoteRegisterAPIView(_BasePayableAPIView):
    serializer_class = PayableNoteRegisterScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        payload = build_vendor_note_register(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            vendor_id=scope.get("vendor"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            note_type=scope.get("note_type"),
            status=scope.get("status"),
            include_trace=scope.get("include_trace", True),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", PAYABLE_DEFAULTS["default_page_size"]),
        )
        response = build_report_envelope(
            report_code="vendor_note_register",
            report_name="Vendor Debit/Credit Note Register",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path="/api/reports/payables/note-register/"))


class PayablesClosePackAPIView(_BasePayableAPIView):
    serializer_class = PayableClosePackScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        include_sections = [
            code
            for code, enabled in [
                ("overview", scope.get("include_overview", True)),
                ("aging", scope.get("include_aging", True)),
                ("reconciliation", scope.get("include_reconciliation", True)),
                ("validation", scope.get("include_validation", True)),
                ("exceptions", scope.get("include_exceptions", True)),
                ("top_vendors", scope.get("include_top_vendors", True)),
            ]
            if enabled
        ]
        payload = build_payables_close_pack(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            include_sections=include_sections,
            include_top_vendors=scope.get("include_top_vendors", True),
            include_top_exceptions=scope.get("include_exceptions", True),
            expanded_validation=scope.get("expanded_validation", False),
        )
        response = build_report_envelope(
            report_code="payables_close_pack",
            report_name="Payables Close Pack",
            payload=payload,
            filters=_payable_scope_filters(scope),
            defaults=PAYABLE_DEFAULTS,
        )
        return Response(_attach_payable_actions(response, request, export_base_path="/api/reports/payables/close-pack/"))


class _VendorLedgerExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableVendorLedgerScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_vendor_ledger_statement(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            vendor_id=scope["vendor"],
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            include_opening=scope.get("include_opening", True),
            include_running_balance=scope.get("include_running_balance", True),
            include_settlement_drilldowns=scope.get("include_settlement_drilldowns", True),
            include_related_reports=scope.get("include_related_reports", True),
            include_trace=scope.get("include_trace", True),
        )
        feature_state = {
            "include_opening": scope.get("include_opening", True),
            "include_running_balance": scope.get("include_running_balance", True),
            "include_settlement_drilldowns": scope.get("include_settlement_drilldowns", True),
            "include_related_reports": scope.get("include_related_reports", True),
            "include_trace": scope.get("include_trace", True),
        }
        headers = _export_headers("vendor_ledger_statement", feature_state=feature_state)
        keys = resolve_report_column_keys("vendor_ledger_statement", enabled_features=feature_state, export=True)
        rows = [_column_values(row, keys) for row in data["rows"]]
        subtitle = f"Vendor: {data['vendor']['vendor_name']} | From: {data['from_date']} | To: {data['to_date']}"
        return scope, headers, rows, subtitle


class VendorLedgerStatementExcelAPIView(_VendorLedgerExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Vendor Ledger Statement", subtitle, headers, rows, numeric_columns={4, 5, 6})
        return self.export_response(filename=f"VendorLedger_{scope['vendor']}.xlsx", content=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class VendorLedgerStatementCSVAPIView(_VendorLedgerExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(filename=f"VendorLedger_{scope['vendor']}.csv", content=content, content_type="text/csv")


class VendorLedgerStatementPDFAPIView(_VendorLedgerExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Vendor Ledger Statement", subtitle, headers, rows)
        return self.export_response(filename=f"VendorLedger_{scope['vendor']}.pdf", content=content, content_type="application/pdf")


class VendorLedgerStatementPrintAPIView(VendorLedgerStatementPDFAPIView):
    export_mode = "inline"


class _VendorSettlementHistoryExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableSettlementHistoryScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_vendor_settlement_history_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            vendor_id=scope.get("vendor"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            settlement_type=scope.get("settlement_type"),
            include_unapplied=scope.get("include_unapplied", True),
            include_trace=scope.get("include_trace", True),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
        )
        feature_state = {
            "include_unapplied": scope.get("include_unapplied", True),
            "include_trace": scope.get("include_trace", True),
        }
        headers = _export_headers("vendor_settlement_history", feature_state=feature_state)
        keys = resolve_report_column_keys("vendor_settlement_history", enabled_features=feature_state, export=True)
        rows = [_column_values(row, keys) for row in data["rows"]]
        subtitle = f"Entity: {scope['entity']} | From: {scope.get('from_date')} | To: {scope.get('to_date')}"
        return scope, headers, rows, subtitle


class VendorSettlementHistoryExcelAPIView(_VendorSettlementHistoryExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Vendor Settlement History", subtitle, headers, rows, numeric_columns={7, 8})
        return self.export_response(filename=f"VendorSettlementHistory_Entity{scope['entity']}.xlsx", content=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class VendorSettlementHistoryCSVAPIView(_VendorSettlementHistoryExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(filename=f"VendorSettlementHistory_Entity{scope['entity']}.csv", content=content, content_type="text/csv")


class VendorSettlementHistoryPDFAPIView(_VendorSettlementHistoryExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Vendor Settlement History", subtitle, headers, rows)
        return self.export_response(filename=f"VendorSettlementHistory_Entity{scope['entity']}.pdf", content=content, content_type="application/pdf")


class VendorSettlementHistoryPrintAPIView(VendorSettlementHistoryPDFAPIView):
    export_mode = "inline"


class _VendorNoteRegisterExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableNoteRegisterScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_vendor_note_register(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            vendor_id=scope.get("vendor"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            note_type=scope.get("note_type"),
            status=scope.get("status"),
            include_trace=scope.get("include_trace", True),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
        )
        feature_state = {"include_trace": scope.get("include_trace", True)}
        headers = _export_headers("vendor_note_register", feature_state=feature_state)
        keys = resolve_report_column_keys("vendor_note_register", enabled_features=feature_state, export=True)
        rows = [_column_values(row, keys) for row in data["rows"]]
        subtitle = f"Entity: {scope['entity']} | From: {scope.get('from_date')} | To: {scope.get('to_date')}"
        return scope, headers, rows, subtitle


class VendorNoteRegisterExcelAPIView(_VendorNoteRegisterExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Vendor Debit Credit Note Register", subtitle, headers, rows, numeric_columns={6, 7, 8, 9})
        return self.export_response(filename=f"VendorNoteRegister_Entity{scope['entity']}.xlsx", content=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class VendorNoteRegisterCSVAPIView(_VendorNoteRegisterExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(filename=f"VendorNoteRegister_Entity{scope['entity']}.csv", content=content, content_type="text/csv")


class VendorNoteRegisterPDFAPIView(_VendorNoteRegisterExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Vendor Debit/Credit Note Register", subtitle, headers, rows)
        return self.export_response(filename=f"VendorNoteRegister_Entity{scope['entity']}.pdf", content=content, content_type="application/pdf")


class VendorNoteRegisterPrintAPIView(VendorNoteRegisterPDFAPIView):
    export_mode = "inline"


class _PayablesClosePackExportMixin(_BasePayableExportAPIView):
    serializer_class = PayableClosePackScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        include_sections = [
            code
            for code, enabled in [
                ("overview", scope.get("include_overview", True)),
                ("aging", scope.get("include_aging", True)),
                ("reconciliation", scope.get("include_reconciliation", True)),
                ("validation", scope.get("include_validation", True)),
                ("exceptions", scope.get("include_exceptions", True)),
                ("top_vendors", scope.get("include_top_vendors", True)),
            ]
            if enabled
        ]
        payload = build_payables_close_pack(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            include_sections=include_sections,
            include_top_vendors=scope.get("include_top_vendors", True),
            include_top_exceptions=scope.get("include_exceptions", True),
            expanded_validation=scope.get("expanded_validation", False),
        )
        rows = close_pack_export_rows(payload)
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')}"
        return scope, payload, rows, subtitle


class PayablesClosePackExcelAPIView(_PayablesClosePackExportMixin):
    def get(self, request):
        scope, _payload, rows, subtitle = self.report_data(request)
        headers = [column["label"] for column in resolve_report_columns("payables_close_pack", export=True)]
        content = _write_excel("Payables Close Pack", subtitle, headers, rows, numeric_columns={2})
        return self.export_response(filename=f"PayablesClosePack_Entity{scope['entity']}.xlsx", content=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class PayablesClosePackCSVAPIView(_PayablesClosePackExportMixin):
    def get(self, request):
        scope, _payload, rows, _subtitle = self.report_data(request)
        headers = [column["label"] for column in resolve_report_columns("payables_close_pack", export=True)]
        content = _write_csv(headers, rows)
        return self.export_response(filename=f"PayablesClosePack_Entity{scope['entity']}.csv", content=content, content_type="text/csv")


class PayablesClosePackPDFAPIView(_PayablesClosePackExportMixin):
    def get(self, request):
        scope, _payload, rows, subtitle = self.report_data(request)
        headers = [column["label"] for column in resolve_report_columns("payables_close_pack", export=True)]
        content = _write_pdf("Payables Close Pack", subtitle, headers, rows)
        return self.export_response(filename=f"PayablesClosePack_Entity{scope['entity']}.pdf", content=content, content_type="application/pdf")


class PayablesClosePackPrintAPIView(PayablesClosePackPDFAPIView):
    export_mode = "inline"
