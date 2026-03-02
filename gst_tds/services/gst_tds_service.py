# gst_tds/services/gst_tds_service.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction

from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger

ZERO2 = Decimal("0.00")
RATE_TOTAL = Decimal("2.0000")  # 2% total under Sec 51
RATE_HALF  = Decimal("1.0000")  # 1% CGST, 1% SGST

def q2(x) -> Decimal:
    if x is None:
        return ZERO2
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def q4(x) -> Decimal:
    if x is None:
        return Decimal("0.0000")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

@dataclass(frozen=True)
class GstTdsComputed:
    eligible: bool
    reason: str
    rate: Decimal
    base: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal


class GstTdsService:
    """
    GST-TDS (Sec 51) service.
    DOES NOT TOUCH Income Tax TDS fields.
    """

    @staticmethod
    def _config_for(inv):
        # prefer subentity config; fallback to entity-only config
        cfg = EntityGstTdsConfig.objects.filter(entity_id=inv.entity_id, subentity_id=inv.subentity_id).first()
        if cfg:
            return cfg
        return EntityGstTdsConfig.objects.filter(entity_id=inv.entity_id, subentity__isnull=True).first()

    @staticmethod
    def compute_for_invoice(inv) -> GstTdsComputed:
        if not getattr(inv, "gst_tds_enabled", False):
            return GstTdsComputed(False, "gst_tds_enabled false", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        cfg = GstTdsService._config_for(inv)
        if not cfg or not cfg.enabled:
            return GstTdsComputed(False, "gst tds config disabled/missing", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        contract_ref = (getattr(inv, "gst_tds_contract_ref", "") or "").strip()
        if not contract_ref:
            return GstTdsComputed(False, "contract ref missing", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        base_full = q2(getattr(inv, "total_taxable", None) or ZERO2)
        if base_full <= ZERO2:
            return GstTdsComputed(False, "taxable base zero", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        # Contract-wise threshold decision (ledger)
        led = GstTdsContractLedger.objects.filter(
            entity_id=inv.entity_id,
            subentity_id=inv.subentity_id,
            entityfinid_id=inv.entityfinid_id,
            vendor_id=inv.vendor_id,
            contract_ref=contract_ref,
        ).first()

        before = q2(led.cumulative_taxable) if led else q2(ZERO2)
        threshold = q2(cfg.threshold_amount)
        after = q2(before + base_full)

        if after <= threshold:
            # not eligible yet (but store base for display if you want)
            return GstTdsComputed(False, f"threshold not reached (after={after})", q4(ZERO2), base_full, q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        # Apply on amount above threshold if crossing occurs now; else full base
        if before < threshold:
            taxable_for_tds = q2(after - threshold)
        else:
            taxable_for_tds = base_full

        if taxable_for_tds <= ZERO2:
            return GstTdsComputed(False, "taxable_for_tds zero", q4(ZERO2), base_full, q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        # Determine split using your existing flags
        is_inter = (int(inv.tax_regime) == 2) or bool(getattr(inv, "is_igst", False))

        total = q2(taxable_for_tds * q4(RATE_TOTAL) / Decimal("100.00"))
        if total <= ZERO2:
            return GstTdsComputed(False, "computed tds zero", q4(RATE_TOTAL), taxable_for_tds, q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        if is_inter:
            return GstTdsComputed(True, "eligible inter-state (IGST 2%)", q4(RATE_TOTAL), taxable_for_tds, q2(ZERO2), q2(ZERO2), total, total)

        half = q2(taxable_for_tds * q4(RATE_HALF) / Decimal("100.00"))
        return GstTdsComputed(True, "eligible intra-state (CGST 1% + SGST 1%)", q4(RATE_TOTAL), taxable_for_tds, half, half, q2(ZERO2), q2(half + half))

    @staticmethod
    def apply_to_header(inv) -> None:
        """
        Apply computed fields to header. Call this after totals are computed.
        No ledger update here (recommended). Ledger update should happen at payment time.
        """
        res = GstTdsService.compute_for_invoice(inv)

        inv.gst_tds_rate = q4(res.rate)
        inv.gst_tds_base_amount = q2(res.base)
        inv.gst_tds_cgst_amount = q2(res.cgst)
        inv.gst_tds_sgst_amount = q2(res.sgst)
        inv.gst_tds_igst_amount = q2(res.igst)
        inv.gst_tds_amount = q2(res.total)

        inv.gst_tds_status = (1 if res.eligible else 0)  # ELIGIBLE else NA
        # keep inv.gst_tds_reason as UI provided; do not overwrite