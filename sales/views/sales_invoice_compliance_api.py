from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError

from sales.models import SalesInvoiceHeader
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.serializers.sales_compliance_serializers import (
    GenerateIRNActionSerializer,
    GenerateEWayActionSerializer,
)

from sales.services.sales_compliance_service import SalesComplianceService


class _InvoiceMixin:
    permission_classes = [IsAuthenticated]

    def _scope_filters(self):
        payload = self.request.data if isinstance(getattr(self.request, "data", None), dict) else {}
        entity_id = self.request.query_params.get("entity_id") or payload.get("entity_id") or payload.get("entity")
        entityfinid_id = self.request.query_params.get("entityfinid_id") or self.request.query_params.get("entityfinid") or payload.get("entityfinid_id") or payload.get("entityfinid")
        subentity_id = self.request.query_params.get("subentity_id")
        if subentity_id is None:
            subentity_id = payload.get("subentity_id", payload.get("subentity"))

        f = {}
        if entity_id:
            f["entity_id"] = int(entity_id)
        if entityfinid_id:
            f["entityfinid_id"] = int(entityfinid_id)
        if subentity_id is not None:
            f["subentity_id"] = int(subentity_id) if str(subentity_id).strip() else None
        return f

    def get_invoice(self) -> SalesInvoiceHeader:
        return get_object_or_404(
            SalesInvoiceHeader.objects.filter(**self._scope_filters()),
            pk=self.kwargs["pk"],
        )


class SalesInvoiceEnsureComplianceAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/ensure/
    Creates compliance artifact rows if missing.
    """
    serializer_class = SalesInvoiceHeaderSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()

        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            result = svc.ensure_rows()
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            einv = svc.generate_irn()
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

        try:
            result = SalesComplianceService.generate_eway(
                inv=invoice,
                entity=invoice.entity,
                req=ser.validated_data,
                created_by=request.user,
            )
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        http_status = status.HTTP_200_OK if result.get("status") == "SUCCESS" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)
