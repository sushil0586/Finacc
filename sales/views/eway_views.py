from __future__ import annotations

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from sales.models import SalesInvoiceHeader
from sales.serializers.eway_serializers import (
    GenerateEWayRequestSerializer,
)
from sales.services.sales_compliance_service import SalesComplianceService


class SalesInvoiceEWayPrefillAPIView(GenericAPIView):
    """
    B2B (IRN-based) EWB prefill.
    GET /api/sales/sales-invoices/<id>/compliance/eway-prefill/
    """
    def get(self, request, id: int, *args, **kwargs):
        inv = (
            SalesInvoiceHeader.objects
            .select_related("customer", "entity", "einvoice_artifact", "eway_artifact")
            .prefetch_related("lines")
            .get(pk=id)
        )
        payload = SalesComplianceService().eway_prefill(inv)  # uses your existing IRN-based logic
        return Response(payload, status=200)


class SalesInvoiceGenerateEWayAPIView(GenericAPIView):
    """
    B2B (IRN-based) EWB generate.
    POST /api/sales/sales-invoices/<id>/compliance/generate-eway/
    """
    serializer_class = GenerateEWayRequestSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = (
            SalesInvoiceHeader.objects
            .select_related("customer", "entity", "einvoice_artifact", "eway_artifact")
            .prefetch_related("lines")
            .get(pk=id)
        )

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        result = SalesComplianceService.generate_eway(
            inv=inv,
            entity=inv.entity,
            req=ser.validated_data,
            created_by=request.user,
        )
        return Response(result, status=200)


class SalesInvoiceEWayB2CPrefillAPIView(GenericAPIView):
    """
    B2C Direct EWB prefill (no IRN).
    GET /api/sales/sales-invoices/<id>/compliance/eway-b2c-prefill/
    """
    def get(self, request, id: int, *args, **kwargs):
        inv = (
            SalesInvoiceHeader.objects
            .select_related("entity", "ship_to_snapshot", "eway_artifact")
            .prefetch_related("lines")
            .get(pk=id)
        )

        if str(inv.supply_category).upper() != "B2C":
            return Response(
                {"eligible": False, "reason": "Invoice is not B2C.", "invoice_id": inv.id},
                status=200,
            )

        payload = SalesComplianceService().eway_prefill_b2c(inv)
        return Response(payload, status=200)


class SalesInvoiceEWayB2CGenerateAPIView(GenericAPIView):
    """
    B2C Direct EWB generate (no IRN).
    POST /api/sales/sales-invoices/<id>/compliance/generate-eway-b2c/
    Body: {}  (optional) or you can keep your existing serializer if you want.
    """
    def post(self, request, id: int, *args, **kwargs):
        inv = (
            SalesInvoiceHeader.objects
            .select_related("entity", "ship_to_snapshot", "eway_artifact")
            .prefetch_related("lines")
            .get(pk=id)
        )

        if str(inv.supply_category).upper() != "B2C":
            return Response(
                {"status": "FAILED", "error_message": "Only B2C invoices allowed here."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            out = SalesComplianceService().eway_generate_b2c(inv, user=request.user)
        except Exception as e:
            return Response(
                {"status": "FAILED", "error_message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        http = status.HTTP_200_OK if out.get("status") == "SUCCESS" else status.HTTP_400_BAD_REQUEST
        return Response(out, status=http)