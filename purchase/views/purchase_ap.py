from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from purchase.models.purchase_ap import VendorSettlement
from purchase.serializers.purchase_ap import (
    VendorAdvanceBalanceSerializer,
    VendorBillOpenItemSerializer,
    VendorSettlementSerializer,
    VendorSettlementCreateInputSerializer,
)
from purchase.services.purchase_ap_service import PurchaseApService


def _parse_scope(request):
    entity = request.query_params.get("entity")
    entityfinid = request.query_params.get("entityfinid")
    subentity = request.query_params.get("subentity")
    if not entity or not entityfinid:
        raise ValidationError({"detail": "entity and entityfinid query params are required."})
    try:
        entity_id = int(entity)
        entityfinid_id = int(entityfinid)
        subentity_id = int(subentity) if subentity not in (None, "", "null") else None
    except (TypeError, ValueError):
        raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
    return entity_id, entityfinid_id, subentity_id


class VendorBillOpenItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorBillOpenItemSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)

        vendor = self.request.query_params.get("vendor")
        is_open = self.request.query_params.get("is_open")
        vendor_id = int(vendor) if vendor not in (None, "", "null") else None

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return PurchaseApService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=open_flag,
        ).select_related("vendor", "header")


class VendorAdvanceBalanceListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorAdvanceBalanceSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        vendor = self.request.query_params.get("vendor")
        is_open = self.request.query_params.get("is_open")
        vendor_id = int(vendor) if vendor not in (None, "", "null") else None

        if is_open in (None, "", "null"):
            open_flag = True
        else:
            open_flag = str(is_open).strip().lower() in ("1", "true", "yes", "y")

        return PurchaseApService.list_open_advances(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=open_flag,
        ).select_related("vendor", "payment_voucher").prefetch_related("settlements__lines__open_item")


class VendorSettlementListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorSettlementSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        qs = VendorSettlement.objects.prefetch_related("lines").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        vendor = self.request.query_params.get("vendor")
        if vendor not in (None, "", "null"):
            qs = qs.filter(vendor_id=int(vendor))
        return qs.order_by("-settlement_date", "-id")

    def create(self, request, *args, **kwargs):
        inp = VendorSettlementCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data

        try:
            res = PurchaseApService.create_settlement(
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                vendor_id=data["vendor"],
                settlement_type=data["settlement_type"],
                settlement_date=data["settlement_date"],
                reference_no=data.get("reference_no"),
                external_voucher_no=data.get("external_voucher_no"),
                remarks=data.get("remarks"),
                lines=data.get("lines"),
                amount=data.get("amount"),
                advance_balance_id=data.get("advance_balance"),
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

        out = VendorSettlementSerializer(res.settlement, context=self.get_serializer_context())
        return Response({"message": res.message, "data": out.data}, status=status.HTTP_201_CREATED)


class VendorSettlementPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            res = PurchaseApService.post_settlement(settlement_id=pk, posted_by_id=request.user.id)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({
            "message": res.message,
            "applied_total": str(res.applied_total),
            "data": VendorSettlementSerializer(res.settlement).data,
        })


class VendorSettlementCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            res = PurchaseApService.cancel_settlement(settlement_id=pk, cancelled_by_id=request.user.id)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({
            "message": res.message,
            "data": VendorSettlementSerializer(res.settlement).data,
        })


class VendorStatementAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        vendor = request.query_params.get("vendor")
        if not vendor:
            raise ValidationError({"vendor": "vendor query param is required."})
        try:
            vendor_id = int(vendor)
        except (TypeError, ValueError):
            raise ValidationError({"vendor": "vendor must be an integer."})
        include_closed = str(request.query_params.get("include_closed") or "").lower() in ("1", "true", "yes", "y")

        data = PurchaseApService.vendor_statement(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            include_closed=include_closed,
        )

        return Response({
            "totals": data["totals"],
            "open_items": VendorBillOpenItemSerializer(data["open_items"], many=True).data,
            "advances": VendorAdvanceBalanceSerializer(data["advances"], many=True).data,
            "settlements": VendorSettlementSerializer(data["settlements"], many=True).data,
        })
