from __future__ import annotations

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from receipts.models import ReceiptVoucherHeader, ReceiptVoucherAllocation
from rbac.services import EffectivePermissionService
from receipts.serializers.receipt_voucher import (
    ReceiptVoucherHeaderSerializer,
    ReceiptVoucherLookupSerializer,
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


def _workflow_feedback(message: str) -> dict:
    trimmed = str(message or "").strip()
    lower = trimmed.lower()
    if lower.startswith("posted with warnings:"):
        warning_text = trimmed.split(":", 1)[1].strip() if ":" in trimmed else ""
        warnings = [item.strip() for item in warning_text.split("|") if item.strip()]
        return {
            "notice": "Posting completed with policy warnings.",
            "warnings": warnings,
        }
    return {
        "notice": trimmed,
        "warnings": [],
    }


def _duplicate_reference_warnings(voucher: ReceiptVoucherHeader) -> list[str]:
    reference = str(getattr(voucher, "reference_number", "") or "").strip()
    if not reference:
        return []
    duplicates = ReceiptVoucherHeader.objects.filter(
        entity_id=voucher.entity_id,
        entityfinid_id=voucher.entityfinid_id,
        reference_number__iexact=reference,
        received_from_id=voucher.received_from_id,
    ).exclude(pk=voucher.id).order_by("-voucher_date", "-id")
    if getattr(voucher, "subentity_id", None):
        duplicates = duplicates.filter(subentity_id=voucher.subentity_id)
    first = duplicates.only("voucher_code", "doc_code", "doc_no").first()
    if not first:
        return []
    voucher_label = getattr(first, "voucher_code", None) or f"{getattr(first, 'doc_code', '')}-{getattr(first, 'doc_no', '')}".strip("-")
    if voucher_label:
        return [f"Reference already appears on voucher {voucher_label}. Please double-check before proceeding."]
    return ["Reference already appears on another receipt voucher. Please double-check before proceeding."]


def _attach_reference_feedback(response: Response, voucher: ReceiptVoucherHeader) -> Response:
    if voucher is None or not isinstance(getattr(response, "data", None), dict):
        return response
    warnings = _duplicate_reference_warnings(voucher)
    if not warnings:
        return response
    response.data["notice"] = "Saved with review warnings."
    response.data["warnings"] = warnings
    return response


class ReceiptVoucherApprovalActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("submit", "approve", "reject"))
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)


class ReceiptVoucherCancelActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)


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


class _ReceiptVoucherScopedActionMixin:
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

    def _get_header(self, pk: int):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = ReceiptVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).only("id", "entity_id")
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        return get_object_or_404(qs, pk=pk)


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
        self._saved_instance = serializer.save(created_by=self.request.user)

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
        response = super().create(request, *args, **kwargs)
        return _attach_reference_feedback(response, getattr(self, "_saved_instance", None))


class ReceiptVoucherLookupAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReceiptVoucherLookupSerializer

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

    def _parse_limit(self) -> int:
        raw_limit = self.request.query_params.get("limit")
        if raw_limit in (None, "", "null"):
            return 100
        try:
            parsed = int(raw_limit)
        except (TypeError, ValueError):
            raise ValidationError({"limit": "limit must be an integer."})
        return min(max(parsed, 1), 250)

    def _base_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        _require_receipt_permission(self.request.user, entity_id=entity_id, action="view")
        qs = ReceiptVoucherHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        ).select_related(
            "received_in",
            "received_in__ledger",
            "received_in__commercial_profile",
            "received_from",
            "received_from__ledger",
            "received_from__commercial_profile",
        )
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        search = str(self.request.query_params.get("search") or self.request.query_params.get("q") or "").strip()
        status_value = self.request.query_params.get("status")
        receipt_type = self.request.query_params.get("receipt_type")
        party_id = self.request.query_params.get("received_from")
        if status_value:
            qs = qs.filter(status=status_value)
        if receipt_type:
            qs = qs.filter(receipt_type=receipt_type)
        if party_id:
            qs = qs.filter(received_from_id=party_id)
        if search:
            qs = qs.filter(
                Q(voucher_code__icontains=search)
                | Q(doc_code__icontains=search)
                | Q(doc_no__icontains=search)
                | Q(reference_number__icontains=search)
                | Q(received_from__accountname__icontains=search)
                | Q(received_in__accountname__icontains=search)
            )
        return qs.order_by("-voucher_date", "-id")

    def get(self, request, *args, **kwargs):
        queryset = self._base_queryset()
        total_count = queryset.count()
        limit = self._parse_limit()
        items = queryset[:limit]
        serializer = self.get_serializer(items, many=True, context={"request": request})
        returned_count = len(serializer.data)
        return Response({
            "items": serializer.data,
            "total_count": total_count,
            "returned_count": returned_count,
            "limit": limit,
            "has_more": total_count > returned_count,
        })


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

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="update")
        return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        self._saved_instance = serializer.save()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="update")
        response = super().update(request, *args, **kwargs)
        return _attach_reference_feedback(response, getattr(self, "_saved_instance", None))

    def perform_destroy(self, instance):
        if int(instance.status) != int(ReceiptVoucherHeader.Status.DRAFT):
            raise ValidationError({"non_field_errors": ["Only draft receipt vouchers can be deleted. Use cancel flow."]})
        super().perform_destroy(instance)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _require_receipt_permission(request.user, entity_id=instance.entity_id, action="delete")
        return super().destroy(request, *args, **kwargs)


class ReceiptVoucherConfirmAPIView(_ReceiptVoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="confirm")
        try:
            result = ReceiptVoucherService.confirm_voucher(pk, confirmed_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            **_workflow_feedback(result.message),
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        })


class ReceiptVoucherPostAPIView(_ReceiptVoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="post")
        try:
            result = ReceiptVoucherService.post_voucher(pk, posted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            **_workflow_feedback(result.message),
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        })


class ReceiptVoucherApprovalAPIView(_ReceiptVoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        serializer = ReceiptVoucherApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        remarks = serializer.validated_data.get("remarks") or None
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
        except ValueError as e:
            _raise_validation_error(e)
        out = ReceiptVoucherHeaderSerializer(result.header).data
        return Response({
            "message": result.message,
            **_workflow_feedback(result.message),
            "approval_status": out.get("approval_status", "DRAFT"),
            "approval_status_name": out.get("approval_status_name", "Draft"),
            "data": out,
        })


class ReceiptVoucherCancelAPIView(_ReceiptVoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="cancel")
        serializer = ReceiptVoucherCancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason") or None
        try:
            result = ReceiptVoucherService.cancel_voucher(pk, reason=reason, cancelled_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            **_workflow_feedback(result.message),
            "data": ReceiptVoucherHeaderSerializer(result.header).data,
        }, status=status.HTTP_200_OK)


class ReceiptVoucherUnpostAPIView(_ReceiptVoucherScopedActionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        header = self._get_header(pk)
        _require_receipt_permission(request.user, entity_id=header.entity_id, action="unpost")
        try:
            result = ReceiptVoucherService.unpost_voucher(pk, unposted_by_id=request.user.id)
        except ValueError as e:
            _raise_validation_error(e)
        return Response({
            "message": result.message,
            **_workflow_feedback(result.message),
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
