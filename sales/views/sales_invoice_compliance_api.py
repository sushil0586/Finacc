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
    EnsureComplianceActionSerializer,
    GenerateIRNActionSerializer,
    GenerateEWayActionSerializer,
    CancelIRNActionSerializer,
    GetIRNDetailsActionSerializer,
    GetEWayByIRNActionSerializer,
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

    @staticmethod
    def _error_payload(e):
        detail = getattr(e, "detail", None)
        if detail is not None:
            return detail
        message_dict = getattr(e, "message_dict", None)
        if message_dict is not None:
            return message_dict
        return {"detail": str(e)}

    @classmethod
    def _error_list_payload(cls, e):
        payload = cls._error_payload(e)
        errors = []

        def add(message, *, code=None, field=None, reason=None, resolution=None):
            row = {"message": str(message)}
            if code not in (None, "", "None", "null"):
                row["code"] = str(code)
            if field not in (None, "", "None", "null"):
                row["field"] = str(field)
            if reason not in (None, "", "None", "null"):
                row["reason"] = str(reason)
            if resolution not in (None, "", "None", "null"):
                row["resolution"] = str(resolution)
            errors.append(row)

        if isinstance(payload, dict):
            # Structured compliance error shape
            if "message" in payload or "code" in payload:
                add(
                    payload.get("message") or payload.get("detail") or "Request failed.",
                    code=payload.get("code"),
                    reason=payload.get("reason"),
                    resolution=payload.get("resolution"),
                )
            else:
                for k, v in payload.items():
                    if k == "raw":
                        continue
                    if isinstance(v, list):
                        for item in v:
                            add(item, field=k)
                    elif isinstance(v, dict):
                        for kk, vv in v.items():
                            if isinstance(vv, list):
                                for item in vv:
                                    add(item, field=f"{k}.{kk}")
                            else:
                                add(vv, field=f"{k}.{kk}")
                    else:
                        add(v, field=k)
        elif isinstance(payload, list):
            for item in payload:
                add(item)
        else:
            add(payload)

        if not errors:
            add("Request failed.")
        return {"errors": errors}


class SalesInvoiceEnsureComplianceAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/ensure/
    Creates compliance artifact rows if missing.
    """
    serializer_class = EnsureComplianceActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        ser = self.get_serializer(data=request.data or {})
        ser.is_valid(raise_exception=True)

        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            result = svc.ensure_rows(eway_data=ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        data = SalesInvoiceHeaderSerializer(invoice).data
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
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        invoice_data = SalesInvoiceHeaderSerializer(invoice).data
        return Response(
            {"ok": True, "einvoice_id": einv.id, "status": einv.status, "invoice": invoice_data},
            status=status.HTTP_200_OK,
        )


class SalesInvoiceCancelIRNAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/cancel-irn/
    Body: {reason_code, remarks?}
    """
    serializer_class = CancelIRNActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            out = svc.cancel_irn(**ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class SalesInvoiceGetIRNDetailsAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/get-irn-details/
    Body: {irn?, supplier_gstin?}
    """
    serializer_class = GetIRNDetailsActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            out = svc.get_irn_details(**ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class SalesInvoiceGetEWayByIRNAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/get-eway-by-irn/
    Body: {irn?, supplier_gstin?}
    """
    serializer_class = GetEWayByIRNActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            out = svc.get_eway_details_by_irn(**ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


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
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        http_status = status.HTTP_200_OK if result.get("status") == "SUCCESS" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)
