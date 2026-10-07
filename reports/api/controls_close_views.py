from __future__ import annotations

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from reports.services.controls.audit_trail import record_controls_audit_event
from reports.services.controls.perf import controls_scope_fields, profile_controls_block
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
        with profile_controls_block(
            "controls.phase_one.year_end_close_preview",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            payload = build_year_end_close_preview(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
            close_state = payload.get("close_state") or {}
            perf["status"] = close_state.get("readiness_state") or payload.get("report_code")
            perf["is_year_closed"] = close_state.get("is_year_closed")
        return Response(payload)


class YearEndCloseExecuteAPIView(YearEndClosePermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = YearEndCloseScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.year_end_close.execute",)
    permission_denied_message = "You do not have permission to execute year-end close."

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
        with profile_controls_block(
            "controls.phase_one.year_end_close_execute",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            result = build_year_end_close_execution(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=request.user,
            )
            perf["status"] = result.get("status")
            perf["run_code"] = result.get("run_code")
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="year_end_close",
            action="year_end_close_executed",
            new_data={
                "status": result.get("status"),
                "report_code": result.get("report_code"),
                "run_code": result.get("run_code"),
                "snapshot": result.get("snapshot"),
                "close": result.get("close"),
            },
        )
        return Response(result)


class YearEndCloseRollbackAPIView(YearEndClosePermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = YearEndCloseScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.year_end_close.rollback",)
    permission_denied_message = "You do not have permission to roll back year-end close."

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
        with profile_controls_block(
            "controls.phase_one.year_end_close_rollback",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            result = build_year_end_close_rollback(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=request.user,
            )
            perf["status"] = result.get("status")
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="year_end_close",
            action="year_end_close_rolled_back",
            new_data={
                "status": result.get("status"),
                "report_code": result.get("report_code"),
                "rollback": result.get("rollback"),
            },
        )
        return Response(result)
