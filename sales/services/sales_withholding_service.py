from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from withholding.models import WithholdingTaxType
from withholding.services import (
    WithholdingResolver,
    WithholdingResult,
    compute_base_amount_excl_gst,
    compute_base_amount_incl_gst,
    q2,
    ZERO2,
)

CUTOFF_DISABLE_206C_1H = date(2025, 4, 1)

class SalesWithholdingService:
    @staticmethod
    def compute_tcs(*, header, customer_account_id: int, invoice_date: date, taxable_total, gross_total) -> WithholdingResult:
        section = getattr(header, "tcs_section", None)
        if not section:
            return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "No TCS section")

        # DO NOT clear 206C(1) here; only 206C(1H) is disabled.
        if section.section_code and section.section_code.strip().upper() in {"206C(1H)", "206C1H"}:
            if invoice_date >= CUTOFF_DISABLE_206C_1H:
                return WithholdingResult(True, None, Decimal("0.0000"), ZERO2, ZERO2, "206C(1H) disabled from 2025-04-01")

        # base rule (most cases excl GST)
        base = q2(taxable_total or ZERO2)
        rate = q2(getattr(section, "rate_default", Decimal("0.0000")))

        if base <= ZERO2 or rate <= Decimal("0.0000"):
            return WithholdingResult(True, section, rate, base, ZERO2, None)

        amt = q2((base * rate) / Decimal("100.0"))
        return WithholdingResult(True, section, rate, base, amt, None)