from django.urls import path

from .views import (
    InventoryAdjustmentCreateAPIView,
    InventoryAdjustmentDetailAPIView,
    InventoryAdjustmentListAPIView,
    InventoryGodownListAPIView,
    InventoryGodownMasterAPIView,
    InventoryGodownMasterDetailAPIView,
    InventoryTransferCreateAPIView,
    InventoryTransferDetailAPIView,
    InventoryTransferListAPIView,
)

app_name = "inventory_ops"

urlpatterns = [
    path("godowns/", InventoryGodownListAPIView.as_view(), name="inventory-godowns"),
    path("godowns/master/", InventoryGodownMasterAPIView.as_view(), name="inventory-godown-master"),
    path("godowns/master/<int:pk>/", InventoryGodownMasterDetailAPIView.as_view(), name="inventory-godown-master-detail"),
    path("transfers/", InventoryTransferCreateAPIView.as_view(), name="inventory-transfers"),
    path("transfers/list/", InventoryTransferListAPIView.as_view(), name="inventory-transfers-list"),
    path("transfers/<int:pk>/", InventoryTransferDetailAPIView.as_view(), name="inventory-transfer-detail"),
    path("adjustments/", InventoryAdjustmentCreateAPIView.as_view(), name="inventory-adjustments"),
    path("adjustments/list/", InventoryAdjustmentListAPIView.as_view(), name="inventory-adjustments-list"),
    path("adjustments/<int:pk>/", InventoryAdjustmentDetailAPIView.as_view(), name="inventory-adjustment-detail"),
]
