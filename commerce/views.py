from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductBarcode

from .models import CommercePromotion, CommercePromotionScope, CommercePromotionSlab
from .serializers import (
    CommerceLineNormalizeSerializer,
    CommercePromotionResponseSerializer,
    CommercePromotionWriteSerializer,
)
from .services import BarcodeResolutionService, CommerceLineNormalizationService


class CommercePromotionListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = int(self.request.query_params.get("entity"))
        subentity_id = self.request.query_params.get("subentity")
        qs = CommercePromotion.objects.filter(entity_id=entity_id).prefetch_related("scopes__product", "scopes__barcode", "slabs")
        if subentity_id in (None, ""):
            return qs.filter(subentity__isnull=True).order_by("code", "id")
        return qs.filter(subentity_id=int(subentity_id)).order_by("code", "id")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return CommercePromotionResponseSerializer
        return CommercePromotionWriteSerializer

    def list(self, request, *args, **kwargs):
        serializer = CommercePromotionResponseSerializer(self.get_queryset(), many=True)
        return Response({"rows": serializer.data})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        promotion = CommercePromotion.objects.create(
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
            code=payload["code"],
            name=payload["name"],
            promotion_type=payload["promotion_type"],
            valid_from=payload.get("valid_from"),
            valid_to=payload.get("valid_to"),
            is_active=payload.get("is_active", True),
        )
        scope_rows = []
        for row in payload["scopes"]:
            product = get_object_or_404(Product, id=row["product"], entity_id=promotion.entity_id)
            barcode_id = row.get("barcode")
            if barcode_id:
                get_object_or_404(ProductBarcode, id=barcode_id, product_id=product.id)
            scope_rows.append(CommercePromotionScope(promotion=promotion, product=product, barcode_id=barcode_id))
        slab_rows = []
        for idx, row in enumerate(payload["slabs"], start=1):
            slab_rows.append(
                CommercePromotionSlab(
                    promotion=promotion,
                    sequence_no=row.get("sequence_no") or idx,
                    min_qty=row["min_qty"],
                    free_qty=row.get("free_qty") or 0,
                    discount_percent=row.get("discount_percent") or 0,
                    discount_amount=row.get("discount_amount") or 0,
                )
            )
        CommercePromotionScope.objects.bulk_create(scope_rows)
        CommercePromotionSlab.objects.bulk_create(slab_rows)
        promotion.refresh_from_db()
        return Response(CommercePromotionResponseSerializer(promotion).data, status=status.HTTP_201_CREATED)


class CommerceMetaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "promotion_types": [
                    {"value": value, "label": label}
                    for value, label in CommercePromotion.PromotionType.choices
                ],
                "costing_note": "Pack, price, and barcode data are resolved from catalog product/barcode masters.",
            }
        )


class CommercePromotionDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CommercePromotion.objects.prefetch_related("scopes__product", "scopes__barcode", "slabs")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return CommercePromotionResponseSerializer
        return CommercePromotionWriteSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        promotion = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        promotion.subentity_id = payload.get("subentity")
        promotion.code = payload["code"]
        promotion.name = payload["name"]
        promotion.promotion_type = payload["promotion_type"]
        promotion.valid_from = payload.get("valid_from")
        promotion.valid_to = payload.get("valid_to")
        promotion.is_active = payload.get("is_active", True)
        promotion.save()
        promotion.scopes.all().delete()
        promotion.slabs.all().delete()
        scope_rows = []
        for row in payload["scopes"]:
            product = get_object_or_404(Product, id=row["product"], entity_id=promotion.entity_id)
            barcode_id = row.get("barcode")
            if barcode_id:
                get_object_or_404(ProductBarcode, id=barcode_id, product_id=product.id)
            scope_rows.append(CommercePromotionScope(promotion=promotion, product=product, barcode_id=barcode_id))
        slab_rows = []
        for idx, row in enumerate(payload["slabs"], start=1):
            slab_rows.append(
                CommercePromotionSlab(
                    promotion=promotion,
                    sequence_no=row.get("sequence_no") or idx,
                    min_qty=row["min_qty"],
                    free_qty=row.get("free_qty") or 0,
                    discount_percent=row.get("discount_percent") or 0,
                    discount_amount=row.get("discount_amount") or 0,
                )
            )
        CommercePromotionScope.objects.bulk_create(scope_rows)
        CommercePromotionSlab.objects.bulk_create(slab_rows)
        promotion.refresh_from_db()
        return Response(CommercePromotionResponseSerializer(promotion).data)


class CommerceBarcodeResolveAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity = request.query_params.get("entity")
        barcode = request.query_params.get("code")
        if not entity or not barcode:
            return Response({"detail": "Query params ?entity=<id>&code=<barcode> are required."}, status=400)
        resolved = BarcodeResolutionService.resolve(
            entity_id=int(entity),
            code=barcode,
            as_of_date=request.query_params.get("as_of_date"),
        )
        return Response(
            {
                "product_id": resolved.product_id,
                "product_name": resolved.product_name,
                "sku": resolved.sku,
                "barcode_id": resolved.barcode_id,
                "barcode": resolved.barcode,
                "uom_id": resolved.uom_id,
                "uom_code": resolved.uom_code,
                "pack_size": resolved.pack_size,
                "selling_price": float(resolved.selling_price) if resolved.selling_price is not None else None,
                "mrp": float(resolved.mrp) if resolved.mrp is not None else None,
                "gst": resolved.default_gst,
            }
        )


class CommerceLineNormalizeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CommerceLineNormalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        normalized = CommerceLineNormalizationService.normalize_line(
            entity_id=payload["entity"],
            subentity_id=payload.get("subentity"),
            product_id=payload.get("product_id"),
            barcode=payload.get("barcode"),
            barcode_id=payload.get("barcode_id"),
            qty=payload["qty"],
            manual_discount_percent=payload.get("manual_discount_percent"),
            manual_discount_amount=payload.get("manual_discount_amount"),
            as_of_date=payload.get("as_of_date"),
        )
        return Response(normalized)
