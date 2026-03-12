from django.urls import path

from assets.views import (
    AssetCategoryListCreateAPIView,
    AssetCategoryRetrieveUpdateAPIView,
    AssetMetaAPIView,
    AssetSettingsAPIView,
    DepreciationRunCalculateAPIView,
    DepreciationRunListCreateAPIView,
    DepreciationRunPostAPIView,
    DepreciationRunRetrieveAPIView,
    FixedAssetCapitalizeAPIView,
    FixedAssetDisposeAPIView,
    FixedAssetImpairAPIView,
    FixedAssetListCreateAPIView,
    FixedAssetRetrieveUpdateAPIView,
    FixedAssetTransferAPIView,
)

app_name = "assets_api"

urlpatterns = [
    path("settings/", AssetSettingsAPIView.as_view(), name="asset-settings"),
    path("meta/", AssetMetaAPIView.as_view(), name="asset-meta"),
    path("categories/", AssetCategoryListCreateAPIView.as_view(), name="asset-category-list-create"),
    path("categories/<int:pk>/", AssetCategoryRetrieveUpdateAPIView.as_view(), name="asset-category-detail"),
    path("fixed-assets/", FixedAssetListCreateAPIView.as_view(), name="fixed-asset-list-create"),
    path("fixed-assets/<int:pk>/", FixedAssetRetrieveUpdateAPIView.as_view(), name="fixed-asset-detail"),
    path("fixed-assets/<int:pk>/capitalize/", FixedAssetCapitalizeAPIView.as_view(), name="fixed-asset-capitalize"),
    path("fixed-assets/<int:pk>/impair/", FixedAssetImpairAPIView.as_view(), name="fixed-asset-impair"),
    path("fixed-assets/<int:pk>/transfer/", FixedAssetTransferAPIView.as_view(), name="fixed-asset-transfer"),
    path("fixed-assets/<int:pk>/dispose/", FixedAssetDisposeAPIView.as_view(), name="fixed-asset-dispose"),
    path("depreciation-runs/", DepreciationRunListCreateAPIView.as_view(), name="depreciation-run-list-create"),
    path("depreciation-runs/<int:pk>/", DepreciationRunRetrieveAPIView.as_view(), name="depreciation-run-detail"),
    path("depreciation-runs/<int:pk>/calculate/", DepreciationRunCalculateAPIView.as_view(), name="depreciation-run-calculate"),
    path("depreciation-runs/<int:pk>/post/", DepreciationRunPostAPIView.as_view(), name="depreciation-run-post"),
]
