from __future__ import annotations

from decimal import Decimal
from typing import Any
from django.db.models import Exists, OuterRef, Prefetch
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Entity
from financial.profile_access import account_pan, account_primary_bank_detail
from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary, SalesInvoiceTransportSnapshot
from rbac.services import EffectivePermissionService
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer, SalesInvoiceListSerializer
from sales.serializers.sales_transport_serializers import SalesInvoiceTransportSnapshotSerializer
from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_settings_service import SalesSettingsService


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
        return self._apply_line_mode_filter(qs)

    def _get_scoped_header(self, pk: int) -> SalesInvoiceHeader:
        return get_object_or_404(self._scoped_queryset(), pk=pk)

    def _get_line_mode(self) -> str | None:
        if self.line_mode in ("service", "goods"):
            return self.line_mode
        raw = (self.request.query_params.get("line_mode") or "").strip().lower()
        if raw in ("service", "goods"):
            return raw
        return None

    def _apply_line_mode_filter(self, qs):
        line_mode = self._get_line_mode()
        if line_mode not in ("service", "goods"):
            return qs
        desired_is_service = line_mode == "service"
        matching_lines = SalesInvoiceLine.objects.filter(
            header_id=OuterRef("pk"),
            is_service=desired_is_service,
        )
        return qs.annotate(_line_mode_match=Exists(matching_lines)).filter(_line_mode_match=True)


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
            .select_related("customer", "customer__ledger", "subentity")
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

        return qs.select_related(None).select_related(
            "customer",
            "customer__ledger",
            "subentity",
        ).only(
            "id",
            "doc_code",
            "doc_type",
            "invoice_number",
            "status",
            "customer_id",
            "customer_name",
            "bill_date",
            "grand_total",
            "outstanding_amount",
            "subentity_id",
            "location_id",
            "customer__accountname",
            "customer__ledger_id",
            "customer__ledger__ledger_code",
            "customer__ledger__name",
            "subentity__subentityname",
        )

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


class SalesInvoiceTransportAPIView(_SalesScopeMixin, APIView):
    @staticmethod
    def _date_str(value: Any) -> str:
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value or "")

    def _to_transport_payload(self, source_obj: Any | None, *, source: str) -> dict:
        if source_obj is None:
            return {
                "transporter_id": "",
                "transporter_name": "",
                "transport_mode": None,
                "vehicle_no": "",
                "vehicle_type": "",
                "lr_gr_no": "",
                "lr_gr_date": None,
                "distance_km": None,
                "dispatch_through": "",
                "driver_name": "",
                "driver_mobile": "",
                "remarks": "",
                "source": source,
            }

        if isinstance(source_obj, SalesInvoiceTransportSnapshot):
            payload = SalesInvoiceTransportSnapshotSerializer(source_obj).data
            payload["source"] = payload.get("source") or source
            return payload

        return {
            "transporter_id": (getattr(source_obj, "transporter_id", None) or "").strip(),
            "transporter_name": (getattr(source_obj, "transporter_name", None) or "").strip(),
            "transport_mode": getattr(source_obj, "transport_mode", None),
            "vehicle_no": (getattr(source_obj, "vehicle_no", None) or "").strip(),
            "vehicle_type": (getattr(source_obj, "vehicle_type", None) or "").strip().upper(),
            "lr_gr_no": (getattr(source_obj, "doc_no", None) or "").strip(),
            "lr_gr_date": self._date_str(getattr(source_obj, "doc_date", None)),
            "distance_km": getattr(source_obj, "distance_km", None),
            "dispatch_through": "",
            "driver_name": "",
            "driver_mobile": "",
            "remarks": "",
            "source": source,
        }

    def get(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="view",
        )

        transport_snapshot = getattr(header, "transport_snapshot", None)
        if transport_snapshot is not None:
            transport = self._to_transport_payload(transport_snapshot, source="snapshot")
            return Response(
                {
                    "invoice_id": header.id,
                    "has_snapshot": True,
                    "transport": transport,
                },
                status=status.HTTP_200_OK,
            )

        eway_artifact = getattr(header, "eway_artifact", None)
        transport = self._to_transport_payload(eway_artifact, source="eway_prefill" if eway_artifact else "none")
        return Response(
            {
                "invoice_id": header.id,
                "has_snapshot": False,
                "transport": transport,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="update",
        )

        payload = request.data if isinstance(getattr(request, "data", None), dict) else {}
        transport_payload = payload.get("transport") if isinstance(payload.get("transport"), dict) else payload
        if not isinstance(transport_payload, dict):
            raise DRFValidationError({"detail": "transport payload must be an object."})

        transport_snapshot = getattr(header, "transport_snapshot", None)
        serializer = SalesInvoiceTransportSnapshotSerializer(
            transport_snapshot,
            data=transport_payload,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        if transport_snapshot is None:
            transport_snapshot = serializer.save(
                invoice=header,
                created_by=request.user,
                updated_by=request.user,
            )
        else:
            transport_snapshot = serializer.save(updated_by=request.user)

        return Response(
            {
                "invoice_id": header.id,
                "has_snapshot": True,
                "transport": SalesInvoiceTransportSnapshotSerializer(transport_snapshot).data,
            },
            status=status.HTTP_200_OK,
        )


class SalesInvoicePrintAPIView(_SalesScopeMixin, APIView):
    @staticmethod
    def _dec(value: Any) -> Decimal:
        if value in (None, ""):
            return Decimal("0.00")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0.00")

    @staticmethod
    def _date_str(value: Any) -> str:
        if hasattr(value, "strftime"):
            return value.strftime("%d-%m-%Y")
        return str(value or "")

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    def _resolve_transport_for_print(self, header: SalesInvoiceHeader) -> dict[str, str]:
        transport_snapshot = getattr(header, "transport_snapshot", None)
        eway_artifact = getattr(header, "eway_artifact", None)

        transportname = ""
        vehicle = ""
        grno = ""

        if transport_snapshot is not None:
            transportname = (
                self._text(getattr(transport_snapshot, "transporter_name", None))
                or self._text(getattr(transport_snapshot, "transporter_id", None))
            )
            vehicle = self._text(getattr(transport_snapshot, "vehicle_no", None))
            grno = self._text(getattr(transport_snapshot, "lr_gr_no", None))

        if not transportname and eway_artifact is not None:
            transportname = (
                self._text(getattr(eway_artifact, "transporter_name", None))
                or self._text(getattr(eway_artifact, "transporter_id", None))
            )
        if not vehicle and eway_artifact is not None:
            vehicle = self._text(getattr(eway_artifact, "vehicle_no", None))
        if not grno and eway_artifact is not None:
            grno = self._text(getattr(eway_artifact, "doc_no", None))

        return {
            "transportname": transportname,
            "vehicle": vehicle,
            "grno": grno,
        }

    def _build_payload(self, header: SalesInvoiceHeader) -> dict:
        seller = SalesSettingsService.get_seller_profile(entity_id=header.entity_id, subentity_id=header.subentity_id)
        entity_obj = Entity.objects.filter(id=header.entity_id).select_related("tax_profile").first()

        line_mode = self._get_line_mode()
        all_lines = list(
            SalesInvoiceLine.objects.filter(header_id=header.id).select_related("product", "uom", "sales_account").order_by("line_no")
        )
        if line_mode in ("service", "goods"):
            desired_is_service = line_mode == "service"
            all_lines = [row for row in all_lines if bool(getattr(row, "is_service", False)) == desired_is_service]

        sale_invoice_details = []
        total_qty = Decimal("0.000")
        for row in all_lines:
            qty = self._dec(getattr(row, "qty", 0))
            rate = self._dec(getattr(row, "rate", 0))
            discount_percent = self._dec(getattr(row, "discount_percent", 0))
            taxable_value = self._dec(getattr(row, "taxable_value", 0))
            effective_rate = (taxable_value / qty) if qty > 0 else rate
            product_obj = getattr(row, "product", None)
            sales_account = getattr(row, "sales_account", None)
            sale_invoice_details.append(
                {
                    "productname": (
                        getattr(product_obj, "productname", None)
                        or getattr(sales_account, "accountname", None)
                        or ""
                    ),
                    "hsn": getattr(row, "hsn_sac_code", "") or "",
                    "pieces": float(qty),
                    "orderqty": float(qty),
                    "units": getattr(getattr(row, "uom", None), "code", "") or "",
                    "ratebefdiscount": float(rate),
                    "orderDiscount": float(discount_percent),
                    "rate": float(effective_rate),
                    "amount": float(taxable_value),
                }
            )
            total_qty += qty

        tax_rows = list(SalesTaxSummary.objects.filter(header_id=header.id))
        gst_summary = [
            {
                "taxPercent": float(self._dec(getattr(row, "gst_rate", 0))),
                "taxable_amount": float(self._dec(getattr(row, "taxable_value", 0))),
                "total_cgst_amount": float(self._dec(getattr(row, "cgst_amount", 0))),
                "total_sgst_amount": float(self._dec(getattr(row, "sgst_amount", 0))),
                "total_igst_amount": float(self._dec(getattr(row, "igst_amount", 0))),
            }
            for row in tax_rows
        ]

        customer = getattr(header, "customer", None)
        ship = getattr(header, "shipping_detail", None)
        shipto_snapshot = getattr(header, "shipto_snapshot", None)
        einvoice_artifact = getattr(header, "einvoice_artifact", None)
        eway_artifact = getattr(header, "eway_artifact", None)
        transport_fields = self._resolve_transport_for_print(header)

        bank_obj = account_primary_bank_detail(customer) if customer is not None else None
        doctype_label = header.get_doc_type_display()
        if line_mode == "service" and int(header.doc_type or 0) == int(SalesInvoiceHeader.DocType.TAX_INVOICE):
            doctype_label = "Service Invoice"

        entity_address = seller.get("address") or ""
        if seller.get("address2"):
            entity_address = f"{entity_address}, {seller.get('address2')}" if entity_address else str(seller.get("address2"))

        total_cgst = self._dec(getattr(header, "total_cgst", 0))
        total_sgst = self._dec(getattr(header, "total_sgst", 0))
        total_igst = self._dec(getattr(header, "total_igst", 0))
        total_cess = self._dec(getattr(header, "total_cess", 0))
        subtotal = self._dec(getattr(header, "total_taxable_value", 0))
        total_discount = self._dec(getattr(header, "total_discount", 0))
        grand_total = self._dec(getattr(header, "grand_total", 0))

        return {
            "id": header.id,
            "sorderdate": self._date_str(getattr(header, "bill_date", None)),
            "billno": getattr(header, "doc_no", None) or 0,
            "accountid": getattr(header, "customer_id", None) or 0,
            "billtostate": getattr(header, "bill_to_state_code", "") or "",
            "billtoname": getattr(header, "customer_name", "") or "",
            "billtoaddress1": getattr(header, "bill_to_address1", "") or "",
            "billtoaddress2": getattr(header, "bill_to_address2", "") or "",
            "billtogst": getattr(header, "customer_gstin", "") or "",
            "billtopan": account_pan(customer) if customer is not None else "",
            "grno": transport_fields["grno"],
            "terms": getattr(header, "credit_days", 0) or 0,
            "stbefdiscount": float(subtotal + total_discount),
            "discount": float(total_discount),
            "vehicle": transport_fields["vehicle"],
            "billcash": 1 if int(getattr(header, "credit_days", 0) or 0) > 0 else 0,
            "totalquanity": float(total_qty),
            "totalpieces": float(total_qty),
            "shiptostate": (
                getattr(getattr(ship, "state", None), "statecode", None)
                or getattr(shipto_snapshot, "state_code", None)
                or ""
            ),
            "shiptoname": (
                getattr(ship, "full_name", None)
                or getattr(shipto_snapshot, "full_name", None)
                or getattr(header, "customer_name", "")
                or ""
            ),
            "shiptoaddress1": getattr(ship, "address1", None) or getattr(shipto_snapshot, "address1", None) or "",
            "shiptoaddress2": getattr(ship, "address2", None) or getattr(shipto_snapshot, "address2", None) or "",
            "shiptopan": account_pan(customer) if customer is not None else "",
            "shiptogst": getattr(ship, "gstno", None) or getattr(header, "customer_gstin", "") or "",
            "remarks": getattr(header, "remarks", "") or "",
            "taxid": 0,
            "tds194q": 0,
            "tds194q1": 0,
            "tcs206c1ch1": 0,
            "tcs206c1ch2": 0,
            "tcs206c1ch3": 0,
            "tcs206C1": 0,
            "tcs206C2": 0,
            "addless": float(self._dec(getattr(header, "round_off", 0))),
            "duedate": self._date_str(getattr(header, "due_date", None)),
            "subtotal": float(subtotal),
            "cgst": float(total_cgst),
            "sgst": float(total_sgst),
            "igst": float(total_igst),
            "cess": float(total_cess),
            "totalgst": float(total_cgst + total_sgst + total_igst),
            "expenses": float(self._dec(getattr(header, "total_other_charges", 0))),
            "gtotal": float(grand_total),
            "amountinwords": "",
            "subentity": getattr(header, "subentity_id", None),
            "entity": getattr(header, "entity_id", None),
            "entityname": seller.get("entityname") or "",
            "entityaddress": entity_address,
            "entitycityname": "",
            "entitystate": seller.get("statecode") or "",
            "entitypincode": str(seller.get("pincode") or ""),
            "entitygst": seller.get("gstno") or "",
            "eway": bool(getattr(header, "is_eway_applicable", False)),
            "einvoice": bool(getattr(header, "is_einvoice_applicable", False)),
            "einvoicepluseway": bool(getattr(header, "is_einvoice_applicable", False) and getattr(header, "is_eway_applicable", False)),
            "isactive": True,
            "phoneno": seller.get("phoneoffice") or "",
            "phoneno2": "",
            "entitydesc": seller.get("legalname") or "",
            "bankname": getattr(bank_obj, "bankname", "") if bank_obj else "",
            "bankacno": getattr(bank_obj, "banKAcno", "") if bank_obj else "",
            "ifsccode": getattr(bank_obj, "ifsc", "") if bank_obj else "",
            "transportname": transport_fields["transportname"],
            "entitypan": getattr(getattr(entity_obj, "tax_profile", None), "pan", "") if entity_obj else "",
            "einvoice_details": {
                "irn": getattr(einvoice_artifact, "irn", None),
                "ack_no": getattr(einvoice_artifact, "ack_no", None),
                "ack_date": self._date_str(getattr(einvoice_artifact, "ack_date", None)),
                "ewb_no": getattr(eway_artifact, "ewb_no", None) or getattr(einvoice_artifact, "ewb_no", None),
                "ewb_date": self._date_str(getattr(eway_artifact, "ewb_date", None) or getattr(einvoice_artifact, "ewb_date", None)),
                "ewb_valid_till": self._date_str(getattr(eway_artifact, "valid_upto", None) or getattr(einvoice_artifact, "ewb_valid_upto", None)),
                "qr_image_base64": getattr(einvoice_artifact, "signed_qr_code", None) or "",
            },
            "saleInvoiceDetails": sale_invoice_details,
            "gst_summary": gst_summary,
            "doctype": doctype_label,
            "reversecharge": bool(getattr(header, "is_reverse_charge", False)),
        }

    def get(self, request, pk: int):
        header = self._get_scoped_header(pk)
        require_sales_request_permission(
            user=request.user,
            entity_id=header.entity_id,
            doc_type=header.doc_type,
            action="view",
        )
        return Response(self._build_payload(header), status=status.HTTP_200_OK)


class SalesServiceInvoicePrintAPIView(SalesInvoicePrintAPIView):
    line_mode = "service"
