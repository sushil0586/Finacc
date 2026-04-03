from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from django.http import Http404

from purchase.models.purchase_core import DocType
from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from purchase.serializers.purchase_actions import ItcBlockSerializer, ItcUnblockSerializer, ItcClaimSerializer, Match2BSerializer
from gst_tds.models import GstTdsContractLedger

from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions
from purchase.services.purchase_note_factory import PurchaseNoteFactory


def _raise_validation_error(err: ValueError) -> None:
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"non_field_errors": [str(payload)]})


def _parse_scope(request, *, required: bool = True):
    payload = request.data if isinstance(getattr(request, "data", None), dict) else {}
    entity = request.query_params.get("entity") or payload.get("entity")
    entityfinid = request.query_params.get("entityfinid") or payload.get("entityfinid")
    subentity = request.query_params.get("subentity")
    if subentity is None:
        subentity = payload.get("subentity")

    if required and (entity in (None, "", "null") or entityfinid in (None, "", "null")):
        raise ValidationError({"detail": "entity and entityfinid are required."})
    if entity in (None, "", "null") and entityfinid in (None, "", "null"):
        return None, None, None

    try:
        entity_id = int(entity)
        entityfinid_id = int(entityfinid)
        subentity_id = int(subentity) if subentity not in (None, "", "null") else None
    except (TypeError, ValueError):
        raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
    return entity_id, entityfinid_id, subentity_id


def _assert_invoice_scope(pk: int, request):
    entity_id, entityfinid_id, subentity_id = _parse_scope(request, required=True)
    header = (
        PurchaseInvoiceHeader.objects
        .only("id", "entity_id", "entityfinid_id", "subentity_id")
        .filter(pk=pk)
        .first()
    )
    if not header:
        raise Http404("Purchase invoice not found.")
    if int(header.entity_id or 0) != int(entity_id or 0) or int(header.entityfinid_id or 0) != int(entityfinid_id or 0):
        raise ValidationError({"detail": "Invoice scope mismatch with entity/entityfinid."})
    if subentity_id is not None and int(header.subentity_id or 0) != int(subentity_id or 0):
        raise ValidationError({"detail": "Invoice subentity mismatch for requested scope."})


def _gst_tds_contract_summary_block(header):
    ref = (getattr(header, "gst_tds_contract_ref", "") or "").strip()
    vendor_id = getattr(header, "vendor_id", None)
    if not ref or not vendor_id:
        return None
    qs = GstTdsContractLedger.objects.filter(
        entity_id=getattr(header, "entity_id", None),
        entityfinid_id=getattr(header, "entityfinid_id", None),
        subentity_id=getattr(header, "subentity_id", None),
        vendor_id=vendor_id,
        contract_ref=ref,
    )
    row = qs.first()
    if row is None:
        return {
            "contract_ref": ref,
            "exists": False,
            "cumulative_taxable": "0.00",
            "cumulative_tds": "0.00",
            "last_updated_at": None,
        }
    return {
        "contract_ref": ref,
        "exists": True,
        "cumulative_taxable": str(row.cumulative_taxable or 0),
        "cumulative_tds": str(row.cumulative_tds or 0),
        "last_updated_at": row.updated_at,
    }


def _response_payload(message: str, header):
    data = PurchaseInvoiceHeaderSerializer(header).data
    summary = _gst_tds_contract_summary_block(header)
    if summary is not None:
        data["gst_tds_contract_summary"] = summary
    return {
        "message": message,
        "data": data,
        "gst_tds_contract_summary": summary,
    }


class PurchaseInvoiceConfirmAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        try:
            result = PurchaseInvoiceActions.confirm(pk, confirmed_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoicePostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        try:
            result = PurchaseInvoiceActions.post(pk, posted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceUnpostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = PurchaseInvoiceActions.unpost(pk, unposted_by_id=request.user.id, reason=reason)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = PurchaseInvoiceActions.cancel(pk, cancelled_by_id=request.user.id, reason=reason)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceRebuildTaxSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        try:
            result = PurchaseInvoiceActions.rebuild_tax_summary(pk)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


# ---- Create CN/DN ----

class PurchaseInvoiceCreateCreditNoteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        try:
            res = PurchaseNoteFactory.create_note_from_invoice(
                invoice_id=pk,
                note_type=DocType.CREDIT_NOTE,
                created_by_id=request.user.id,
            )
        except ValueError as e:
            _raise_validation_error(e)
        return Response(
            _response_payload(res.message, res.header),
            status=status.HTTP_201_CREATED,
        )


class PurchaseInvoiceCreateDebitNoteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        try:
            res = PurchaseNoteFactory.create_note_from_invoice(
                invoice_id=pk,
                note_type=DocType.DEBIT_NOTE,
                created_by_id=request.user.id,
            )
        except ValueError as e:
            _raise_validation_error(e)
        return Response(
            _response_payload(res.message, res.header),
            status=status.HTTP_201_CREATED,
        )


# ---- ITC ----

class PurchaseInvoiceITCBlockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        ser = ItcBlockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = PurchaseInvoiceActions.mark_itc_blocked(
                pk,
                reason=ser.validated_data["reason"],
                acted_by_id=request.user.id,
            )
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceITCPendingAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        try:
            result = PurchaseInvoiceActions.mark_itc_pending(pk, acted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceITCUnblockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        ser = ItcUnblockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = (ser.validated_data.get("reason") or "").strip() or None
        try:
            result = PurchaseInvoiceActions.mark_itc_unblocked(pk, reason=reason, acted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceITCClaimAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        ser = ItcClaimSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = PurchaseInvoiceActions.mark_itc_claimed(
                pk,
                period=ser.validated_data["period"],
                acted_by_id=request.user.id,
            )
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


class PurchaseInvoiceITCReverseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = PurchaseInvoiceActions.mark_itc_reversed(pk, reason=reason, acted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))


# ---- GSTR-2B ----

class PurchaseInvoice2BMatchStatusAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        _assert_invoice_scope(pk, request)
        ser = Match2BSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = PurchaseInvoiceActions.update_2b_match_status(
                pk,
                match_status=ser.validated_data["match_status"],
                acted_by_id=request.user.id,
            )
        except ValueError as e:
            _raise_validation_error(e)
        return Response(_response_payload(result.message, result.header))
