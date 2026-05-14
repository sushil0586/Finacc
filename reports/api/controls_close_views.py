from __future__ import annotations

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from reports.services.controls.year_end_close import build_year_end_close_execution, build_year_end_close_preview, build_year_end_close_rollback


class YearEndCloseScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class YearEndClosePermissionMixin:
    required_permission_codes = ("reports.financial_hub.year_end_close.view",)
    permission_denied_message = "You do not have permission to access year-end close."

    def enforce_report_permission(self, request, *, entity_id: int):
        assert_any_report_permission(
            user=request.user,
            entity_id=entity_id,
            required_permissions=self.required_permission_codes,
            message=self.permission_denied_message,
        )


class YearEndClosePreviewAPIView(YearEndClosePermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = YearEndCloseScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        return Response(
            build_year_end_close_preview(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )


class YearEndCloseExecuteAPIView(YearEndClosePermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = YearEndCloseScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        return Response(
            build_year_end_close_execution(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=request.user,
            )
        )


class YearEndCloseRollbackAPIView(YearEndClosePermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = YearEndCloseScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        return Response(
            build_year_end_close_rollback(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=request.user,
            )
        )
