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
            "paid_from__ledger",
            "paid_to",
            "paid_to__ledger",
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
            Prefetch("allocations", queryset=PaymentVoucherAllocation.objects.select_related("open_item")),
            "advance_adjustments__advance_balance__payment_voucher",
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method.upper() == "GET":
            ctx["skip_preview_numbers"] = True
            ctx["skip_navigation"] = True
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
            "paid_from__ledger",
            "paid_to",
            "paid_to__ledger",
            "payment_mode",
            "ap_settlement",
        ).prefetch_related(
            Prefetch("allocations", queryset=PaymentVoucherAllocation.objects.select_related("open_item")),
            "advance_adjustments__advance_balance__payment_voucher",
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


class PaymentVoucherApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        action = (request.data.get("action") or "").strip().lower()
        remarks = (request.data.get("remarks") or "").strip() or None
        try:
            if action == "submit":
                result = PaymentVoucherService.submit_voucher(pk, submitted_by_id=request.user.id, remarks=remarks)
            elif action == "approve":
                result = PaymentVoucherService.approve_voucher(pk, approved_by_id=request.user.id, remarks=remarks)
            elif action == "reject":
                result = PaymentVoucherService.reject_voucher(pk, rejected_by_id=request.user.id, remarks=remarks)
            else:
                raise ValidationError({"detail": "action must be submit|approve|reject"})
        except ValueError as e:
            _raise_validation_error(e)
        out = PaymentVoucherHeaderSerializer(result.header).data
        return Response({
            "message": result.message,
            "approval_status": out.get("approval_status", "DRAFT"),
            "approval_status_name": out.get("approval_status_name", "Draft"),
            "data": out,
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


class PaymentVoucherSettlementSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
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

        qs = PaymentVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        voucher = qs.prefetch_related("allocations", "advance_adjustments").get(pk=pk)
        ser = PaymentVoucherHeaderSerializer(voucher, context={"skip_preview_numbers": True})
        data = ser.data
        return Response({
            "cash_paid_amount": data.get("cash_paid_amount", 0),
            "adjustment_effect_amount": data.get("total_adjustment_amount", 0),
            "advance_consumed_amount": data.get("advance_consumed_amount", 0),
            "total_settlement_support_amount": data.get("total_settlement_support_amount", 0),
            "allocated_amount": data.get("allocated_amount", 0),
            "balance_amount": data.get("settlement_balance_amount", 0),
        })
