from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from vouchers.models import VoucherHeader, VoucherLine
from vouchers.serializers.voucher import VoucherDetailSerializer, VoucherListSerializer, VoucherWriteSerializer
from rbac.services import EffectivePermissionService
from vouchers.services.voucher_service import VoucherService
from financial.profile_access import account_gstno, account_pan, account_partytype
from helpers.utils.api_validation import (
    raise_structured_validation_error,
    raise_scope_type_error,
    require_query_scope,
)
from helpers.utils.document_actions import build_document_action_flags



def _perm_code(voucher_type: str, action: str) -> str:
    vt = (voucher_type or "").upper()
    suffix = {"CASH": "cash", "BANK": "bank", "JOURNAL": "journal"}.get(vt)
    if not suffix:
        return ""
    return f"voucher.{suffix}.{action}"


def _assert_permission(user, *, entity_id: int, voucher_type: str, action: str):
    code = _perm_code(voucher_type, action)
    if not code:
        raise PermissionDenied({"detail": "Unknown voucher type for permission check."})
    codes = EffectivePermissionService.permission_codes_for_user(user, entity_id)
    if code not in codes:
        raise PermissionDenied({"detail": f"Missing permission: {code}"})


def _raise_validation_error(err: ValueError) -> None:
    payload = err.args[0] if err.args else str(err)
    raise_structured_validation_error(payload)


class _VoucherScopeMixin:
    def _scope_ids(self, *, required: bool = True):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        if required:
            require_query_scope(entity, entityfinid)
        if not entity or not entityfinid:
            return None, None, None
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
        except (TypeError, ValueError):
            raise_scope_type_error()
        return entity_id, entityfinid_id, subentity_id

    def _scoped_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids(required=True)
        qs = VoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "entity", "entityfinid", "subentity", "cash_bank_account", "cash_bank_account__ledger", "created_by", "approved_by", "cancelled_by"
        ).prefetch_related(Prefetch("lines", queryset=VoucherLine.objects.select_related("account", "account__ledger", "generated_from_line").order_by("line_no", "id")))
        return qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)


class _VoucherScopedActionMixin(_VoucherScopeMixin):
    """
    For state-changing actions enforce entity/entityfinid/subentity scoping
    to avoid cross-tenant access.
    """

    def _get_header(self, pk: int) -> VoucherHeader:
        return self._scoped_queryset().get(pk=pk)

    def _require(self, header: VoucherHeader, action: str):
        _assert_permission(self.request.user, entity_id=header.entity_id, voucher_type=header.voucher_type, action=action)


class VoucherListCreateAPIView(_VoucherScopeMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return VoucherListSerializer if self.request.method.upper() == "GET" else VoucherWriteSerializer

    def get_queryset(self):
        qs = self._scoped_queryset().order_by("-voucher_date", "-id")
        voucher_type = self.request.query_params.get("voucher_type")
        if voucher_type:
            qs = qs.filter(voucher_type=voucher_type)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id, _, _ = self._scope_ids(required=True)
        voucher_type = serializer.validated_data.get("voucher_type") or VoucherHeader.VoucherType.JOURNAL
        _assert_permission(request.user, entity_id=entity_id, voucher_type=voucher_type, action="create")
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
        _assert_permission(request.user, entity_id=instance.entity_id, voucher_type=instance.voucher_type, action="update")
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(VoucherDetailSerializer(instance, context={"request": request}).data)

    def perform_destroy(self, instance):
        if int(instance.status) != int(VoucherHeader.Status.DRAFT):
            raise ValidationError({"non_field_errors": ["Only draft vouchers can be deleted. Use cancel flow."]})
        _assert_permission(self.request.user, entity_id=instance.entity_id, voucher_type=instance.voucher_type, action="delete")
        super().perform_destroy(instance)


class VoucherConfirmAPIView(_VoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        self._require(header, "confirm")
        try:
            result = VoucherService.confirm_voucher(header.id, confirmed_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data})


class VoucherPostAPIView(_VoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        self._require(header, "post")
        try:
            result = VoucherService.post_voucher(header.id, posted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data})


class VoucherApprovalAPIView(_VoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        action = (request.data.get("action") or "").strip().lower()
        remarks = (request.data.get("remarks") or "").strip() or None
        try:
            if action == "submit":
                self._require(header, "submit")
                result = VoucherService.submit_voucher(header.id, submitted_by_id=request.user.id, remarks=remarks)
            elif action == "approve":
                self._require(header, "approve")
                result = VoucherService.approve_voucher(header.id, approved_by_id=request.user.id, remarks=remarks)
            elif action == "reject":
                self._require(header, "reject")
                result = VoucherService.reject_voucher(header.id, rejected_by_id=request.user.id, remarks=remarks)
            else:
                raise ValidationError({"action": "Use submit, approve, or reject."})
        except ValueError as e:
            _raise_validation_error(e)
        out = VoucherDetailSerializer(result.header, context={"request": request}).data
        return Response({"message": result.message, "approval_status": out.get("approval_status", "DRAFT"), "approval_status_name": out.get("approval_status_name", "Draft"), "data": out})


class VoucherUnpostAPIView(_VoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        self._require(header, "unpost")
        try:
            result = VoucherService.unpost_voucher(header.id, unposted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data})


class VoucherCancelAPIView(_VoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        self._require(header, "cancel")
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = VoucherService.cancel_voucher(header.id, cancelled_by_id=request.user.id, reason=reason)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({"message": result.message, "data": VoucherDetailSerializer(result.header, context={"request": request}).data}, status=status.HTTP_200_OK)


class VoucherSummaryAPIView(_VoucherScopeMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _action_flags(self, voucher: VoucherHeader):
        return build_document_action_flags(
            status_value=int(voucher.status),
            draft_status=int(VoucherHeader.Status.DRAFT),
            confirmed_status=int(VoucherHeader.Status.CONFIRMED),
            posted_status=int(VoucherHeader.Status.POSTED),
            cancelled_status=int(VoucherHeader.Status.CANCELLED),
            status_name=voucher.get_status_display(),
        )

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
            "partytype": account_partytype(acct),
            "gstno": account_gstno(acct),
            "pan": account_pan(acct),
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

