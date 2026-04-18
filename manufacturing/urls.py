from django.urls import path

from .views import (
    ManufacturingBOMDetailAPIView,
    ManufacturingBOMFormMetaAPIView,
    ManufacturingBOMListCreateAPIView,
    ManufacturingRouteDetailAPIView,
    ManufacturingRouteListCreateAPIView,
    ManufacturingSettingsAPIView,
    ManufacturingSettingsMetaAPIView,
    ManufacturingWorkOrderCancelAPIView,
    ManufacturingWorkOrderDetailAPIView,
    ManufacturingWorkOrderFormMetaAPIView,
    ManufacturingWorkOrderOperationCompleteAPIView,
    ManufacturingWorkOrderOperationSkipAPIView,
    ManufacturingWorkOrderOperationStartAPIView,
    ManufacturingWorkOrderListCreateAPIView,
    ManufacturingWorkOrderPostAPIView,
    ManufacturingWorkOrderUnpostAPIView,
)

app_name = "manufacturing"

urlpatterns = [
    path("meta/settings/", ManufacturingSettingsMetaAPIView.as_view(), name="manufacturing-settings-meta"),
    path("meta/route-form/", ManufacturingBOMFormMetaAPIView.as_view(), name="manufacturing-route-form-meta"),
    path("meta/bom-form/", ManufacturingBOMFormMetaAPIView.as_view(), name="manufacturing-bom-form-meta"),
    path("meta/work-order-form/", ManufacturingWorkOrderFormMetaAPIView.as_view(), name="manufacturing-work-order-form-meta"),
    path("settings/", ManufacturingSettingsAPIView.as_view(), name="manufacturing-settings"),
    path("routes/", ManufacturingRouteListCreateAPIView.as_view(), name="manufacturing-routes"),
    path("routes/<int:pk>/", ManufacturingRouteDetailAPIView.as_view(), name="manufacturing-route-detail"),
    path("boms/", ManufacturingBOMListCreateAPIView.as_view(), name="manufacturing-boms"),
    path("boms/<int:pk>/", ManufacturingBOMDetailAPIView.as_view(), name="manufacturing-bom-detail"),
    path("work-orders/", ManufacturingWorkOrderListCreateAPIView.as_view(), name="manufacturing-work-orders"),
    path("work-orders/<int:pk>/", ManufacturingWorkOrderDetailAPIView.as_view(), name="manufacturing-work-order-detail"),
    path("work-orders/<int:pk>/post/", ManufacturingWorkOrderPostAPIView.as_view(), name="manufacturing-work-order-post"),
    path("work-orders/<int:pk>/operations/<int:operation_pk>/start/", ManufacturingWorkOrderOperationStartAPIView.as_view(), name="manufacturing-work-order-operation-start"),
    path("work-orders/<int:pk>/operations/<int:operation_pk>/complete/", ManufacturingWorkOrderOperationCompleteAPIView.as_view(), name="manufacturing-work-order-operation-complete"),
    path("work-orders/<int:pk>/operations/<int:operation_pk>/skip/", ManufacturingWorkOrderOperationSkipAPIView.as_view(), name="manufacturing-work-order-operation-skip"),
    path("work-orders/<int:pk>/unpost/", ManufacturingWorkOrderUnpostAPIView.as_view(), name="manufacturing-work-order-unpost"),
    path("work-orders/<int:pk>/cancel/", ManufacturingWorkOrderCancelAPIView.as_view(), name="manufacturing-work-order-cancel"),
]
