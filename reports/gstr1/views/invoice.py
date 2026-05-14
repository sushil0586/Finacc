from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from posting.models import Entry
from reports.schemas.common import build_report_envelope
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.views.utils import Gstr1ScopedReportMixin, scope_filters
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer


class Gstr1InvoiceDetailAPIView(Gstr1ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request, invoice_id):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        self.enforce_report_scope(request, scope)
        invoice = service.invoice_detail(scope, invoice_id)
        entry_filters = {
            "entity_id": scope.entity_id,
            "txn_id": invoice.id,
        }
        if scope.entityfinid_id:
            entry_filters["entityfin_id"] = scope.entityfinid_id
        if scope.subentity_id is not None:
            entry_filters["subentity_id"] = scope.subentity_id
        entry = Entry.objects.filter(**entry_filters).order_by("-id").first()
        posting_lookup = (
            {
                "entry_id": entry.id,
                "txn_id": entry.txn_id,
                "txn_type": entry.txn_type,
                "voucher_number": entry.voucher_no,
                "posting_date": entry.posting_date,
                "voucher_date": entry.voucher_date,
                "status": entry.status,
                "status_name": entry.get_status_display(),
                "source_module": "sales",
                "document_type": "sales_invoice",
                "document_id": invoice.id,
            }
            if entry
            else None
        )

        payload = {
            "invoice": SalesInvoiceHeaderSerializer(invoice, context={"request": request}).data,
            "posting_lookup": posting_lookup,
            "drilldowns": {
                "source_document": {
                    "drilldown_target": "sales_invoice_detail",
                    "label": "Open source invoice",
                    "document_type": "sales_invoice",
                    "document_id": invoice.id,
                    "drilldown_params": {
                        "id": invoice.id,
                        "entity": scope.entity_id,
                        "entityfinid": scope.entityfinid_id,
                        "subentity": scope.subentity_id,
                    },
                },
                "posting_detail": (
                    {
                        "drilldown_target": "journal_entry_detail",
                        "label": "Open posted voucher",
                        "entry_id": posting_lookup["entry_id"],
                        "voucher_number": posting_lookup.get("voucher_number"),
                        "posting_date": posting_lookup.get("posting_date"),
                        "query_params": {
                            "entity": scope.entity_id,
                            "entityfinid": scope.entityfinid_id,
                            "subentity": scope.subentity_id,
                        },
                    }
                    if posting_lookup
                    else None
                ),
            },
        }
        response = build_report_envelope(
            report_code="gstr1-invoice-detail",
            report_name="GSTR-1 Invoice Detail",
            payload=payload,
            filters=scope_filters(scope),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        return Response(response)
