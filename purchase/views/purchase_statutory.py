from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from purchase.models.purchase_statutory import PurchaseStatutoryChallan, PurchaseStatutoryReturn
from purchase.serializers.purchase_statutory import (
    PurchaseStatutoryChallanSerializer,
    PurchaseStatutoryChallanCreateInputSerializer,
    PurchaseStatutoryReturnSerializer,
    PurchaseStatutoryReturnCreateInputSerializer,
)
from purchase.services.purchase_statutory_service import PurchaseStatutoryService


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


class PurchaseStatutoryChallanListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchaseStatutoryChallanSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        qs = PurchaseStatutoryChallan.objects.prefetch_related("lines").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        tax_type = self.request.query_params.get("tax_type")
        if tax_type:
            qs = qs.filter(tax_type=tax_type)
        status_q = self.request.query_params.get("status")
        if status_q not in (None, "", "null"):
            qs = qs.filter(status=int(status_q))
        return qs.order_by("-challan_date", "-id")

    def create(self, request, *args, **kwargs):
        inp = PurchaseStatutoryChallanCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        try:
            res = PurchaseStatutoryService.create_challan(
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                tax_type=data["tax_type"],
                challan_no=data["challan_no"],
                challan_date=data["challan_date"],
                period_from=data.get("period_from"),
                period_to=data.get("period_to"),
                bank_ref_no=data.get("bank_ref_no"),
                bsr_code=data.get("bsr_code"),
                remarks=data.get("remarks"),
                lines=data["lines"],
                created_by_id=request.user.id,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryChallanSerializer(res.obj, context=self.get_serializer_context())
        return Response({"message": res.message, "data": out.data}, status=status.HTTP_201_CREATED)


class PurchaseStatutoryChallanDepositAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        deposited_on = request.data.get("deposited_on")
        try:
            res = PurchaseStatutoryService.deposit_challan(
                challan_id=pk,
                deposited_by_id=request.user.id,
                deposited_on=deposited_on,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": res.message, "data": PurchaseStatutoryChallanSerializer(res.obj).data})


class PurchaseStatutoryReturnListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchaseStatutoryReturnSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        qs = PurchaseStatutoryReturn.objects.prefetch_related("lines").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        tax_type = self.request.query_params.get("tax_type")
        if tax_type:
            qs = qs.filter(tax_type=tax_type)
        status_q = self.request.query_params.get("status")
        if status_q not in (None, "", "null"):
            qs = qs.filter(status=int(status_q))
        return qs.order_by("-period_to", "-id")

    def create(self, request, *args, **kwargs):
        inp = PurchaseStatutoryReturnCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        try:
            res = PurchaseStatutoryService.create_return(
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                tax_type=data["tax_type"],
                return_code=data["return_code"],
                period_from=data["period_from"],
                period_to=data["period_to"],
                ack_no=data.get("ack_no"),
                remarks=data.get("remarks"),
                lines=data["lines"],
                created_by_id=request.user.id,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryReturnSerializer(res.obj, context=self.get_serializer_context())
        return Response({"message": res.message, "data": out.data}, status=status.HTTP_201_CREATED)


class PurchaseStatutoryReturnFileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        filed_on = request.data.get("filed_on")
        ack_no = request.data.get("ack_no")
        try:
            res = PurchaseStatutoryService.file_return(
                filing_id=pk,
                filed_by_id=request.user.id,
                filed_on=filed_on,
                ack_no=ack_no,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": res.message, "data": PurchaseStatutoryReturnSerializer(res.obj).data})
