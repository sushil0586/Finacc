from __future__ import annotations

"""
Classification rules for mapping sales documents into GSTR-1 sections.

Precedence rules:
- supply_category overrides GSTIN validity for B2B/SEZ/Deemed exports.
- GSTIN must be regex-valid to be treated as registered unless supply_category says otherwise.
- Interstate vs intrastate falls back to seller_state_code vs place_of_supply_state_code when available,
  otherwise uses tax_regime/is_igst as a best-effort hint.
- Credit/debit notes follow recipient registration either from the note itself or the linked original invoice.
"""

from dataclasses import dataclass
from django.db.models import F, Q

from reports.gstr1.conf import b2cl_threshold
from sales.models import SalesInvoiceHeader


@dataclass(frozen=True)
class SectionRule:
    code: str
    label: str


SECTION_B2B = SectionRule(code="B2B", label="B2B")
SECTION_B2CL = SectionRule(code="B2CL", label="B2CL")
SECTION_B2CS = SectionRule(code="B2CS", label="B2CS")
SECTION_CDNR = SectionRule(code="CDNR", label="CDNR")
SECTION_CDNUR = SectionRule(code="CDNUR", label="CDNUR")
SECTION_EXP = SectionRule(code="EXP", label="EXP")

ALL_SECTIONS = (
    SECTION_B2B,
    SECTION_B2CL,
    SECTION_B2CS,
    SECTION_CDNR,
    SECTION_CDNUR,
    SECTION_EXP,
)

GSTIN_PATTERN = r"^[0-9A-Z]{15}$"
class Gstr1ClassificationService:
    @staticmethod
    def section_filter(section_code: str) -> Q:
        section_code = (section_code or "").upper()

        is_note = Q(doc_type__in=[SalesInvoiceHeader.DocType.CREDIT_NOTE, SalesInvoiceHeader.DocType.DEBIT_NOTE])
        # note: queryset-level regex check first; checksum enforced in validation path
        has_valid_gstin = Q(customer_gstin__isnull=False) & ~Q(customer_gstin="") & Q(
            customer_gstin__regex=GSTIN_PATTERN
        )
        is_tax_invoice = Q(doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE)

        export_supply = Q(
            supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
            ]
        )
        sez_supply = Q(
            supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
            ]
        )
        deemed_export = Q(supply_category=SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT)
        b2b_supply = Q(
            supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
                SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
            ]
        )
        registered_recipient = has_valid_gstin | b2b_supply
        unregistered_recipient = ~registered_recipient

        has_state_match = (
            Q(seller_state_code__isnull=False)
            & ~Q(seller_state_code="")
            & Q(place_of_supply_state_code__isnull=False)
            & ~Q(place_of_supply_state_code="")
        )
        state_interstate = has_state_match & ~Q(seller_state_code=F("place_of_supply_state_code"))
        state_intrastate = has_state_match & Q(seller_state_code=F("place_of_supply_state_code"))
        interstate = state_interstate | (~has_state_match & (Q(tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE) | Q(is_igst=True)))
        intrastate = state_intrastate | (~has_state_match & (Q(tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE) | Q(is_igst=False)))

        original_b2b_supply = Q(
            original_invoice__supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
                SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
            ]
        )
        original_registered = (
            Q(original_invoice__customer_gstin__isnull=False)
            & ~Q(original_invoice__customer_gstin="")
            & Q(original_invoice__customer_gstin__regex=GSTIN_PATTERN)
        ) | original_b2b_supply

        if section_code == SECTION_EXP.code:
            return export_supply

        if section_code == SECTION_CDNR.code:
            return is_note & (registered_recipient | original_registered)

        if section_code == SECTION_CDNUR.code:
            return is_note & ~(registered_recipient | original_registered)

        if section_code == SECTION_B2B.code:
            return is_tax_invoice & registered_recipient & ~export_supply

        if section_code == SECTION_B2CL.code:
            return (
                is_tax_invoice
                & unregistered_recipient
                & interstate
                & ~export_supply
                & ~sez_supply
                & Q(grand_total__gte=b2cl_threshold())
            )

        if section_code == SECTION_B2CS.code:
            return (
                is_tax_invoice
                & unregistered_recipient
                & ~export_supply
                & ~sez_supply
                & (intrastate | Q(grand_total__lt=b2cl_threshold()))
            )

        raise ValueError(f"Unsupported section: {section_code}")

    @staticmethod
    def section_codes() -> list[str]:
        return [section.code for section in ALL_SECTIONS]
