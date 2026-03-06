from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from sales.models import SalesInvoiceHeader
from sales.models.sales_compliance import SalesEWayBill
from sales.serializers.eway_serializers import GenerateEWayRequestSerializer
from sales.serializers.sales_compliance_serializers import (
    CancelEWayActionSerializer,
    UpdateEWayVehicleActionSerializer,
    UpdateEWayTransporterActionSerializer,
    ExtendEWayValidityActionSerializer,
)
from sales.services.sales_compliance_service import SalesComplianceService


class _ScopedInvoiceMixin:
    permission_classes = [IsAuthenticated]

    def _scope_filters(self):
        payload = self.request.data if isinstance(getattr(self.request, "data", None), dict) else {}
        entity_id = self.request.query_params.get("entity_id") or payload.get("entity_id") or payload.get("entity")
        entityfinid_id = (
            self.request.query_params.get("entityfinid_id")
            or self.request.query_params.get("entityfinid")
            or payload.get("entityfinid_id")
            or payload.get("entityfinid")
        )
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

    def _get_invoice(self, id: int) -> SalesInvoiceHeader:
        return get_object_or_404(
            SalesInvoiceHeader.objects.filter(**self._scope_filters()),
            pk=id,
        )

    def _fetch_invoice_with_related(self, id: int) -> SalesInvoiceHeader:
        return get_object_or_404(
            SalesInvoiceHeader.objects.filter(**self._scope_filters())
            .select_related("customer", "entity", "einvoice_artifact", "eway_artifact", "shipto_snapshot")
            .prefetch_related("lines"),
            pk=id,
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


class SalesInvoiceEWayPrefillAPIView(_ScopedInvoiceMixin, GenericAPIView):
    """
    B2B (IRN-based) EWB prefill.
    GET /api/sales/sales-invoices/<id>/compliance/eway-prefill/
    """

    def get(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)
        try:
            payload = SalesComplianceService(invoice=inv, user=request.user).eway_prefill(inv)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)


class SalesInvoiceGenerateEWayAPIView(_ScopedInvoiceMixin, GenericAPIView):
    """
    B2B (IRN-based) EWB generate.
    POST /api/sales/sales-invoices/<id>/compliance/generate-eway/
    """

    serializer_class = GenerateEWayRequestSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            result = SalesComplianceService.generate_eway(
                inv=inv,
                entity=inv.entity,
                req=ser.validated_data,
                created_by=request.user,
            )
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        http_status = status.HTTP_200_OK if result.get("status") == "SUCCESS" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)


class SalesInvoiceEWayB2CPrefillAPIView(_ScopedInvoiceMixin, GenericAPIView):
    """
    B2C Direct EWB prefill (no IRN).
    GET /api/sales/sales-invoices/<id>/compliance/eway-b2c-prefill/
    """

    def get(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)

        if int(inv.supply_category or 0) != 2:
            return Response(
                {"eligible": False, "reason": "Invoice is not B2C.", "invoice_id": inv.id},
                status=status.HTTP_200_OK,
            )

        svc = SalesComplianceService(invoice=inv, user=request.user)
        payload = svc.eway_prefill_b2c(inv)
        return Response(payload, status=status.HTTP_200_OK)


class SalesInvoiceEWayB2CGenerateAPIView(_ScopedInvoiceMixin, GenericAPIView):
    def post(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)

        if int(inv.supply_category or 0) != 2:
            return Response(
                {"status": "FAILED", "error_message": "Only B2C invoices allowed here."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ewb = getattr(inv, "eway_artifact", None) or SalesEWayBill.objects.create(invoice=inv)
        d = request.data or {}

        if not d.get("distance_km"):
            return Response(
                {"status": "FAILED", "error_message": "distance_km required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not d.get("trans_mode"):
            return Response(
                {"status": "FAILED", "error_message": "trans_mode required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ewb.distance_km = int(d["distance_km"])
        ewb.transport_mode = int(d["trans_mode"])
        ewb.transporter_id = (d.get("transporter_id") or "").strip() or None
        ewb.transporter_name = (d.get("transporter_name") or "").strip() or None
        ewb.doc_type = (d.get("doc_type") or "").strip() or None
        ewb.doc_no = (d.get("trans_doc_no") or "").strip() or None
        ewb.doc_date = d.get("trans_doc_date") or None
        ewb.vehicle_no = (d.get("vehicle_no") or "").strip() or None
        ewb.vehicle_type = (d.get("vehicle_type") or "").strip() or None
        ewb.last_attempt_at = timezone.now()
        if request.user.is_authenticated:
            ewb.updated_by = request.user
        ewb.save()

        svc = SalesComplianceService(invoice=inv, user=request.user)
        try:
            out = svc.eway_generate_b2c(inv, user=request.user)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response({"status": "FAILED", **self._error_list_payload(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            out,
            status=(status.HTTP_200_OK if out.get("status") == "SUCCESS" else status.HTTP_400_BAD_REQUEST),
        )


class SalesInvoiceCancelEWayAPIView(_ScopedInvoiceMixin, GenericAPIView):
    serializer_class = CancelEWayActionSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = SalesComplianceService(invoice=inv, user=request.user).cancel_eway(**ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class SalesInvoiceEWayUpdateVehicleAPIView(_ScopedInvoiceMixin, GenericAPIView):
    serializer_class = UpdateEWayVehicleActionSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = SalesComplianceService(invoice=inv, user=request.user).update_eway_vehicle(req=ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class SalesInvoiceEWayUpdateTransporterAPIView(_ScopedInvoiceMixin, GenericAPIView):
    serializer_class = UpdateEWayTransporterActionSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = SalesComplianceService(invoice=inv, user=request.user).update_eway_transporter(
                transporter_id=ser.validated_data["transporter_id"]
            )
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class SalesInvoiceEWayExtendValidityAPIView(_ScopedInvoiceMixin, GenericAPIView):
    serializer_class = ExtendEWayValidityActionSerializer

    def post(self, request, id: int, *args, **kwargs):
        inv = self._fetch_invoice_with_related(id)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = SalesComplianceService(invoice=inv, user=request.user).extend_eway_validity(req=ser.validated_data)
        except (ValueError, DjangoValidationError, DRFValidationError) as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)
