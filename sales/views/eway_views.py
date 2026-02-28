from __future__ import annotations

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status as http_status
import inspect


from sales.models import SalesInvoiceHeader
from sales.serializers.eway_serializers import (
    EWayPrefillResponseSerializer,
    GenerateEWayRequestSerializer,
)
from sales.services.sales_compliance_service import SalesComplianceService


class SalesInvoiceEWayPrefillAPIView(GenericAPIView):
    def get(self, request, id: int, *args, **kwargs):
        inv = (
            SalesInvoiceHeader.objects
            .select_related("customer", "einvoice_artifact")  # keep eway related later
            .prefetch_related("lines")
            .get(pk=id)
        )

        print("### DEBUG PREFILL ###")
        print("Service file:", inspect.getfile(SalesComplianceService))
        print("build_eway_prefill defined at:", SalesComplianceService.build_eway_prefill.__qualname__)
        print("_get_irn defined at:", getattr(SalesComplianceService, "_get_irn", None))

        # show first 300 chars of the running code
        try:
            print("build_eway_prefill src:", inspect.getsource(SalesComplianceService.build_eway_prefill)[:300])
        except Exception as e:
            print("cannot read build_eway_prefill source:", e)

        try:
            print("_get_irn src:", inspect.getsource(SalesComplianceService._get_irn)[:300])
        except Exception as e:
            print("cannot read _get_irn source:", e)

        payload = SalesComplianceService.build_eway_prefill(inv=inv, entity=inv.entity)
        return Response(payload)


class SalesInvoiceGenerateEWayAPIView(GenericAPIView):
    """
    POST /api/sales/sales-invoices/<id>/compliance/generate-eway/
    """
    serializer_class = GenerateEWayRequestSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = SalesInvoiceHeader.objects.select_related("customer").get(pk=id)
        entity = inv.entity

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        result = SalesComplianceService.generate_eway(
            inv=inv,
            entity=entity,
            req=ser.validated_data,
            created_by=request.user,
        )

        return Response(result, status=200)