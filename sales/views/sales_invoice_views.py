from __future__ import annotations

from decimal import Decimal
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.services.sales_invoice_service import SalesInvoiceService


class _SalesScopeMixin:
    permission_classes = [IsAuthenticated]
    line_mode = None  # None | "service" | "goods"

    @staticmethod
    def _scope_filters(request):
        payload = request.data if isinstance(getattr(request, "data", None), dict) else {}
        entity_id = request.query_params.get("entity_id") or payload.get("entity_id") or payload.get("entity")
        entityfinid_id = request.query_params.get("entityfinid_id") or request.query_params.get("entityfinid") or payload.get("entityfinid_id") or payload.get("entityfinid")
        subentity_id = request.query_params.get("subentity_id")
        if subentity_id is None:
            subentity_id = payload.get("subentity_id", payload.get("subentity"))

        filters = {}
        if entity_id:
            filters["entity_id"] = int(entity_id)
        if entityfinid_id:
            filters["entityfinid_id"] = int(entityfinid_id)
        if subentity_id is not None:
            parsed_subentity_id = int(subentity_id) if str(subentity_id).strip() else None
            if parsed_subentity_id == 0:
                parsed_subentity_id = None
            filters["subentity_id"] = parsed_subentity_id
        return filters

    def _scoped_queryset(self):
        qs = SalesInvoiceHeader.objects.filter(**self._scope_filters(self.request))
        line_mode = self._get_line_mode()
        if line_mode == "service":
            qs = qs.filter(lines__is_service=True).distinct()
        elif line_mode == "goods":
            qs = qs.filter(lines__is_service=False).distinct()
        return qs

    def _get_scoped_header(self, pk: int) -> SalesInvoiceHeader:
        return get_object_or_404(self._scoped_queryset(), pk=pk)

    def _get_line_mode(self) -> str | None:
        if self.line_mode in ("service", "goods"):
            return self.line_mode
        raw = (self.request.query_params.get("line_mode") or "").strip().lower()
        if raw in ("service", "goods"):
            return raw
        return None


class SalesInvoiceListCreateAPIView(_SalesScopeMixin, generics.ListCreateAPIView):
    serializer_class = SalesInvoiceHeaderSerializer

    def get_queryset(self):
        qs = (
            self._scoped_queryset()
            .select_related(
                "customer",
                "customer__ledger",
                "shipping_detail",              # ✅ new
                "shipping_detail__state",       # ✅ optional
                "shipping_detail__city",        # ✅ optional
                "shipto_snapshot",              # ✅ new (OneToOne)
            )
            .prefetch_related(
                Prefetch(
                    "lines",
                    queryset=SalesInvoiceLine.objects.select_related("product", "uom", "sales_account").order_by("line_no"),
                ),
                Prefetch("tax_summaries", queryset=SalesTaxSummary.objects.all()),
            )
            .order_by("-doc_no")
        )

        params = self.request.query_params

        entity_id = params.get("entity_id")
        entityfinid_id = params.get("entityfinid_id")
        subentity_id = params.get("subentity_id")
        if subentity_id == "0":
            subentity_id = None

        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        if entityfinid_id:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if "subentity_id" in params:
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

        line_mode = self._get_line_mode()
        if line_mode == "service":
            qs = qs.filter(lines__is_service=True).distinct()
        elif line_mode == "goods":
            qs = qs.filter(lines__is_service=False).distinct()

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["line_mode"] = self._get_line_mode()
        return ctx

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


class SalesInvoiceRetrieveUpdateAPIView(_SalesScopeMixin, generics.RetrieveUpdateAPIView):
    serializer_class = SalesInvoiceHeaderSerializer

    def get_queryset(self):
        lines_qs = SalesInvoiceLine.objects.select_related("product", "uom", "sales_account").order_by("line_no")

        return (
            self._scoped_queryset()
            .select_related(
                "customer",
                "customer__ledger",
                "shipping_detail",
                "shipping_detail__state",
                "shipping_detail__city",
                "shipto_snapshot",
            )
            .prefetch_related(
                Prefetch("lines", queryset=lines_qs),
                Prefetch("tax_summaries", queryset=SalesTaxSummary.objects.all()),
            )
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["line_mode"] = self._get_line_mode()
        return ctx

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        try:
            return super().partial_update(request, *args, **kwargs)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


class SalesServiceInvoiceListCreateAPIView(SalesInvoiceListCreateAPIView):
    line_mode = "service"


class SalesServiceInvoiceRetrieveUpdateAPIView(SalesInvoiceRetrieveUpdateAPIView):
    line_mode = "service"


class SalesInvoiceConfirmAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        try:
            header = SalesInvoiceService.confirm(header=header, user=request.user)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data, status=status.HTTP_200_OK)


class SalesInvoicePostAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        try:
            header = SalesInvoiceService.post(header=header, user=request.user)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data, status=status.HTTP_200_OK)


class SalesInvoiceCancelAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        reason = (request.data or {}).get("reason", "")
        try:
            header = SalesInvoiceService.cancel(header=header, user=request.user, reason=reason)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data, status=status.HTTP_200_OK)


class SalesInvoiceReverseAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        reason = (request.data or {}).get("reason", "")
        try:
            header = SalesInvoiceService.reverse_posting(header=header, user=request.user, reason=reason)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            detail = getattr(e, "message_dict", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data, status=status.HTTP_200_OK)


class SalesInvoiceSettlementAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        payload = request.data or {}
        settled_amount = payload.get("settled_amount")
        note = payload.get("note", "")
        if settled_amount is None:
            return Response({"settled_amount": "This field is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            header = SalesInvoiceService.apply_settlement(
                header=header,
                user=request.user,
                settled_amount=Decimal(str(settled_amount)),
                note=note,
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceHeaderSerializer(header, context={"request": request}).data, status=status.HTTP_200_OK)
