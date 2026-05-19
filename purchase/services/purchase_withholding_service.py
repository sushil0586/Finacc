from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from purchase.models.purchase_core import PurchaseInvoiceHeader

from withholding.threshold_service import FyPartyThresholdService, ZERO2, q2


from withholding.models import WithholdingBaseRule, WithholdingTaxType
from withholding.services import (
    WithholdingResolver,
    WithholdingResult,
    _apply_section_threshold,
    compute_base_amount_excl_gst,
    compute_base_amount_incl_gst,
    q2,
    ZERO2,
)

class PurchaseWithholdingService:
    @staticmethod
    def _194i_subtype_rate(*, header: Any, section: Any) -> tuple[Optional[Decimal], Optional[str], Optional[str]]:
        if str(getattr(section, "section_code", "") or "").strip().upper() != "194I":
            return None, None, None

        policy = getattr(section, "applicability_json", None) or {}
        if not isinstance(policy, dict):
            return None, None, None

        plant_rate_raw = policy.get("rent_rate_plant_machinery")
        if plant_rate_raw in (None, ""):
            return None, None, None

        try:
            plant_rate = Decimal(str(plant_rate_raw))
        except Exception:
            return None, None, None

        keywords = policy.get("rent_plant_machinery_keywords") or []
        if not isinstance(keywords, (list, tuple, set)):
            keywords = []
        normalized_keywords = [str(token).strip().lower() for token in keywords if str(token).strip()]
        if not normalized_keywords:
            normalized_keywords = ["plant", "machinery", "machine", "equipment"]

        lines = getattr(header, "lines", None)
        if lines is None:
            return None, None, None

        try:
            iterable = list(lines.all()) if hasattr(lines, "all") else list(lines)
        except Exception:
            return None, None, None

        text_chunks: list[str] = []
        for ln in iterable:
            text_chunks.extend(
                [
                    str(getattr(ln, "product_desc", "") or "").strip().lower(),
                    str(getattr(ln, "hsn_sac", "") or "").strip().lower(),
                ]
            )

        combined = " ".join(chunk for chunk in text_chunks if chunk)
        if not combined:
            return None, None, None

        if any(keyword in combined for keyword in normalized_keywords):
            return q2(plant_rate), "194I plant/machinery rent rate applied.", "RATE_SUBTYPE_194I_PLANT_MACHINERY"
        return None, None, None

    @staticmethod
    def _is_credit_note_or_reversal(*, header: Any, taxable_total: Decimal, gross_total: Decimal) -> bool:
        doc_type = getattr(header, "doc_type", None)
        if doc_type is not None and int(doc_type) == int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE):
            return True
        return q2(taxable_total) < ZERO2 or q2(gross_total) < ZERO2

    @staticmethod
    def _cumulative_194c_eligibility(
        *,
        header: Any,
        bill_date: date,
        current_amount: Decimal,
    ) -> tuple[Decimal, Optional[str], Optional[str]]:
        """
        194C supports both:
        - single invoice threshold via section.threshold_default
        - aggregate FY threshold via applicability_json.aggregate_threshold

        When the cumulative threshold is crossed, TDS applies on the full current
        invoice amount, not only the excess portion.
        """
        section = getattr(header, "tds_section", None)
        if section is None:
            return current_amount, None, None
        policy = getattr(section, "applicability_json", None) or {}
        if not isinstance(policy, dict):
            return current_amount, None, None

        aggregate_threshold = policy.get("aggregate_threshold")
        if aggregate_threshold in (None, ""):
            return current_amount, None, None

        aggregate_threshold = q2(Decimal(str(aggregate_threshold)))
        if aggregate_threshold <= ZERO2:
            return current_amount, None, None

        threshold_result = FyPartyThresholdService.compute_base_above_threshold(
            model=PurchaseInvoiceHeader,
            amount_field="total_taxable",
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            party_field="vendor_id",
            party_id=header.vendor_id,
            txn_date=bill_date,
            current_amount=q2(current_amount),
            threshold=aggregate_threshold,
            current_id=getattr(header, "id", None),
            allowed_statuses=(
                PurchaseInvoiceHeader.Status.CONFIRMED,
                PurchaseInvoiceHeader.Status.POSTED,
            ),
            date_field="bill_date",
        )
        if threshold_result.base_applicable <= ZERO2:
            return ZERO2, f"Below cumulative threshold ({aggregate_threshold})", "BELOW_THRESHOLD_CUMULATIVE"
        return q2(current_amount), "Threshold crossed in current transaction (cumulative mode).", "THRESHOLD_CROSSED_CUMULATIVE"

    @staticmethod
    def _194q_goods_only_eligibility(*, header: Any) -> tuple[bool, Optional[str], Optional[str]]:
        """
        194Q applies only to goods purchases. The current computation path works at
        invoice-header level, so mixed goods+service invoices are blocked rather than
        overstating the deduction base.
        """
        lines = getattr(header, "lines", None)
        if lines is None:
            return True, None, None

        try:
            has_service_lines = bool(lines.filter(is_service=True).exists())
            has_goods_lines = bool(lines.filter(is_service=False).exists())
        except Exception:
            return True, None, None

        if has_service_lines and not has_goods_lines:
            return False, "Section 194Q is not applicable to service invoices.", "NOT_APPLICABLE_SERVICE_INVOICE"
        if has_service_lines and has_goods_lines:
            return (
                False,
                "Section 194Q is not supported on mixed goods and service invoices.",
                "NOT_APPLICABLE_MIXED_GOODS_SERVICES",
            )
        return True, None, None

    @staticmethod
    def compute_tds(
        *,
        header: Any,
        vendor_account_id: int,
        bill_date: date,
        taxable_total: Decimal,
        gross_total: Decimal,
    ) -> WithholdingResult:
        # Resolve config for defaults/policy (when available).
        cfg = WithholdingResolver.get_entity_config(
            entity_id=header.entity_id,
            entityfin_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            doc_date=bill_date,
        )
        if not header.withholding_enabled:
            return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "TDS disabled")

        # Explicitly selected section should be honored even when cfg row is missing.
        explicit_section_id = getattr(header, "tds_section_id", None)
        section = WithholdingResolver.resolve_section(
            tax_type=WithholdingTaxType.TDS,
            explicit_section_id=explicit_section_id,
            cfg=cfg,
            doc_date=bill_date,
            party_account_id=vendor_account_id or getattr(header, "vendor_id", None),
        )
        if not section:
            return WithholdingResult(False, None, Decimal("0.0000"), ZERO2, ZERO2, "No TDS section")

        # If a config exists and TDS is explicitly disabled there, block auto compute.
        if cfg and not getattr(cfg, "enable_tds", True):
            return WithholdingResult(False, section, Decimal("0.0000"), ZERO2, ZERO2, "TDS disabled in withholding configuration for this scope/date.")

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
                "Section base rule is not invoice-based for purchase invoice context.",
                "NOT_APPLICABLE_BASE_RULE_CONTEXT",
            )

        party_profile = WithholdingResolver.resolve_party_profile(
            party_account_id=vendor_account_id or getattr(header, "vendor_id", None),
        )

        rate_resolution = WithholdingResolver.resolve_rate(
            section=section,
            party_profile=party_profile,
            doc_date=bill_date,
        )
        rate = Decimal(rate_resolution.rate or 0)
        reason = rate_resolution.reason
        reason_code = rate_resolution.reason_code

        subtype_rate, subtype_reason, subtype_reason_code = PurchaseWithholdingService._194i_subtype_rate(
            header=header,
            section=section,
        )
        if (
            subtype_rate is not None
            and not rate_resolution.no_pan_applied
            and not rate_resolution.sec_206ab_applied
            and not rate_resolution.lower_rate_applied
        ):
            rate = subtype_rate
            reason = subtype_reason or reason
            reason_code = subtype_reason_code or reason_code

        # base
        if section.base_rule == 1:  # excl GST
            base = compute_base_amount_excl_gst(taxable_total=taxable_total)
        elif section.base_rule == 2:  # incl GST
            base = compute_base_amount_incl_gst(gross_total=gross_total)
        else:
            base = compute_base_amount_excl_gst(taxable_total=taxable_total)

        if base <= ZERO2:
            if PurchaseWithholdingService._is_credit_note_or_reversal(
                header=header,
                taxable_total=taxable_total,
                gross_total=gross_total,
            ):
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    ZERO2,
                    ZERO2,
                    "Credit note / reversal document does not create a fresh TDS deduction.",
                    "CREDIT_NOTE_REVERSAL_NO_TDS",
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )
            return WithholdingResult(
                True,
                section,
                rate,
                ZERO2,
                ZERO2,
                reason,
                reason_code,
                no_pan_applied=rate_resolution.no_pan_applied,
                sec_206ab_applied=rate_resolution.sec_206ab_applied,
                lower_rate_applied=rate_resolution.lower_rate_applied,
            )

        if rate <= Decimal("0.0000"):
            return WithholdingResult(
                True,
                section,
                rate,
                base,
                ZERO2,
                reason,
                rate_resolution.reason_code,
                no_pan_applied=rate_resolution.no_pan_applied,
                sec_206ab_applied=rate_resolution.sec_206ab_applied,
                lower_rate_applied=rate_resolution.lower_rate_applied,
            )
        
        if section.section_code.strip().upper() == "194Q":
            if not cfg or not getattr(cfg, "apply_194q", False):
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    ZERO2,
                    ZERO2,
                    "Section 194Q is disabled in withholding configuration for this scope/date.",
                    "NOT_APPLICABLE_194Q_DISABLED",
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )

            turnover_limit = q2(getattr(cfg, "tds_194q_turnover_limit", ZERO2) or ZERO2)
            prev_turnover = q2(getattr(cfg, "tds_194q_prev_fy_turnover", ZERO2) or ZERO2)
            force_eligible = getattr(cfg, "tds_194q_force_eligible", None)
            if force_eligible is None:
                eligible = bool(turnover_limit <= ZERO2 or prev_turnover >= turnover_limit)
            else:
                eligible = bool(force_eligible)
            if not eligible:
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    ZERO2,
                    ZERO2,
                    "194Q turnover eligibility not met for this entity config.",
                    "NOT_ELIGIBLE_TURNOVER_GATE",
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )

            if int(getattr(header, "supply_category", 0) or 0) in {
                int(PurchaseInvoiceHeader.SupplyCategory.IMPORT_GOODS),
                int(PurchaseInvoiceHeader.SupplyCategory.IMPORT_SERVICES),
            }:
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    ZERO2,
                    ZERO2,
                    "Section 194Q is not applicable to import purchases.",
                    "NOT_APPLICABLE_IMPORT",
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )

            applicable, applicability_reason, applicability_reason_code = WithholdingResolver.evaluate_section_applicability(
                section=section,
                party_account_id=vendor_account_id or getattr(header, "vendor_id", None),
            )
            if not applicable:
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    ZERO2,
                    ZERO2,
                    applicability_reason,
                    applicability_reason_code,
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )

            applicable, applicability_reason, applicability_reason_code = PurchaseWithholdingService._194q_goods_only_eligibility(
                header=header,
            )
            if not applicable:
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    ZERO2,
                    ZERO2,
                    applicability_reason,
                    applicability_reason_code,
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )

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
        

        threshold_reason = None
        threshold_reason_code = None
        code = section.section_code.strip().upper()
        if code == "194C":
            single_threshold = q2(getattr(section, "threshold_default", ZERO2) or ZERO2)
            if base < single_threshold:
                effective_base, threshold_reason, threshold_reason_code = PurchaseWithholdingService._cumulative_194c_eligibility(
                    header=header,
                    bill_date=bill_date,
                    current_amount=base,
                )
                if effective_base <= ZERO2:
                    return WithholdingResult(
                        True,
                        section,
                        rate,
                        q2(base),
                        ZERO2,
                        threshold_reason or f"Below threshold ({single_threshold})",
                        threshold_reason_code or "BELOW_THRESHOLD",
                        no_pan_applied=rate_resolution.no_pan_applied,
                        sec_206ab_applied=rate_resolution.sec_206ab_applied,
                        lower_rate_applied=rate_resolution.lower_rate_applied,
                    )
                base = effective_base
        elif code != "194Q":
            effective_base, threshold_reason, threshold_reason_code = _apply_section_threshold(
                section=section,
                base_amount=base,
                doc_date=bill_date,
                entity_id=header.entity_id,
                entityfin_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                party_account_id=vendor_account_id or getattr(header, "vendor_id", None),
            )
            if effective_base <= ZERO2:
                return WithholdingResult(
                    True,
                    section,
                    rate,
                    q2(base),
                    ZERO2,
                    threshold_reason or f"Below threshold ({getattr(section, 'threshold_default', 0)})",
                    threshold_reason_code or "BELOW_THRESHOLD",
                    no_pan_applied=rate_resolution.no_pan_applied,
                    sec_206ab_applied=rate_resolution.sec_206ab_applied,
                    lower_rate_applied=rate_resolution.lower_rate_applied,
                )
            base = effective_base

        amount = q2((base * rate) / Decimal("100.0"))
        return WithholdingResult(
            True,
            section,
            rate,
            base,
            amount,
            threshold_reason or reason,
            threshold_reason_code or reason_code,
            no_pan_applied=rate_resolution.no_pan_applied,
            sec_206ab_applied=rate_resolution.sec_206ab_applied,
            lower_rate_applied=rate_resolution.lower_rate_applied,
        )
