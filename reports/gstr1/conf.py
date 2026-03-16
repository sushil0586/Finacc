"""
Centralized configuration access for GSTR-1 business rules.

Defaults preserve existing behavior. Override via Django settings:
- GSTR1_B2CL_THRESHOLD: Decimal-compatible (string/number); default 250000.00
- GSTR1_EXPORT_POS: string GST state code for exports; default "96"
- GSTR1_ENABLE_GSTIN_CHECKSUM: bool; default False
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django.conf import settings

DEFAULT_B2CL_THRESHOLD = Decimal("250000.00")
DEFAULT_EXPORT_POS = "96"
DEFAULT_ENABLE_GSTIN_CHECKSUM = False


def _to_decimal(value, default):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def b2cl_threshold() -> Decimal:
    return _to_decimal(getattr(settings, "GSTR1_B2CL_THRESHOLD", DEFAULT_B2CL_THRESHOLD), DEFAULT_B2CL_THRESHOLD)


def export_pos_code() -> str:
    code = str(getattr(settings, "GSTR1_EXPORT_POS", DEFAULT_EXPORT_POS)).strip()
    return code or DEFAULT_EXPORT_POS


def enable_gstin_checksum() -> bool:
    return bool(getattr(settings, "GSTR1_ENABLE_GSTIN_CHECKSUM", DEFAULT_ENABLE_GSTIN_CHECKSUM))
