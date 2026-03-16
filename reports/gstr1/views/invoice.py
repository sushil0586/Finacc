from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.views.utils import scope_filters
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer


class Gstr1InvoiceDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request, invoice_id):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        invoice = service.invoice_detail(scope, invoice_id)
        payload = {
            "invoice": SalesInvoiceHeaderSerializer(invoice, context={"request": request}).data,
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
