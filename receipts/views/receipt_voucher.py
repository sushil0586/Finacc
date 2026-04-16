from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from receipts.models import ReceiptVoucherHeader, ReceiptVoucherAllocation
from rbac.services import EffectivePermissionService
from receipts.serializers.receipt_voucher import (
    ReceiptVoucherHeaderSerializer,
    ReceiptVoucherListSerializer,
)
from receipts.services.receipt_voucher_service import ReceiptVoucherService
from financial.profile_access import account_gstno, account_pan, account_partytype
from helpers.utils.api_validation import (
    raise_structured_validation_error,
    raise_scope_type_error,
    require_query_scope,
)
from helpers.utils.document_actions import build_document_action_flags


def _raise_validation_error(err: ValueError) -> None:
    payload = err.args[0] if err.args else str(err)
    raise_structured_validation_error(payload)


def _receipt_permission_code(action: str) -> str:
    return f"voucher.receipt.{action}"


def _require_receipt_permission(user, *, entity_id: int, action: str):
    entity = EffectivePermissionService.entity_for_user(user, int(entity_id))
    if entity is None:
        raise PermissionDenied({"detail": "Entity not found or inaccessible."})

    permission_codes = EffectivePermissionService.permission_codes_for_user(user, int(entity_id))
    permission_code = _receipt_permission_code(action)
    legacy_code = f"receipt.voucher.{action}"
    if permission_code not in permission_codes and legacy_code not in permission_codes:
        raise PermissionDenied({"detail": f"Missing permission: {permission_code}"})


class ReceiptVoucherListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def _scope_ids(self, *, required: bool):
        if self.request.method.upper() == "POST":
            return None, None, None
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

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ReceiptVoucherListSerializer
        return ReceiptVoucherHeaderSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids(required=True)
        _require_receipt_permission(self.request.user, entity_id=entity_id, action="view")
        qs = ReceiptVoucherHeader.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "received_in",
            "received_in__ledger",
            "received_from",
            "received_from__ledger",
            "receipt_mode",
            "ap_settlement",
        )
        if entity_id is not None and entityfinid_id is not None:
            qs = qs.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            if subentity_id is not None:
                qs = qs.filter(subentity_id=subentity_id)
        if self.request.method.upper() == "GET":
            return qs.order_by("-voucher_date", "-id")
        return qs.prefetch_related(
            Prefetch("allocations", queryset=ReceiptVoucherAllocation.objects.select_related("open_item")),
            "advance_adjustments__advance_balance__receipt_voucher",
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method.upper() == "GET":
            ctx["skip_preview_numbers"] = True
            ctx["skip_navigation"] = True
        return ctx

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        payload = request.data if isinstance(getattr(request, "data", None), dict) else {}
        entity_id = payload.get("entity_id", payload.get("entity"))
        if entity_id in (None, "", "null"):
            raise ValidationError({"entity": "This field is required."})
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError):
            raise ValidationError({"entity": "Must be an integer."})
        _require_receipt_permission(request.user, entity_id=entity_id, action="create")
        return super().create(request, *args, **kwargs)


class ReceiptVoucherRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReceiptVoucherHeaderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _scope_ids(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        require_query_scope(entity, entityfinid)
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
        except (TypeError, ValueError):
            raise_scope_type_error()
        return entity_id, entityfinid_id, subentity_id

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = ReceiptVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "entity",
            "entityfinid",
            "subentity",
            "received_in",
            "received_in__ledger",
            "received_from",
            "received_from__ledger",
            "receipt_mode",
            "ap_settlement",
        ).prefetch_related(
            Prefetch("allocations", queryset=ReceiptVoucherAllocation.objects.select_related("open_item")),
            "advance_adjustments__advance_balance__receipt_voucher",
            "adjustments",
        )
        if subentity_id is None:
            return qs
        return qs.filter(subentity_id=subentity_id)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="view")
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="update")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="update")
        return super().partial_update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if int(instance.status) != int(ReceiptVoucherHeader.Status.DRAFT):
            raise ValidationError({"non_field_errors": ["Only draft receipt vouchers can be deleted. Use cancel flow."]})
        super().perform_destroy(instance)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="delete")
        return super().destroy(request, *args, **kwargs)


class ReceiptVoucherConfirmAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = ReceiptVoucherHeader.objects.only("id", "entity_id").get(pk=pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="confirm")
        try:
            result = ReceiptVoucherService.confirm_voucher(pk, confirmed_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        })


class ReceiptVoucherPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = ReceiptVoucherHeader.objects.only("id", "entity_id").get(pk=pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="post")
        try:
            result = ReceiptVoucherService.post_voucher(pk, posted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        })


class ReceiptVoucherApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = ReceiptVoucherHeader.objects.only("id", "entity_id").get(pk=pk)
        action = (request.data.get("action") or "").strip().lower()
        remarks = (request.data.get("remarks") or "").strip() or None
        try:
            if action == "submit":
                _require_receipt_permission(request.user, entity_id=header.entity_id, action="submit")
                result = ReceiptVoucherService.submit_voucher(pk, submitted_by_id=request.user.id, remarks=remarks)
            elif action == "approve":
                _require_receipt_permission(request.user, entity_id=header.entity_id, action="approve")
                result = ReceiptVoucherService.approve_voucher(pk, approved_by_id=request.user.id, remarks=remarks)
            elif action == "reject":
                _require_receipt_permission(request.user, entity_id=header.entity_id, action="reject")
                result = ReceiptVoucherService.reject_voucher(pk, rejected_by_id=request.user.id, remarks=remarks)
            else:
                raise ValidationError({"action": "Use submit, approve, or reject."})
        except ValueError as e:
            _raise_validation_error(e)
        out = ReceiptVoucherHeaderSerializer(result.header).data
        return Response({
            "message": result.message,
            "approval_status": out.get("approval_status", "DRAFT"),
            "approval_status_name": out.get("approval_status_name", "Draft"),
            "data": out,
        })


class ReceiptVoucherCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = ReceiptVoucherHeader.objects.only("id", "entity_id").get(pk=pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="cancel")
        reason = (request.data.get("reason") or "").strip() or None
        try:
            result = ReceiptVoucherService.cancel_voucher(pk, reason=reason, cancelled_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        }, status=status.HTTP_200_OK)


class ReceiptVoucherUnpostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = ReceiptVoucherHeader.objects.only("id", "entity_id").get(pk=pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="unpost")
        try:
            result = ReceiptVoucherService.unpost_voucher(pk, unposted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        }, status=status.HTTP_200_OK)


class ReceiptVoucherSettlementSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _action_flags(voucher: ReceiptVoucherHeader):
        return build_document_action_flags(
            status_value=int(voucher.status),
            draft_status=int(ReceiptVoucherHeader.Status.DRAFT),
            confirmed_status=int(ReceiptVoucherHeader.Status.CONFIRMED),
            posted_status=int(ReceiptVoucherHeader.Status.POSTED),
            cancelled_status=int(ReceiptVoucherHeader.Status.CANCELLED),
            status_name=voucher.get_status_display(),
        )

    @staticmethod
    def _account_block(voucher: ReceiptVoucherHeader, field_name: str):
        acct = getattr(voucher, field_name, None)
        if not acct:
            return None
        stored_ledger_id = getattr(voucher, f"{field_name}_ledger_id", None)
        return {
            "id": acct.id,
            "accountname": getattr(acct, "accountname", None),
            "display_name": getattr(acct, "effective_accounting_name", None),
            "accountcode": getattr(acct, "effective_accounting_code", None),
            "ledger_id": stored_ledger_id or getattr(acct, "ledger_id", None),
            "partytype": account_partytype(acct),
            "gstno": account_gstno(acct),
            "pan": account_pan(acct),
        }

    def get(self, request, pk: int):
        entity = request.query_params.get("entity")
        entityfinid = request.query_params.get("entityfinid")
        subentity = request.query_params.get("subentity")
        require_query_scope(entity, entityfinid)
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
            if subentity_id == 0:
                subentity_id = None
        except (TypeError, ValueError):
            raise_scope_type_error()
        _require_receipt_permission(request.user, entity_id=entity_id, action="view")

        qs = ReceiptVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        voucher = qs.select_related(
            "received_in",
            "received_in__ledger",
            "received_from",
            "received_from__ledger",
            "receipt_mode",
        ).prefetch_related("allocations", "advance_adjustments").filter(pk=pk).first()
        if not voucher:
            raise ValidationError({"voucher": "Receipt voucher not found in selected scope."})
        ser = ReceiptVoucherHeaderSerializer(voucher, context={"skip_preview_numbers": True})
        data = ser.data
        return Response({
            "voucher_id": voucher.id,
            "voucher_date": data.get("voucher_date"),
            "doc_code": data.get("doc_code"),
            "doc_no": data.get("doc_no"),
            "voucher_code": data.get("voucher_code"),
            "receipt_type": data.get("receipt_type"),
            "receipt_type_name": data.get("receipt_type_name"),
            "status": data.get("status"),
            "status_name": data.get("status_name"),
            "received_in": self._account_block(voucher, "received_in"),
            "received_from": self._account_block(voucher, "received_from"),
            "cash_received_amount": data.get("cash_received_amount", 0),
            "adjustment_effect_amount": data.get("total_adjustment_amount", 0),
            "advance_consumed_amount": data.get("advance_consumed_amount", 0),
            "total_settlement_support_amount": data.get("total_settlement_support_amount", 0),
            "allocated_amount": data.get("allocated_amount", 0),
            "balance_amount": data.get("settlement_balance_amount", 0),
            "action_flags": self._action_flags(voucher),
        })
