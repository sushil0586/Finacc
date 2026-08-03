from __future__ import annotations

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from payments.services.payment_choice_service import PaymentChoiceService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class PaymentCompiledChoicesAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    @staticmethod
    def _parse_int(raw_value, field_name: str, *, required: bool = False):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise serializers.ValidationError({field_name: f"{field_name} query param is required"})
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            raise serializers.ValidationError({field_name: f"{field_name} must be an integer"})

    def get(self, request):
        entity_id = self._parse_int(
            request.query_params.get("entity_id", request.query_params.get("entity")),
            "entity_id",
            required=True,
        )
        subentity_id = self._parse_int(
            request.query_params.get("subentity_id", request.query_params.get("subentity")),
            "subentity_id",
            required=False,
        )
        if subentity_id == 0:
            subentity_id = None
        self.enforce_scope(request, entity_id=entity_id, subentity_id=subentity_id)
        return Response(PaymentChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id))
