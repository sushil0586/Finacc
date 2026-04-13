from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch, Q

from .models import Product, ProductBarcode, ProductGstRate, ProductPrice, ProductUomConversion


class TransactionProductCatalogService:
    """
    Transaction-facing product catalog read service.

    This keeps product/UOM/price/barcode shaping in one place so
    purchase/sales line-entry screens do not need to reconstruct
    product-specific UOM rules from multiple endpoints.
    """

    @staticmethod
    def _decimal_str(value, default: str | None = None) -> str | None:
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _taxability_from_hsn(hsn_obj) -> int:
        """
        Align with purchase/sales taxability semantics:
        1 TAXABLE, 2 EXEMPT, 3 NIL_RATED, 4 NON_GST
        """
        if not hsn_obj:
            return 1
        if getattr(hsn_obj, "is_exempt", False):
            return 2
        if getattr(hsn_obj, "is_nil_rated", False):
            return 3
        if getattr(hsn_obj, "is_non_gst", False):
            return 4
        return 1

    @staticmethod
    def _normalize_limit(limit):
        if limit in (None, ""):
            return None
        try:
            limit_int = int(limit)
        except (TypeError, ValueError):
            return 50
        return max(1, min(limit_int, 200))

    @staticmethod
    def _normalize_offset(offset):
        try:
            return max(0, int(offset or 0))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _product_queryset(cls, *, entity_id: int, search: str = "", as_of_date=None):
        gst_qs = (
            ProductGstRate.objects.select_related("hsn")
            .filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=as_of_date) if as_of_date else Q(),
                Q(valid_to__isnull=True) | Q(valid_to__gte=as_of_date) if as_of_date else Q(),
            )
            .order_by("-isdefault", "-valid_from", "-id")
        )
        price_qs = (
            ProductPrice.objects.select_related("pricelist", "uom")
            .filter(
                Q(effective_from__lte=as_of_date) if as_of_date else Q(),
                Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date) if as_of_date else Q(),
            )
            .order_by("uom_id", "-pricelist__isdefault", "-effective_from", "-id")
        )
        barcode_qs = ProductBarcode.objects.select_related("uom").order_by("-isprimary", "uom__code", "pack_size", "id")
        conversion_qs = ProductUomConversion.objects.select_related("from_uom", "to_uom").order_by("from_uom__code", "to_uom__code", "id")

        qs = (
            Product.objects.filter(entity_id=entity_id, isactive=True)
            .select_related("base_uom")
            .prefetch_related(
                Prefetch("gst_rates", queryset=gst_qs, to_attr="transaction_gst_rates"),
                Prefetch("prices", queryset=price_qs, to_attr="transaction_prices"),
                Prefetch("barcode_details", queryset=barcode_qs, to_attr="transaction_barcodes"),
                Prefetch("uom_conversions", queryset=conversion_qs, to_attr="transaction_uom_conversions"),
            )
            .order_by("productname", "id")
        )

        if search:
            qs = qs.filter(Q(productname__icontains=search) | Q(sku__icontains=search))
        return qs

    @classmethod
    def _best_price_map(cls, product) -> dict[int, ProductPrice]:
        best_by_uom: dict[int, ProductPrice] = {}
        for price in getattr(product, "transaction_prices", []) or []:
            if price.uom_id not in best_by_uom:
                best_by_uom[price.uom_id] = price
        return best_by_uom

    @classmethod
    def _best_gst(cls, product):
        gst_rows = getattr(product, "transaction_gst_rates", []) or []
        return gst_rows[0] if gst_rows else None

    @classmethod
    def _uom_payload(cls, product) -> tuple[list[dict], list[dict]]:
        base_uom = getattr(product, "base_uom", None)
        base_uom_id = getattr(product, "base_uom_id", None)
        best_prices = cls._best_price_map(product)

        uom_options: dict[int, dict] = {}

        def ensure_option(uom_obj, *, is_base: bool = False):
            if uom_obj is None:
                return None
            option = uom_options.get(uom_obj.id)
            if option is None:
                option = {
                    "uom_id": uom_obj.id,
                    "uom_code": uom_obj.code,
                    "uqc": getattr(uom_obj, "uqc", None),
                    "description": getattr(uom_obj, "description", ""),
                    "is_base": is_base,
                    "factor_to_base": "1.0000" if is_base else None,
                    "factor_from_base": "1.0000" if is_base else None,
                    "purchase_rate": None,
                    "selling_price": None,
                    "mrp": None,
                    "barcode_options": [],
                }
                uom_options[uom_obj.id] = option
            elif is_base:
                option["is_base"] = True
                option["factor_to_base"] = "1.0000"
                option["factor_from_base"] = "1.0000"
            return option

        if base_uom_id and base_uom:
            ensure_option(base_uom, is_base=True)

        conversion_rows = []
        for conv in getattr(product, "transaction_uom_conversions", []) or []:
            from_option = ensure_option(conv.from_uom, is_base=conv.from_uom_id == base_uom_id)
            to_option = ensure_option(conv.to_uom, is_base=conv.to_uom_id == base_uom_id)

            factor_str = cls._decimal_str(conv.factor, "0.0000")
            conversion_rows.append(
                {
                    "id": conv.id,
                    "from_uom_id": conv.from_uom_id,
                    "from_uom_code": getattr(conv.from_uom, "code", None),
                    "to_uom_id": conv.to_uom_id,
                    "to_uom_code": getattr(conv.to_uom, "code", None),
                    "factor": factor_str,
                }
            )

            if conv.from_uom_id == base_uom_id and to_option is not None:
                to_option["factor_from_base"] = factor_str
                try:
                    factor_decimal = Decimal(conv.factor)
                    if factor_decimal:
                        to_option["factor_to_base"] = cls._decimal_str((Decimal("1") / factor_decimal).quantize(Decimal("0.0001")))
                except (InvalidOperation, ZeroDivisionError, TypeError):
                    pass
            elif conv.to_uom_id == base_uom_id and from_option is not None:
                from_option["factor_to_base"] = factor_str
                try:
                    factor_decimal = Decimal(conv.factor)
                    if factor_decimal:
                        from_option["factor_from_base"] = cls._decimal_str((Decimal("1") / factor_decimal).quantize(Decimal("0.0001")))
                except (InvalidOperation, ZeroDivisionError, TypeError):
                    pass

        for uom_id, price in best_prices.items():
            option = uom_options.get(uom_id)
            if option is None and getattr(price, "uom", None) is not None:
                option = ensure_option(price.uom, is_base=price.uom_id == base_uom_id)
            if option is not None:
                option["purchase_rate"] = cls._decimal_str(price.purchase_rate)
                option["selling_price"] = cls._decimal_str(price.selling_price)
                option["mrp"] = cls._decimal_str(price.mrp)

        for barcode in getattr(product, "transaction_barcodes", []) or []:
            option = ensure_option(barcode.uom, is_base=barcode.uom_id == base_uom_id)
            barcode_row = {
                "id": barcode.id,
                "barcode": barcode.barcode,
                "uom_id": barcode.uom_id,
                "uom_code": getattr(barcode.uom, "code", None),
                "pack_size": barcode.pack_size,
                "isprimary": barcode.isprimary,
                "mrp": cls._decimal_str(barcode.mrp),
                "selling_price": cls._decimal_str(barcode.selling_price),
                "barcode_image_url": getattr(barcode.barcode_image, "url", None) if getattr(barcode, "barcode_image", None) else None,
            }
            if option is not None:
                option["barcode_options"].append(barcode_row)

        # Ensure a base-only option still gets through even if no conversion rows exist
        if base_uom and base_uom_id and base_uom_id not in uom_options:
            ensure_option(base_uom, is_base=True)

        options = sorted(
            uom_options.values(),
            key=lambda item: (0 if item["is_base"] else 1, item["uom_code"] or "", item["uom_id"]),
        )
        return options, conversion_rows

    @classmethod
    def _price_options(cls, product) -> list[dict]:
        price_rows = []
        for price in cls._best_price_map(product).values():
            price_rows.append(
                {
                    "uom_id": price.uom_id,
                    "uom_code": getattr(price.uom, "code", None),
                    "pricelist_id": price.pricelist_id,
                    "pricelist_name": getattr(price.pricelist, "name", None),
                    "is_default_pricelist": getattr(price.pricelist, "isdefault", False),
                    "purchase_rate": cls._decimal_str(price.purchase_rate),
                    "purchase_rate_less_percent": cls._decimal_str(price.purchase_rate_less_percent),
                    "mrp": cls._decimal_str(price.mrp),
                    "mrp_less_percent": cls._decimal_str(price.mrp_less_percent),
                    "selling_price": cls._decimal_str(price.selling_price),
                    "effective_from": getattr(price, "effective_from", None),
                    "effective_to": getattr(price, "effective_to", None),
                }
            )
        return sorted(price_rows, key=lambda row: (row["uom_code"] or "", row["pricelist_name"] or ""))

    @classmethod
    def serialize_product(cls, product) -> dict:
        best_gst = cls._best_gst(product)
        hsn = getattr(best_gst, "hsn", None)
        taxability = cls._taxability_from_hsn(hsn)
        if taxability in (2, 3, 4):
            is_itc_eligible = False
            itc_reason = "No GST / no ITC"
        else:
            is_itc_eligible = bool(getattr(product, "is_itc_eligible", True))
            itc_reason = getattr(product, "itc_block_reason", None)

        uom_options, uom_conversions = cls._uom_payload(product)
        price_options = cls._price_options(product)
        base_price = next((row for row in price_options if row["uom_id"] == getattr(product, "base_uom_id", None)), None)
        if base_price is None and price_options:
            base_price = price_options[0]

        default_gst = None
        if best_gst is not None:
            default_gst = {
                "hsn_id": best_gst.hsn_id,
                "hsn_code": getattr(hsn, "code", None),
                "gst_type": best_gst.gst_type,
                "gst_rate": cls._decimal_str(best_gst.gst_rate, "0.00"),
                "cgst": cls._decimal_str(best_gst.cgst, "0.00"),
                "sgst": cls._decimal_str(best_gst.sgst, "0.00"),
                "igst": cls._decimal_str(best_gst.igst, "0.00"),
                "cess": cls._decimal_str(best_gst.cess, "0.00"),
                "cess_type": best_gst.cess_type,
                "cess_specific_amount": cls._decimal_str(best_gst.cess_specific_amount),
            }

        barcode_options = []
        for option in uom_options:
            barcode_options.extend(option.get("barcode_options", []))
        barcode_options.sort(key=lambda row: (0 if row["isprimary"] else 1, row["uom_code"] or "", row["pack_size"] or 0, row["id"]))

        return {
            "id": product.id,
            "productname": product.productname,
            "productdesc": product.productdesc,
            "sku": product.sku,
            "is_service": product.is_service,
            "is_pieces": product.is_pieces,
            "is_batch_managed": bool(getattr(product, "is_batch_managed", False)),
            "is_expiry_tracked": bool(getattr(product, "is_expiry_tracked", False)),
            "shelf_life_days": getattr(product, "shelf_life_days", None),
            "expiry_warning_days": getattr(product, "expiry_warning_days", None),
            "base_uom_id": getattr(product, "base_uom_id", None),
            "base_uom_code": getattr(getattr(product, "base_uom", None), "code", None),
            "uom_id": getattr(product, "base_uom_id", None),
            "uom": getattr(getattr(product, "base_uom", None), "code", None),
            "uom_options": uom_options,
            "uom_conversions": uom_conversions,
            "price_options": price_options,
            "barcode_options": barcode_options,
            "default_gst": default_gst,
            "hsn_id": getattr(best_gst, "hsn_id", None) if best_gst is not None else None,
            "hsn": getattr(hsn, "code", None),
            "hsn_is_service": getattr(hsn, "is_service", None) if hsn is not None else None,
            "taxability": taxability,
            "cgst": cls._decimal_str(getattr(best_gst, "cgst", None)),
            "sgst": cls._decimal_str(getattr(best_gst, "sgst", None)),
            "igst": cls._decimal_str(getattr(best_gst, "igst", None)),
            "gst_rate": cls._decimal_str(getattr(best_gst, "gst_rate", None)),
            "cess": cls._decimal_str(getattr(best_gst, "cess", None)),
            "cesstype": getattr(best_gst, "cess_type", None) if best_gst is not None else None,
            "cess_specific_amount": cls._decimal_str(getattr(best_gst, "cess_specific_amount", None)),
            "is_itc_eligible": is_itc_eligible,
            "itc_block_reason": itc_reason,
            "mrp": base_price["mrp"] if base_price else None,
            "salesprice": base_price["selling_price"] if base_price else None,
            "purchaserate": base_price["purchase_rate"] if base_price else None,
        }

    @classmethod
    def list_products(cls, *, entity_id: int, search: str = "", as_of_date=None, limit=None, offset=0):
        qs = cls._product_queryset(entity_id=entity_id, search=search, as_of_date=as_of_date)
        total = qs.count()
        limit_value = cls._normalize_limit(limit)
        offset_value = cls._normalize_offset(offset)

        if limit_value is None:
            products = list(qs)
        else:
            products = list(qs[offset_value : offset_value + limit_value])

        return {
            "count": total,
            "items": [cls.serialize_product(product) for product in products],
        }

    @classmethod
    def get_product(cls, *, entity_id: int, product_id: int, as_of_date=None):
        product = cls._product_queryset(entity_id=entity_id, as_of_date=as_of_date).get(pk=product_id)
        return cls.serialize_product(product)
