from __future__ import annotations

from decimal import Decimal
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from rbac.services import EffectivePermissionService
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer, SalesInvoiceListSerializer
from sales.services.sales_invoice_service import SalesInvoiceService


def _resolve_sales_doc_type(raw_doc_type) -> int:
    try:
        return int(raw_doc_type or SalesInvoiceHeader.DocType.TAX_INVOICE)
    except (TypeError, ValueError):
        return int(SalesInvoiceHeader.DocType.TAX_INVOICE)


def _sales_permission_prefix(raw_doc_type) -> str:
    doc_type = _resolve_sales_doc_type(raw_doc_type)
    if doc_type == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
        return "sales.credit_note"
    if doc_type == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
        return "sales.debit_note"
    return "sales.invoice"


def require_sales_request_permission(*, user, entity_id: int, doc_type, action: str):
    entity = EffectivePermissionService.entity_for_user(user, int(entity_id))
    if entity is None:
        raise PermissionDenied({"detail": "Entity not found or inaccessible."})

    permission_code = f"{_sales_permission_prefix(doc_type)}.{action}"
    permission_codes = EffectivePermissionService.permission_codes_for_user(user, int(entity_id))
    if permission_code not in permission_codes:
        if action == "update" and "sales.invoice.edit" in permission_codes:
            return
        raise PermissionDenied({"detail": f"Missing permission: {permission_code}"})


class _SalesScopeMixin:
    permission_classes = [IsAuthenticated]
    line_mode = None  # None | "service" | "goods"

    def _serialize_invoice(self, header: SalesInvoiceHeader):
        return SalesInvoiceHeaderSerializer(
            header,
            context={"request": self.request, "line_mode": self._get_line_mode()},
        ).data

    @staticmethod
    def _error_payload(exc):
        detail = getattr(exc, "detail", None)
        if detail is not None:
            return detail
        message_dict = getattr(exc, "message_dict", None)
        if message_dict is not None:
            return message_dict
        return {"detail": str(exc)}

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
        scope_filters = self._scope_filters(self.request)
        entity_id = scope_filters.get("entity_id")
        if entity_id:
            require_sales_request_permission(
                user=self.request.user,
                entity_id=entity_id,
                doc_type=self.request.query_params.get("doc_type"),
                action="view",
            )
        qs = (
            self._scoped_queryset()
            .select_related(
                "customer",
                "customer__ledger",
                "subentity",
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

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = SalesInvoiceListSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["line_mode"] = self._get_line_mode()
        return ctx

    def create(self, request, *args, **kwargs):
        payload = request.data if isinstance(getattr(request, "data", None), dict) else {}
        entity_id = payload.get("entity_id", payload.get("entity"))
        if entity_id in (None, "", "null"):
            raise DRFValidationError({"detail": "entity is required."})
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError):
            raise DRFValidationError({"detail": "entity must be an integer."})

        require_sales_request_permission(
            user=request.user,
            entity_id=entity_id,
            doc_type=payload.get("doc_type"),
            action="create",
        )
        try:
            return super().create(request, *args, **kwargs)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)


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

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        require_sales_request_permission(
            user=request.user,
            entity_id=instance.entity_id,
            doc_type=instance.doc_type,
            action="view",
        )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        require_sales_request_permission(
            user=request.user,
            entity_id=instance.entity_id,
            doc_type=instance.doc_type,
            action="update",
        )
        try:
            return super().update(request, *args, **kwargs)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        require_sales_request_permission(
            user=request.user,
            entity_id=instance.entity_id,
            doc_type=instance.doc_type,
            action="update",
        )
        try:
            return super().partial_update(request, *args, **kwargs)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        require_sales_request_permission(
            user=request.user,
            entity_id=instance.entity_id,
            doc_type=instance.doc_type,
            action="delete",
        )
        return super().destroy(request, *args, **kwargs)


class SalesServiceInvoiceListCreateAPIView(SalesInvoiceListCreateAPIView):
    line_mode = "service"


class SalesServiceInvoiceRetrieveUpdateAPIView(SalesInvoiceRetrieveUpdateAPIView):
    line_mode = "service"


class SalesInvoiceConfirmAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="confirm",
        )
        try:
            header = SalesInvoiceService.confirm(header=header, user=request.user)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize_invoice(header), status=status.HTTP_200_OK)


class SalesInvoicePostAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="post",
        )
        try:
            header = SalesInvoiceService.post(header=header, user=request.user)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize_invoice(header), status=status.HTTP_200_OK)


class SalesInvoiceCancelAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="cancel",
        )
        reason = (request.data or {}).get("reason", "")
        try:
            header = SalesInvoiceService.cancel(header=header, user=request.user, reason=reason)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize_invoice(header), status=status.HTTP_200_OK)


class SalesInvoiceReverseAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="unpost",
        )
        reason = (request.data or {}).get("reason", "")
        try:
            header = SalesInvoiceService.reverse_posting(header=header, user=request.user, reason=reason)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize_invoice(header), status=status.HTTP_200_OK)


class SalesInvoiceSettlementAPIView(_SalesScopeMixin, APIView):
    def post(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="update",
        )
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
            return Response(self._error_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize_invoice(header), status=status.HTTP_200_OK)
