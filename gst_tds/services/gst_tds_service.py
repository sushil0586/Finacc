# gst_tds/services/gst_tds_service.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger

ZERO2 = Decimal("0.00")
RATE_TOTAL = Decimal("2.0000")  # 2% total under Sec 51
RATE_HALF  = Decimal("1.0000")  # 1% CGST, 1% SGST


def normalize_contract_ref(value: str | None) -> str:
    return str(value or "").strip().upper()

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
    def _master_rule_for_config(cfg):
        rule = getattr(cfg, "master_rule", None)
        if rule and getattr(rule, "is_active", False):
            return rule
        return None

    @staticmethod
    def compute_for_invoice(inv) -> GstTdsComputed:
        if not getattr(inv, "gst_tds_enabled", False):
            return GstTdsComputed(False, "gst_tds_enabled false", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        cfg = GstTdsService._config_for(inv)
        if not cfg or not cfg.enabled:
            return GstTdsComputed(False, "gst tds config disabled/missing", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))
        rule = GstTdsService._master_rule_for_config(cfg)

        contract_ref = normalize_contract_ref(getattr(inv, "gst_tds_contract_ref", ""))
        if not contract_ref:
            return GstTdsComputed(False, "contract ref missing", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        base_full = q2(getattr(inv, "total_taxable", None) or ZERO2)
        if base_full <= ZERO2:
            return GstTdsComputed(False, "taxable base zero", q4(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        # Contract-wise threshold decision (ledger)
        before = q2(
            GstTdsContractLedger.objects.filter(
                entity_id=inv.entity_id,
                subentity_id=inv.subentity_id,
                entityfinid_id=inv.entityfinid_id,
                vendor_id=inv.vendor_id,
                contract_ref__iexact=contract_ref,
            ).aggregate(total=Coalesce(Sum("cumulative_taxable"), ZERO2)).get("total") or ZERO2
        )

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
        total_rate = q4(getattr(rule, "total_rate", RATE_TOTAL) if rule else RATE_TOTAL)
        igst_rate = q4(getattr(rule, "igst_rate", RATE_TOTAL) if rule else RATE_TOTAL)
        cgst_rate = q4(getattr(rule, "cgst_rate", RATE_HALF) if rule else RATE_HALF)
        sgst_rate = q4(getattr(rule, "sgst_rate", RATE_HALF) if rule else RATE_HALF)

        total = q2(taxable_for_tds * total_rate / Decimal("100.00"))
        if total <= ZERO2:
            return GstTdsComputed(False, "computed tds zero", total_rate, taxable_for_tds, q2(ZERO2), q2(ZERO2), q2(ZERO2), q2(ZERO2))

        if is_inter:
            igst = q2(taxable_for_tds * igst_rate / Decimal("100.00"))
            return GstTdsComputed(True, "eligible inter-state (IGST)", total_rate, taxable_for_tds, q2(ZERO2), q2(ZERO2), igst, igst)

        cgst = q2(taxable_for_tds * cgst_rate / Decimal("100.00"))
        sgst = q2(taxable_for_tds * sgst_rate / Decimal("100.00"))
        return GstTdsComputed(True, "eligible intra-state (CGST + SGST)", total_rate, taxable_for_tds, cgst, sgst, q2(ZERO2), q2(cgst + sgst))

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

    @staticmethod
    def _scope_key_for_header(inv):
        contract_ref = normalize_contract_ref(getattr(inv, "gst_tds_contract_ref", ""))
        if not contract_ref:
            return None
        return (
            int(getattr(inv, "entity_id", 0) or 0),
            int(getattr(inv, "entityfinid_id", 0) or 0),
            int(getattr(inv, "subentity_id", 0) or 0),
            int(getattr(inv, "vendor_id", 0) or 0),
            contract_ref,
        )

    @staticmethod
    def sync_contract_ledger_for_scope(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id,
        vendor_id: int,
        contract_ref: str,
    ) -> None:
        from purchase.models.purchase_core import PurchaseInvoiceHeader

        ref = normalize_contract_ref(contract_ref)
        if not (entity_id and entityfinid_id and vendor_id and ref):
            return

        header_qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            vendor_id=vendor_id,
            gst_tds_enabled=True,
            gst_tds_contract_ref__iexact=ref,
            status__in=[PurchaseInvoiceHeader.Status.CONFIRMED, PurchaseInvoiceHeader.Status.POSTED],
        )
        if subentity_id in (None, 0):
            header_qs = header_qs.filter(subentity__isnull=True)
            subentity_val = None
        else:
            header_qs = header_qs.filter(subentity_id=subentity_id)
            subentity_val = subentity_id

        totals = header_qs.aggregate(
            taxable=Coalesce(Sum("total_taxable"), ZERO2),
            tds=Coalesce(Sum("gst_tds_amount"), ZERO2),
        )
        taxable = q2(totals.get("taxable") or ZERO2)
        tds = q2(totals.get("tds") or ZERO2)

        ledger_qs = GstTdsContractLedger.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_val,
            vendor_id=vendor_id,
            contract_ref__iexact=ref,
        )

        if taxable <= ZERO2 and tds <= ZERO2:
            ledger_qs.delete()
            return

        obj = ledger_qs.order_by("id").first()
        if obj is None:
            GstTdsContractLedger.objects.create(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_val,
                vendor_id=vendor_id,
                contract_ref=ref,
                cumulative_taxable=taxable,
                cumulative_tds=tds,
            )
            return

        # Keep one canonical uppercase row per scope/contract and remove case-variant duplicates.
        duplicate_ids = list(ledger_qs.exclude(id=obj.id).values_list("id", flat=True))
        if duplicate_ids:
            GstTdsContractLedger.objects.filter(id__in=duplicate_ids).delete()

        if obj.contract_ref != ref:
            obj.contract_ref = ref
        obj.cumulative_taxable = taxable
        obj.cumulative_tds = tds
        obj.save(update_fields=["contract_ref", "cumulative_taxable", "cumulative_tds", "updated_at"])

    @staticmethod
    def sync_contract_ledger_for_header(inv, *, old_scope_key=None) -> None:
        """
        Keep GstTdsContractLedger consistent after header create/update/status transitions.
        - old_scope_key is optional and should be passed when vendor/contract/subentity changes.
        """
        new_key = GstTdsService._scope_key_for_header(inv)
        keys = []
        if old_scope_key:
            keys.append(old_scope_key)
        if new_key:
            keys.append(new_key)

        # De-dupe while preserving order.
        seen = set()
        unique_keys = []
        for key in keys:
            if not key or key in seen:
                continue
            seen.add(key)
            unique_keys.append(key)

        for entity_id, entityfinid_id, subentity_id, vendor_id, contract_ref in unique_keys:
            GstTdsService.sync_contract_ledger_for_scope(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=None if int(subentity_id or 0) == 0 else subentity_id,
                vendor_id=vendor_id,
                contract_ref=contract_ref,
            )
