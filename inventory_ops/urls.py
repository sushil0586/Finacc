from django.urls import path

from .views import (
    InventoryAdjustmentCreateAPIView,
    InventoryAdjustmentDetailAPIView,
    InventoryAdjustmentListAPIView,
    InventoryGodownListAPIView,
    InventoryGodownMasterAPIView,
    InventoryGodownMasterDetailAPIView,
    InventoryOpsSettingsAPIView,
    InventoryOpsSettingsMetaAPIView,
    InventoryTransferCreateAPIView,
    InventoryTransferCancelAPIView,
    InventoryTransferDetailAPIView,
    InventoryTransferListAPIView,
    InventoryTransferPostAPIView,
    InventoryTransferUnpostAPIView,
)

app_name = "inventory_ops"

urlpatterns = [
    path("meta/settings/", InventoryOpsSettingsMetaAPIView.as_view(), name="inventory-settings-meta"),
    path("settings/", InventoryOpsSettingsAPIView.as_view(), name="inventory-settings"),
    path("godowns/", InventoryGodownListAPIView.as_view(), name="inventory-godowns"),
    path("godowns/master/", InventoryGodownMasterAPIView.as_view(), name="inventory-godown-master"),
    path("godowns/master/<int:pk>/", InventoryGodownMasterDetailAPIView.as_view(), name="inventory-godown-master-detail"),
    path("transfers/", InventoryTransferCreateAPIView.as_view(), name="inventory-transfers"),
    path("transfers/list/", InventoryTransferListAPIView.as_view(), name="inventory-transfers-list"),
    path("transfers/<int:pk>/", InventoryTransferDetailAPIView.as_view(), name="inventory-transfer-detail"),
    path("transfers/<int:pk>/post/", InventoryTransferPostAPIView.as_view(), name="inventory-transfer-post"),
    path("transfers/<int:pk>/unpost/", InventoryTransferUnpostAPIView.as_view(), name="inventory-transfer-unpost"),
    path("transfers/<int:pk>/cancel/", InventoryTransferCancelAPIView.as_view(), name="inventory-transfer-cancel"),
    path("adjustments/", InventoryAdjustmentCreateAPIView.as_view(), name="inventory-adjustments"),
    path("adjustments/list/", InventoryAdjustmentListAPIView.as_view(), name="inventory-adjustments-list"),
    path("adjustments/<int:pk>/", InventoryAdjustmentDetailAPIView.as_view(), name="inventory-adjustment-detail"),
]
