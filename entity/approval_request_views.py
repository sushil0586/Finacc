from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.approval_request_serializers import ApprovalRequestActionSerializer, ApprovalRequestSerializer
from entity.approval_workflow_service import ApprovalWorkflowService
from entity.models import ApprovalRequest
from subscriptions.services import SubscriptionService


class ApprovalRequestScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    @staticmethod
    def _parse_int(raw_value, field_name, *, required):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity=True):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        if entity_id is not None:
            self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return entity_id, subentity_id

    def _get_request(self, request, pk):
        obj = ApprovalRequest.objects.select_related(
            "entity",
            "subentity",
            "content_type",
            "requested_by",
            "approved_by",
            "rejected_by",
            "cancelled_by",
            "locked_by",
        ).prefetch_related(
            "steps__approver_user",
            "steps__acted_by",
            "action_logs__acted_by",
        ).filter(pk=pk, isactive=True).first()
        if obj is None:
            return None
        self.enforce_scope(request, entity_id=obj.entity_id, subentity_id=obj.subentity_id)
        return obj


class ApprovalRequestListAPIView(ApprovalRequestScopedAPIView):
    def get(self, request):
        entity_id, subentity_id = self._scope_from_query(request, require_entity=True)
        queryset = ApprovalRequest.objects.select_related(
            "content_type",
            "requested_by",
            "approved_by",
            "rejected_by",
            "cancelled_by",
            "locked_by",
        ).prefetch_related("steps", "action_logs").filter(entity_id=entity_id, isactive=True)
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)
        workflow_key = (request.query_params.get("workflow_key") or "").strip().lower()
        status_filter = (request.query_params.get("status") or "").strip().upper()
        object_id = (request.query_params.get("object_id") or "").strip()
        model = (request.query_params.get("model") or "").strip().lower()
        inbox_only = (request.query_params.get("inbox") or "").strip().lower() in {"1", "true", "yes"}
        if workflow_key:
            queryset = queryset.filter(workflow_key=workflow_key)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if object_id:
            queryset = queryset.filter(object_id=object_id)
        if model:
            content_types = ContentType.objects.filter(model=model)
            queryset = queryset.filter(content_type__in=content_types)
        if inbox_only:
            queryset = queryset.filter(status__in=[ApprovalRequest.Status.SUBMITTED, ApprovalRequest.Status.PENDING_APPROVAL])
        return Response(ApprovalRequestSerializer(queryset.order_by("-updated_at", "-id"), many=True).data)


class ApprovalRequestDetailAPIView(ApprovalRequestScopedAPIView):
    def get(self, request, pk):
        obj = self._get_request(request, pk)
        if obj is None:
            return Response({"detail": "Approval request not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ApprovalRequestSerializer(obj).data)


class ApprovalRequestActionAPIView(ApprovalRequestScopedAPIView):
    action_name = ""

    def post(self, request, pk):
        serializer = ApprovalRequestActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        obj = self._get_request(request, pk)
        if obj is None:
            return Response({"detail": "Approval request not found."}, status=status.HTTP_404_NOT_FOUND)
        content_object = obj.content_object
        if content_object is None:
            return Response({"detail": "Approval request target not found."}, status=status.HTTP_404_NOT_FOUND)
        remarks = serializer.validated_data.get("remarks", "")
        if self.action_name == "approve":
            ApprovalWorkflowService.approve(
                instance=content_object,
                workflow_key=obj.workflow_key,
                actor_id=request.user.id,
                remarks=remarks,
            )
        elif self.action_name == "reject":
            ApprovalWorkflowService.reject(
                instance=content_object,
                workflow_key=obj.workflow_key,
                actor_id=request.user.id,
                remarks=remarks,
            )
        elif self.action_name == "cancel":
            ApprovalWorkflowService.cancel(
                instance=content_object,
                workflow_key=obj.workflow_key,
                actor_id=request.user.id,
                remarks=remarks,
            )
        elif self.action_name == "lock":
            ApprovalWorkflowService.lock_after_approval(
                instance=content_object,
                workflow_key=obj.workflow_key,
                actor_id=request.user.id,
                remarks=remarks,
            )
        refreshed = self._get_request(request, pk)
        return Response(ApprovalRequestSerializer(refreshed).data)


class ApprovalRequestApproveAPIView(ApprovalRequestActionAPIView):
    action_name = "approve"


class ApprovalRequestRejectAPIView(ApprovalRequestActionAPIView):
    action_name = "reject"


class ApprovalRequestCancelAPIView(ApprovalRequestActionAPIView):
    action_name = "cancel"


class ApprovalRequestLockAPIView(ApprovalRequestActionAPIView):
    action_name = "lock"
