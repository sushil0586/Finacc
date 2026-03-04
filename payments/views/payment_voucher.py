from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PaymentVoucherHeader, PaymentVoucherAllocation
from payments.serializers.payment_voucher import (
    PaymentVoucherHeaderSerializer,
    PaymentVoucherListSerializer,
)
from payments.services.payment_voucher_service import PaymentVoucherService


def _raise_validation_error(err: ValueError) -> None:
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"non_field_errors": [str(payload)]})


class PaymentVoucherListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def _scope_ids(self, *, required: bool):
        if self.request.method.upper() == "POST":
            return None, None, None
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        if required and (not entity or not entityfinid):
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        if not entity or not entityfinid:
            return None, None, None
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return PaymentVoucherListSerializer
        return PaymentVoucherHeaderSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids(required=True)
        qs = PaymentVoucherHeader.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "paid_from",
            "paid_to",
            "payment_mode",
            "ap_settlement",
        )
        if entity_id is not None and entityfinid_id is not None:
            qs = qs.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            if subentity_id is None:
                qs = qs.filter(subentity__isnull=True)
            else:
                qs = qs.filter(subentity_id=subentity_id)
        if self.request.method.upper() == "GET":
            return qs.order_by("-voucher_date", "-id")
        return qs.prefetch_related(
            Prefetch("allocations", queryset=PaymentVoucherAllocation.objects.select_related("open_item"))
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method.upper() == "GET":
            ctx["skip_preview_numbers"] = True
        return ctx

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PaymentVoucherRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PaymentVoucherHeaderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _scope_ids(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = PaymentVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "entity",
            "entityfinid",
            "subentity",
            "paid_from",
            "paid_to",
            "payment_mode",
            "ap_settlement",
        ).prefetch_related(
            Prefetch("allocations", queryset=PaymentVoucherAllocation.objects.select_related("open_item")),
            "adjustments",
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(subentity_id=subentity_id)

    def perform_destroy(self, instance):
        if int(instance.status) != int(PaymentVoucherHeader.Status.DRAFT):
            raise ValidationError({"detail": "Only draft payment vouchers can be deleted. Use cancel flow."})
        super().perform_destroy(instance)


class PaymentVoucherConfirmAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            result = PaymentVoucherService.confirm_voucher(pk, confirmed_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": PaymentVoucherHeaderSerializer(result.header).data,
        })


class PaymentVoucherPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            result = PaymentVoucherService.post_voucher(pk, posted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": PaymentVoucherHeaderSerializer(result.header).data,
        })


class PaymentVoucherCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = PaymentVoucherService.cancel_voucher(pk, reason=reason, cancelled_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": PaymentVoucherHeaderSerializer(result.header).data,
        }, status=status.HTTP_200_OK)


class PaymentVoucherUnpostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            result = PaymentVoucherService.unpost_voucher(pk, unposted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": PaymentVoucherHeaderSerializer(result.header).data,
        }, status=status.HTTP_200_OK)
