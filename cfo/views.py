from __future__ import annotations

from rest_framework import permissions
from django.shortcuts import get_object_or_404

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from cfo.models import BudgetLine, CashFlowForecastAdjustment, CfoEvidenceItem, CfoManagementPackSnapshot, CfoScenarioPlan
from core.entitlements import ScopedEntitlementMixin
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from .serializers import (
    BudgetLineSerializer,
    BudgetVarianceReviewSerializer,
    CashFlowForecastAdjustmentSerializer,
    CfoControlTowerScopeSerializer,
    CfoRiskReviewSerializer,
    EvidenceItemSerializer,
    EvidenceReviewSerializer,
    InsightSignalReviewSerializer,
    ManagementPackSnapshotSerializer,
    MonthCloseActionSerializer,
    ScenarioPlanSerializer,
)
from .services import (
    CFO_BUDGET_MANAGE_PERMISSION,
    CFO_BUDGET_PERMISSION,
    CFO_BUDGET_REVIEW_PERMISSION,
    CFO_CASH_FLOW_ADJUST_PERMISSION,
    CFO_CASH_FLOW_PERMISSION,
    CFO_CONTROL_TOWER_PERMISSION,
    CFO_EVIDENCE_CENTER_MANAGE_PERMISSION,
    CFO_EVIDENCE_CENTER_PERMISSION,
    CFO_INSIGHTS_PERMISSION,
    CFO_INSIGHTS_REVIEW_PERMISSION,
    CFO_MANAGEMENT_PACK_PERMISSION,
    CFO_MANAGEMENT_PACK_PUBLISH_PERMISSION,
    CFO_MONTH_CLOSE_LOCK_PERMISSION,
    CFO_MONTH_CLOSE_MANAGE_PERMISSION,
    CFO_MONTH_CLOSE_PERMISSION,
    CFO_PAYABLES_PERMISSION,
    CFO_RECEIVABLES_PERMISSION,
    CFO_RISK_QUEUE_PERMISSION,
    CFO_RISK_QUEUE_REVIEW_PERMISSION,
    CFO_SCENARIO_PLANNER_MANAGE_PERMISSION,
    CFO_SCENARIO_PLANNER_PERMISSION,
    build_control_tower_summary,
    build_budget_vs_actual_summary,
    build_cash_flow_forecast,
    build_evidence_center,
    build_management_pack,
    build_month_close_status,
    build_predictive_insights,
    build_risk_queue,
    build_scenario_planner,
    complete_month_close_task,
    create_cash_flow_adjustment,
    create_evidence_item,
    create_management_pack_snapshot,
    create_scenario_plan,
    delete_cash_flow_adjustment,
    lock_month_close_period,
    build_payables_aging,
    build_payables_worklist,
    build_receivables_aging,
    build_receivables_worklist,
    reopen_month_close_task,
    unlock_month_close_period,
    update_cash_flow_adjustment,
    upsert_budget_line,
    review_budget_variance,
    review_evidence_item,
    review_insight_signal,
    review_risk_queue_item,
)


class CfoControlTowerSummaryAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CfoControlTowerScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(scope["entity"]),
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        summary = build_control_tower_summary(request=request, scope=scope)
        if summary is None:
            raise PermissionDenied("You do not have access to this entity.")
        if not summary["permissions"]["page"]["granted"]:
            raise PermissionDenied(f"You do not have permission to access {CFO_CONTROL_TOWER_PERMISSION}.")
        return Response(summary)


class CfoScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CfoControlTowerScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    page_permission = ""
    builder = None

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(scope["entity"]),
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        payload = self.builder(request=request, scope=scope)
        if payload is None:
            raise PermissionDenied("You do not have access to this entity.")
        if not payload["permissions"]["page"]["granted"]:
            raise PermissionDenied(f"You do not have permission to access {self.page_permission}.")
        return Response(payload)


class CfoReceivablesAgingAPIView(CfoScopedAPIView):
    page_permission = CFO_RECEIVABLES_PERMISSION
    builder = staticmethod(build_receivables_aging)


class CfoReceivablesWorklistAPIView(CfoScopedAPIView):
    page_permission = CFO_RECEIVABLES_PERMISSION
    builder = staticmethod(build_receivables_worklist)


class CfoPayablesAgingAPIView(CfoScopedAPIView):
    page_permission = CFO_PAYABLES_PERMISSION
    builder = staticmethod(build_payables_aging)


class CfoPayablesWorklistAPIView(CfoScopedAPIView):
    page_permission = CFO_PAYABLES_PERMISSION
    builder = staticmethod(build_payables_worklist)


class CfoCashFlowForecastAPIView(CfoScopedAPIView):
    page_permission = CFO_CASH_FLOW_PERMISSION
    builder = staticmethod(build_cash_flow_forecast)


class CfoMonthCloseStatusAPIView(CfoScopedAPIView):
    page_permission = CFO_MONTH_CLOSE_PERMISSION
    builder = staticmethod(build_month_close_status)


class CfoBudgetVsActualSummaryAPIView(CfoScopedAPIView):
    page_permission = CFO_BUDGET_PERMISSION
    builder = staticmethod(build_budget_vs_actual_summary)


class CfoRiskQueueAPIView(CfoScopedAPIView):
    page_permission = CFO_RISK_QUEUE_PERMISSION
    builder = staticmethod(build_risk_queue)


class CfoManagementPackAPIView(CfoScopedAPIView):
    page_permission = CFO_MANAGEMENT_PACK_PERMISSION
    builder = staticmethod(build_management_pack)


class CfoEvidenceCenterAPIView(CfoScopedAPIView):
    page_permission = CFO_EVIDENCE_CENTER_PERMISSION
    builder = staticmethod(build_evidence_center)


class CfoPredictiveInsightsAPIView(CfoScopedAPIView):
    page_permission = CFO_INSIGHTS_PERMISSION
    builder = staticmethod(build_predictive_insights)


class CfoScenarioPlannerAPIView(CfoScopedAPIView):
    page_permission = CFO_SCENARIO_PLANNER_PERMISSION
    builder = staticmethod(build_scenario_planner)


class CfoCashFlowAdjustmentCreateAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CashFlowForecastAdjustmentSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_CASH_FLOW_ADJUST_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_CASH_FLOW_ADJUST_PERMISSION}.")
        adjustment = create_cash_flow_adjustment(payload=payload, actor=request.user)
        return Response(_serialize_adjustment(adjustment), status=201)


class CfoCashFlowAdjustmentDetailAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CashFlowForecastAdjustmentSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def _get_adjustment(self, adjustment_id):
        return get_object_or_404(CashFlowForecastAdjustment, pk=adjustment_id, isactive=True)

    def patch(self, request, adjustment_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        existing = self._get_adjustment(adjustment_id)
        if int(payload["entity"]) != existing.entity_id:
            raise ValidationError({"entity": "Entity cannot be changed for an existing cash-flow adjustment."})
        self.enforce_scope(
            request,
            entity_id=existing.entity_id,
            entityfinid_id=existing.entityfinid_id,
            subentity_id=existing.subentity_id,
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, existing.entity_id)
        if CFO_CASH_FLOW_ADJUST_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_CASH_FLOW_ADJUST_PERMISSION}.")
        adjustment = update_cash_flow_adjustment(adjustment_id=adjustment_id, payload=payload, actor=request.user)
        return Response(_serialize_adjustment(adjustment))

    def delete(self, request, adjustment_id):
        existing = self._get_adjustment(adjustment_id)
        self.enforce_scope(
            request,
            entity_id=existing.entity_id,
            entityfinid_id=existing.entityfinid_id,
            subentity_id=existing.subentity_id,
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, existing.entity_id)
        if CFO_CASH_FLOW_ADJUST_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_CASH_FLOW_ADJUST_PERMISSION}.")
        adjustment = delete_cash_flow_adjustment(adjustment_id=adjustment_id)
        return Response(_serialize_adjustment(adjustment))


class CfoMonthCloseActionAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MonthCloseActionSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission = CFO_MONTH_CLOSE_MANAGE_PERMISSION
    action = ""

    def post(self, request, task_code=None):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if self.required_permission not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {self.required_permission}.")

        try:
            response = self.perform_action(request=request, payload=payload, task_code=task_code)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        if response is None:
            raise PermissionDenied("You do not have access to this entity.")
        if not response["permissions"]["page"]["granted"]:
            raise PermissionDenied(f"You do not have permission to access {CFO_MONTH_CLOSE_PERMISSION}.")
        return Response(response)

    def perform_action(self, *, request, payload, task_code=None):
        if self.action == "complete":
            return complete_month_close_task(
                request=request,
                scope=payload,
                task_code=task_code,
                reason=payload.get("reason") or "",
            )
        if self.action == "reopen":
            return reopen_month_close_task(
                request=request,
                scope=payload,
                task_code=task_code,
                reason=payload.get("reason") or "",
            )
        if self.action == "lock":
            return lock_month_close_period(
                request=request,
                scope=payload,
                notes=payload.get("notes") or payload.get("reason") or "",
            )
        if self.action == "unlock":
            return unlock_month_close_period(
                request=request,
                scope=payload,
                reason=payload.get("reason") or "",
            )
        raise ValidationError({"detail": "Unsupported month close action."})


class CfoMonthCloseTaskCompleteAPIView(CfoMonthCloseActionAPIView):
    action = "complete"


class CfoMonthCloseTaskReopenAPIView(CfoMonthCloseActionAPIView):
    action = "reopen"


class CfoMonthCloseLockAPIView(CfoMonthCloseActionAPIView):
    required_permission = CFO_MONTH_CLOSE_LOCK_PERMISSION
    action = "lock"


class CfoMonthCloseUnlockAPIView(CfoMonthCloseActionAPIView):
    required_permission = CFO_MONTH_CLOSE_LOCK_PERMISSION
    action = "unlock"


class CfoBudgetLineUpsertAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BudgetLineSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_BUDGET_MANAGE_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_BUDGET_MANAGE_PERMISSION}.")
        line = upsert_budget_line(payload=payload, actor=request.user)
        return Response(_serialize_budget_line(line), status=201)


class CfoBudgetVarianceReviewAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BudgetVarianceReviewSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, category):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_BUDGET_REVIEW_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_BUDGET_REVIEW_PERMISSION}.")
        try:
            review = review_budget_variance(payload=payload, category=category, actor=request.user)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(_serialize_variance_review(review))


class CfoRiskQueueReviewAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CfoRiskReviewSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_RISK_QUEUE_REVIEW_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_RISK_QUEUE_REVIEW_PERMISSION}.")
        review = review_risk_queue_item(payload=payload, actor=request.user)
        return Response(_serialize_risk_review(review))


class CfoManagementPackSnapshotCreateAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ManagementPackSnapshotSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_MANAGEMENT_PACK_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_MANAGEMENT_PACK_PERMISSION}.")
        if CFO_MANAGEMENT_PACK_PUBLISH_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_MANAGEMENT_PACK_PUBLISH_PERMISSION}.")
        snapshot = create_management_pack_snapshot(request=request, payload=payload)
        if snapshot is None:
            raise PermissionDenied("You do not have access to this entity.")
        return Response(_serialize_management_pack_snapshot(snapshot), status=201)


class CfoEvidenceItemCreateAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EvidenceItemSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_EVIDENCE_CENTER_MANAGE_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_EVIDENCE_CENTER_MANAGE_PERMISSION}.")
        item = create_evidence_item(payload=payload, actor=request.user)
        return Response(_serialize_evidence_item(item), status=201)


class CfoEvidenceItemReviewAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EvidenceReviewSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, item_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        item = get_object_or_404(CfoEvidenceItem, pk=item_id, isactive=True)
        self.enforce_scope(
            request,
            entity_id=item.entity_id,
            entityfinid_id=item.entityfinid_id,
            subentity_id=item.subentity_id,
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, item.entity_id)
        if CFO_EVIDENCE_CENTER_MANAGE_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_EVIDENCE_CENTER_MANAGE_PERMISSION}.")
        reviewed = review_evidence_item(item_id=item_id, payload=payload, actor=request.user)
        return Response(_serialize_evidence_item(reviewed))


class CfoInsightSignalReviewAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InsightSignalReviewSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_INSIGHTS_REVIEW_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_INSIGHTS_REVIEW_PERMISSION}.")
        signal = review_insight_signal(payload=payload, actor=request.user)
        return Response(_serialize_insight_signal_review(signal))


class CfoScenarioPlanCreateAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ScenarioPlanSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=int(payload["entity"]),
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, int(payload["entity"]))
        if CFO_SCENARIO_PLANNER_MANAGE_PERMISSION not in permission_codes:
            raise PermissionDenied(f"You do not have permission to access {CFO_SCENARIO_PLANNER_MANAGE_PERMISSION}.")
        plan = create_scenario_plan(request=request, payload=payload, actor=request.user)
        return Response(_serialize_scenario_plan(plan), status=201)


def _serialize_budget_line(line: BudgetLine):
    return {
        "id": line.id,
        "entity": line.entity_id,
        "entityfinid": line.entityfinid_id,
        "subentity": line.subentity_id,
        "period_start": line.period_start.isoformat(),
        "period_end": line.period_end.isoformat(),
        "category": line.category,
        "budget_amount": str(line.budget_amount),
        "notes": line.notes,
        "isactive": line.isactive,
    }


def _serialize_variance_review(review):
    return {
        "id": review.id,
        "entity": review.entity_id,
        "entityfinid": review.entityfinid_id,
        "subentity": review.subentity_id,
        "period_start": review.period_start.isoformat(),
        "period_end": review.period_end.isoformat(),
        "category": review.category,
        "status": review.status,
        "explanation": review.explanation,
        "action_owner": review.action_owner,
        "due_date": review.due_date.isoformat() if review.due_date else None,
        "reviewed_by": getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }


def _serialize_risk_review(review):
    return {
        "id": review.id,
        "entity": review.entity_id,
        "entityfinid": review.entityfinid_id,
        "subentity": review.subentity_id,
        "item_key": review.item_key,
        "risk_type": review.risk_type,
        "source_type": review.source_type,
        "source_id": review.source_id,
        "status": review.status,
        "note": review.note,
        "reviewed_by": getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }


def _serialize_management_pack_snapshot(snapshot):
    return {
        "id": snapshot.id,
        "entity": snapshot.entity_id,
        "entityfinid": snapshot.entityfinid_id,
        "subentity": snapshot.subentity_id,
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "title": snapshot.title,
        "status": snapshot.status,
        "notes": snapshot.notes,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "created_by": getattr(snapshot.createdby, "username", None) if snapshot.createdby_id else None,
        "published_at": snapshot.published_at.isoformat() if snapshot.published_at else None,
        "published_by": getattr(snapshot.published_by, "username", None) if snapshot.published_by_id else None,
    }


def _serialize_evidence_item(item):
    return {
        "id": item.id,
        "entity": item.entity_id,
        "entityfinid": item.entityfinid_id,
        "subentity": item.subentity_id,
        "period_start": item.period_start.isoformat(),
        "period_end": item.period_end.isoformat(),
        "evidence_type": item.evidence_type,
        "title": item.title,
        "description": item.description,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "source_route": item.source_route,
        "status": item.status,
        "owner": item.owner,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "created_by": getattr(item.createdby, "username", None) if item.createdby_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "reviewed_by": getattr(item.reviewed_by, "username", None) if item.reviewed_by_id else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _serialize_insight_signal_review(signal):
    return {
        "id": signal.id,
        "entity": signal.entity_id,
        "entityfinid": signal.entityfinid_id,
        "subentity": signal.subentity_id,
        "period_start": signal.period_start.isoformat(),
        "period_end": signal.period_end.isoformat(),
        "signal_key": signal.signal_key,
        "signal_type": signal.signal_type,
        "severity": signal.severity,
        "status": signal.status,
        "note": signal.note,
        "reviewed_by": getattr(signal.reviewed_by, "username", None) if signal.reviewed_by_id else None,
        "reviewed_at": signal.reviewed_at.isoformat() if signal.reviewed_at else None,
    }


def _serialize_scenario_plan(plan: CfoScenarioPlan):
    return {
        "id": plan.id,
        "entity": plan.entity_id,
        "entityfinid": plan.entityfinid_id,
        "subentity": plan.subentity_id,
        "period_start": plan.period_start.isoformat(),
        "period_end": plan.period_end.isoformat(),
        "title": plan.title,
        "status": plan.status,
        "assumptions": plan.assumptions,
        "result": plan.result,
        "notes": plan.notes,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "created_by": getattr(plan.createdby, "username", None) if plan.createdby_id else None,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "approved_by": getattr(plan.approved_by, "username", None) if plan.approved_by_id else None,
    }


def _serialize_adjustment(adjustment):
    return {
        "id": adjustment.id,
        "entity": adjustment.entity_id,
        "entityfinid": adjustment.entityfinid_id,
        "subentity": adjustment.subentity_id,
        "scenario": adjustment.scenario,
        "adjustment_date": adjustment.adjustment_date.isoformat(),
        "direction": adjustment.direction,
        "category": adjustment.category,
        "description": adjustment.description,
        "amount": str(adjustment.amount),
        "isactive": adjustment.isactive,
    }
