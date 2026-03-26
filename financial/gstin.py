from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import ValidationError


STRICT_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
RELAXED_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$")


def financial_relaxed_gstin_enabled() -> bool:
    return bool(
        getattr(
            settings,
            "FINANCIAL_ACCOUNT_ALLOW_RELAXED_GSTIN",
            getattr(settings, "ALLOW_RELAXED_GSTIN_FOR_SANDBOX", False),
        )
    )


def validate_financial_gstin(value: str | None) -> str | None:
    gstin = (value or "").strip().upper()
    if not gstin:
        return None

    regex = RELAXED_GSTIN_RE if financial_relaxed_gstin_enabled() else STRICT_GSTIN_RE
    if not regex.fullmatch(gstin):
        raise ValidationError("Enter a valid GSTIN.")
    return gstin
