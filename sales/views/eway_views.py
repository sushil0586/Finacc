from __future__ import annotations

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.utils import timezone
from sales.models.sales_compliance import SalesEWayBill


from sales.models import SalesInvoiceHeader
from sales.serializers.eway_serializers import (
    GenerateEWayRequestSerializer,SalesEWayB2CGenerateSerializer,
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
        payload = SalesComplianceService(invoice=inv, user=request.user).eway_prefill(inv)  # uses your existing IRN-based logic
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
            .select_related("entity", "shipto_snapshot", "eway_artifact")  # ✅ match your model/service
            .prefetch_related("lines")
            .get(pk=id)
        )

        # B2C code as per your enum storage
        if str(inv.supply_category).upper() != "2":
            return Response(
                {"eligible": False, "reason": "Invoice is not B2C.", "invoice_id": inv.id},
                status=200,
            )

        svc = SalesComplianceService(invoice=inv, user=request.user)  # ✅ FIX
        payload = svc.eway_prefill_b2c(inv)  # (can be svc.eway_prefill_b2c(svc.invoice) too)
        return Response(payload, status=200)


class SalesInvoiceEWayB2CGenerateAPIView(GenericAPIView):
    def post(self, request, id: int, *args, **kwargs):
        inv = (
            SalesInvoiceHeader.objects
            .select_related("entity", "shipto_snapshot", "eway_artifact")
            .prefetch_related("lines")
            .get(pk=id)
        )

        if str(inv.supply_category).upper() != "2":
            return Response(
                {"status": "FAILED", "error_message": "Only B2C invoices allowed here."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ewb = getattr(inv, "eway_artifact", None) or SalesEWayBill.objects.create(invoice=inv)
        d = request.data or {}

        if not d.get("distance_km"):
            return Response({"status": "FAILED", "error_message": "distance_km required."}, status=400)
        if not d.get("trans_mode"):
            return Response({"status": "FAILED", "error_message": "trans_mode required."}, status=400)

        ewb.distance_km = int(d["distance_km"])
        ewb.transport_mode = int(d["trans_mode"])

        ewb.transporter_id = (d.get("transporter_id") or "").strip() or None
        ewb.transporter_name = (d.get("transporter_name") or "").strip() or None

        # ✅ IMPORTANT: Use trans_doc_* for NIC transport doc fields
        ewb.doc_type = (d.get("doc_type") or "").strip() or None  # optional, not used in payload
        ewb.doc_no = (d.get("trans_doc_no") or "").strip() or None
        ewb.doc_date = d.get("trans_doc_date") or None  # ISO string ok, builder converts

        ewb.vehicle_no = (d.get("vehicle_no") or "").strip() or None
        ewb.vehicle_type = (d.get("vehicle_type") or "").strip() or None

        ewb.last_attempt_at = timezone.now()
        if request.user.is_authenticated:
            ewb.updated_by = request.user
        ewb.save()

        svc = SalesComplianceService(invoice=inv, user=request.user)

        try:
            out = svc.eway_generate_b2c(inv, user=request.user)
        except Exception as e:
            return Response({"status": "FAILED", "error_message": str(e)}, status=400)

        return Response(out, status=(200 if out.get("status") == "SUCCESS" else 400))