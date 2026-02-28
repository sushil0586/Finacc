from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from purchase.models.purchase_core import PurchaseInvoiceHeader

from withholding.threshold_service import FyPartyThresholdService, ZERO2, q2


from withholding.models import WithholdingTaxType
from withholding.services import (
    WithholdingResolver,
    WithholdingResult,
    compute_base_amount_excl_gst,
    compute_base_amount_incl_gst,
    q2,
    ZERO2,
)

class PurchaseWithholdingService:
    @staticmethod
    def compute_tds(
        *,
        header: Any,
        vendor_account_id: int,
        bill_date: date,
        taxable_total: Decimal,
        gross_total: Decimal,
    ) -> WithholdingResult:
        # feature flag
        cfg = WithholdingResolver.get_entity_config(
            entity_id=header.entity_id,
            entityfin_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            doc_date=bill_date,
        )
        if not (cfg and cfg.enable_tds) or not header.withholding_enabled:
            return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "TDS disabled")

        section = WithholdingResolver.resolve_section(
            tax_type=WithholdingTaxType.TDS,
            explicit_section_id=getattr(header, "tds_section_id", None),
            cfg=cfg,
            doc_date=bill_date,
        )
        if not section:
            return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "No TDS section")

        party_profile = getattr(header, "vendor_tax_profile", None)  # if you prefetch/attach
        if party_profile is None:
            # best: query through Account.tax_profile
            try:
                party_profile = header.vendor.tax_profile  # type: ignore
            except Exception:
                party_profile = None

        rate, reason = WithholdingResolver.resolve_rate(section=section, party_profile=party_profile, doc_date=bill_date)

        # base
        if section.base_rule == 1:  # excl GST
            base = compute_base_amount_excl_gst(taxable_total=taxable_total)
        elif section.base_rule == 2:  # incl GST
            base = compute_base_amount_incl_gst(gross_total=gross_total)
        else:
            base = compute_base_amount_excl_gst(taxable_total=taxable_total)

        if base <= ZERO2 or rate <= Decimal("0.0000"):
            return WithholdingResult(True, section, rate, base, ZERO2, reason)
        
        if section.section_code.strip().upper() == "194Q":
            # threshold is 50L (or from section.threshold_default)
            threshold = section.threshold_default or Decimal("5000000.00")

            tr = FyPartyThresholdService.compute_base_above_threshold(
                model=PurchaseInvoiceHeader,
                amount_field="total_taxable",        # ✅ use your stored totals field
                entity_id=header.entity_id,
                entityfinid_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                party_field="vendor_id",
                party_id=header.vendor_id,
                txn_date=bill_date,
                current_amount=q2(taxable_total),    # current invoice taxable
                threshold=threshold,
                current_id=getattr(header, "id", None),  # for update ordering
                allowed_statuses=(
                    PurchaseInvoiceHeader.Status.CONFIRMED,
                    PurchaseInvoiceHeader.Status.POSTED,
                ),
                date_field="bill_date",
            )

            base = tr.base_applicable
        

        amount = q2((base * rate) / Decimal("100.0"))
        return WithholdingResult(True, section, rate, base, amount, reason)