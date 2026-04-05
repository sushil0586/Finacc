from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from withholding.models import WithholdingBaseRule
from withholding.services import (
    _apply_section_threshold,
    WithholdingResolver,
    WithholdingResult,
    q2,
    ZERO2,
)

Q4 = Decimal("0.0001")


def q4(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.0000")

class SalesWithholdingService:
    @staticmethod
    def compute_tcs(*, header, customer_account_id: int, invoice_date: date, taxable_total, gross_total) -> WithholdingResult:
        cfg = None
        if getattr(header, "entity_id", None) and getattr(header, "entityfinid_id", None):
            cfg = WithholdingResolver.get_entity_config(
                entity_id=header.entity_id,
                entityfin_id=header.entityfinid_id,
                subentity_id=getattr(header, "subentity_id", None),
                doc_date=invoice_date,
            )
        if cfg and not bool(getattr(cfg, "enable_tcs", True)):
            return WithholdingResult(
                False,
                None,
                Decimal("0.0000"),
                ZERO2,
                ZERO2,
                "TCS disabled in entity config",
                "DISABLED",
            )

        section = getattr(header, "tcs_section", None)
        if not section:
            return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "No TCS section", "NO_SECTION")

        if (
            cfg
            and section.section_code
            and section.section_code.strip().upper() in {"206C(1H)", "206C1H"}
            and not bool(getattr(cfg, "apply_tcs_206c1h", False))
        ):
            return WithholdingResult(
                True,
                section,
                Decimal("0.0000"),
                ZERO2,
                ZERO2,
                "206C(1H) disabled in withholding configuration",
                "DISABLED_206C_1H_BY_CONFIG",
            )

        if int(getattr(section, "base_rule", 0) or 0) not in {
            int(WithholdingBaseRule.INVOICE_VALUE_EXCL_GST),
            int(WithholdingBaseRule.INVOICE_VALUE_INCL_GST),
        }:
            return WithholdingResult(
                True,
                section,
                Decimal("0.0000"),
                ZERO2,
                ZERO2,
                "Section base rule is not invoice-based for sales invoice context.",
                "NOT_APPLICABLE_BASE_RULE_CONTEXT",
            )

        # base rule (most cases excl GST)
        base = q2(taxable_total or ZERO2)
        effective_base, threshold_reason, threshold_reason_code = _apply_section_threshold(
            section=section,
            base_amount=base,
            doc_date=invoice_date,
            entity_id=header.entity_id,
            entityfin_id=getattr(header, "entityfinid_id", None),
            subentity_id=getattr(header, "subentity_id", None),
            party_account_id=customer_account_id,
            exclude_doc=("sales", "invoice", int(getattr(header, "id", 0) or 0)) if getattr(header, "id", None) else None,
        )
        rate = q4(getattr(section, "rate_default", Decimal("0.0000")))

        if effective_base <= ZERO2 or rate <= Decimal("0.0000"):
            return WithholdingResult(
                True,
                section,
                rate,
                q2(effective_base),
                ZERO2,
                threshold_reason,
                threshold_reason_code,
            )

        amt = q2((effective_base * rate) / Decimal("100.0"))
        return WithholdingResult(True, section, rate, q2(effective_base), amt, threshold_reason, threshold_reason_code)
