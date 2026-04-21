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
    ProductAttributeListCreateAPIView,
    ProductAttributeRetrieveUpdateDestroyAPIView,

    # Choices + Bootstrap
    GstTypeListAPIView,
    CessTypeListAPIView,
    ProductStatusListAPIView,
    ProductPageBootstrapAPIView,

    # Lightweight lists
    ProductImportantListAPIView,
    InvoiceProductListAPIView,
    TransactionProductMetaAPIView,
    TransactionProductDetailAPIView,

    # Barcode APIs
    BarcodeLabelTemplateListCreateAPIView,
    BarcodeLabelTemplateRUDAPIView,
    BarcodeLabelTemplateDefaultAPIView,
    ProductBarcodeListCreateAPIView,
    ProductBarcodeRUDAPIView,
    BarcodeLookupAPIView,
    ProductBarcodeDownloadPDFAPIView,
    BarcodeLayoutOptionsAPIView,PurchaseInvoiceProductListAPIView,
    ProductGstRateListCreateAPIView,
    ProductGstRateRUDAPIView,
    ProductUomConversionListCreateAPIView,
    ProductUomConversionRUDAPIView,
    OpeningStockByLocationListCreateAPIView,
    OpeningStockByLocationRUDAPIView,
    ProductPriceListCreateAPIView,
    ProductPriceRUDAPIView,
    ProductPlanningListCreateAPIView,
    ProductPlanningRUDAPIView,
    ProductAttributeValueListCreateAPIView,
    ProductAttributeValueRUDAPIView,
    ProductImageListCreateAPIView,
    ProductImageRUDAPIView,
)
from .views_bulk import (
    ProductBulkTemplateAPIView,
    ProductBulkExportAPIView,
    ProductBulkImportValidateAPIView,
    ProductBulkImportCommitAPIView,
    ProductBulkJobDetailAPIView,
    ProductBulkJobErrorsExportAPIView,
)
from .views_bulk_hsn import (
    HsnSacBulkTemplateAPIView,
    HsnSacBulkExportAPIView,
    HsnSacBulkImportValidateAPIView,
    HsnSacBulkImportCommitAPIView,
    HsnSacBulkJobDetailAPIView,
    HsnSacBulkJobErrorsExportAPIView,
)



urlpatterns = [
    # ------------------------------------------------------------------
    # PRODUCT (Nested)
    # ------------------------------------------------------------------
    path("products/", ProductListCreateAPIView.as_view(), name="product-list-create"),
    path("products/<int:pk>/", ProductRetrieveUpdateDestroyAPIView.as_view(), name="product-detail"),

    # ------------------------------------------------------------------
    # CHOICES / BOOTSTRAP
    # ------------------------------------------------------------------
    path("gst-types/", GstTypeListAPIView.as_view(), name="gst-types"),
    path("cess-types/", CessTypeListAPIView.as_view(), name="cess-types"),
    path("product-statuses/", ProductStatusListAPIView.as_view(), name="product-statuses"),
    path("product-page-all/", ProductPageBootstrapAPIView.as_view(), name="product-page-bootstrap"),

    # ------------------------------------------------------------------
    # PRODUCT CATEGORY (Entity-wise, via ?entity=<id>)
    # ------------------------------------------------------------------
    path("product-categories/", ProductCategoryListCreateAPIView.as_view(), name="product-category-list-create"),
    path("product-categories/<int:pk>/", ProductCategoryRetrieveUpdateDestroyAPIView.as_view(), name="product-category-detail"),

    # ------------------------------------------------------------------
    # BRAND (Entity-wise, via ?entity=<id>)
    # ------------------------------------------------------------------
    path("brands/", BrandListCreateAPIView.as_view(), name="brand-list-create"),
    path("brands/<int:pk>/", BrandRetrieveUpdateDestroyAPIView.as_view(), name="brand-detail"),

    # ------------------------------------------------------------------
    # UNIT OF MEASURE (Entity-wise, via ?entity=<id>)
    # ------------------------------------------------------------------
    path("uoms/", UnitOfMeasureListCreateAPIView.as_view(), name="uom-list-create"),
    path("uoms/<int:pk>/", UnitOfMeasureRetrieveUpdateDestroyAPIView.as_view(), name="uom-detail"),

    # ------------------------------------------------------------------
    # HSN / SAC (Entity-wise, via ?entity=<id>)
    # ------------------------------------------------------------------
    path("hsn-sac/", HsnSacListCreateAPIView.as_view(), name="hsn-sac-list-create"),
    path("hsn-sac/<int:pk>/", HsnSacRetrieveUpdateDestroyAPIView.as_view(), name="hsn-sac-detail"),

    # ------------------------------------------------------------------
    # PRICE LIST (Entity-wise, via ?entity=<id>)
    # ------------------------------------------------------------------
    path("pricelists/", PriceListListCreateAPIView.as_view(), name="pricelist-list-create"),
    path("pricelists/<int:pk>/", PriceListRetrieveUpdateDestroyAPIView.as_view(), name="pricelist-detail"),

    # ------------------------------------------------------------------
    # PRODUCT ATTRIBUTE MASTER
    # ------------------------------------------------------------------
    path("product-attributes/", ProductAttributeListCreateAPIView.as_view(), name="product-attribute-list-create"),
    path("product-attributes/<int:pk>/", ProductAttributeRetrieveUpdateDestroyAPIView.as_view(), name="product-attribute-detail"),

    # ------------------------------------------------------------------
    # LIGHTWEIGHT LIST ENDPOINTS (keep same style)
    # ------------------------------------------------------------------
    path("entity/<int:entity_id>/list/", ProductImportantListAPIView.as_view(), name="product-important-list"),
    path("invoice-products/<int:entity_id>/", InvoiceProductListAPIView.as_view(), name="invoice-product-list"),
    path("meta/transaction-products/", TransactionProductMetaAPIView.as_view(), name="transaction-product-meta"),
    path("products/<int:product_id>/transaction-meta/", TransactionProductDetailAPIView.as_view(), name="transaction-product-detail"),

    # ------------------------------------------------------------------
    # BARCODES
    # ------------------------------------------------------------------
    path("barcodes/lookup/", BarcodeLookupAPIView.as_view(), name="barcode-lookup"),
    path("products/<int:product_id>/barcodes/", ProductBarcodeListCreateAPIView.as_view(), name="product-barcode-list-create"),
    path("barcodes/<int:pk>/", ProductBarcodeRUDAPIView.as_view(), name="barcode-detail"),
    path("barcodes/download/", ProductBarcodeDownloadPDFAPIView.as_view(), name="barcode-download-pdf"),
    path("barcodes/layout-options/", BarcodeLayoutOptionsAPIView.as_view(), name="barcode-layout-options"),
    path("barcodes/label-templates/", BarcodeLabelTemplateListCreateAPIView.as_view(), name="barcode-label-template-list-create"),
    path("barcodes/label-templates/default/", BarcodeLabelTemplateDefaultAPIView.as_view(), name="barcode-label-template-default"),
    path("barcodes/label-templates/<int:pk>/", BarcodeLabelTemplateRUDAPIView.as_view(), name="barcode-label-template-detail"),
    path("products/<int:product_id>/gst-rates/", ProductGstRateListCreateAPIView.as_view(), name="product-gst-rate-list-create"),
    path("gst-rates/<int:pk>/", ProductGstRateRUDAPIView.as_view(), name="product-gst-rate-detail"),
    path("products/<int:product_id>/uom-conversions/", ProductUomConversionListCreateAPIView.as_view(), name="product-uom-conversion-list-create"),
    path("uom-conversions/<int:pk>/", ProductUomConversionRUDAPIView.as_view(), name="product-uom-conversion-detail"),
    path("products/<int:product_id>/opening-stocks/", OpeningStockByLocationListCreateAPIView.as_view(), name="opening-stock-list-create"),
    path("opening-stocks/<int:pk>/", OpeningStockByLocationRUDAPIView.as_view(), name="opening-stock-detail"),
    path("products/<int:product_id>/prices/", ProductPriceListCreateAPIView.as_view(), name="product-price-list-create"),
    path("prices/<int:pk>/", ProductPriceRUDAPIView.as_view(), name="product-price-detail"),
    path("products/<int:product_id>/planning/", ProductPlanningListCreateAPIView.as_view(), name="product-planning-list-create"),
    path("planning/<int:pk>/", ProductPlanningRUDAPIView.as_view(), name="product-planning-detail"),
    path("products/<int:product_id>/attribute-values/", ProductAttributeValueListCreateAPIView.as_view(), name="product-attribute-value-list-create"),
    path("attribute-values/<int:pk>/", ProductAttributeValueRUDAPIView.as_view(), name="product-attribute-value-detail"),
    path("products/<int:product_id>/images/", ProductImageListCreateAPIView.as_view(), name="product-image-list-create"),
    path("images/<int:pk>/", ProductImageRUDAPIView.as_view(), name="product-image-detail"),
    path(
        "purchaseinvoice-products/",
        PurchaseInvoiceProductListAPIView.as_view(),
        name="invoice-products",
    ),
    path("products/bulk/template/", ProductBulkTemplateAPIView.as_view(), name="product-bulk-template"),
    path("products/bulk/export/", ProductBulkExportAPIView.as_view(), name="product-bulk-export"),
    path("products/bulk/import/validate/", ProductBulkImportValidateAPIView.as_view(), name="product-bulk-import-validate"),
    path("products/bulk/import/commit/", ProductBulkImportCommitAPIView.as_view(), name="product-bulk-import-commit"),
    path("products/bulk/jobs/<int:job_id>/", ProductBulkJobDetailAPIView.as_view(), name="product-bulk-job-detail"),
    path("products/bulk/jobs/<int:job_id>/errors/", ProductBulkJobErrorsExportAPIView.as_view(), name="product-bulk-job-errors"),
    path("hsn-sac/bulk/template/", HsnSacBulkTemplateAPIView.as_view(), name="hsn-sac-bulk-template"),
    path("hsn-sac/bulk/export/", HsnSacBulkExportAPIView.as_view(), name="hsn-sac-bulk-export"),
    path("hsn-sac/bulk/import/validate/", HsnSacBulkImportValidateAPIView.as_view(), name="hsn-sac-bulk-import-validate"),
    path("hsn-sac/bulk/import/commit/", HsnSacBulkImportCommitAPIView.as_view(), name="hsn-sac-bulk-import-commit"),
    path("hsn-sac/bulk/jobs/<int:job_id>/", HsnSacBulkJobDetailAPIView.as_view(), name="hsn-sac-bulk-job-detail"),
    path("hsn-sac/bulk/jobs/<int:job_id>/errors/", HsnSacBulkJobErrorsExportAPIView.as_view(), name="hsn-sac-bulk-job-errors"),
]
