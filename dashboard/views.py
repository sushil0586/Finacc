from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from .registry import DASHBOARD_PAGE_PERMISSION
from .serializers import DashboardHomeScopeSerializer
from .services import build_dashboard_home_contract
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class DashboardHomeMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DashboardHomeScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def get(self, request):
        scope = self.get_scope(request)
        self.enforce_scope(
            request,
            entity_id=int(scope["entity"]),
            entityfinid_id=getattr(scope.get("entityfinid"), "id", scope.get("entityfinid")),
            subentity_id=getattr(scope.get("subentity"), "id", scope.get("subentity")),
        )
        contract = build_dashboard_home_contract(request=request, scope=scope)
        if not contract:
            raise PermissionDenied("You do not have access to this entity.")
        if not contract["permissions"]["page"]["granted"]:
            raise PermissionDenied(f"You do not have permission to access {DASHBOARD_PAGE_PERMISSION}.")
        return Response(contract)
