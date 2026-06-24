from __future__ import annotations

from .models import Product, ProductGstRate

TAXABILITY_TAXABLE = 1
TAXABILITY_EXEMPT = 2
TAXABILITY_NIL_RATED = 3
TAXABILITY_NON_GST = 4


def taxability_from_hsn(hsn_obj) -> int:
    if not hsn_obj:
        return TAXABILITY_TAXABLE
    if getattr(hsn_obj, "is_exempt", False):
        return TAXABILITY_EXEMPT
    if getattr(hsn_obj, "is_nil_rated", False):
        return TAXABILITY_NIL_RATED
    if getattr(hsn_obj, "is_non_gst", False):
        return TAXABILITY_NON_GST
    return TAXABILITY_TAXABLE


def resolve_product_default_taxability(*, product=None, product_id=None, fallback: int = TAXABILITY_TAXABLE) -> int:
    explicit = getattr(product, "default_taxability", None)
    if explicit not in (None, ""):
        return int(explicit)

    if product is None and product_id:
        product = Product.objects.filter(pk=int(product_id)).only("id", "default_taxability").first()
        explicit = getattr(product, "default_taxability", None) if product is not None else None
        if explicit not in (None, ""):
            return int(explicit)

    best_gst = None
    prefetched_rows = getattr(product, "transaction_gst_rates", None)
    if prefetched_rows:
        best_gst = prefetched_rows[0]
    elif product is not None and getattr(product, "pk", None):
        best_gst = (
            ProductGstRate.objects.select_related("hsn")
            .filter(product_id=product.pk)
            .order_by("-isdefault", "-valid_from", "-id")
            .first()
        )

    hsn = getattr(best_gst, "hsn", None) if best_gst is not None else None
    return taxability_from_hsn(hsn) if hsn is not None else int(fallback)
