from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from vouchers.models import VoucherHeader, VoucherLine
from vouchers.serializers.voucher import VoucherDetailSerializer, VoucherListSerializer, VoucherWriteSerializer
from vouchers.services.voucher_service import VoucherService


def _raise_validation_error(err: ValueError) -> None:
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"non_field_errors": [str(payload)]})


class _VoucherScopeMixin:
    def _scope_ids(self, *, required: bool = True):
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
            if subentity_id == 0:
                subentity_id = None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def _scoped_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids(required=True)
        qs = VoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "entity", "entityfinid", "subentity", "cash_bank_account", "cash_bank_account__ledger", "created_by", "approved_by", "cancelled_by"
        ).prefetch_related(Prefetch("lines", queryset=VoucherLine.objects.select_related("account", "account__ledger", "generated_from_line").order_by("line_no", "id")))
        return qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)


class VoucherListCreateAPIView(_VoucherScopeMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return VoucherListSerializer if self.request.method.upper() == "GET" else VoucherWriteSerializer

    def get_queryset(self):
        qs = self._scoped_queryset().order_by("-voucher_date", "-id")
        voucher_type = self.request.query_params.get("voucher_type")
        if voucher_type:
            qs = qs.filter(voucher_type=voucher_type)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(VoucherDetailSerializer(instance, context={"request": request}).data, status=status.HTTP_201_CREATED)


class VoucherRetrieveUpdateDestroyAPIView(_VoucherScopeMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self._scoped_queryset()

    def get_serializer_class(self):
        return VoucherDetailSerializer if self.request.method.upper() == "GET" else VoucherWriteSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(VoucherDetailSerializer(instance, context={"request": request}).data)

    def perform_destroy(self, instance):
        if int(instance.status) != int(VoucherHeader.Status.DRAFT):
            raise ValidationError({"detail": "Only draft vouchers can be deleted. Use cancel flow."})
        super().perform_destroy(instance)


class VoucherConfirmAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            result = VoucherService.confirm_voucher(pk, confirmed_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data})


class VoucherPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            result = VoucherService.post_voucher(pk, posted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data})


class VoucherApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        action = (request.data.get("action") or "").strip().lower()
        remarks = (request.data.get("remarks") or "").strip() or None
        try:
            if action == "submit":
                result = VoucherService.submit_voucher(pk, submitted_by_id=request.user.id, remarks=remarks)
            elif action == "approve":
                result = VoucherService.approve_voucher(pk, approved_by_id=request.user.id, remarks=remarks)
            elif action == "reject":
                result = VoucherService.reject_voucher(pk, rejected_by_id=request.user.id, remarks=remarks)
            else:
                raise ValidationError({"detail": "action must be submit|approve|reject"})
        except ValueError as e:
            _raise_validation_error(e)
        out = VoucherDetailSerializer(result.header, context={"request": request}).data
        return Response({"message": result.message, "approval_status": out.get("approval_status", "DRAFT"), "approval_status_name": out.get("approval_status_name", "Draft"), "data": out})


class VoucherUnpostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        try:
            result = VoucherService.unpost_voucher(pk, unposted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data})


class VoucherCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = VoucherService.cancel_voucher(pk, cancelled_by_id=request.user.id, reason=reason)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data}, status=status.HTTP_200_OK)


class VoucherSummaryAPIView(_VoucherScopeMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _action_flags(self, voucher: VoucherHeader):
        is_draft = int(voucher.status) == int(VoucherHeader.Status.DRAFT)
        is_confirmed = int(voucher.status) == int(VoucherHeader.Status.CONFIRMED)
        is_posted = int(voucher.status) == int(VoucherHeader.Status.POSTED)
        is_cancelled = int(voucher.status) == int(VoucherHeader.Status.CANCELLED)
        return {
            "can_edit": not is_posted and not is_cancelled,
            "can_confirm": is_draft,
            "can_post": is_confirmed,
            "can_cancel": is_draft or is_confirmed,
            "can_unpost": is_posted,
            "status": int(voucher.status),
            "status_name": voucher.get_status_display(),
        }

    def _cash_bank_block(self, voucher: VoucherHeader):
        acct = voucher.cash_bank_account
        if not acct:
            return None
        return {
            "id": acct.id,
            "accountname": getattr(acct, "accountname", None),
            "display_name": getattr(acct, "effective_accounting_name", None),
            "accountcode": getattr(acct, "effective_accounting_code", None),
            "ledger_id": voucher.cash_bank_ledger_id or getattr(acct, "ledger_id", None),
            "partytype": getattr(acct, "partytype", None),
            "gstno": getattr(acct, "gstno", None),
            "pan": getattr(acct, "pan", None),
        }

    def get(self, request, pk: int):
        voucher = self._scoped_queryset().get(pk=pk)
        line_count = voucher.lines.filter(is_system_generated=False).count()
        system_line_count = voucher.lines.filter(is_system_generated=True).count()
        return Response(
            {
                "voucher_id": voucher.id,
                "voucher_date": voucher.voucher_date,
                "doc_code": voucher.doc_code,
                "doc_no": voucher.doc_no,
                "voucher_code": voucher.voucher_code,
                "voucher_type": voucher.voucher_type,
                "voucher_type_name": voucher.get_voucher_type_display(),
                "status": int(voucher.status),
                "status_name": voucher.get_status_display(),
                "cash_bank_account": self._cash_bank_block(voucher),
                "total_debit_amount": voucher.total_debit_amount,
                "total_credit_amount": voucher.total_credit_amount,
                "balance_amount": voucher.total_debit_amount - voucher.total_credit_amount,
                "counts": {
                    "line_count": line_count,
                    "system_line_count": system_line_count,
                    "business_line_count": line_count,
                },
                "action_flags": self._action_flags(voucher),
            }
        )
