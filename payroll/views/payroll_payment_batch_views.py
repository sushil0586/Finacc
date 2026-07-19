from __future__ import annotations

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from payroll.models import PayrollPaymentBatch
from payroll.serializers import (
    PayrollPaymentBatchActionSerializer,
    PayrollPaymentBatchCreateSerializer,
    PayrollPaymentBatchDetailSerializer,
    PayrollPaymentBatchListSerializer,
)
from payroll.services import PayrollPaymentBatchService, PayrollPermissionService
from payroll.views.payroll_run_views import _raise_value_error
from payroll.views.scoped import PayrollScopedAPIView


def _assert_action_permission(request, action: str, *, entity_id: int | None = None) -> None:
    try:
        PayrollPermissionService.assert_action_access(user=request.user, action=action, entity_id=entity_id)
    except PermissionError as err:
        raise PermissionDenied(detail=str(err))


class PayrollPaymentBatchListCreateAPIView(PayrollScopedAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["entity", "entityfinid", "subentity", "source_type", "status", "payroll_run", "fnf_settlement"]

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        queryset = PayrollPaymentBatch.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "payroll_run__payroll_period",
            "fnf_settlement",
        ).filter(entity_id=entity_id)
        if entityfinid_id is not None:
            queryset = queryset.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        return queryset.order_by("-created_at", "-id")

    def get_serializer_class(self):
        if self.request.method.upper() == "POST":
            return PayrollPaymentBatchCreateSerializer
        return PayrollPaymentBatchListSerializer

    def list(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_entity_permission(
            request,
            entity_id=entity_id,
            permission_codes={
                "payroll.run.payment_handoff",
                "payments.payroll.handoff",
                "payroll.run.view",
                "payroll.run.manage",
            },
            label="view payroll payment batches",
        )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        source = data.get("payroll_run") or data.get("fnf_settlement")
        entity_id = getattr(source, "entity_id", None)
        entityfinid_id = getattr(source, "entityfinid_id", None)
        subentity_id = getattr(source, "subentity_id", None)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        _assert_action_permission(request, "payment_batch_create", entity_id=entity_id)
        try:
            if data["source_type"] == PayrollPaymentBatch.SourceType.PAYROLL_RUN:
                batch = PayrollPaymentBatchService.create_from_payroll_run(
                    run=data["payroll_run"],
                    user_id=request.user.id,
                    batch_name=data.get("batch_name", ""),
                    payout_date=data.get("payout_date"),
                    allow_non_positive_amounts=data.get("allow_non_positive_amounts", False),
                    export_format=data.get("export_format"),
                )
            else:
                batch = PayrollPaymentBatchService.create_from_fnf_settlement(
                    settlement=data["fnf_settlement"],
                    user_id=request.user.id,
                    batch_name=data.get("batch_name", ""),
                    payout_date=data.get("payout_date"),
                    allow_non_positive_amounts=data.get("allow_non_positive_amounts", False),
                    export_format=data.get("export_format"),
                )
        except ValueError as err:
            _raise_value_error(err)
        detail = PayrollPaymentBatch.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "payroll_run__payroll_period",
            "fnf_settlement",
        ).prefetch_related("lines", "exports", "status_logs").get(pk=batch.pk)
        return Response({"message": "Payment batch created.", "data": PayrollPaymentBatchDetailSerializer(detail).data}, status=201)


class PayrollPaymentBatchRetrieveAPIView(PayrollScopedAPIView, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollPaymentBatchDetailSerializer

    def get_queryset(self):
        return PayrollPaymentBatch.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "payroll_run__payroll_period",
            "payroll_run__created_by",
            "payroll_run__approved_by",
            "fnf_settlement",
            "approved_by",
            "exported_by",
            "paid_by",
            "failed_by",
            "cancelled_by",
        ).prefetch_related(
            "lines__payment_account",
            "exports__exported_by",
            "status_logs__acted_by",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        self._assert_entity_permission(
            self.request,
            entity_id=obj.entity_id,
            permission_codes={
                "payroll.run.payment_handoff",
                "payments.payroll.handoff",
                "payroll.run.view",
                "payroll.run.manage",
            },
            label="view payroll payment batches",
        )
        return obj


class PayrollPaymentBatchValidateAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PayrollPaymentBatchActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = PayrollPaymentBatch.objects.get(pk=pk)
        self._enforce_object_scope(request, batch)
        _assert_action_permission(request, "payment_batch_validate", entity_id=batch.entity_id)
        try:
            batch = PayrollPaymentBatchService.validate_batch(
                batch=batch,
                user_id=request.user.id,
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payment batch validated.", "data": PayrollPaymentBatchDetailSerializer(batch).data})


class PayrollPaymentBatchApproveAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PayrollPaymentBatchActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = PayrollPaymentBatch.objects.get(pk=pk)
        self._enforce_object_scope(request, batch)
        _assert_action_permission(request, "payment_batch_approve", entity_id=batch.entity_id)
        try:
            batch = PayrollPaymentBatchService.approve_batch(
                batch=batch,
                user_id=request.user.id,
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payment batch approved.", "data": PayrollPaymentBatchDetailSerializer(batch).data})


class PayrollPaymentBatchExportAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PayrollPaymentBatchActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = PayrollPaymentBatch.objects.get(pk=pk)
        self._enforce_object_scope(request, batch)
        _assert_action_permission(request, "payment_batch_export", entity_id=batch.entity_id)
        try:
            result = PayrollPaymentBatchService.export_batch(
                batch=batch,
                user_id=request.user.id,
                export_format=serializer.validated_data.get("export_format"),
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        response = HttpResponse(result.file_content, content_type=result.content_type)
        response["Content-Disposition"] = f'attachment; filename="{result.file_name}"'
        response["X-Payroll-Payment-Batch-Id"] = str(result.batch.id)
        response["X-Payroll-Payment-Batch-Status"] = str(result.batch.status)
        return response


class PayrollPaymentBatchMarkPaidAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PayrollPaymentBatchActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = PayrollPaymentBatch.objects.get(pk=pk)
        self._enforce_object_scope(request, batch)
        _assert_action_permission(request, "payment_batch_mark_paid", entity_id=batch.entity_id)
        try:
            batch = PayrollPaymentBatchService.mark_paid(
                batch=batch,
                user_id=request.user.id,
                payment_reference=serializer.validated_data.get("payment_reference", ""),
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payment batch marked paid.", "data": PayrollPaymentBatchDetailSerializer(batch).data})


class PayrollPaymentBatchMarkFailedAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PayrollPaymentBatchActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = PayrollPaymentBatch.objects.get(pk=pk)
        self._enforce_object_scope(request, batch)
        _assert_action_permission(request, "payment_batch_mark_failed", entity_id=batch.entity_id)
        try:
            batch = PayrollPaymentBatchService.mark_failed(
                batch=batch,
                user_id=request.user.id,
                failure_reason=serializer.validated_data.get("failure_reason", ""),
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payment batch marked failed.", "data": PayrollPaymentBatchDetailSerializer(batch).data})


class PayrollPaymentBatchCancelAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PayrollPaymentBatchActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = PayrollPaymentBatch.objects.get(pk=pk)
        self._enforce_object_scope(request, batch)
        _assert_action_permission(request, "payment_batch_cancel", entity_id=batch.entity_id)
        try:
            batch = PayrollPaymentBatchService.cancel_batch(
                batch=batch,
                user_id=request.user.id,
                cancellation_reason=serializer.validated_data.get("cancellation_reason", ""),
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payment batch cancelled.", "data": PayrollPaymentBatchDetailSerializer(batch).data})
