from __future__ import annotations

from datetime import date, datetime
from typing import Any


INTERNAL_EXPIRY_LOT_PREFIX = "EXP"


def normalize_lot_batch_number(value: Any) -> str:
    return str(value or "").strip()


def normalize_lot_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_internal_expiry_lot_code(*, product_id: int | None, expiry_date: Any) -> str:
    normalized_expiry = normalize_lot_date(expiry_date)
    if not normalized_expiry or int(product_id or 0) <= 0:
        return ""
    return f"{INTERNAL_EXPIRY_LOT_PREFIX}-{int(product_id)}-{normalized_expiry.strftime('%Y%m%d')}"


def resolve_tracked_lot_number(*, product: Any, batch_number: Any = None, expiry_date: Any = None) -> str:
    explicit_batch = normalize_lot_batch_number(batch_number)
    if explicit_batch:
        return explicit_batch
    if not product:
        return ""
    if bool(getattr(product, "is_expiry_tracked", False)) and not bool(getattr(product, "is_batch_managed", False)):
        return build_internal_expiry_lot_code(
            product_id=getattr(product, "id", None),
            expiry_date=expiry_date,
        )
    return ""


def is_internal_expiry_lot(batch_number: Any, *, product_id: int | None = None) -> bool:
    normalized = normalize_lot_batch_number(batch_number)
    if not normalized:
        return False
    if product_id and normalized.startswith(f"{INTERNAL_EXPIRY_LOT_PREFIX}-{int(product_id)}-"):
        return True
    return normalized.startswith(f"{INTERNAL_EXPIRY_LOT_PREFIX}-")
