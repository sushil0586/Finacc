# catalog/views.py

from rest_framework import generics, permissions

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
