from __future__ import annotations

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from reports.services.controls.phase_one import build_phase_one_controls_hub
from reports.services.controls.opening_setup import apply_posting_setup, build_posting_setup_preview
from reports.services.controls.opening_generation import build_opening_generation
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy, update_opening_policy
from reports.services.controls.opening_preview import build_opening_preview


class PhaseOneControlsScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PhaseOneControlsHubAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneControlsScopeSerializer
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
        return Response(
            build_phase_one_controls_hub(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )


class OpeningPolicySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    opening_mode = serializers.ChoiceField(choices=["single_batch", "grouped_batches", "hybrid"], required=False)
    batch_materialization = serializers.ChoiceField(choices=["single_batch", "grouped_batches", "hybrid"], required=False)
    opening_posting_date_strategy = serializers.ChoiceField(choices=["first_day_of_new_year", "manual"], required=False)
    require_closed_source_year = serializers.BooleanField(required=False)
    allow_partial_opening = serializers.BooleanField(required=False)
    opening_equity_static_account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    opening_inventory_static_account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    carry_forward = serializers.DictField(child=serializers.BooleanField(), required=False)
    reset = serializers.DictField(child=serializers.BooleanField(), required=False)
    grouped_sections = serializers.ListField(child=serializers.CharField(), required=False)


class PhaseOneOpeningPolicyAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningPolicySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        opening_policy = resolve_opening_policy(entity_id)
        return Response(
            {
                "entity": entity_id,
                "opening_policy": opening_policy,
                "summary": summarize_opening_policy(opening_policy),
            }
        )


class OpeningPreviewScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PhaseOneOpeningPreviewAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningPreviewScopeSerializer
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
        return Response(
            build_opening_preview(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)

        updates = {key: value for key, value in serializer.validated_data.items() if key != "entity"}
        opening_policy = update_opening_policy(
            entity_id=entity_id,
            updates=updates,
            created_by=getattr(request, "user", None),
        )
        return Response(
            {
                "entity": entity_id,
                "opening_policy": opening_policy,
                "summary": summarize_opening_policy(opening_policy),
            }
        )


class OpeningGenerationSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PhaseOneOpeningGenerateAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningGenerationSerializer
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
        return Response(
            build_opening_generation(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=getattr(request, "user", None),
            )
        )


class PostingSetupScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PostingSetupTargetOverrideSerializer(serializers.Serializer):
    code = serializers.CharField()
    enabled = serializers.BooleanField(required=False)
    editable_ledger_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    suggested_ledger_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    editable_account_preference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    account_preference = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PostingSetupApplySerializer(PostingSetupScopeSerializer):
    targets = PostingSetupTargetOverrideSerializer(many=True, required=False)


class PhaseOnePostingSetupPreviewAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PostingSetupScopeSerializer
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
        return Response(
            build_posting_setup_preview(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )


class PhaseOnePostingSetupApplyAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PostingSetupApplySerializer
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
        return Response(
            apply_posting_setup(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                created_by=getattr(request, "user", None),
                target_overrides=scope.get("targets"),
            )
        )
