from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

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


class AssetSettingsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"entity": "This query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        subentity_id = request.query_params.get("subentity")
        settings_obj = AssetSettingsService.get_settings(int(entity_id), int(subentity_id) if subentity_id else None)
        return Response(AssetSettingsSerializer(settings_obj).data)

    def put(self, request):
        entity_id = request.data.get("entity")
        if not entity_id:
            return Response({"entity": "This field is required."}, status=status.HTTP_400_BAD_REQUEST)
        subentity_id = request.data.get("subentity")
        try:
            updated = AssetSettingsService.upsert_settings(
                entity_id=int(entity_id),
                subentity_id=int(subentity_id) if subentity_id not in (None, "") else None,
                updates=request.data,
                user_id=request.user.id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AssetSettingsSerializer(updated).data)


class AssetCategoryListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssetCategorySerializer

    def get_queryset(self):
        qs = AssetCategory.objects.filter(entity_id=self.request.query_params.get("entity")).order_by("name")
        subentity_id = self.request.query_params.get("subentity")
        if subentity_id:
            qs = qs.filter(subentity_id=subentity_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)


class AssetCategoryRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = AssetCategory.objects.all()
    serializer_class = AssetCategorySerializer

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class FixedAssetListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        if not entity_id:
            return FixedAsset.objects.none()
        subentity_id = self.request.query_params.get("subentity")
        search = self.request.query_params.get("search")
        qs = AssetService.asset_queryset(entity_id=int(entity_id), subentity_id=int(subentity_id) if subentity_id else None, search=search)
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
        asset = AssetService.create_asset(data=serializer.validated_data, user_id=request.user.id)
        return Response(FixedAssetListSerializer(asset).data, status=status.HTTP_201_CREATED)


class FixedAssetRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = FixedAsset.objects.select_related("category", "ledger", "vendor_account")

    def get_serializer_class(self):
        return FixedAssetListSerializer if self.request.method == "GET" else FixedAssetWriteSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        asset = AssetService.update_asset(instance=instance, data=serializer.validated_data, user_id=request.user.id)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetCapitalizeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        asset = FixedAsset.objects.select_related("category").get(pk=pk)
        serializer = AssetCapitalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.capitalize_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetImpairAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        asset = FixedAsset.objects.select_related("category").get(pk=pk)
        serializer = AssetImpairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.impair_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetTransferAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        asset = FixedAsset.objects.select_related("category").get(pk=pk)
        serializer = AssetTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.transfer_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetDisposeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        asset = FixedAsset.objects.select_related("category").get(pk=pk)
        serializer = AssetDisposalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.dispose_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class AssetMetaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"entity": "This query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        subentity_id = request.query_params.get("subentity")
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


class DepreciationRunListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DepreciationRun.objects.all().order_by("-period_to", "-id")
        entity_id = self.request.query_params.get("entity")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        entityfinid = self.request.query_params.get("entityfinid")
        if entityfinid:
            qs = qs.filter(entityfinid_id=entityfinid)
        subentity_id = self.request.query_params.get("subentity")
        if subentity_id:
            qs = qs.filter(subentity_id=subentity_id)
        return qs

    def get_serializer_class(self):
        return DepreciationRunSerializer if self.request.method == "GET" else DepreciationRunCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save(created_by=request.user, updated_by=request.user)
        return Response(DepreciationRunSerializer(run).data, status=status.HTTP_201_CREATED)


class DepreciationRunRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = DepreciationRun.objects.prefetch_related("lines__asset__category")
    serializer_class = DepreciationRunSerializer


class DepreciationRunCalculateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        run = DepreciationRun.objects.get(pk=pk)
        serializer = DepreciationRunCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = AssetService.calculate_run(run=run, category_id=serializer.validated_data.get("category_id"), user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)


class DepreciationRunPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        run = DepreciationRun.objects.prefetch_related("lines__asset__category").get(pk=pk)
        try:
            run = AssetService.post_run(run=run, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)
