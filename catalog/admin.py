# catalog/admin.py

from django.contrib import admin
from .models import (
    ProductCategory,
    Brand,
    UnitOfMeasure,
    HsnSac,
    PriceList,
    Product,
    ProductGstRate,
    ProductBarcode,
    ProductUomConversion,
    OpeningStockByLocation,
    ProductPrice,
    ProductPlanning,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
)


# ======================================================================
# MASTER MODELS
# ======================================================================

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "pcategoryname",
        "entity",
        "maincategory",
        "level",
        "isactive",
        "createdon",
        "modifiedon",
    )
    list_filter = ("entity", "isactive", "level")
    search_fields = ("pcategoryname",)
    ordering = ("pcategoryname",)
    readonly_fields = ("createdon", "modifiedon")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "entity", "isactive", "createdon", "modifiedon")
    list_filter = ("entity", "isactive")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("createdon", "modifiedon")


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "entity", "isactive", "createdon", "modifiedon")
    list_filter = ("entity", "isactive")
    search_fields = ("code", "description")
    ordering = ("code",)
    readonly_fields = ("createdon", "modifiedon")


@admin.register(HsnSac)
class HsnSacAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "description",
        "entity",
        "is_service",
        "default_sgst",
        "default_cgst",
        "default_igst",
        "default_cess",
        "is_exempt",
        "is_nil_rated",
        "is_non_gst",
        "isactive",
        "createdon",
        "modifiedon",
    )
    list_filter = (
        "entity",
        "is_service",
        "is_exempt",
        "is_nil_rated",
        "is_non_gst",
        "isactive",
    )
    search_fields = ("code", "description")
    ordering = ("code",)
    readonly_fields = ("createdon", "modifiedon")


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("name", "entity", "isdefault", "isactive", "createdon", "modifiedon")
    list_filter = ("entity", "isdefault", "isactive")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("createdon", "modifiedon")


# ======================================================================
# INLINE MODELS FOR PRODUCT
# ======================================================================

class ProductGstRateInline(admin.TabularInline):
    model = ProductGstRate
    extra = 1
    fields = (
        "hsn",
        "gst_type",
        "sgst",
        "cgst",
        "igst",
        "gst_rate",
        "cess",
        "cess_type",
        "valid_from",
        "valid_to",
        "isdefault",
    )


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 1
    fields = ("barcode", "uom", "isprimary", "pack_size")


class ProductUomConversionInline(admin.TabularInline):
    model = ProductUomConversion
    extra = 1
    fields = ("from_uom", "to_uom", "factor")


class OpeningStockInline(admin.TabularInline):
    model = OpeningStockByLocation
    extra = 1
    fields = ("location", "openingqty", "openingrate", "openingvalue", "as_of_date")


class ProductPriceInline(admin.TabularInline):
    model = ProductPrice
    extra = 1
    fields = (
        "pricelist",
        "uom",
        "purchase_rate",
        "purchase_rate_less_percent",
        "mrp",
        "mrp_less_percent",
        "selling_price",
        "effective_from",
        "effective_to",
    )


class ProductPlanningInline(admin.StackedInline):
    model = ProductPlanning
    extra = 0
    max_num = 1  # only one record
    fields = (
        "min_stock",
        "max_stock",
        "reorder_level",
        "reorder_qty",
        "lead_time_days",
        "abc_class",
        "fsn_class",
    )


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 1
    fields = ("attribute", "value_char", "value_number", "value_date", "value_bool")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "is_primary", "caption")


# ======================================================================
# PRODUCT ADMIN (WITH ALL INLINES)
# ======================================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        "productname",
        "sku",
        "entity",
        "productcategory",
        "brand",
        "base_uom",
        "sales_account",
        "purchase_account",
        "is_service",
        "product_status",
        "isactive",
        "createdon",
        "modifiedon",
    )

    search_fields = ("productname", "sku")
    list_filter = (
        "entity",
        "productcategory",
        "brand",
        "product_status",
        "is_service",
        "is_batch_managed",
        "is_serialized",
        "isactive",
    )
    ordering = ("productname",)
    readonly_fields = ("createdon", "modifiedon")

    inlines = [
        ProductGstRateInline,
        ProductBarcodeInline,
        ProductUomConversionInline,
        OpeningStockInline,
        ProductPriceInline,
        ProductPlanningInline,
        ProductAttributeValueInline,
        ProductImageInline,
    ]


# ======================================================================
# ATTRIBUTE MASTER (Optional admin)
# ======================================================================

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "data_type", "entity", "isactive", "createdon", "modifiedon")
    list_filter = ("entity", "data_type", "isactive")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("createdon", "modifiedon")
