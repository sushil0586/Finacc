from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from reports.gst_compliance.contracts import parse_gst_compliance_scope
from reports.gst_compliance.services import GstComplianceSnapshotService
from reports.gst_compliance.task_serializers import (
    GstComplianceTaskAttachmentSerializer,
    GstComplianceTaskCommentSerializer,
    GstComplianceTaskDetailSerializer,
    GstComplianceTaskSerializer,
)
from reports.models import GstComplianceTask, GstComplianceTaskAttachment, GstComplianceTaskAudit, GstComplianceTaskComment
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS = (
    "reports.gst.view",
    "reports.gstr1report.view",
    "reports.gstr3b.view",
    "reports.gstr9.view",
    "reports.gstr1_gstr3b_reconciliation.view",
    "reports.gst_exception_dashboard.view",
    "gst.reconciliation.view",
    "reports.financial_hub.gst_tds_compliance_center.view",
    "reports.financial_hub.tcs_compliance_center.view",
)

GST_COMPLIANCE_TASK_MANAGE_PERMISSIONS = GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS


def _task_snapshot(task: GstComplianceTask) -> dict:
    return {
        "status": task.status,
        "priority": task.priority,
        "owner_id": task.owner_id,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "closure_note": task.closure_note,
    }


def _audit_task(*, task: GstComplianceTask, action: str, actor, old_data: dict | None = None, new_data: dict | None = None, note: str = ""):
    GstComplianceTaskAudit.objects.create(
        task=task,
        action=action,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        old_data=old_data or {},
        new_data=new_data or {},
        note=note or "",
    )


class GstComplianceSnapshotAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    service_class = GstComplianceSnapshotService

    def get(self, request):
        try:
            scope = parse_gst_compliance_scope(request.query_params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)

        self.enforce_scope(
            request,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
        )
        permission_codes = assert_any_report_permission(
            user=request.user,
            entity_id=scope.entity_id,
            required_permissions=GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS,
            message="You do not have permission to access the GST Compliance Center.",
        )
        return Response(self.service_class().build(scope=scope, permission_codes=permission_codes))


class GstComplianceTaskListCreateAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def _scope(self, request):
        try:
            scope = parse_gst_compliance_scope(request.query_params if request.method == "GET" else request.data)
        except ValidationError as exc:
            return None, Response(exc.message_dict, status=400)
        self.enforce_scope(
            request,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
        )
        assert_any_report_permission(
            user=request.user,
            entity_id=scope.entity_id,
            required_permissions=GST_COMPLIANCE_TASK_MANAGE_PERMISSIONS,
            message="You do not have permission to manage GST compliance tasks.",
        )
        return scope, None

    def get(self, request):
        scope, error = self._scope(request)
        if error:
            return error
        queryset = (
            GstComplianceTask.objects.select_related("owner", "created_by", "updated_by", "closed_by")
            .annotate(comment_count=Count("comments", distinct=True), attachment_count=Count("attachments", distinct=True))
            .filter(entity_id=scope.entity_id, entityfinid_id=scope.entityfinid_id, isactive=True)
        )
        if scope.subentity_id:
            queryset = queryset.filter(subentity_id=scope.subentity_id)
        if scope.gstin:
            queryset = queryset.filter(gstin=scope.gstin)
        if scope.return_period:
            queryset = queryset.filter(return_period=scope.return_period)
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        owner_filter = request.query_params.get("owner")
        if owner_filter:
            queryset = queryset.filter(owner_id=owner_filter)
        return Response({"results": GstComplianceTaskSerializer(queryset, many=True).data})

    @transaction.atomic
    def post(self, request):
        scope, error = self._scope(request)
        if error:
            return error
        data = request.data.copy()
        data["entity"] = scope.entity_id
        data["entityfinid"] = scope.entityfinid_id
        data["subentity"] = scope.subentity_id
        data["gstin"] = data.get("gstin") or scope.gstin
        data["return_period"] = data.get("return_period") or scope.return_period
        serializer = GstComplianceTaskSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(created_by=request.user, updated_by=request.user)
        _audit_task(task=task, action="created", actor=request.user, new_data=_task_snapshot(task))
        detail = (
            GstComplianceTask.objects.select_related("owner", "created_by", "updated_by", "closed_by")
            .annotate(comment_count=Count("comments", distinct=True), attachment_count=Count("attachments", distinct=True))
            .get(pk=task.pk)
        )
        return Response(GstComplianceTaskDetailSerializer(detail).data, status=201)


class GstComplianceTaskDetailAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def _task(self, request, pk: int) -> GstComplianceTask:
        task = get_object_or_404(
            GstComplianceTask.objects.select_related("owner", "created_by", "updated_by", "closed_by")
            .prefetch_related("comments__created_by", "attachments__uploaded_by", "audit_logs__actor")
            .annotate(comment_count=Count("comments", distinct=True), attachment_count=Count("attachments", distinct=True)),
            pk=pk,
            isactive=True,
        )
        self.enforce_scope(
            request,
            entity_id=task.entity_id,
            entityfinid_id=task.entityfinid_id,
            subentity_id=task.subentity_id,
        )
        assert_any_report_permission(
            user=request.user,
            entity_id=task.entity_id,
            required_permissions=GST_COMPLIANCE_TASK_MANAGE_PERMISSIONS,
            message="You do not have permission to manage GST compliance tasks.",
        )
        return task

    def get(self, request, pk: int):
        return Response(GstComplianceTaskDetailSerializer(self._task(request, pk)).data)

    @transaction.atomic
    def patch(self, request, pk: int):
        task = self._task(request, pk)
        old_data = _task_snapshot(task)
        serializer = GstComplianceTaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(updated_by=request.user)
        _audit_task(task=updated, action="updated", actor=request.user, old_data=old_data, new_data=_task_snapshot(updated))
        return Response(GstComplianceTaskDetailSerializer(self._task(request, pk)).data)


class GstComplianceTaskCommentAPIView(GstComplianceTaskDetailAPIView):
    @transaction.atomic
    def post(self, request, pk: int):
        task = self._task(request, pk)
        serializer = GstComplianceTaskCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(task=task, created_by=request.user)
        _audit_task(
            task=task,
            action="commented",
            actor=request.user,
            new_data={"comment_id": comment.pk, "comment": comment.comment},
        )
        return Response(GstComplianceTaskCommentSerializer(comment).data, status=201)


class GstComplianceTaskCloseAPIView(GstComplianceTaskDetailAPIView):
    @transaction.atomic
    def post(self, request, pk: int):
        task = self._task(request, pk)
        old_data = _task_snapshot(task)
        task.status = GstComplianceTask.Status.CLOSED
        task.closed_at = timezone.now()
        task.closed_by = request.user
        task.closure_note = (request.data.get("closure_note") or request.data.get("note") or task.closure_note or "").strip()
        task.updated_by = request.user
        task.save(update_fields=["status", "closed_at", "closed_by", "closure_note", "updated_by", "updated_at"])
        _audit_task(task=task, action="closed", actor=request.user, old_data=old_data, new_data=_task_snapshot(task), note=task.closure_note)
        return Response(GstComplianceTaskDetailSerializer(self._task(request, pk)).data)


class GstComplianceTaskReopenAPIView(GstComplianceTaskDetailAPIView):
    @transaction.atomic
    def post(self, request, pk: int):
        task = self._task(request, pk)
        old_data = _task_snapshot(task)
        task.status = GstComplianceTask.Status.OPEN
        task.closed_at = None
        task.closed_by = None
        task.closure_note = ""
        task.updated_by = request.user
        task.save(update_fields=["status", "closed_at", "closed_by", "closure_note", "updated_by", "updated_at"])
        _audit_task(
            task=task,
            action="reopened",
            actor=request.user,
            old_data=old_data,
            new_data=_task_snapshot(task),
            note=(request.data.get("note") or "").strip(),
        )
        return Response(GstComplianceTaskDetailSerializer(self._task(request, pk)).data)


class GstComplianceTaskAttachmentAPIView(GstComplianceTaskDetailAPIView):
    @transaction.atomic
    def post(self, request, pk: int):
        task = self._task(request, pk)
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"file": ["This field is required."]}, status=400)
        attachment = GstComplianceTaskAttachment.objects.create(
            task=task,
            file=uploaded,
            original_name=getattr(uploaded, "name", ""),
            content_type=getattr(uploaded, "content_type", "") or "",
            size=getattr(uploaded, "size", 0) or 0,
            uploaded_by=request.user,
        )
        _audit_task(
            task=task,
            action="attachment_added",
            actor=request.user,
            new_data={"attachment_id": attachment.pk, "original_name": attachment.original_name, "size": attachment.size},
        )
        return Response(GstComplianceTaskAttachmentSerializer(attachment).data, status=201)
