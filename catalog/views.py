# catalog/views.py

from rest_framework import generics, permissions
from rest_framework import status
from django.db.models import Q

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
)
from catalog.serializers import (
    ProductCategorySerializer,
    BrandSerializer,
    UnitOfMeasureSerializer,
    ProductSerializer,
    HsnSacSerializer,
    PriceListSerializer,
    GstTypeChoiceSerializer,
    CessTypeChoiceSerializer,
    ProductStatusChoiceSerializer,
)

from rest_framework.views import APIView
from rest_framework.response import Response


# ----------------------------------------------------------------------
# Helper mixin for entity filtering (optional)
# ----------------------------------------------------------------------

class EntityFilteredQuerysetMixin:
    """
    Optional mixin: filter queryset by ?entity=<id> if present.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        entity_id = self.request.query_params.get("entity")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        return qs


# ----------------------------------------------------------------------
# Product master generic views
# ----------------------------------------------------------------------

class ProductListCreateAPIView(EntityFilteredQuerysetMixin,
                               generics.ListCreateAPIView):
    """
    GET  /api/products/           -> list (with nested if serializer returns)
    POST /api/products/           -> create Product + nested children
    """
    queryset = (
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
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProductRetrieveUpdateDestroyAPIView(EntityFilteredQuerysetMixin,
                                          generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/products/<id>/    -> detail with nested
    PUT    /api/products/<id>/    -> full update with nested
    PATCH  /api/products/<id>/    -> partial update (nested if included)
    DELETE /api/products/<id>/    -> delete
    """
    queryset = (
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
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]


# ----------------------------------------------------------------------
# Basic master data APIs
# ----------------------------------------------------------------------

class ProductCategoryListCreateAPIView(EntityFilteredQuerysetMixin,
                                       generics.ListCreateAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class ProductCategoryRetrieveUpdateDestroyAPIView(
        generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class BrandListCreateAPIView(EntityFilteredQuerysetMixin,
                             generics.ListCreateAPIView):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [permissions.IsAuthenticated]


class BrandRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [permissions.IsAuthenticated]


class UnitOfMeasureListCreateAPIView(EntityFilteredQuerysetMixin,
                                     generics.ListCreateAPIView):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [permissions.IsAuthenticated]


class UnitOfMeasureRetrieveUpdateDestroyAPIView(
        generics.RetrieveUpdateDestroyAPIView):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [permissions.IsAuthenticated]


class HsnSacListCreateAPIView(EntityFilteredQuerysetMixin,
                              generics.ListCreateAPIView):
    queryset = HsnSac.objects.all()
    serializer_class = HsnSacSerializer
    permission_classes = [permissions.IsAuthenticated]


class HsnSacRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = HsnSac.objects.all()
    serializer_class = HsnSacSerializer
    permission_classes = [permissions.IsAuthenticated]


class PriceListListCreateAPIView(EntityFilteredQuerysetMixin,
                                 generics.ListCreateAPIView):
    queryset = PriceList.objects.all()
    serializer_class = PriceListSerializer
    permission_classes = [permissions.IsAuthenticated]


class PriceListRetrieveUpdateDestroyAPIView(
        generics.RetrieveUpdateDestroyAPIView):
    queryset = PriceList.objects.all()
    serializer_class = PriceListSerializer
    permission_classes = [permissions.IsAuthenticated]


class GstTypeListAPIView(APIView):
    """
    Returns GST type choices:
    [
        {"value": "regular", "label": "Regular"},
        {"value": "exempt", "label": "Exempt"},
        {"value": "nil_rated", "label": "Nil Rated"},
        {"value": "non_gst", "label": "Non-GST"},
        {"value": "composition", "label": "Composition"}
    ]
    """

    def get(self, request):
        data = [{"value": choice.value, "label": choice.label}
                for choice in GstType]

        serializer = GstTypeChoiceSerializer(data, many=True)
        return Response(serializer.data)
    

class CessTypeListAPIView(APIView):
    def get(self, request):
        data = [{"value": c.value, "label": c.label} for c in CessType]
        serializer = CessTypeChoiceSerializer(data, many=True)
        return Response(serializer.data)
    

class ProductStatusListAPIView(APIView):
    """
    Returns product status choices:
    [
        {"value": "active", "label": "Active"},
        {"value": "discontinued", "label": "Discontinued"},
        {"value": "blocked", "label": "Blocked"},
        {"value": "upcoming", "label": "Upcoming"}
    ]
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = [
            {"value": choice.value, "label": choice.label}
            for choice in ProductStatus
        ]
        serializer = ProductStatusChoiceSerializer(data, many=True)
        return Response(serializer.data)
    

class ProductPageBootstrapAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        entity_id = request.query_params.get("entity")
        product_id = request.query_params.get("product_id")

        product = None
        if product_id:
            product_obj = Product.objects.get(pk=product_id, entity_id=entity_id)
            product = ProductSerializer(product_obj).data

        categories = ProductCategory.objects.filter(entity_id=entity_id, isactive=True)
        brands = Brand.objects.filter(entity_id=entity_id, isactive=True)
        uoms = UnitOfMeasure.objects.filter(entity_id=entity_id, isactive=True)
        hsn_sac = HsnSac.objects.filter(entity_id=entity_id, isactive=True)
        pricelists = PriceList.objects.filter(entity_id=entity_id, isactive=True)

        data = {
            "product": product,

            "gst_types": [
                {"value": choice.value, "label": choice.label}
                for choice in GstType
            ],

            "cess_types": [
                {"value": choice.value, "label": choice.label}
                for choice in CessType
            ],

            "product_statuses": [
                {"value": choice.value, "label": choice.label}
                for choice in ProductStatus
            ],

            "product_categories": ProductCategorySerializer(categories, many=True).data,
            "brands": BrandSerializer(brands, many=True).data,
            "uoms": UnitOfMeasureSerializer(uoms, many=True).data,
            "hsn_sac": HsnSacSerializer(hsn_sac, many=True).data,
            "pricelists": PriceListSerializer(pricelists, many=True).data,
        }

        return Response(data)



class InvoiceProductListAPIView(APIView):
    """
    Lightweight product list for invoice page.

    GET /api/catalog/entity/<entity_id>/invoice-products/
    Optional: ?search=<text>  (search by name or sku)
    """

    def get(self, request, entity_id, format=None):
        search = (request.query_params.get("search") or "").strip()

        # Base queryset: entity + active
        qs = (
            Product.objects
            .filter(entity_id=entity_id, isactive=True)
            .select_related("base_uom")
            .prefetch_related("gst_rates", "prices")
            .order_by("productname")
        )

        if search:
            qs = qs.filter(
                Q(productname__icontains=search) |
                Q(sku__icontains=search)
            )

        items = []

        for p in qs:
            # ---------- GST / HSN (pick default, else latest) ----------
            default_gst = (
                p.gst_rates.filter(isdefault=True).order_by("-valid_from").first()
                or p.gst_rates.order_by("-valid_from").first()
            )

            if default_gst:
                hsn_code = default_gst.hsn.code
                cgst = default_gst.cgst
                sgst = default_gst.sgst
                igst = default_gst.igst
                cess = default_gst.cess
                cess_type = default_gst.cess_type
            else:
                hsn_code = None
                cgst = sgst = igst = cess = None
                cess_type = None

            # ---------- Prices (pick default pricelist, else latest) ----------
            default_price = (
                p.prices.filter(pricelist__isdefault=True)
                .order_by("-effective_from")
                .first()
                or p.prices.order_by("-effective_from").first()
            )

            if default_price:
                mrp = default_price.mrp
                salesprice = default_price.selling_price
                purchaserate = default_price.purchase_rate
            else:
                mrp = salesprice = purchaserate = None

            # ---------- UOM ----------
            uom_code = p.base_uom.code if p.base_uom else None

            # ---------- Build response row ----------
            items.append({
                "id": p.id,
                "productname": p.productname,
                "productdesc": p.productdesc,
                "sku": p.sku,
                "uom": uom_code,
                "is_service": p.is_service,
                "is_pieces": p.is_pieces,

                "mrp": float(mrp) if mrp is not None else None,
                "salesprice": float(salesprice) if salesprice is not None else None,
                "purchaserate": float(purchaserate) if purchaserate is not None else None,

                "hsn": hsn_code,
                "cgst": float(cgst) if cgst is not None else None,
                "sgst": float(sgst) if sgst is not None else None,
                "igst": float(igst) if igst is not None else None,
                "cess": float(cess) if cess is not None else None,
                "cesstype": cess_type,
            })

        return Response(items, status=status.HTTP_200_OK)




class ProductImportantListAPIView(APIView):
    """
    Returns lightweight flat list of products for main product screen.
    GET /api/catalog/entity/<entity_id>/products/list/
    """

    def get(self, request, entity_id):
        items = []

        # Preload related objects
        qs = (
            Product.objects
            .filter(entity_id=entity_id, isactive=True)
            .select_related("brand", "productcategory", "base_uom")
            .order_by("productname")
        )

        for p in qs:
            # Get latest GST rate (if exists)
            latest_gst = (
                p.gst_rates.order_by("-valid_from").first()
                if hasattr(p, "gst_rates")
                else None
            )

            gst_rate = (
                latest_gst.gst_rate if latest_gst else None
            )

            # Get default selling price
            default_price = (
                p.prices.filter(pricelist__isdefault=True)
                .order_by("-effective_from")
                .first()
            )

            selling_price = default_price.selling_price if default_price else None

            items.append({
                "id": p.id,
                "productname": p.productname,
                "sku": p.sku,
                "brand": p.brand.name if p.brand else None,
                "category": p.productcategory.pcategoryname if p.productcategory else None,
                "uom": p.base_uom.code if p.base_uom else None,
                "hsn": p.hsn_sac.code if hasattr(p, "hsn_sac") and p.hsn_sac else None,
                "gst": float(gst_rate) if gst_rate is not None else None,
                "selling_price": selling_price,
                "isactive": p.isactive
            })

        return Response(items, status=status.HTTP_200_OK)
