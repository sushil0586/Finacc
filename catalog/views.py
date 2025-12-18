# catalog/views.py

from rest_framework import generics, permissions
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.db import transaction
import math
from io import BytesIO
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



from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from catalog.models import Product, ProductBarcode
from catalog.serializers.product_barcode_manage import ProductBarcodeManageSerializer


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
    



class ProductBarcodeListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    serializer_class = ProductBarcodeManageSerializer

    def get_product(self):
        return get_object_or_404(Product, pk=self.kwargs["product_id"])

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


# ---------------------------------------------------------
# GET    /api/barcodes/<id>/
# PATCH  /api/barcodes/<id>/
# DELETE /api/barcodes/<id>/
# ---------------------------------------------------------
class ProductBarcodeRUDAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductBarcodeManageSerializer
    queryset = ProductBarcode.objects.select_related("product", "uom")


# ---------------------------------------------------------
# GET /api/barcodes/download/?product_id=123&layout=16
# GET /api/barcodes/download/?ids=1,2,3&layout=4
# layout must be 4 or 10 or 16
# ---------------------------------------------------------
class ProductBarcodeDownloadPDFAPIView(APIView):
    permission_classes =[permissions.IsAuthenticated]

    def get(self, request):
        # validate layout
        try:
            layout = int(request.query_params.get("layout", 16))
        except Exception:
            return Response({"detail": "layout must be 4, 10, or 16"}, status=400)

        if layout not in (4, 10, 16):
            return Response({"detail": "layout must be one of 4, 10, 16"}, status=400)

        ids = request.query_params.get("ids")
        product_id = request.query_params.get("product_id")
        include_primary_only = request.query_params.get("include_primary_only") in ("1", "true", "True")

        qs = ProductBarcode.objects.select_related("product", "uom")

        if ids:
            id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
            if not id_list:
                return Response({"detail": "ids is empty/invalid"}, status=400)
            qs = qs.filter(id__in=id_list).order_by("id")
            filename = "barcodes_selected.pdf"
        elif product_id:
            qs = qs.filter(product_id=product_id).order_by("-isprimary", "id")
            if include_primary_only:
                qs = qs.filter(isprimary=True)
            filename = f"barcodes_product_{product_id}.pdf"
        else:
            return Response({"detail": "Provide either ids=1,2,3 or product_id=123"}, status=400)

        barcodes = list(qs)
        if not barcodes:
            return Response({"detail": "No barcodes found."}, status=404)

        # ensure images exist (your model save() generates them)
        with transaction.atomic():
            for b in barcodes:
                if not b.barcode_image:
                    b.save()

        pdf_file = self._build_pdf(barcodes, layout=layout)
        return FileResponse(pdf_file, as_attachment=True, filename=filename, content_type="application/pdf")

    def _build_pdf(self, barcode_objects, layout: int):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        page_w, page_h = A4

        margin = 18
        gap = 10

        if layout == 4:
            cols, rows = 2, 2
        elif layout == 16:
            cols, rows = 4, 4
        else:  # 10
            cols, rows = 2, 5

        cell_w = (page_w - 2 * margin - (cols - 1) * gap) / cols
        cell_h = (page_h - 2 * margin - (rows - 1) * gap) / rows

        per_page = cols * rows
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

                    # If you want border for labels, uncomment:
                    # c.rect(x, y, cell_w, cell_h, stroke=1, fill=0)

                    if b.barcode_image:
                        img = ImageReader(b.barcode_image.path)

                        pad = 6
                        img_w = cell_w - 2 * pad
                        img_h = cell_h - 2 * pad

                        c.drawImage(
                            img,
                            x + pad,
                            y + pad,
                            width=img_w,
                            height=img_h,
                            preserveAspectRatio=True,
                            anchor="c",
                        )
                    else:
                        c.setFont("Helvetica", 9)
                        c.drawString(x + 8, y + (cell_h / 2), f"Missing image: {b.barcode}")

            c.showPage()

        c.save()
        buffer.seek(0)
        return buffer
