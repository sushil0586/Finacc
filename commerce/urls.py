from django.urls import path

from .views import (
    CommerceBarcodeResolveAPIView,
    CommerceLineNormalizeAPIView,
    CommerceMetaAPIView,
    CommercePromotionDetailAPIView,
    CommercePromotionListCreateAPIView,
)

app_name = "commerce"

urlpatterns = [
    path("meta/", CommerceMetaAPIView.as_view(), name="meta"),
    path("barcodes/resolve/", CommerceBarcodeResolveAPIView.as_view(), name="barcode-resolve"),
    path("lines/normalize/", CommerceLineNormalizeAPIView.as_view(), name="line-normalize"),
    path("promotions/", CommercePromotionListCreateAPIView.as_view(), name="promotion-list-create"),
    path("promotions/<int:pk>/", CommercePromotionDetailAPIView.as_view(), name="promotion-detail"),
]
