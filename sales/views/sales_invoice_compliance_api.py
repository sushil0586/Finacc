from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.exceptions import PermissionDenied

from sales.models import SalesInvoiceHeader
from sales.models.sales_compliance import SalesEInvoice, SalesEInvoiceStatus
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.serializers.sales_compliance_serializers import (
    EnsureComplianceActionSerializer,
    GenerateIRNActionSerializer,
    GenerateIRNAndEWayActionSerializer,
    GenerateEWayActionSerializer,
    CancelIRNActionSerializer,
    GetIRNDetailsActionSerializer,
    GetEWayByIRNActionSerializer,
)

from sales.services.sales_compliance_service import SalesComplianceService
from rbac.services import EffectivePermissionService

COMPLIANCE_EXCEPTIONS = (ValueError, RuntimeError, DjangoValidationError, DRFValidationError)


class _InvoiceMixin:
    permission_classes = [IsAuthenticated]
    permission_view_code = "sales.invoice.view"
    permission_manage_code = "sales.invoice.update"

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
        invoice = get_object_or_404(
            SalesInvoiceHeader.objects.filter(**self._scope_filters()),
            pk=self.kwargs["pk"],
        )
        self._require_any_permission(["sales.compliance.view", self.permission_view_code], invoice.entity_id)
        return invoice

    def _require_permission(self, permission_code: str, entity_id: int) -> None:
        if not entity_id:
            raise PermissionDenied("Entity scope is required for permission check.")
        permission_codes = EffectivePermissionService.permission_codes_for_user(
            self.request.user,
            int(entity_id),
        )
        if permission_code not in permission_codes:
            raise PermissionDenied(f"Missing permission: {permission_code}")

    def _require_any_permission(self, permission_codes: list[str], entity_id: int) -> None:
        if not entity_id:
            raise PermissionDenied("Entity scope is required for permission check.")
        available = EffectivePermissionService.permission_codes_for_user(self.request.user, int(entity_id))
        for code in permission_codes:
            if code in available:
                return
        raise PermissionDenied(f"Missing permission: one of {', '.join(permission_codes)}")

    def _require_manage_permission(self, invoice: SalesInvoiceHeader) -> None:
        self._require_any_permission(
            ["sales.compliance.ensure", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )

    @staticmethod
    def _compliance_summary(invoice: SalesInvoiceHeader) -> dict:
        einv = getattr(invoice, "einvoice_artifact", None)
        ewb = getattr(invoice, "eway_artifact", None)
        from sales.services.sales_compliance_service import SalesComplianceService

        return {
            "invoice_id": invoice.id,
            "invoice_status": int(getattr(invoice, "status", 0) or 0),
            "invoice_status_name": invoice.get_status_display() if hasattr(invoice, "get_status_display") else None,
            "is_einvoice_applicable": bool(getattr(invoice, "is_einvoice_applicable", False)),
            "is_eway_applicable": bool(getattr(invoice, "is_eway_applicable", False)),
            "einvoice": {
                "status": int(getattr(einv, "status", 0) or 0) if einv else None,
                "irn": getattr(einv, "irn", None) if einv else None,
                "ack_no": getattr(einv, "ack_no", None) if einv else None,
                "ack_date": getattr(einv, "ack_date", None) if einv else None,
                "last_error_code": getattr(einv, "last_error_code", None) if einv else None,
                "last_error_message": getattr(einv, "last_error_message", None) if einv else None,
            },
            "eway": {
                "status": int(getattr(ewb, "status", 0) or 0) if ewb else None,
                "ewb_no": getattr(ewb, "ewb_no", None) if ewb else None,
                "valid_upto": getattr(ewb, "valid_upto", None) if ewb else None,
                "last_error_code": getattr(ewb, "last_error_code", None) if ewb else None,
                "last_error_message": getattr(ewb, "last_error_message", None) if ewb else None,
            },
            "action_flags": SalesComplianceService.compliance_action_flags(invoice),
        }

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
        self._require_any_permission(
            ["sales.compliance.ensure", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )
        ser = self.get_serializer(data=request.data or {})
        ser.is_valid(raise_exception=True)

        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            result = svc.ensure_rows(eway_data=ser.validated_data)
        except COMPLIANCE_EXCEPTIONS as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        data = SalesInvoiceHeaderSerializer(invoice).data
        return Response({"ok": True, "result": result, "invoice": data, "compliance": self._compliance_summary(invoice)}, status=status.HTTP_200_OK)


class SalesInvoiceComplianceStatusAPIView(_InvoiceMixin, GenericAPIView):
    """
    GET /sales-invoices/{pk}/compliance/status/
    Returns normalized compliance status + backend action flags.
    """

    def get(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        invoice_data = SalesInvoiceHeaderSerializer(invoice, context={"request": request}).data
        return Response(
            {"ok": True, "invoice": invoice_data, "compliance": self._compliance_summary(invoice)},
            status=status.HTTP_200_OK,
        )


class SalesInvoiceGenerateIRNAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/generate-irn/
    Body: {}
    """
    serializer_class = GenerateIRNActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        self._require_any_permission(
            ["sales.compliance.generate_irn", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )
        existing = (
            SalesEInvoice.objects.filter(invoice=invoice)
            .only("status", "irn", "attempt_count")
            .first()
        )
        was_generated = bool(
            existing
            and int(getattr(existing, "status", 0) or 0) == int(SalesEInvoiceStatus.GENERATED)
            and getattr(existing, "irn", None)
        )

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            einv = svc.generate_irn()
        except COMPLIANCE_EXCEPTIONS as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        invoice_data = SalesInvoiceHeaderSerializer(invoice).data
        return Response(
            {
                "ok": True,
                "einvoice": {
                    "id": einv.id,
                    "status": einv.status,
                    "irn": getattr(einv, "irn", None),
                    "ack_no": getattr(einv, "ack_no", None),
                    "ack_date": getattr(einv, "ack_date", None),
                    "idempotent": was_generated,
                },
                "invoice": invoice_data,
            },
            status=status.HTTP_200_OK,
        )


class SalesInvoiceGenerateIRNAndEWayAPIView(_InvoiceMixin, GenericAPIView):
    """
    POST /sales-invoices/{pk}/compliance/generate-irn-and-eway/
    Body:
      {
        "generate_eway": true,
        "eway": { ...transport fields... }
      }
    """

    serializer_class = GenerateIRNAndEWayActionSerializer

    def post(self, request, pk: int, *args, **kwargs):
        invoice = self.get_invoice()
        self._require_any_permission(
            ["sales.compliance.generate_irn", "sales.compliance.generate_eway", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )
        ser = self.get_serializer(data=request.data or {})
        ser.is_valid(raise_exception=True)

        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            einv = svc.generate_irn()
        except COMPLIANCE_EXCEPTIONS as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        workflow_status = "SUCCESS"
        eway_result = {
            "status": "SKIPPED",
            "reason": "generate_eway=false",
        }

        if ser.validated_data.get("generate_eway", True):
            if bool(getattr(invoice, "is_eway_applicable", False)):
                try:
                    eway_result = SalesComplianceService.generate_eway(
                        inv=invoice,
                        entity=invoice.entity,
                        req=ser.validated_data.get("eway") or {},
                        created_by=request.user,
                    )
                    if eway_result.get("status") != "SUCCESS":
                        workflow_status = "PARTIAL_SUCCESS"
                except COMPLIANCE_EXCEPTIONS as e:
                    workflow_status = "PARTIAL_SUCCESS"
                    eway_result = {
                        "status": "FAILED",
                        "errors": self._error_list_payload(e).get("errors", []),
                    }
            else:
                eway_result = {
                    "status": "SKIPPED",
                    "reason": "E-Way not applicable for this invoice.",
                }
                workflow_status = "PARTIAL_SUCCESS"

        invoice_data = SalesInvoiceHeaderSerializer(invoice).data
        return Response(
            {
                "ok": workflow_status == "SUCCESS",
                "workflow_status": workflow_status,
                "einvoice": {
                    "id": einv.id,
                    "status": einv.status,
                    "irn": getattr(einv, "irn", None),
                    "ack_no": getattr(einv, "ack_no", None),
                    "ack_date": getattr(einv, "ack_date", None),
                },
                "eway": eway_result,
                "invoice": invoice_data,
            },
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
        self._require_any_permission(
            ["sales.compliance.cancel_irn", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            out = svc.cancel_irn(**ser.validated_data)
        except COMPLIANCE_EXCEPTIONS as e:
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
        self._require_any_permission(
            ["sales.compliance.fetch", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            out = svc.get_irn_details(**ser.validated_data)
        except COMPLIANCE_EXCEPTIONS as e:
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
        self._require_any_permission(
            ["sales.compliance.fetch", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            svc = SalesComplianceService(invoice=invoice, user=request.user)
            out = svc.get_eway_details_by_irn(**ser.validated_data)
        except COMPLIANCE_EXCEPTIONS as e:
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
        self._require_any_permission(
            ["sales.compliance.generate_eway", "sales.invoice.update", "sales.invoice.edit"],
            invoice.entity_id,
        )

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            result = SalesComplianceService.generate_eway(
                inv=invoice,
                entity=invoice.entity,
                req=ser.validated_data,
                created_by=request.user,
            )
        except COMPLIANCE_EXCEPTIONS as e:
            return Response(self._error_list_payload(e), status=status.HTTP_400_BAD_REQUEST)

        http_status = status.HTTP_200_OK if result.get("status") == "SUCCESS" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)
