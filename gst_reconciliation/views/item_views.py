from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from Authentication.models import User
from gst_reconciliation.models import GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.pagination import GstReconciliationPagination
from gst_reconciliation.serializers import (
    GstBulkItemActionSerializer,
    GstItemActionSerializer,
    GstItemAssignSerializer,
    GstItemManualMatchSerializer,
    GstItemNotesSerializer,
    GstReconciliationActionLogSerializer,
    GstReconciliationItemGridSerializer,
    GstReconciliationItemSerializer,
)
from gst_reconciliation.services.dashboard_service import GstReconciliationDashboardService
from gst_reconciliation.services.access import GstReconciliationWorkflowAccess
from gst_reconciliation.services.item_workflow_service import GstReconciliationItemWorkflowService
from gst_reconciliation.services.performance import timed_call
from gst_reconciliation.services.ui_service import GstReconciliationUiService


class _ItemActionBaseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_item(self, pk: int) -> GstReconciliationItem:
        item = get_object_or_404(GstReconciliationItem.objects.select_related("run"), pk=pk)
        GstReconciliationWorkflowAccess.assert_can_view_item(user=self.request.user, item=item)
        return item

    def response_for_item(self, item: GstReconciliationItem) -> Response:
        item.refresh_from_db()
        return Response(GstReconciliationItemSerializer(item).data, status=status.HTTP_200_OK)


class _ItemGridFilterMixin:
    pagination_class = GstReconciliationPagination

    def filter_queryset(self, queryset):
        run_id = self.request.query_params.get("run")
        match_status = self.request.query_params.get("status")
        resolution_status = self.request.query_params.get("resolution_status")
        supplier_gstin = self.request.query_params.get("supplier_gstin")
        mismatch_reason = self.request.query_params.get("mismatch_reason")
        assigned_reviewer = self.request.query_params.get("assigned_reviewer")
        unresolved_only = self.request.query_params.get("unresolved_only")
        min_confidence = self.request.query_params.get("min_confidence")
        max_confidence = self.request.query_params.get("max_confidence")

        if run_id:
            queryset = queryset.filter(run_id=run_id)
        if match_status:
            queryset = queryset.filter(match_status=match_status)
        if resolution_status:
            queryset = queryset.filter(resolution_status=resolution_status)
        if supplier_gstin:
            queryset = queryset.filter(Q(counterparty_gstin__iexact=supplier_gstin) | Q(gstin__iexact=supplier_gstin))
        if mismatch_reason:
            queryset = queryset.filter(mismatch_reasons__code=mismatch_reason)
        if assigned_reviewer:
            queryset = queryset.filter(assigned_reviewer_id=assigned_reviewer)
        if min_confidence:
            queryset = queryset.filter(match_confidence_score__gte=min_confidence)
        if max_confidence:
            queryset = queryset.filter(match_confidence_score__lte=max_confidence)
        if str(unresolved_only).lower() in {"1", "true", "yes"}:
            queryset = queryset.exclude(
                resolution_status__in=[
                    GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                    GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                    GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                    GstReconciliationItem.ResolutionStatus.IGNORED,
                    GstReconciliationItem.ResolutionStatus.RESOLVED,
                ]
            )
        ordering = self.request.query_params.get("ordering") or "-updated_at"
        allowed = {
            "id",
            "-id",
            "invoice_date",
            "-invoice_date",
            "invoice_number",
            "-invoice_number",
            "match_confidence_score",
            "-match_confidence_score",
            "resolution_status",
            "-resolution_status",
            "match_status",
            "-match_status",
            "updated_at",
            "-updated_at",
        }
        if ordering not in allowed:
            ordering = "-updated_at"
        return queryset.distinct().order_by(ordering, "-id")


class GstReconciliationItemGridAPIView(_ItemActionBaseAPIView, _ItemGridFilterMixin):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        run_id = request.query_params.get("run")
        entity_id = request.query_params.get("entity")
        if run_id:
            scoped_run = get_object_or_404(GstReconciliationRun, pk=run_id)
            GstReconciliationWorkflowAccess.assert_can_view_run(user=request.user, run=scoped_run)
            entity_id = scoped_run.entity_id
        elif entity_id:
            GstReconciliationWorkflowAccess.assert_can_view_scope(user=request.user, entity_id=int(entity_id))
        else:
            raise ValidationError({"entity": ["Entity or run is required."]})
        def _build_payload():
            queryset = GstReconciliationItem.objects.select_related(
                "run",
                "assigned_reviewer",
                "reviewed_by",
                "resolved_by",
            ).prefetch_related("mismatch_reasons")
            queryset = self.filter_queryset(queryset)
            page = self.paginate_queryset(queryset)
            rows = page if page is not None else queryset
            serializer = GstReconciliationItemGridSerializer(rows, many=True)
            return queryset, page, serializer

        timed = timed_call("item_grid", _build_payload, run_id=run_id, entity_id=entity_id)
        queryset, page, serializer = timed.value
        if page is not None:
            response = self.paginator.get_paginated_response(
                serializer.data,
                meta_echo={
                    "ordering": request.query_params.get("ordering") or "-updated_at",
                    "timing_ms": timed.duration_ms,
                    "filters": {
                        "run": request.query_params.get("run"),
                        "status": request.query_params.get("status"),
                        "resolution_status": request.query_params.get("resolution_status"),
                        "supplier_gstin": request.query_params.get("supplier_gstin"),
                        "mismatch_reason": request.query_params.get("mismatch_reason"),
                        "assigned_reviewer": request.query_params.get("assigned_reviewer"),
                        "unresolved_only": request.query_params.get("unresolved_only"),
                    },
                },
            )
            response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
            return response
        response = Response({"meta": {"count": len(serializer.data), "timing_ms": timed.duration_ms}, "rows": serializer.data}, status=status.HTTP_200_OK)
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response

    def paginate_queryset(self, queryset):
        paginator = self.pagination_class()
        paginator.request = self.request
        self.paginator = paginator
        return paginator.paginate_queryset(queryset, self.request, view=self)


class GstReconciliationItemDetailAPIView(_ItemActionBaseAPIView):
    def get(self, request, pk: int):
        item = get_object_or_404(
            GstReconciliationItem.objects.select_related(
                "run",
                "assigned_reviewer",
                "reviewed_by",
                "resolved_by",
            ).prefetch_related("mismatch_reasons", "action_logs__actor"),
            pk=pk,
        )
        GstReconciliationWorkflowAccess.assert_can_view_item(user=request.user, item=item)
        timed = timed_call("item_detail", lambda: GstReconciliationUiService.build_item_detail(item=item), item_id=item.id, run_id=item.run_id)
        response = Response(timed.value, status=status.HTTP_200_OK)
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response


class GstReconciliationReviewerQueueAPIView(_ItemActionBaseAPIView, _ItemGridFilterMixin):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        run_id = request.query_params.get("run")
        entity_id = request.query_params.get("entity")
        if run_id:
            scoped_run = get_object_or_404(GstReconciliationRun, pk=run_id)
            GstReconciliationWorkflowAccess.assert_can_view_run(user=request.user, run=scoped_run)
        elif entity_id:
            GstReconciliationWorkflowAccess.assert_can_view_scope(user=request.user, entity_id=int(entity_id))
        else:
            raise ValidationError({"entity": ["Entity or run is required."]})
        def _build_queue():
            queryset = GstReconciliationItem.objects.select_related(
                "run",
                "assigned_reviewer",
                "reviewed_by",
                "resolved_by",
            ).prefetch_related("mismatch_reasons")
            queryset = queryset.exclude(
                resolution_status__in=[
                    GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                    GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                    GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                    GstReconciliationItem.ResolutionStatus.IGNORED,
                    GstReconciliationItem.ResolutionStatus.RESOLVED,
                ]
            )
            reviewer_id = request.query_params.get("reviewer_id")
            if reviewer_id:
                queryset = queryset.filter(assigned_reviewer_id=reviewer_id)
            queryset = self.filter_queryset(queryset)
            summary = GstReconciliationUiService.build_reviewer_queue_summary(queryset=queryset)
            page = self.paginate_queryset(queryset)
            rows = page if page is not None else queryset
            serializer = GstReconciliationItemGridSerializer(rows, many=True)
            return page, serializer, summary

        timed = timed_call("reviewer_queue", _build_queue, run_id=run_id, entity_id=entity_id)
        page, serializer, summary = timed.value
        if page is not None:
            response = self.paginator.get_paginated_response(
                serializer.data,
                meta_echo={
                    "ordering": request.query_params.get("ordering") or "-updated_at",
                    "summary": summary,
                    "timing_ms": timed.duration_ms,
                },
            )
            response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
            return response
        response = Response({"meta": {"count": len(serializer.data), "summary": summary, "timing_ms": timed.duration_ms}, "rows": serializer.data}, status=status.HTTP_200_OK)
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response

    def paginate_queryset(self, queryset):
        paginator = self.pagination_class()
        paginator.request = self.request
        self.paginator = paginator
        return paginator.paginate_queryset(queryset, self.request, view=self)


class GstReconciliationItemAssignAPIView(_ItemActionBaseAPIView):
    def post(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_assign_item(user=request.user, item=item)
        serializer = GstItemAssignSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        reviewer = None
        reviewer_id = serializer.validated_data.get("reviewer_id")
        if reviewer_id:
            reviewer = get_object_or_404(User, pk=reviewer_id)
        try:
            GstReconciliationItemWorkflowService.assign_reviewer(
                item=item,
                reviewer=reviewer,
                user=request.user,
                note=serializer.validated_data.get("note"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)


class GstReconciliationItemManualMatchAPIView(_ItemActionBaseAPIView):
    def post(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_manual_match(user=request.user, item=item)
        serializer = GstItemManualMatchSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            GstReconciliationItemWorkflowService.manual_match_source_document(
                item=item,
                source_document_type=serializer.validated_data["source_document_type"],
                source_document_id=str(serializer.validated_data["source_document_id"]),
                user=request.user,
                note=serializer.validated_data.get("note"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)


class GstReconciliationItemUnmatchAPIView(_ItemActionBaseAPIView):
    def post(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=request.user, item=item)
        serializer = GstItemActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            GstReconciliationItemWorkflowService.manual_unmatch(
                item=item,
                user=request.user,
                note=serializer.validated_data.get("note"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)


class GstReconciliationItemNotesAPIView(_ItemActionBaseAPIView):
    def _save(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=request.user, item=item)
        serializer = GstItemNotesSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            GstReconciliationItemWorkflowService.update_notes(
                item=item,
                user=request.user,
                reviewer_notes=serializer.validated_data.get("reviewer_notes"),
                resolution_notes=serializer.validated_data.get("resolution_notes"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)

    def post(self, request, pk: int):
        return self._save(request, pk)

    def put(self, request, pk: int):
        return self._save(request, pk)


class GstReconciliationItemIgnoreAPIView(_ItemActionBaseAPIView):
    def post(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=request.user, item=item)
        serializer = GstItemActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            GstReconciliationItemWorkflowService.ignore_item(
                item=item,
                user=request.user,
                note=serializer.validated_data.get("note"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)


class GstReconciliationItemReopenAPIView(_ItemActionBaseAPIView):
    def post(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_review_item(user=request.user, item=item)
        serializer = GstItemActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            GstReconciliationItemWorkflowService.reopen_item(
                item=item,
                user=request.user,
                note=serializer.validated_data.get("note"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)


class GstReconciliationItemAcceptMismatchAPIView(_ItemActionBaseAPIView):
    def post(self, request, pk: int):
        item = self.get_item(pk)
        GstReconciliationWorkflowAccess.assert_can_accept_mismatch(user=request.user, item=item)
        serializer = GstItemActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            GstReconciliationItemWorkflowService.accept_mismatch(
                item=item,
                user=request.user,
                note=serializer.validated_data.get("note"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.response_for_item(item)


class _BulkItemActionBaseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    action_name: str | None = None

    def post(self, request):
        serializer = GstBulkItemActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        action_name = self.action_name or serializer.validated_data["action"]
        if self.action_name and serializer.validated_data["action"] != self.action_name:
            serializer.validated_data["action"] = self.action_name
        item_ids = serializer.validated_data["item_ids"]
        queryset = GstReconciliationItem.objects.filter(id__in=item_ids)
        run_id = getattr(self, "_run_id_override", None)
        if run_id is not None:
            queryset = queryset.filter(run_id=run_id)
        items = list(queryset.select_related("run", "assigned_reviewer"))
        found_ids = {item.id for item in items}
        missing_errors = [{"item_id": item_id, "error": "Item not found."} for item_id in item_ids if item_id not in found_ids]
        if not items:
            return Response({"action": self.action_name, "success_count": 0, "failed_count": len(item_ids), "errors": missing_errors}, status=status.HTTP_400_BAD_REQUEST)
        GstReconciliationWorkflowAccess.assert_can_bulk_review(user=request.user, run=items[0].run)
        reviewer = None
        reviewer_id = serializer.validated_data.get("reviewer_id")
        if reviewer_id:
            reviewer = get_object_or_404(User, pk=reviewer_id)
        timed = timed_call(
            "bulk_action_view",
            lambda: GstReconciliationItemWorkflowService.bulk_action(
                items=items,
                action=action_name,
                user=request.user,
                note=serializer.validated_data.get("note"),
                reviewer=reviewer,
            ),
            run_id=items[0].run_id,
            action=action_name,
            item_count=len(items),
        )
        result, errors = timed.value
        refreshed_items = GstReconciliationItem.objects.filter(id__in=result.processed_item_ids).order_by("id")
        all_errors = [*missing_errors, *errors]
        response = Response(
            {
                "action": result.action,
                "success_count": len(result.processed_item_ids),
                "failed_count": len(all_errors),
                "processed_item_ids": result.processed_item_ids,
                "errors": all_errors,
                "timing_ms": timed.duration_ms,
                "items": GstReconciliationItemSerializer(refreshed_items, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response


class GstLegacyRunBulkItemActionAPIView(_BulkItemActionBaseAPIView):
    action_name = None

    def post(self, request, pk: int):
        self._run_id_override = pk
        return super().post(request)


class GstBulkAssignAPIView(_BulkItemActionBaseAPIView):
    action_name = "assign"


class GstBulkIgnoreAPIView(_BulkItemActionBaseAPIView):
    action_name = "ignore"


class GstBulkReopenAPIView(_BulkItemActionBaseAPIView):
    action_name = "reopen"


class GstBulkAcceptMismatchAPIView(_BulkItemActionBaseAPIView):
    action_name = "accept_mismatch"


class GstBulkUnmatchAPIView(_BulkItemActionBaseAPIView):
    action_name = "unmatch"


class GstBulkMarkReviewedAPIView(_BulkItemActionBaseAPIView):
    action_name = "mark_reviewed"


class GstReconciliationRunSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        run = get_object_or_404(GstReconciliationRun, pk=pk)
        GstReconciliationWorkflowAccess.assert_can_view_run(user=request.user, run=run)
        timed = timed_call("run_summary_view", lambda: GstReconciliationDashboardService.run_summary(run=run), run_id=run.id)
        response = Response(timed.value, status=status.HTTP_200_OK)
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response


class GstReconciliationRunSupplierAnalyticsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        run = get_object_or_404(GstReconciliationRun, pk=pk)
        GstReconciliationWorkflowAccess.assert_can_view_run(user=request.user, run=run)
        timed = timed_call("supplier_analytics_view", lambda: GstReconciliationDashboardService.supplier_mismatch_analytics(run=run), run_id=run.id)
        response = Response(
            {
                "run_id": run.id,
                "timing_ms": timed.duration_ms,
                "results": timed.value,
            },
            status=status.HTTP_200_OK,
        )
        response["X-GST-Recon-Timing-Ms"] = str(timed.duration_ms)
        return response
