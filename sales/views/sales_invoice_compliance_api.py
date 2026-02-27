from __future__ import annotations

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from sales.models import SalesInvoiceHeader
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.serializers.sales_compliance_serializers import (
    GenerateIRNActionSerializer,
    GenerateEWayActionSerializer,
)

from sales.services.sales_compliance_service import SalesComplianceService


class _InvoiceMixin:
    permission_classes = [IsAuthenticated]

    def get_invoice(self) -> SalesInvoiceHeader:
        # Add your entity scope filters here (entity/entityfin/subentity) if you already enforce that
        return SalesInvoiceHeader.objects.get(pk=self.kwargs["pk"])


class SalesInvoiceEnsureComplianceAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/ensure/
    Creates compliance artifact rows if missing.
    """
    serializer_class = SalesInvoiceHeaderSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()

        svc = SalesComplianceService(invoice=invoice, user=request.user)
        result = svc.ensure_rows()

        data = self.get_serializer(invoice).data
        return Response({"ok": True, "result": result, "invoice": data}, status=status.HTTP_200_OK)


class SalesInvoiceGenerateIRNAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/generate-irn/
    Body: {}
    """
    serializer_class = GenerateIRNActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        svc = SalesComplianceService(invoice=invoice, user=request.user)
        einv = svc.generate_irn()

        invoice_data = SalesInvoiceHeaderSerializer(invoice).data
        return Response(
            {"ok": True, "einvoice_id": einv.id, "status": einv.status, "invoice": invoice_data},
            status=status.HTTP_200_OK,
        )


class SalesInvoiceGenerateEWayAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/generate-eway/
    Body: transport details
    """
    serializer_class = GenerateEWayActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # We'll wire real E-Way provider after IRN is live.
        return Response(
            {"ok": False, "error": "EWAY_NOT_WIRED_YET", "message": "E-Way generation will be enabled next."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )