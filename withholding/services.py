from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from withholding.models import (
    TcsComputation,
    WithholdingSection,
    WithholdingTaxType,
    EntityWithholdingConfig,
    PartyTaxProfile,
    WithholdingBaseRule,
)

ZERO2 = Decimal("0.00")
CUTOFF_DISABLE_206C_1H = date(2025, 4, 1)

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


def determine_fy_quarter(doc_date: date) -> tuple[str, int, str]:
    year = doc_date.year
    if doc_date.month < 4:
        fy_start = year - 1
        fy_end = year
    else:
        fy_start = year
        fy_end = year + 1
    fy = f"{fy_start}-{str(fy_end)[-2:]}"

    if doc_date.month in (4, 5, 6):
        quarter = "Q1"
    elif doc_date.month in (7, 8, 9):
        quarter = "Q2"
    elif doc_date.month in (10, 11, 12):
        quarter = "Q3"
    else:
        quarter = "Q4"

    return fy, doc_date.month, quarter


def compute_withholding_preview(
    *,
    entity_id: int,
    entityfin_id: int,
    subentity_id: int | None,
    party_account_id: int | None,
    tax_type: int,
    explicit_section_id: int | None,
    doc_date: date,
    taxable_total: Decimal,
    gross_total: Decimal,
) -> WithholdingResult:
    cfg = WithholdingResolver.get_entity_config(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        doc_date=doc_date,
    )

    if tax_type == WithholdingTaxType.TCS and (not cfg or not cfg.enable_tcs):
        return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "TCS disabled in entity config")
    if tax_type == WithholdingTaxType.TDS and (not cfg or not cfg.enable_tds):
        return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "TDS disabled in entity config")

    sec = WithholdingResolver.resolve_section(
        tax_type=tax_type,
        explicit_section_id=explicit_section_id,
        cfg=cfg,
        doc_date=doc_date,
    )
    if not sec:
        return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "No section resolved")

    if sec.effective_from and sec.effective_from > doc_date:
        return WithholdingResult(False, sec, Decimal("0.0000"), ZERO2, ZERO2, "Section not effective on doc date")
    if sec.effective_to and sec.effective_to < doc_date:
        return WithholdingResult(False, sec, Decimal("0.0000"), ZERO2, ZERO2, "Section expired on doc date")

    if sec.section_code and sec.section_code.strip().upper() in {"206C(1H)", "206C1H"} and doc_date >= CUTOFF_DISABLE_206C_1H:
        return WithholdingResult(True, sec, Decimal("0.0000"), ZERO2, ZERO2, "206C(1H) disabled from 2025-04-01")

    p = PartyTaxProfile.objects.filter(party_account_id=party_account_id).first() if party_account_id else None
    rate, reason = WithholdingResolver.resolve_rate(section=sec, party_profile=p, doc_date=doc_date)

    if sec.base_rule == WithholdingBaseRule.INVOICE_VALUE_INCL_GST:
        base = compute_base_amount_incl_gst(gross_total=q2(gross_total or ZERO2))
    else:
        base = compute_base_amount_excl_gst(taxable_total=q2(taxable_total or ZERO2))

    if sec.threshold_default is not None and base < q2(sec.threshold_default):
        return WithholdingResult(True, sec, rate, base, ZERO2, f"Below threshold ({sec.threshold_default})")

    amount = q2((q2(base) * Decimal(rate or 0)) / Decimal("100.0"))
    return WithholdingResult(True, sec, Decimal(rate or 0), q2(base), q2(amount), reason)


def upsert_tcs_computation(
    *,
    module_name: str,
    document_type: str,
    document_id: int,
    document_no: str,
    doc_date: date,
    entity_id: int,
    entityfin_id: int,
    subentity_id: int | None,
    party_account_id: int | None,
    preview: WithholdingResult,
    status: str = TcsComputation.Status.CONFIRMED,
    trigger_basis: str = "INVOICE",
    override_reason: str = "",
    overridden_by=None,
) -> TcsComputation:
    fy, _, quarter = determine_fy_quarter(doc_date)

    defaults = {
        "doc_date": doc_date,
        "document_no": (document_no or "").strip(),
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "party_account_id": party_account_id,
        "section": preview.section,
        "applicability_status": "APPLICABLE" if preview.enabled else "NOT_APPLICABLE",
        "trigger_basis": (trigger_basis or "INVOICE").upper(),
        "taxable_base": q2(preview.base_amount),
        "excluded_base": ZERO2,
        "tcs_base_amount": q2(preview.base_amount),
        "rate": Decimal(preview.rate or 0),
        "tcs_amount": q2(preview.amount),
        "no_pan_applied": bool((preview.reason or "").upper().find("PAN") >= 0),
        "lower_rate_applied": bool((preview.reason or "").upper().find("LOWER") >= 0),
        "override_reason": (override_reason or "").strip(),
        "fiscal_year": fy,
        "quarter": quarter,
        "status": status,
        "rule_snapshot_json": {
            "reason": preview.reason,
            "section_code": preview.section.section_code if preview.section else "",
            "section_id": preview.section.id if preview.section else None,
        },
        "computation_json": {
            "enabled": preview.enabled,
            "base_amount": str(q2(preview.base_amount)),
            "rate": str(Decimal(preview.rate or 0)),
            "amount": str(q2(preview.amount)),
            "reason": preview.reason,
        },
    }
    if overridden_by:
        defaults["overridden_by"] = overridden_by
        defaults["overridden_at"] = timezone.now()

    obj, _ = TcsComputation.objects.update_or_create(
        module_name=module_name,
        document_type=document_type,
        document_id=document_id,
        defaults=defaults,
    )
    return obj
