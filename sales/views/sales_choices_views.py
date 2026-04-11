from __future__ import annotations

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.entitlements import ScopedEntitlementMixin
from sales.services.sales_choices_service import SalesChoicesService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class SalesChoicesAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_SALES
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        entity_id = request.query_params.get("entity_id")
        if not entity_id:
            return Response({"entity_id": "This query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        subentity_id = request.query_params.get("subentity_id")
        if subentity_id == "0":
            subentity_id = None
        self.enforce_scope(
            request,
            entity_id=int(entity_id),
            subentity_id=int(subentity_id) if subentity_id else None,
        )
        data = SalesChoicesService.get_choices(
            entity_id=int(entity_id),
            subentity_id=int(subentity_id) if subentity_id else None,
        )
        return Response(data)
