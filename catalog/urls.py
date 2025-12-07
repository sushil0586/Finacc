# catalog/urls.py

from django.urls import path
from .views import (
    # Product
    ProductListCreateAPIView,
    ProductRetrieveUpdateDestroyAPIView,

    # Masters
    ProductCategoryListCreateAPIView,
    ProductCategoryRetrieveUpdateDestroyAPIView,
    BrandListCreateAPIView,
    BrandRetrieveUpdateDestroyAPIView,
    UnitOfMeasureListCreateAPIView,
    UnitOfMeasureRetrieveUpdateDestroyAPIView,
    HsnSacListCreateAPIView,
    HsnSacRetrieveUpdateDestroyAPIView,
    PriceListListCreateAPIView,
    PriceListRetrieveUpdateDestroyAPIView,
    GstTypeListAPIView,
    ProductPageBootstrapAPIView
)

urlpatterns = [

    # ------------------------------------------------------------------
    # PRODUCT (Nested)
    # ------------------------------------------------------------------
    path(
        "products/",
        ProductListCreateAPIView.as_view(),
        name="product-list-create",
    ),

    path(
        "gst-types/",
        GstTypeListAPIView.as_view(),
        name="gst-types",
    ),

    path(
        "product-page-all/",
        ProductPageBootstrapAPIView.as_view(),
        name="product-page-bootstrap",
    ),

    path(
        "products/<int:pk>/",
        ProductRetrieveUpdateDestroyAPIView.as_view(),
        name="product-detail",
    ),

    # ------------------------------------------------------------------
    # PRODUCT CATEGORY (Entity-wise)
    # ------------------------------------------------------------------
    path(
        "product-categories/",
        ProductCategoryListCreateAPIView.as_view(),
        name="product-category-list-create",
    ),
    path(
        "product-categories/<int:pk>/",
        ProductCategoryRetrieveUpdateDestroyAPIView.as_view(),
        name="product-category-detail",
    ),

    # ------------------------------------------------------------------
    # BRAND (Entity-wise)
    # ------------------------------------------------------------------
    path(
        "brands/",
        BrandListCreateAPIView.as_view(),
        name="brand-list-create",
    ),
    path(
        "brands/<int:pk>/",
        BrandRetrieveUpdateDestroyAPIView.as_view(),
        name="brand-detail",
    ),

    # ------------------------------------------------------------------
    # UNIT OF MEASURE (Entity-wise)
    # ------------------------------------------------------------------
    path(
        "uoms/",
        UnitOfMeasureListCreateAPIView.as_view(),
        name="uom-list-create",
    ),
    path(
        "uoms/<int:pk>/",
        UnitOfMeasureRetrieveUpdateDestroyAPIView.as_view(),
        name="uom-detail",
    ),

    # ------------------------------------------------------------------
    # HSN / SAC (Entity-wise)
    # ------------------------------------------------------------------
    path(
        "hsn-sac/",
        HsnSacListCreateAPIView.as_view(),
        name="hsn-sac-list-create",
    ),
    path(
        "hsn-sac/<int:pk>/",
        HsnSacRetrieveUpdateDestroyAPIView.as_view(),
        name="hsn-sac-detail",
    ),

    # ------------------------------------------------------------------
    # PRICE LIST (Entity-wise)
    # ------------------------------------------------------------------
    path(
        "pricelists/",
        PriceListListCreateAPIView.as_view(),
        name="pricelist-list-create",
    ),
    path(
        "pricelists/<int:pk>/",
        PriceListRetrieveUpdateDestroyAPIView.as_view(),
        name="pricelist-detail",
    ),
]
