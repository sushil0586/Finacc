from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status

from purchase.models.purchase_core import DocType
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from purchase.serializers.purchase_actions import ItcBlockSerializer, ItcClaimSerializer, Match2BSerializer

from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions
from purchase.services.purchase_note_factory import PurchaseNoteFactory


class PurchaseInvoiceConfirmAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        result = PurchaseInvoiceActions.confirm(pk)
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


class PurchaseInvoicePostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        result = PurchaseInvoiceActions.post(pk)
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


class PurchaseInvoiceCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        result = PurchaseInvoiceActions.cancel(pk)
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


class PurchaseInvoiceRebuildTaxSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        result = PurchaseInvoiceActions.rebuild_tax_summary(pk)
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


# ---- Create CN/DN ----

class PurchaseInvoiceCreateCreditNoteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        res = PurchaseNoteFactory.create_note_from_invoice(
            invoice_id=pk,
            note_type=DocType.CREDIT_NOTE,
            created_by_id=request.user.id,
        )
        return Response(
            {"message": res.message, "data": PurchaseInvoiceHeaderSerializer(res.header).data},
            status=status.HTTP_201_CREATED,
        )


class PurchaseInvoiceCreateDebitNoteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        res = PurchaseNoteFactory.create_note_from_invoice(
            invoice_id=pk,
            note_type=DocType.DEBIT_NOTE,
            created_by_id=request.user.id,
        )
        return Response(
            {"message": res.message, "data": PurchaseInvoiceHeaderSerializer(res.header).data},
            status=status.HTTP_201_CREATED,
        )


# ---- ITC ----

class PurchaseInvoiceITCBlockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        ser = ItcBlockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = PurchaseInvoiceActions.mark_itc_blocked(pk, reason=ser.validated_data["reason"])
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


class PurchaseInvoiceITCPendingAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        result = PurchaseInvoiceActions.mark_itc_pending(pk)
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


class PurchaseInvoiceITCClaimAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        ser = ItcClaimSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = PurchaseInvoiceActions.mark_itc_claimed(pk, period=ser.validated_data["period"])
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


class PurchaseInvoiceITCReverseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        reason = (request.data.get("reason") or "").strip() or None
        result = PurchaseInvoiceActions.mark_itc_reversed(pk, reason=reason)
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})


# ---- GSTR-2B ----

class PurchaseInvoice2BMatchStatusAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        ser = Match2BSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = PurchaseInvoiceActions.update_2b_match_status(pk, match_status=ser.validated_data["match_status"])
        return Response({"message": result.message, "data": PurchaseInvoiceHeaderSerializer(result.header).data})
