from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from catalog.models import Product, ProductBarcode
from catalog.transaction_products import TransactionProductCatalogService

from .models import CommercePromotion, CommercePromotionScope, CommercePromotionSlab


def _q4(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0000"))


def _q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _normalize_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    parsed = parse_date(str(value))
    if parsed:
        return parsed
    raise ValidationError({"as_of_date": "Use YYYY-MM-DD format."})


@dataclass
class ResolvedBarcodeResult:
    product_id: int
    product_name: str
    sku: str
    barcode_id: int
    barcode: str
    uom_id: int | None
    uom_code: str | None
    pack_size: int | None
    selling_price: Decimal | None
    mrp: Decimal | None
    default_gst: dict | None


class BarcodeResolutionService:
    @staticmethod
    def resolve(*, entity_id: int, code: str, as_of_date=None) -> ResolvedBarcodeResult:
        barcode_qs = (
            ProductBarcode.objects
            .select_related("product", "uom")
            .filter(product__entity_id=entity_id, barcode=(code or "").strip())
        )
        barcode_count = barcode_qs.count()
        if barcode_count == 0:
            raise ValidationError({"barcode": "Barcode not found for the selected entity."})
        if barcode_count > 1:
            raise ValidationError({"barcode": "Duplicate barcode found in this entity. Please fix the master data."})

        barcode = barcode_qs.first()

        product_payload = TransactionProductCatalogService.get_product(
            entity_id=entity_id,
            product_id=barcode.product_id,
            as_of_date=_normalize_date(as_of_date),
        )
        default_gst = product_payload.get("default_gst")
        selling_price = barcode.selling_price
        if selling_price is None:
            default_barcode = product_payload.get("default_barcode") or {}
            selling_price = Decimal(str(default_barcode.get("selling_price") or product_payload.get("salesprice") or 0)) if (default_barcode.get("selling_price") or product_payload.get("salesprice")) is not None else None

        mrp = barcode.mrp
        if mrp is None:
            default_barcode = product_payload.get("default_barcode") or {}
            mrp = Decimal(str(default_barcode.get("mrp") or product_payload.get("mrp") or 0)) if (default_barcode.get("mrp") or product_payload.get("mrp")) is not None else None

        return ResolvedBarcodeResult(
            product_id=barcode.product_id,
            product_name=barcode.product.productname,
            sku=barcode.product.sku or "",
            barcode_id=barcode.id,
            barcode=barcode.barcode,
            uom_id=barcode.uom_id,
            uom_code=getattr(barcode.uom, "code", None),
            pack_size=barcode.pack_size,
            selling_price=selling_price,
            mrp=mrp,
            default_gst=default_gst,
        )


@dataclass
class AppliedPromotionResult:
    promotion_id: int | None
    promotion_code: str | None
    free_qty: Decimal
    discount_percent: Decimal
    discount_amount: Decimal


class PromotionEngineService:
    @staticmethod
    def resolve_same_item_slab(
        *,
        entity_id: int,
        subentity_id: int | None,
        product_id: int,
        barcode_id: int | None,
        qty,
        as_of_date=None,
    ) -> AppliedPromotionResult:
        qty = _q4(qty)
        if qty <= Decimal("0.0000"):
            return AppliedPromotionResult(None, None, Decimal("0.0000"), Decimal("0.0000"), Decimal("0.00"))

        on_date = _normalize_date(as_of_date)
        promo_qs = (
            CommercePromotion.objects
            .filter(
                entity_id=entity_id,
                promotion_type=CommercePromotion.PromotionType.SAME_ITEM_SLAB,
                is_active=True,
            )
            .prefetch_related(
                Prefetch("scopes", queryset=CommercePromotionScope.objects.select_related("product", "barcode")),
                Prefetch("slabs", queryset=CommercePromotionSlab.objects.order_by("-min_qty", "sequence_no")),
            )
        )
        promo_qs = promo_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
        if on_date:
            promo_qs = promo_qs.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=on_date), Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))

        best_result = AppliedPromotionResult(None, None, Decimal("0.0000"), Decimal("0.0000"), Decimal("0.00"))
        best_rank = Decimal("-1")
        for promotion in promo_qs:
            matched_scope = None
            for scope in promotion.scopes.all():
                if scope.product_id != product_id:
                    continue
                if scope.barcode_id and barcode_id and scope.barcode_id != barcode_id:
                    continue
                if scope.barcode_id and not barcode_id:
                    continue
                matched_scope = scope
                break
            if matched_scope is None:
                continue

            slab = next((row for row in promotion.slabs.all() if qty >= _q4(row.min_qty)), None)
            if slab is None:
                continue

            current_rank = _q4(slab.min_qty)
            if current_rank > best_rank:
                best_rank = current_rank
                best_result = AppliedPromotionResult(
                    promotion_id=promotion.id,
                    promotion_code=promotion.code,
                    free_qty=_q4(slab.free_qty),
                    discount_percent=_q4(slab.discount_percent),
                    discount_amount=_q2(slab.discount_amount),
                )

        return best_result


class CommerceLineNormalizationService:
    @staticmethod
    def normalize_line(
        *,
        entity_id: int,
        subentity_id: int | None,
        qty,
        product_id: int | None = None,
        barcode: str | None = None,
        barcode_id: int | None = None,
        manual_discount_percent=None,
        manual_discount_amount=None,
        as_of_date=None,
    ) -> dict:
        qty = _q4(qty)
        if qty <= Decimal("0.0000"):
            raise ValidationError({"qty": "Quantity must be greater than zero."})

        resolved = None
        if barcode:
            resolved = BarcodeResolutionService.resolve(entity_id=entity_id, code=barcode, as_of_date=as_of_date)
            product_id = resolved.product_id
            barcode_id = resolved.barcode_id
        elif barcode_id:
            barcode_obj = ProductBarcode.objects.select_related("uom", "product").filter(product__entity_id=entity_id, id=barcode_id).first()
            if barcode_obj is None:
                raise ValidationError({"barcode_id": "Barcode not found for the selected entity."})
            resolved = BarcodeResolutionService.resolve(entity_id=entity_id, code=barcode_obj.barcode, as_of_date=as_of_date)
            product_id = resolved.product_id
        elif product_id:
            product_payload = TransactionProductCatalogService.get_product(
                entity_id=entity_id,
                product_id=product_id,
                as_of_date=_normalize_date(as_of_date),
            )
            default_barcode = product_payload.get("default_barcode") or {}
            resolved = ResolvedBarcodeResult(
                product_id=product_id,
                product_name=product_payload.get("productname") or "",
                sku=product_payload.get("sku") or "",
                barcode_id=default_barcode.get("id"),
                barcode=default_barcode.get("barcode") or "",
                uom_id=default_barcode.get("uom_id") or product_payload.get("base_uom_id"),
                uom_code=default_barcode.get("uom_code") or product_payload.get("base_uom_code"),
                pack_size=default_barcode.get("pack_size"),
                selling_price=Decimal(str(default_barcode.get("selling_price") or product_payload.get("salesprice") or 0)),
                mrp=Decimal(str(default_barcode.get("mrp") or product_payload.get("mrp") or 0)),
                default_gst=product_payload.get("default_gst"),
            )
        else:
            raise ValidationError({"line": "Provide product_id, barcode, or barcode_id."})

        manual_discount_percent = _q4(manual_discount_percent)
        manual_discount_amount = _q2(manual_discount_amount)
        promotion = AppliedPromotionResult(None, None, Decimal("0.0000"), Decimal("0.0000"), Decimal("0.00"))
        if manual_discount_percent <= Decimal("0.0000") and manual_discount_amount <= Decimal("0.00"):
            promotion = PromotionEngineService.resolve_same_item_slab(
                entity_id=entity_id,
                subentity_id=subentity_id,
                product_id=resolved.product_id,
                barcode_id=resolved.barcode_id,
                qty=qty,
                as_of_date=as_of_date,
            )

        rate = _q2(resolved.selling_price or 0)
        gross_value = _q2(qty * rate)
        auto_discount_value = _q2(gross_value * promotion.discount_percent / Decimal("100.0000")) + promotion.discount_amount
        applied_discount_percent = manual_discount_percent if manual_discount_percent > Decimal("0.0000") else promotion.discount_percent
        applied_discount_amount = manual_discount_amount if manual_discount_amount > Decimal("0.00") else auto_discount_value
        taxable_value = _q2(gross_value - applied_discount_amount)

        return {
            "product_id": resolved.product_id,
            "product_name": resolved.product_name,
            "sku": resolved.sku,
            "barcode_id": resolved.barcode_id,
            "barcode": resolved.barcode,
            "uom_id": resolved.uom_id,
            "uom_code": resolved.uom_code,
            "pack_size": resolved.pack_size,
            "qty": float(qty),
            "free_qty": float(promotion.free_qty),
            "stock_issue_qty": float(_q4(qty + promotion.free_qty)),
            "rate": float(rate),
            "gross_value": float(gross_value),
            "discount_percent": float(applied_discount_percent),
            "discount_amount": float(applied_discount_amount),
            "taxable_value": float(taxable_value),
            "promotion_id": promotion.promotion_id,
            "promotion_code": promotion.promotion_code,
            "mrp": float(_q2(resolved.mrp or 0)) if resolved.mrp is not None else None,
            "gst": resolved.default_gst,
        }
