from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from assets.models import AssetCategory, DepreciationRun, FixedAsset
from assets.serializers import (
    AssetCapitalizeSerializer,
    AssetCategorySerializer,
    AssetDisposalSerializer,
    AssetImpairSerializer,
    AssetSettingsSerializer,
    AssetTransferSerializer,
    DepreciationRunCalculateSerializer,
    DepreciationRunCreateSerializer,
    DepreciationRunSerializer,
    FixedAssetListSerializer,
    FixedAssetWriteSerializer,
)
from assets.services.asset_service import AssetService
from assets.services.settings import AssetSettingsService
from financial.models import Ledger
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class AssetScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_ASSETS
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    @staticmethod
    def _parse_int(raw_value, field_name: str, *, required: bool) -> int | None:
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity: bool = True, require_entityfinid: bool = False):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        if entity_id is None:
            return None, None, None
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    def _scope_from_payload(self, request, payload, *, require_entityfinid: bool = False):
        entity_id = self._parse_int(payload.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(payload.get("subentity"), "subentity", required=False)
        entityfinid_id = self._parse_int(payload.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    @staticmethod
    def _asset_queryset(*, entity_id: int, subentity_id: int | None = None, search: str | None = None):
        qs = AssetService.asset_queryset(entity_id=entity_id, subentity_id=subentity_id, search=search)
        return qs

    @staticmethod
    def _run_queryset(*, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None):
        qs = DepreciationRun.objects.prefetch_related("lines__asset__category").filter(entity_id=entity_id)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs

    def _scoped_asset(self, request, pk: int):
        asset = get_object_or_404(FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity"), pk=pk)
        self.enforce_scope(request, entity_id=asset.entity_id, entityfinid_id=asset.entityfinid_id, subentity_id=asset.subentity_id)
        return asset

    def _scoped_run(self, request, pk: int):
        run = get_object_or_404(DepreciationRun.objects.prefetch_related("lines__asset__category"), pk=pk)
        self.enforce_scope(request, entity_id=run.entity_id, entityfinid_id=run.entityfinid_id, subentity_id=run.subentity_id)
        return run


class AssetSettingsAPIView(AssetScopedAPIView):
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    def get(self, request):
        entity_id, _, subentity_id = self._scope_from_query(request, require_entity=True)
        settings_obj = AssetSettingsService.get_settings(entity_id, subentity_id)
        return Response(AssetSettingsSerializer(settings_obj).data)

    def put(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        try:
            entity_id, _, subentity_id = self._scope_from_payload(request, request.data)
            updated = AssetSettingsService.upsert_settings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                updates=request.data,
                user_id=request.user.id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AssetSettingsSerializer(updated).data)


class AssetCategoryListCreateAPIView(AssetScopedAPIView, generics.ListCreateAPIView):
    serializer_class = AssetCategorySerializer

    def get_queryset(self):
        entity_id, _, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = AssetCategory.objects.filter(entity_id=entity_id).order_by("name")
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.enforce_scope(
            request,
            entity_id=serializer.validated_data["entity"].id,
            subentity_id=getattr(serializer.validated_data.get("subentity"), "id", None),
        )
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AssetCategoryRetrieveUpdateAPIView(AssetScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = AssetCategorySerializer

    def get_queryset(self):
        return AssetCategory.objects.all()

    def get_object(self):
        obj = super().get_object()
        self.enforce_scope(
            self.request,
            entity_id=obj.entity_id,
            subentity_id=obj.subentity_id,
        )
        return obj

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class FixedAssetListCreateAPIView(AssetScopedAPIView, generics.ListCreateAPIView):

    def get_queryset(self):
        entity_id, _, subentity_id = self._scope_from_query(self.request, require_entity=True)
        search = self.request.query_params.get("search")
        qs = self._asset_queryset(entity_id=entity_id, subentity_id=subentity_id, search=search)
        category_id = self.request.query_params.get("category")
        status_value = self.request.query_params.get("status")
        if category_id:
            qs = qs.filter(category_id=category_id)
        if status_value:
            qs = qs.filter(status=status_value)
        return qs

    def get_serializer_class(self):
        return FixedAssetListSerializer if self.request.method == "GET" else FixedAssetWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = serializer.validated_data["entity"]
        subentity = serializer.validated_data.get("subentity")
        entityfinid = serializer.validated_data.get("entityfinid")
        self.enforce_scope(
            request,
            entity_id=entity.id,
            entityfinid_id=getattr(entityfinid, "id", None),
            subentity_id=getattr(subentity, "id", None),
        )
        asset = AssetService.create_asset(data=serializer.validated_data, user_id=request.user.id)
        return Response(FixedAssetListSerializer(asset).data, status=status.HTTP_201_CREATED)


class FixedAssetRetrieveUpdateAPIView(AssetScopedAPIView, generics.RetrieveUpdateAPIView):

    def get_serializer_class(self):
        return FixedAssetListSerializer if self.request.method == "GET" else FixedAssetWriteSerializer

    def get_queryset(self):
        return FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity")

    def get_object(self):
        obj = super().get_object()
        self.enforce_scope(
            self.request,
            entity_id=obj.entity_id,
            entityfinid_id=obj.entityfinid_id,
            subentity_id=obj.subentity_id,
        )
        return obj

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        self.enforce_scope(
            request,
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
        )
        asset = AssetService.update_asset(instance=instance, data=serializer.validated_data, user_id=request.user.id)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetCapitalizeAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetCapitalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.capitalize_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetImpairAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetImpairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.impair_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetTransferAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.transfer_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetDisposeAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetDisposalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.dispose_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class AssetMetaAPIView(AssetScopedAPIView):

    def get(self, request):
        entity_id, _, subentity_id = self._scope_from_query(request, require_entity=True)
        categories = AssetCategory.objects.filter(entity_id=entity_id)
        if subentity_id:
            categories = categories.filter(subentity_id=subentity_id)
        ledgers = Ledger.objects.filter(entity_id=entity_id).order_by("name").values("id", "name", "ledger_code", "accounthead_id")
        return Response(
            {
                "choices": {
                    "asset_statuses": [{"value": code, "label": label} for code, label in FixedAsset.AssetStatus.choices],
                    "depreciation_methods": [{"value": code, "label": label} for code, label in FixedAsset.DepreciationMethod.choices],
                },
                "categories": list(categories.values("id", "code", "name", "nature")),
                "ledgers": list(ledgers),
            }
        )


class DepreciationRunListCreateAPIView(AssetScopedAPIView, generics.ListCreateAPIView):

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True, require_entityfinid=False)
        qs = self._run_queryset(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id).order_by("-period_to", "-id")
        return qs

    def get_serializer_class(self):
        return DepreciationRunSerializer if self.request.method == "GET" else DepreciationRunCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = serializer.validated_data["entity"]
        entityfinid = serializer.validated_data["entityfinid"]
        subentity = serializer.validated_data.get("subentity")
        self.enforce_scope(
            request,
            entity_id=entity.id,
            entityfinid_id=entityfinid.id,
            subentity_id=getattr(subentity, "id", None),
        )
        run = serializer.save(created_by=request.user, updated_by=request.user)
        return Response(DepreciationRunSerializer(run).data, status=status.HTTP_201_CREATED)


class DepreciationRunRetrieveAPIView(AssetScopedAPIView, generics.RetrieveAPIView):
    serializer_class = DepreciationRunSerializer

    def get_queryset(self):
        return DepreciationRun.objects.prefetch_related("lines__asset__category")

    def get_object(self):
        obj = super().get_object()
        self.enforce_scope(
            self.request,
            entity_id=obj.entity_id,
            entityfinid_id=obj.entityfinid_id,
            subentity_id=obj.subentity_id,
        )
        return obj


class DepreciationRunCalculateAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        run = self._scoped_run(request, pk)
        serializer = DepreciationRunCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = AssetService.calculate_run(run=run, category_id=serializer.validated_data.get("category_id"), user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)


class DepreciationRunPostAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        run = self._scoped_run(request, pk)
        try:
            run = AssetService.post_run(run=run, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)
