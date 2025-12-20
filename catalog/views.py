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
from catalog.serializers import ProductBarcodeManageSerializer





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

        # ✅ Expect root-level array
        if not isinstance(data, list):
            return Response(
                {"detail": "Request body must be a JSON array"},
                status=400
            )

        all_barcodes = []
        final_layout = None
        show_createdon = False

        for idx, job in enumerate(data):
            # -------------------------
            # layout
            # -------------------------
            try:
                layout = int(job.get("layout", 16))
            except Exception:
                return Response(
                    {"detail": f"Invalid layout in item {idx}"},
                    status=400
                )

            if layout not in self.GRID_MAP:
                return Response(
                    {"detail": f"Invalid layout in item {idx}"},
                    status=400
                )

            final_layout = layout  # last one wins (simple rule)

            # -------------------------
            # ids (int OR list)
            # -------------------------
            ids = job.get("ids")
            if ids is None:
                return Response(
                    {"detail": f"'ids' missing in item {idx}"},
                    status=400
                )

            # ✅ normalize ids
            if isinstance(ids, int):
                id_list = [ids]
            elif isinstance(ids, list):
                id_list = ids
            else:
                return Response(
                    {"detail": f"'ids' must be int or list in item {idx}"},
                    status=400
                )

            # -------------------------
            # copies
            # -------------------------
            try:
                copies = int(job.get("copies", 1))
            except Exception:
                return Response(
                    {"detail": f"'copies' must be integer in item {idx}"},
                    status=400
                )

            if copies <= 0:
                return Response(
                    {"detail": f"'copies' must be > 0 in item {idx}"},
                    status=400
                )

            show_createdon = bool(job.get("show_createdon", False))

            qs = ProductBarcode.objects.filter(
                id__in=id_list
            ).select_related("product", "uom")

            barcodes = list(qs)
            if not barcodes:
                continue

            # ensure images exist
            with transaction.atomic():
                for b in barcodes:
                    if not b.barcode_image:
                        b.save()

            # expand copies
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

    # ✅ Sticker-style PDF builder
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

                    # Border (rounded)
                    c.setLineWidth(0.6)
                    c.roundRect(x, y, cell_w, cell_h, corner_radius, stroke=1, fill=0)

                    # Cut guide (dashed)
                    if show_cut_lines:
                        c.saveState()
                        c.setDash(2, 2)
                        c.setLineWidth(0.3)
                        c.roundRect(x + 1.5, y + 1.5, cell_w - 3, cell_h - 3, corner_radius, stroke=1, fill=0)
                        c.restoreState()

                    # PRIMARY badge
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

                    # Barcode image
                    if b.barcode_image:
                        img = ImageReader(b.barcode_image.path)
                        img_x = x + pad
                        img_y = y + text_area_h + pad
                        img_w = cell_w - 2 * pad
                        img_h = img_area_h

                        c.drawImage(
                            img,
                            img_x,
                            img_y,
                            width=img_w,
                            height=img_h,
                            preserveAspectRatio=True,
                            anchor="c",
                        )

                    # Text
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

                    tx_left = x + pad
                    tx_right = x + cell_w - pad
                    tx_width = tx_right - tx_left

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
    """
    Returns supported barcode sticker layouts for UI.
    """
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

        # ✅ Return plain array instead of {"layouts": [...]}
        return Response(layouts)

