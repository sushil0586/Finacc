from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple

from django.db.models import Q

from withholding.models import (
    WithholdingSection,
    WithholdingTaxType,
    EntityWithholdingConfig,
    PartyTaxProfile,
    WithholdingBaseRule,
)

ZERO2 = Decimal("0.00")

def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))

@dataclass(frozen=True)
class WithholdingResult:
    enabled: bool
    section: Optional[WithholdingSection]
    rate: Decimal
    base_amount: Decimal
    amount: Decimal
    reason: Optional[str] = None


class WithholdingResolver:
    @staticmethod
    def get_entity_config(*, entity_id: int, entityfin_id: int, subentity_id: int | None, doc_date: date) -> Optional[EntityWithholdingConfig]:
        qs = EntityWithholdingConfig.objects.filter(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            effective_from__lte=doc_date,
        ).order_by("-effective_from")
        return qs.first()

    @staticmethod
    def resolve_section(*, tax_type: int, explicit_section_id: int | None, cfg: Optional[EntityWithholdingConfig], doc_date: date) -> Optional[WithholdingSection]:
        if explicit_section_id:
            sec = WithholdingSection.objects.filter(id=explicit_section_id, tax_type=tax_type, is_active=True).first()
            if sec:
                return sec

        if not cfg:
            return None

        sec = cfg.default_tds_section if tax_type == WithholdingTaxType.TDS else cfg.default_tcs_section
        if not sec:
            return None

        # Ensure section is valid for doc_date
        if sec.effective_from and sec.effective_from > doc_date:
            return None
        if sec.effective_to and sec.effective_to < doc_date:
            return None

        return sec

    @staticmethod
    def resolve_rate(*, section: WithholdingSection, party_profile: Optional[PartyTaxProfile], doc_date: date) -> Tuple[Decimal, Optional[str]]:
        # Exempt?
        if party_profile and party_profile.is_exempt_withholding:
            return Decimal("0.0000"), "Party exempt from withholding"

        # Lower deduction certificate?
        if party_profile and party_profile.lower_deduction_rate is not None:
            vf = party_profile.lower_deduction_valid_from
            vt = party_profile.lower_deduction_valid_to
            if (vf is None or vf <= doc_date) and (vt is None or doc_date <= vt):
                return party_profile.lower_deduction_rate, "Lower deduction certificate"

        # PAN not available => higher rate (if defined)
        if section.requires_pan:
            pan_ok = bool(party_profile and party_profile.is_pan_available)
            if not pan_ok and section.higher_rate_no_pan is not None:
                return section.higher_rate_no_pan, "Higher rate (PAN missing)"

        return section.rate_default, None


def compute_base_amount_excl_gst(*, taxable_total: Decimal) -> Decimal:
    return q2(taxable_total)

def compute_base_amount_incl_gst(*, gross_total: Decimal) -> Decimal:
    return q2(gross_total)