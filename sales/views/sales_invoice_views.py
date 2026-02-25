from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.services.sales_invoice_service import SalesInvoiceService


class SalesInvoiceListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = SalesInvoiceHeaderSerializer

    def get_queryset(self):
        qs = (
            SalesInvoiceHeader.objects.all()
            .select_related("customer")
            .prefetch_related(
                Prefetch("lines", queryset=SalesInvoiceLine.objects.select_related("product", "uom").order_by("line_no")),
                Prefetch("tax_summaries", queryset=SalesTaxSummary.objects.all()),
            )
            .order_by("-doc_no")
        )

        # Basic filters (extend like purchase filters)
        params = self.request.query_params

        entity_id = params.get("entity_id")
        entityfinid_id = params.get("entityfinid_id")
        subentity_id = params.get("subentity_id")

        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        if entityfinid_id:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            # treat empty as NULL
            qs = qs.filter(subentity_id=subentity_id or None)

        if params.get("doc_type"):
            qs = qs.filter(doc_type=params["doc_type"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("customer_id"):
            qs = qs.filter(customer_id=params["customer_id"])

        if params.get("bill_date_from"):
            qs = qs.filter(bill_date__gte=params["bill_date_from"])
        if params.get("bill_date_to"):
            qs = qs.filter(bill_date__lte=params["bill_date_to"])

        search = params.get("search")
        if search:
            qs = qs.filter(invoice_number__icontains=search)

        return qs


class SalesInvoiceRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = SalesInvoiceHeaderSerializer

    def get_queryset(self):
        return (
            SalesInvoiceHeader.objects.all()
            .select_related("customer")
            .prefetch_related(
                Prefetch("lines", queryset=SalesInvoiceLine.objects.select_related("product", "uom").order_by("line_no")),
                Prefetch("tax_summaries", queryset=SalesTaxSummary.objects.all()),
            )
        )


class SalesInvoiceConfirmAPIView(APIView):
    def post(self, request, pk: int):
        header = SalesInvoiceHeader.objects.get(pk=pk)
        header = SalesInvoiceService.confirm(header=header, user=request.user)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data)


class SalesInvoicePostAPIView(APIView):
    def post(self, request, pk: int):
        header = SalesInvoiceHeader.objects.get(pk=pk)
        header = SalesInvoiceService.post(header=header, user=request.user)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data)


class SalesInvoiceCancelAPIView(APIView):
    def post(self, request, pk: int):
        header = SalesInvoiceHeader.objects.get(pk=pk)
        reason = (request.data or {}).get("reason", "")
        header = SalesInvoiceService.cancel(header=header, user=request.user, reason=reason)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data, status=status.HTTP_200_OK)
