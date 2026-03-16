"""
GSTIN validation helpers.

- Format: 15 uppercase alphanumerics, regex-validated.
- Checksum (optional): implements official base36 weighted checksum on the first 14 chars.
"""

from __future__ import annotations

import re

GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
BASE36_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE36_MAP = {ch: idx for idx, ch in enumerate(BASE36_CHARS)}


def format_valid(gstin: str | None) -> bool:
    return bool(gstin) and bool(GSTIN_RE.match(gstin))


def checksum_valid(gstin: str | None) -> bool:
    if not format_valid(gstin):
        return False
    # Compute checksum on first 14 chars
    factors = [1, 2]
    total = 0
    for idx, ch in enumerate(gstin[:14]):
        val = BASE36_MAP.get(ch, -1)
        if val < 0:
            return False
        factor = factors[idx % 2]
        product = val * factor
        # Base36 sum of digits of product
        total += (product // 36) + (product % 36)
    check_code = (36 - (total % 36)) % 36
    return BASE36_CHARS[check_code] == gstin[14]


def is_valid(gstin: str | None, *, checksum_enabled: bool = False) -> bool:
    if not format_valid(gstin):
        return False
    if not checksum_enabled:
        return True
    return checksum_valid(gstin)
