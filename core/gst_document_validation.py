from __future__ import annotations

import re


GST_CLASSIFICATION_RE = re.compile(r"^\d+$")


def gst_classification_error(code: object, *, is_service: bool) -> str | None:
    """Return a user-facing HSN/SAC error, or None when the code is valid."""
    normalized = str(code or "").strip()
    label = "SAC" if is_service else "HSN"

    if not normalized:
        return f"{label} is required for taxable {'service' if is_service else 'goods'} lines."
    if not GST_CLASSIFICATION_RE.fullmatch(normalized):
        return f"{label} must contain digits only."
    if is_service and len(normalized) != 6:
        return "SAC must contain exactly 6 digits."
    if not is_service and len(normalized) not in {4, 6, 8}:
        return "HSN must contain 4, 6, or 8 digits."
    return None
