from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


Q8 = Decimal("0.00000001")


def q8(value) -> Decimal:
    return Decimal(value or 0).quantize(Q8, rounding=ROUND_HALF_UP)


def resolve_product_uom(
    *,
    product,
    raw_uom_id: int | str | None,
) -> tuple[object | None, Decimal]:
    """
    Resolve a transaction UOM back to the product base-UOM factor.

    Returns:
      (selected_uom_object_or_none, factor_to_base)

    factor_to_base means:
      base_qty = entered_qty * factor_to_base
    """
    base_uom = getattr(product, "base_uom", None)
    base_uom_id = getattr(product, "base_uom_id", None)
    if not base_uom_id or base_uom is None:
        return None, Decimal("1")

    selected_uom_id = int(raw_uom_id or 0) or int(base_uom_id)
    if selected_uom_id == int(base_uom_id):
        return base_uom, Decimal("1")

    conversions_rel = getattr(product, "uom_conversions", None)
    if hasattr(conversions_rel, "all"):
        conversions = list(conversions_rel.all())
    else:
        conversions = list(conversions_rel or [])

    for conv in conversions:
        factor = Decimal(str(getattr(conv, "factor", 0) or 0))
        if factor <= 0:
            continue
        if int(getattr(conv, "from_uom_id", 0) or 0) == int(base_uom_id) and int(getattr(conv, "to_uom_id", 0) or 0) == selected_uom_id:
            return getattr(conv, "to_uom", None), q8(Decimal("1") / factor)
        if int(getattr(conv, "to_uom_id", 0) or 0) == int(base_uom_id) and int(getattr(conv, "from_uom_id", 0) or 0) == selected_uom_id:
            return getattr(conv, "from_uom", None), q8(factor)

    linked_uom_ids = {int(base_uom_id)}
    for conv in conversions:
        from_uom_id = getattr(conv, "from_uom_id", None)
        to_uom_id = getattr(conv, "to_uom_id", None)
        if from_uom_id is not None:
            linked_uom_ids.add(int(from_uom_id))
        if to_uom_id is not None:
            linked_uom_ids.add(int(to_uom_id))

    if selected_uom_id not in linked_uom_ids:
        raise ValueError("Selected UOM is not valid for this product.")
    raise ValueError("Missing UOM conversion for selected product UOM.")
