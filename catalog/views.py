# catalog/views.py  (OPTIMIZED + UPDATED FOR NEW MODEL DESIGN)
# Key improvements:
# 1) Removed duplicate ProductCategory views (kept the "create" serializer variant + entity scoping)
# 2) Added EntityFromQueryMixin usage consistently
# 3) Optimized ProductList/Detail querysets (planning is a 1:1 -> use select_related where applicable)
# 4) Optimized InvoiceProductListAPIView & ProductImportantListAPIView using DB-side selection + fixed HSN lookup bug
# 5) Updated UOM serialization bootstrap (now includes uqc automatically via serializer)
# 6) Better error handling for missing/invalid entity_id/product_id
# 7) Kept barcode PDF generator as-is (already good), only minor safety tweaks
#
# NOTE: Because ProductGstRate.gst_rate is derived in model.save(), invoice list should rely on gst_rate if present,
# but CGST/SGST/IGST remain available.

from io import BytesIO
import math

from django.db import transaction
from django.utils.dateparse import parse_date
from rest_framework.generics import ListAPIView
from django.db.models import Q, Prefetch, OuterRef, Subquery
from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import FileResponse

from catalog.serializers import InvoiceProductListItemSerializer

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from entity.models import Entity, SubEntity
from entity.serializers import subentitySerializerbyentity
from financial.models import account
from financial.serializers import SimpleAccountSerializer

from .models import (
    ProductCategory,
    Brand,
    UnitOfMeasure,
    Product,
    HsnSac,
    PriceList,
    GstType,
    CessType,
    ProductStatus,
    ProductBarcode,
    ProductGstRate,
    ProductPrice,
    ProductUomConversion,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    OpeningStockByLocation,
    ProductPlanning,
)
from .serializers import (
    ProductCategorySerializer,
    ProductCategorySerializercreate,
    BrandSerializer,
    UnitOfMeasureSerializer,
    ProductSerializer,
    ProductListSerializer,
    HsnSacSerializer,
    PriceListSerializer,
    ProductAttributeSerializer,
    ProductGstRateSerializer,
    ProductUomConversionSerializer,
    OpeningStockByLocationSerializer,
    ProductPriceSerializer,
    ProductPlanningSerializer,
    ProductAttributeValueSerializer,
    ProductImageNestedSerializer,
    GstTypeChoiceSerializer,
    CessTypeChoiceSerializer,
    ProductStatusChoiceSerializer,
    ProductBarcodeManageSerializer,
)
from .transaction_products import TransactionProductCatalogService


# ----------------------------------------------------------------------
# Mixins
# ----------------------------------------------------------------------

class EntityFromQueryMixin:
    """
    Forces entity scoping using ?entity=<id> query param.
    Helps prevent cross-entity access by plain id.
    """
    def get_entity(self):
        entity_param = self.request.query_params.get("entity")
        if not entity_param:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})

        try:
            return Entity.objects.get(id=int(entity_param))
        except (ValueError, Entity.DoesNotExist):
            raise NotFound("Invalid entity")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["entity"] = self.get_entity()
        return ctx


# ----------------------------------------------------------------------
# Product master views
# ----------------------------------------------------------------------

def product_queryset_optimized():
    """
    Centralized queryset to avoid duplication and ensure consistent prefetching.
    planning is 1:1 in design -> prefer select_related if you change model to OneToOne.
    But your current model is FK with unique constraint, so prefetch is OK.
    """
    return (
        Product.objects
        .select_related(
            "productcategory",
            "brand",
            "base_uom",
            "entity",
            "sales_account",
            "purchase_account",
        )
        .prefetch_related(
            "gst_rates",
            "barcode_details",
            "uom_conversions",
            "opening_stocks",
            "prices",
            "planning",
            "attributes",
            "images",
        )
    )


class ProductListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    """
    GET  /api/products/?entity=<id>
    POST /api/products/?entity=<id>
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity = self.get_entity()
        queryset = Product.objects.filter(entity=entity).select_related(
            "productcategory",
            "brand",
            "base_uom",
        )
        if self.request.method.upper() == "GET":
            return queryset.order_by("productname", "id")
        return product_queryset_optimized().filter(entity=entity)

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ProductListSerializer
        return ProductSerializer

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class ProductRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/PUT/DELETE /api/products/<pk>/?entity=<id>
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity = self.get_entity()
        return product_queryset_optimized().filter(entity=entity)

    def perform_update(self, serializer):
        serializer.save(entity=self.get_entity())


# ----------------------------------------------------------------------
# Basic master data APIs (entity-scoped)
# ----------------------------------------------------------------------

class ProductCategoryListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductCategorySerializercreate

    def get_queryset(self):
        entity = self.get_entity()
        return (
            ProductCategory.objects
            .filter(entity=entity)
            .select_related("maincategory")
            .order_by("pcategoryname")
        )

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class ProductCategoryRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductCategorySerializercreate

    def get_queryset(self):
        entity = self.get_entity()
        return (
            ProductCategory.objects
            .filter(entity=entity)
            .select_related("entity", "maincategory")
        )

    def perform_update(self, serializer):
        serializer.save(entity=self.get_entity())


class BrandListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BrandSerializer

    def get_queryset(self):
        return Brand.objects.filter(entity=self.get_entity()).order_by("name")

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class BrandRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BrandSerializer

    def get_queryset(self):
        return Brand.objects.filter(entity=self.get_entity())


class UnitOfMeasureListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UnitOfMeasureSerializer

    def get_queryset(self):
        return UnitOfMeasure.objects.filter(entity=self.get_entity()).order_by("code")

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class UnitOfMeasureRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UnitOfMeasureSerializer

    def get_queryset(self):
        return UnitOfMeasure.objects.filter(entity=self.get_entity())


class HsnSacListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HsnSacSerializer

    def get_queryset(self):
        return HsnSac.objects.filter(entity=self.get_entity()).order_by("code")

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class HsnSacRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HsnSacSerializer

    def get_queryset(self):
        return HsnSac.objects.filter(entity=self.get_entity())


class PriceListListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PriceListSerializer

    def get_queryset(self):
        return PriceList.objects.filter(entity=self.get_entity()).order_by("name")

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class PriceListRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PriceListSerializer

    def get_queryset(self):
        return PriceList.objects.filter(entity=self.get_entity())


class ProductAttributeListCreateAPIView(EntityFromQueryMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductAttributeSerializer

    def get_queryset(self):
        return ProductAttribute.objects.filter(entity=self.get_entity()).order_by("name")

    def perform_create(self, serializer):
        serializer.save(entity=self.get_entity())


class ProductAttributeRetrieveUpdateDestroyAPIView(EntityFromQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductAttributeSerializer

    def get_queryset(self):
        return ProductAttribute.objects.filter(entity=self.get_entity())


# ----------------------------------------------------------------------
# Choice APIs
# ----------------------------------------------------------------------

class GstTypeListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = [{"value": choice.value, "label": choice.label} for choice in GstType]
        return Response(GstTypeChoiceSerializer(data, many=True).data)


class CessTypeListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = [{"value": c.value, "label": c.label} for c in CessType]
        return Response(CessTypeChoiceSerializer(data, many=True).data)


class ProductStatusListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = [{"value": choice.value, "label": choice.label} for choice in ProductStatus]
        return Response(ProductStatusChoiceSerializer(data, many=True).data)


# ----------------------------------------------------------------------
# Bootstrap API for Product Page (one call for dropdowns + optional product)
# ----------------------------------------------------------------------

class ProductPageBootstrapAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})

        try:
            entity_id_int = int(entity_id)
        except ValueError:
            raise ValidationError({"entity": "Invalid entity id"})

        product_id = request.query_params.get("product_id")
        product = None
        if product_id:
            try:
                product_obj = product_queryset_optimized().get(pk=int(product_id), entity_id=entity_id_int)
            except (ValueError, Product.DoesNotExist):
                raise NotFound("Invalid product for this entity")
            product = ProductSerializer(product_obj, context={"request": request}).data

        categories = ProductCategory.objects.filter(entity_id=entity_id_int, isactive=True).select_related("maincategory")
        brands = Brand.objects.filter(entity_id=entity_id_int, isactive=True)
        uoms = UnitOfMeasure.objects.filter(entity_id=entity_id_int, isactive=True)
        hsn_sac = HsnSac.objects.filter(entity_id=entity_id_int, isactive=True)
        pricelists = PriceList.objects.filter(entity_id=entity_id_int, isactive=True)
        product_attributes = ProductAttribute.objects.filter(entity_id=entity_id_int, isactive=True).order_by("name")
        accounts = (
            account.objects.filter(entity_id=entity_id_int)
            .select_related("state", "ledger", "ledger__accounthead")
            .order_by("accountname", "id")
        )
        locations = SubEntity.objects.filter(entity_id=entity_id_int).order_by("subentityname", "id")

        data = {
            "product": product,
            "gst_types": [{"value": choice.value, "label": choice.label} for choice in GstType],
            "cess_types": [{"value": choice.value, "label": choice.label} for choice in CessType],
            "product_statuses": [{"value": choice.value, "label": choice.label} for choice in ProductStatus],

            "product_categories": ProductCategorySerializer(categories, many=True).data,
            "brands": BrandSerializer(brands, many=True).data,
            "uoms": UnitOfMeasureSerializer(uoms, many=True).data,          # includes uqc now
            "hsn_sac": HsnSacSerializer(hsn_sac, many=True).data,
            "pricelists": PriceListSerializer(pricelists, many=True).data,
            "product_attributes": ProductAttributeSerializer(product_attributes, many=True).data,
            "accounts": SimpleAccountSerializer(accounts, many=True).data,
            "locations": subentitySerializerbyentity(locations, many=True).data,
        }
        return Response(data)


# ----------------------------------------------------------------------
# Transaction-ready product meta APIs
# ----------------------------------------------------------------------

class TransactionProductMetaAPIView(APIView):
    """
    Rich product catalog for transactional line-entry screens.
    Returns product-specific UOM options, conversions, prices, and barcodes.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        entity = request.query_params.get("entity")
        if not entity:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})

        try:
            entity_id = int(entity)
        except (TypeError, ValueError):
            raise ValidationError({"entity": "Invalid entity id."})

        search = (request.query_params.get("search") or "").strip()
        as_of_date_raw = (request.query_params.get("as_of_date") or "").strip()
        as_of_date = parse_date(as_of_date_raw) if as_of_date_raw else None
        if as_of_date_raw and not as_of_date:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD format."})

        try:
            limit = int(request.query_params.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = int(request.query_params.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0

        payload = TransactionProductCatalogService.list_products(
            entity_id=entity_id,
            search=search,
            as_of_date=as_of_date,
            limit=max(1, min(limit, 200)),
            offset=max(0, offset),
        )
        return Response(payload)


class TransactionProductDetailAPIView(APIView):
    """
    Rich single-product transaction meta for line-entry defaults.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, product_id: int, format=None):
        entity = request.query_params.get("entity")
        if not entity:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})

        try:
            entity_id = int(entity)
        except (TypeError, ValueError):
            raise ValidationError({"entity": "Invalid entity id."})

        as_of_date_raw = (request.query_params.get("as_of_date") or "").strip()
        as_of_date = parse_date(as_of_date_raw) if as_of_date_raw else None
        if as_of_date_raw and not as_of_date:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD format."})

        payload = TransactionProductCatalogService.get_product(
            entity_id=entity_id,
            product_id=product_id,
            as_of_date=as_of_date,
        )
        return Response(payload)


# ----------------------------------------------------------------------
# Lightweight product list for invoice page (optimized)
# ----------------------------------------------------------------------

class InvoiceProductListAPIView(APIView):
    """
    Lightweight transaction-ready product list for invoice pages.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, entity_id, format=None):
        search = (request.query_params.get("search") or "").strip()
        as_of_date_raw = (request.query_params.get("as_of_date") or "").strip()
        as_of_date = parse_date(as_of_date_raw) if as_of_date_raw else None
        if as_of_date_raw and not as_of_date:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD format."})

        payload = TransactionProductCatalogService.list_products(
            entity_id=entity_id,
            search=search,
            as_of_date=as_of_date,
            limit=200,
            offset=0,
        )
        return Response(payload["items"], status=status.HTTP_200_OK)


# ----------------------------------------------------------------------
# Flat list for product screen (optimized + fixed HSN bug)
# ----------------------------------------------------------------------

class ProductImportantListAPIView(APIView):
    """
    GET /api/catalog/entity/<entity_id>/products/list/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, entity_id):
        gst_latest_sq = ProductGstRate.objects.filter(
            product_id=OuterRef("pk")
        ).order_by("-valid_from")

        price_default_sq = ProductPrice.objects.filter(
            product_id=OuterRef("pk"),
            pricelist__isdefault=True
        ).order_by("-effective_from")

        qs = (
            Product.objects
            .filter(entity_id=entity_id, isactive=True)
            .select_related("brand", "productcategory", "base_uom")
            .annotate(
                gst_rate=Subquery(gst_latest_sq.values("gst_rate")[:1]),
                hsn_id=Subquery(gst_latest_sq.values("hsn_id")[:1]),
                selling_price=Subquery(price_default_sq.values("selling_price")[:1]),
            )
            .order_by("productname")
        )

        hsn_ids = list(set([x for x in qs.values_list("hsn_id", flat=True) if x]))
        hsn_map = {h.id: h.code for h in HsnSac.objects.filter(id__in=hsn_ids)}

        items = []
        for p in qs:
            items.append({
                "id": p.id,
                "productname": p.productname,
                "sku": p.sku,
                "brand": p.brand.name if p.brand else None,
                "category": p.productcategory.pcategoryname if p.productcategory else None,
                "uom": p.base_uom.code if p.base_uom else None,
                "hsn": hsn_map.get(p.hsn_id),  # ✅ FIXED: previously p.hsn_sac did not exist
                "gst": float(p.gst_rate) if p.gst_rate is not None else None,
                "selling_price": float(p.selling_price) if p.selling_price is not None else None,
                "isactive": p.isactive,
            })

        return Response(items, status=status.HTTP_200_OK)


# ----------------------------------------------------------------------
# Barcode CRUD
# ----------------------------------------------------------------------

class ProductBarcodeListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductBarcodeManageSerializer

    def _get_entity(self):
        entity_param = self.request.query_params.get("entity")
        if not entity_param:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})
        try:
            return Entity.objects.get(id=int(entity_param))
        except (ValueError, Entity.DoesNotExist):
            raise NotFound("Invalid entity")

    def get_product(self):
        product_id = self.kwargs["product_id"]
        return get_object_or_404(Product, pk=product_id, entity=self._get_entity())

    def get_queryset(self):
        product = self.get_product()
        return (
            ProductBarcode.objects.filter(product=product)
            .select_related("product", "uom")
            .order_by("-isprimary", "id")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["product"] = self.get_product()
        return ctx


class ProductBarcodeRUDAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductBarcodeManageSerializer

    def get_queryset(self):
        entity_param = self.request.query_params.get("entity")
        if not entity_param:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})
        try:
            entity_id = int(entity_param)
        except (TypeError, ValueError):
            raise ValidationError({"entity": "Invalid entity id"})
        return ProductBarcode.objects.select_related("product", "uom").filter(product__entity_id=entity_id)


class ProductScopedChildMixin:
    permission_classes = [permissions.IsAuthenticated]

    def _get_entity(self):
        entity_param = self.request.query_params.get("entity")
        if not entity_param:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})
        try:
            return Entity.objects.get(id=int(entity_param))
        except (ValueError, Entity.DoesNotExist):
            raise NotFound("Invalid entity")

    def _get_entity_id(self):
        entity_param = self.request.query_params.get("entity")
        if not entity_param:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})
        try:
            return int(entity_param)
        except (TypeError, ValueError):
            raise ValidationError({"entity": "Invalid entity id"})

    def get_product(self):
        return get_object_or_404(Product, pk=self.kwargs["product_id"], entity=self._get_entity())

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if "product_id" in self.kwargs:
            ctx["product"] = self.get_product()
        ctx["entity"] = self._get_entity()
        return ctx


class ProductGstRateListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = ProductGstRateSerializer

    def get_queryset(self):
        return ProductGstRate.objects.filter(product=self.get_product()).select_related("hsn").order_by("-isdefault", "-valid_from", "-id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class ProductGstRateRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductGstRateSerializer

    def get_queryset(self):
        return ProductGstRate.objects.select_related("product", "hsn").filter(product__entity_id=self._get_entity_id())


class ProductUomConversionListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = ProductUomConversionSerializer

    def get_queryset(self):
        return ProductUomConversion.objects.filter(product=self.get_product()).select_related("from_uom", "to_uom").order_by("id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class ProductUomConversionRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductUomConversionSerializer

    def get_queryset(self):
        return ProductUomConversion.objects.select_related("product", "from_uom", "to_uom").filter(product__entity_id=self._get_entity_id())


class OpeningStockByLocationListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = OpeningStockByLocationSerializer

    def get_queryset(self):
        return OpeningStockByLocation.objects.filter(product=self.get_product()).select_related("location").order_by("-as_of_date", "id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product(), entity=self.get_product().entity)


class OpeningStockByLocationRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningStockByLocationSerializer

    def get_queryset(self):
        return OpeningStockByLocation.objects.select_related("product", "location").filter(entity_id=self._get_entity_id())


class ProductPriceListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = ProductPriceSerializer

    def get_queryset(self):
        return ProductPrice.objects.filter(product=self.get_product()).select_related("pricelist", "uom").order_by("-effective_from", "-id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class ProductPriceRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductPriceSerializer

    def get_queryset(self):
        return ProductPrice.objects.select_related("product", "pricelist", "uom").filter(product__entity_id=self._get_entity_id())


class ProductPlanningListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = ProductPlanningSerializer

    def get_queryset(self):
        return ProductPlanning.objects.filter(product=self.get_product()).order_by("id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class ProductPlanningRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductPlanningSerializer

    def get_queryset(self):
        return ProductPlanning.objects.select_related("product").filter(product__entity_id=self._get_entity_id())


class ProductAttributeValueListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = ProductAttributeValueSerializer

    def get_queryset(self):
        return ProductAttributeValue.objects.filter(product=self.get_product()).select_related("attribute").order_by("id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class ProductAttributeValueRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductAttributeValueSerializer

    def get_queryset(self):
        return ProductAttributeValue.objects.select_related("product", "attribute").filter(product__entity_id=self._get_entity_id())


class ProductImageListCreateAPIView(ProductScopedChildMixin, generics.ListCreateAPIView):
    serializer_class = ProductImageNestedSerializer

    def get_queryset(self):
        return ProductImage.objects.filter(product=self.get_product()).order_by("-is_primary", "id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class ProductImageRUDAPIView(ProductScopedChildMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductImageNestedSerializer

    def get_queryset(self):
        return ProductImage.objects.select_related("product").filter(product__entity_id=self._get_entity_id())


# ----------------------------------------------------------------------
# Barcode PDF download (kept mostly same; already good)
# ----------------------------------------------------------------------

def _fit_font_size(c, text, max_width, start_size=8.0, min_size=5.5):
    size = start_size
    while size >= min_size:
        c.setFont("Helvetica", size)
        if c.stringWidth(text, "Helvetica", size) <= max_width:
            return size
        size -= 0.3
    return min_size


class ProductBarcodeDownloadPDFAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    GRID_MAP = {
        1:  (1, 1),
        2:  (1, 2),
        4:  (2, 2),
        8:  (2, 4),
        10: (2, 5),
        12: (3, 4),
        16: (4, 4),
        20: (4, 5),
    }

    def post(self, request):
        data = request.data
        entity_param = request.query_params.get("entity")
        if not entity_param:
            return Response({"detail": "Query param ?entity=<id> is required."}, status=400)
        try:
            entity_id = int(entity_param)
        except Exception:
            return Response({"detail": "Invalid entity id"}, status=400)

        if not isinstance(data, list):
            return Response({"detail": "Request body must be a JSON array"}, status=400)

        all_barcodes = []
        final_layout = None
        show_createdon = False

        for idx, job in enumerate(data):
            try:
                layout = int(job.get("layout", 16))
            except Exception:
                return Response({"detail": f"Invalid layout in item {idx}"}, status=400)

            if layout not in self.GRID_MAP:
                return Response({"detail": f"Invalid layout in item {idx}"}, status=400)

            final_layout = layout

            ids = job.get("ids")
            if ids is None:
                return Response({"detail": f"'ids' missing in item {idx}"}, status=400)

            if isinstance(ids, int):
                id_list = [ids]
            elif isinstance(ids, list):
                id_list = ids
            else:
                return Response({"detail": f"'ids' must be int or list in item {idx}"}, status=400)

            try:
                copies = int(job.get("copies", 1))
            except Exception:
                return Response({"detail": f"'copies' must be integer in item {idx}"}, status=400)

            if copies <= 0:
                return Response({"detail": f"'copies' must be > 0 in item {idx}"}, status=400)

            show_createdon = bool(job.get("show_createdon", False))

            barcodes = list(
                ProductBarcode.objects
                .filter(id__in=id_list, product__entity_id=entity_id)
                .select_related("product", "uom")
            )
            if not barcodes:
                continue

            # ensure images exist (one atomic block is enough)
            with transaction.atomic():
                for b in barcodes:
                    if not b.barcode_image:
                        b.save()

            expanded = []
            i = 0
            while len(expanded) < copies:
                expanded.append(barcodes[i % len(barcodes)])
                i += 1

            all_barcodes.extend(expanded)

        if not all_barcodes:
            return Response({"detail": "No barcodes found"}, status=404)

        pdf_file = self._build_pdf(
            all_barcodes,
            layout=final_layout or 16,
            show_createdon=show_createdon
        )

        return FileResponse(
            pdf_file,
            as_attachment=True,
            filename="barcodes_bulk.pdf",
            content_type="application/pdf",
        )

    def _build_pdf(self, barcode_objects, layout: int, show_createdon: bool):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        page_w, page_h = A4

        cols, rows = self.GRID_MAP[layout]
        per_page = cols * rows

        margin = 18
        gap = 10
        pad = 7
        corner_radius = 10
        show_cut_lines = True

        cell_w = (page_w - 2 * margin - (cols - 1) * gap) / cols
        cell_h = (page_h - 2 * margin - (rows - 1) * gap) / rows

        if layout in (1, 2, 4):
            text_area_h = 48
            base_font = 8.6
        elif layout in (8, 10, 12):
            text_area_h = 38
            base_font = 7.4
        else:
            text_area_h = 30
            base_font = 6.6

        img_area_h = max(40, cell_h - text_area_h - 2 * pad)

        total_pages = math.ceil(len(barcode_objects) / per_page)
        idx = 0

        for _ in range(total_pages):
            for r in range(rows):
                for col in range(cols):
                    if idx >= len(barcode_objects):
                        break

                    b = barcode_objects[idx]
                    idx += 1

                    x = margin + col * (cell_w + gap)
                    y = page_h - margin - (r + 1) * cell_h - r * gap

                    c.setLineWidth(0.6)
                    c.roundRect(x, y, cell_w, cell_h, corner_radius, stroke=1, fill=0)

                    if show_cut_lines:
                        c.saveState()
                        c.setDash(2, 2)
                        c.setLineWidth(0.3)
                        c.roundRect(x + 1.5, y + 1.5, cell_w - 3, cell_h - 3, corner_radius, stroke=1, fill=0)
                        c.restoreState()

                    if getattr(b, "isprimary", False):
                        badge_w, badge_h = 46, 14
                        bx = x + cell_w - badge_w - pad
                        by = y + cell_h - badge_h - pad
                        c.saveState()
                        c.setLineWidth(0.8)
                        c.roundRect(bx, by, badge_w, badge_h, 6, stroke=1, fill=0)
                        c.setFont("Helvetica-Bold", max(6, base_font))
                        c.drawCentredString(bx + badge_w / 2, by + 4, "PRIMARY")
                        c.restoreState()

                    if b.barcode_image:
                        img = ImageReader(b.barcode_image.path)
                        img_x = x + pad
                        img_y = y + text_area_h + pad
                        img_w = cell_w - 2 * pad
                        img_h = img_area_h
                        c.drawImage(
                            img, img_x, img_y,
                            width=img_w, height=img_h,
                            preserveAspectRatio=True, anchor="c",
                        )

                    product_name = ((b.product.productname or "").strip() if b.product_id else "")
                    sku = ((b.product.sku or "").strip() if b.product_id else "")
                    uom_code = ((b.uom.code or "").strip() if b.uom_id else "")
                    pack = b.pack_size or 1
                    barcode_val = b.barcode or ""

                    if len(product_name) > 34:
                        product_name = product_name[:31] + "..."

                    line1 = product_name
                    line2 = f"SKU: {sku}   UOM: {uom_code}   Pack: {pack}"
                    line3 = f"{barcode_val}"

                    extra = None
                    if show_createdon and getattr(b, "createdon", None):
                        extra = f"Created: {b.createdon.date().isoformat()}"

                    tx_width = (x + cell_w - pad) - (x + pad)
                    ty_top = y + text_area_h - pad
                    ty_bottom = y + pad
                    line_gap = 2
                    current_y = ty_top

                    if line1:
                        s = _fit_font_size(c, line1, tx_width, start_size=base_font + 0.8, min_size=base_font - 1.0)
                        c.setFont("Helvetica-Bold", s)
                        c.drawCentredString(x + cell_w / 2, current_y - s, line1)
                        current_y -= (s + line_gap)

                    s2 = _fit_font_size(c, line2, tx_width, start_size=base_font, min_size=base_font - 1.2)
                    c.setFont("Helvetica", s2)
                    c.drawCentredString(x + cell_w / 2, current_y - s2, line2)
                    current_y -= (s2 + line_gap)

                    s3 = _fit_font_size(c, line3, tx_width, start_size=base_font + 0.4, min_size=base_font - 0.8)
                    c.setFont("Helvetica", s3)
                    c.drawCentredString(x + cell_w / 2, current_y - s3, line3)
                    current_y -= (s3 + line_gap)

                    if extra and current_y > ty_bottom + 6:
                        c.setFont("Helvetica", max(5.5, base_font - 1.2))
                        c.drawCentredString(x + cell_w / 2, ty_bottom + 2, extra)

            c.showPage()

        c.save()
        buffer.seek(0)
        return buffer


class BarcodeLayoutOptionsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    GRID_MAP = {
        1:  (1, 1),
        2:  (2, 1),
        4:  (2, 2),
        8:  (4, 2),
        10: (5, 2),
        12: (4, 3),
        16: (4, 4),
        20: (5, 4),
    }

    SIZE_LABELS = {
        1: "Extra Large",
        2: "Large",
        4: "Large",
        8: "Medium",
        10: "Medium",
        12: "Medium",
        16: "Small",
        20: "Small",
    }

    def get(self, request):
        layouts = []
        for layout, (rows, cols) in self.GRID_MAP.items():
            layouts.append({
                "layout": layout,
                "rows": rows,
                "cols": cols,
                "labels_per_page": layout,
                "label": f"{layout} sticker{'s' if layout > 1 else ''} per page ({self.SIZE_LABELS.get(layout)})",
            })
        return Response(layouts)
    

def _taxability_from_hsn(hsn_row) -> int:
    """
    Align with PurchaseInvoiceHeader.Taxability:
    1 TAXABLE, 2 EXEMPT, 3 NIL_RATED, 4 NON_GST
    """
    if not hsn_row:
        return 1
    if hsn_row.get("is_exempt"):
        return 2
    if hsn_row.get("is_nil_rated"):
        return 3
    if hsn_row.get("is_non_gst"):
        return 4
    return 1
    


class PurchaseInvoiceProductListAPIView(APIView):
    """
    Paged transaction-ready product list for purchase invoice screens.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        entity = self.request.query_params.get("entity")
        as_of_date_raw = (request.query_params.get("as_of_date") or "").strip()
        as_of_date = parse_date(as_of_date_raw) if as_of_date_raw else None
        if as_of_date_raw and not as_of_date:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD format."})

        try:
            limit = int(request.query_params.get("limit") or 50)
        except Exception:
            limit = 50
        try:
            offset = int(request.query_params.get("offset") or 0)
        except Exception:
            offset = 0

        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        if not entity:
            raise ValidationError({"entity": "Query param ?entity=<id> is required."})
        try:
            entity_id = int(entity)
        except (TypeError, ValueError):
            raise ValidationError({"entity": "Invalid entity id."})

        search = (request.query_params.get("search") or "").strip()
        payload = TransactionProductCatalogService.list_products(
            entity_id=entity_id,
            search=search,
            as_of_date=as_of_date,
            limit=limit,
            offset=offset,
        )
        return Response(payload, status=status.HTTP_200_OK)
