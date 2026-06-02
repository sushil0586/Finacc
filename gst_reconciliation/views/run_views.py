from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from gst_reconciliation.pagination import GstReconciliationPagination
from gst_reconciliation.models import GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.serializers import (
    GstReconciliationItemSerializer,
    GstReconciliationRunCreateSerializer,
    GstReconciliationRunListRowSerializer,
    GstReconciliationRunSerializer,
    GstRunActionSerializer,
    PurchaseGstr2bBatchAdapterSerializer,
)
from gst_reconciliation.services.adapters import PurchaseGstr2bBatchAdapter
from gst_reconciliation.services.access import GstReconciliationWorkflowAccess
from gst_reconciliation.services.performance import timed_call
from gst_reconciliation.services.run_service import GstReconciliationRunLifecycleService
from gst_reconciliation.services.ui_service import GstReconciliationUiService


class GstReconciliationRunListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        if not entity_id:
            raise ValidationError({"entity": ["Entity is required."]})
        GstReconciliationWorkflowAccess.assert_can_view_scope(user=self.request.user, entity_id=int(entity_id))
        queryset = GstReconciliationRun.objects.all().select_related(
            "entity",
            "entityfinid",
            "subentity",
            "imported_return",
            "submitted_by",
            "reviewed_by",
            "approved_by",
            "closed_by",
        )
        reconciliation_type = self.request.query_params.get("reconciliation_type")
        return_period = self.request.query_params.get("return_period")
        status_value = self.request.query_params.get("status")
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        if reconciliation_type:
            queryset = queryset.filter(reconciliation_type=reconciliation_type)
        if return_period:
            queryset = queryset.filter(return_period=return_period)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset.order_by("-created_at", "-id")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return GstReconciliationRunCreateSerializer
        return GstReconciliationRunSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        GstReconciliationWorkflowAccess.assert_can_manage_scope(
            user=request.user,
            entity_id=serializer.validated_data["entity"].id,
        )
        run = GstReconciliationRunLifecycleService.create_run(serializer=serializer, user=request.user)
        output = GstReconciliationRunSerializer(run, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)


class GstReconciliationRunSummaryListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = GstReconciliationPagination

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        if not entity_id:
            raise ValidationError({"entity": ["Entity is required."]})
        GstReconciliationWorkflowAccess.assert_can_view_scope(user=self.request.user, entity_id=int(entity_id))
        queryset = GstReconciliationRun.objects.all().select_related(
            "entity",
            "entityfinid",
            "subentity",
            "imported_return",
        )
        reconciliation_type = self.request.query_params.get("reconciliation_type")
        return_period = self.request.query_params.get("return_period")
        status_value = self.request.query_params.get("status")
        gst_registration_gstin = self.request.query_params.get("gst_registration_gstin")
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        if reconciliation_type:
            queryset = queryset.filter(reconciliation_type=reconciliation_type)
        if return_period:
            queryset = queryset.filter(return_period=return_period)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if gst_registration_gstin:
            queryset = queryset.filter(gst_registration_gstin__iexact=gst_registration_gstin)
        ordering = self.request.query_params.get("ordering") or "-created_at"
        allowed = {
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "return_period",
            "-return_period",
            "status",
            "-status",
        }
        if ordering not in allowed:
            ordering = "-created_at"
        return GstReconciliationUiService.build_run_list_summary_queryset(queryset).order_by(ordering, "-id")

    def list(self, request, *args, **kwargs):
        def _build_payload():
            queryset = self.get_queryset()
            page = self.paginate_queryset(queryset)
            rows = page if page is not None else queryset
            payload = [GstReconciliationUiService.build_run_list_row(run) for run in rows]
            return page, payload

        timed = timed_call("run_summary_list", _build_payload, entity_id=request.query_params.get("entity"))
        page, payload = timed.value
        serializer = GstReconciliationRunListRowSerializer(payload, many=True)
        if page is not None:
            response = self.paginator.get_paginated_response(
                serializer.data,
                meta_echo={"ordering": request.query_params.get("ordering") or "-created_at", "timing_ms": timed.duration_ms},
            )
            response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
            return response
        response = Response({"meta": {"count": len(payload), "timing_ms": timed.duration_ms}, "rows": serializer.data}, status=status.HTTP_200_OK)
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response


class GstReconciliationRunDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = GstReconciliationRun.objects.all().select_related(
        "entity",
        "entityfinid",
        "subentity",
        "imported_return",
        "submitted_by",
        "reviewed_by",
        "approved_by",
        "closed_by",
    ).prefetch_related("items__mismatch_reasons", "action_logs")
    serializer_class = GstReconciliationRunSerializer

    def get_object(self):
        obj = super().get_object()
        GstReconciliationWorkflowAccess.assert_can_view_run(user=self.request.user, run=obj)
        return obj


class GstReconciliationRunItemListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GstReconciliationItemSerializer

    def get_queryset(self):
        run = GstReconciliationRun.objects.get(pk=self.kwargs["pk"])
        GstReconciliationWorkflowAccess.assert_can_view_run(user=self.request.user, run=run)
        return (
            GstReconciliationItem.objects.filter(run_id=self.kwargs["pk"])
            .select_related("run")
            .prefetch_related("mismatch_reasons")
            .order_by("id")
        )


class _RunActionBaseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_run(self, pk: int) -> GstReconciliationRun:
        run = GstReconciliationRun.objects.get(pk=pk)
        GstReconciliationWorkflowAccess.assert_can_view_run(user=self.request.user, run=run)
        return run

    def get_comment(self, request) -> str | None:
        serializer = GstRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data.get("comment")

    def response_for_run(self, run: GstReconciliationRun):
        payload = GstReconciliationRunSerializer(run).data
        return Response(payload, status=status.HTTP_200_OK)


class GstReconciliationRunSubmitAPIView(_RunActionBaseAPIView):
    def post(self, request, pk: int):
        run = self.get_run(pk)
        GstReconciliationWorkflowAccess.assert_can_manage_scope(user=request.user, entity_id=run.entity_id)
        try:
            GstReconciliationRunLifecycleService.submit_run(run=run, user=request.user, comment=self.get_comment(request))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        run.refresh_from_db()
        return self.response_for_run(run)


class GstReconciliationRunReviewStartAPIView(_RunActionBaseAPIView):
    def post(self, request, pk: int):
        run = self.get_run(pk)
        GstReconciliationWorkflowAccess.assert_can_review_scope(user=request.user, entity_id=run.entity_id)
        try:
            GstReconciliationRunLifecycleService.start_review(run=run, user=request.user, comment=self.get_comment(request))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        run.refresh_from_db()
        return self.response_for_run(run)


class GstReconciliationRunApproveAPIView(_RunActionBaseAPIView):
    def post(self, request, pk: int):
        run = self.get_run(pk)
        GstReconciliationWorkflowAccess.assert_can_review_scope(user=request.user, entity_id=run.entity_id)
        try:
            GstReconciliationRunLifecycleService.approve_run(run=run, user=request.user, comment=self.get_comment(request))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        run.refresh_from_db()
        return self.response_for_run(run)


class GstReconciliationRunRejectAPIView(_RunActionBaseAPIView):
    def post(self, request, pk: int):
        run = self.get_run(pk)
        GstReconciliationWorkflowAccess.assert_can_review_scope(user=request.user, entity_id=run.entity_id)
        try:
            GstReconciliationRunLifecycleService.reject_run(run=run, user=request.user, comment=self.get_comment(request))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        run.refresh_from_db()
        return self.response_for_run(run)


class GstReconciliationRunCloseAPIView(_RunActionBaseAPIView):
    def post(self, request, pk: int):
        run = self.get_run(pk)
        GstReconciliationWorkflowAccess.assert_can_manage_scope(user=request.user, entity_id=run.entity_id)
        try:
            GstReconciliationRunLifecycleService.close_run(run=run, user=request.user, comment=self.get_comment(request))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        run.refresh_from_db()
        return self.response_for_run(run)


class GstReconciliationRunMatchAPIView(_RunActionBaseAPIView):
    def post(self, request, pk: int):
        run = self.get_run(pk)
        GstReconciliationWorkflowAccess.assert_can_manage_scope(user=request.user, entity_id=run.entity_id)
        try:
            prefer_async = str(request.query_params.get("async", "")).lower() in {"1", "true", "yes"}
            GstReconciliationRunLifecycleService.execute_matching(run=run, user=request.user, prefer_async=prefer_async)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        run.refresh_from_db()
        return self.response_for_run(run)


class PurchaseGstr2bBatchCreateRunAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, batch_id: int):
        from purchase.models.gstr2b_models import Gstr2bImportBatch

        batch = Gstr2bImportBatch.objects.select_related("entity").get(pk=batch_id)
        GstReconciliationWorkflowAccess.assert_can_manage_scope(user=request.user, entity_id=batch.entity_id)
        serializer = PurchaseGstr2bBatchAdapterSerializer(
            data={
                "batch_id": batch_id,
                "match_strategy_code": request.data.get("match_strategy_code"),
                "notes": request.data.get("notes"),
            }
        )
        serializer.is_valid(raise_exception=True)
        result = PurchaseGstr2bBatchAdapter.build_run_from_batch(
            batch_id=serializer.validated_data["batch_id"],
            user=request.user,
            match_strategy_code=serializer.validated_data.get("match_strategy_code") or "purchase_gstr2b_existing",
            notes=serializer.validated_data.get("notes"),
        )
        payload = GstReconciliationRunSerializer(result.run).data
        response_status = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(payload, status=response_status)
