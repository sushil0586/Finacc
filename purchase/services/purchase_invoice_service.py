from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re
from gst_tds.services.gst_tds_service import GstTdsService, normalize_contract_ref
from purchase.models.purchase_addons import PurchaseChargeLine, PurchaseChargeType


from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Max, Q, Sum
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from catalog.models import Product, ProductPurchaseBehavior
from catalog.taxability import resolve_product_default_taxability
from catalog.uom_helpers import resolve_product_uom
from entity.models import EntityFinancialYear
from financial.gstin import validate_financial_gstin
from financial.profile_access import account_compliance_profile, account_gstno, account_pan, account_partytype
from posting.common.location_resolver import resolve_posting_location_id
from posting.models import InventoryMove
from withholding.models import WithholdingBaseRule
from withholding.services import WithholdingResolver


from purchase.services.purchase_settings_service import PurchaseSettingsService
from purchase.services.purchase_withholding_service import PurchaseWithholdingService
from purchase.models.purchase_config import PurchaseLockPeriod
from purchase.models.purchase_core import (
    PurchaseInvoiceHeader,
    PurchaseInvoiceLine,
    PurchaseTaxSummary,
    DocType,
    Status,
    Taxability,
    TaxRegime,
    ItcClaimStatus,
)

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")
DEC2 = Decimal("0.01")
DEC4 = Decimal("0.0001")
GST_TDS_TOLERANCE = Decimal("0.02")

# paisa tolerance: allows tiny rounding differences from UI (e.g. 0.01–0.02)
TOL = Decimal("0.02")


def q2(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC2, rounding=ROUND_HALF_UP)


def q4(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC4, rounding=ROUND_HALF_UP)


def _line_product_ref(line: Dict[str, Any]):
    return line.get("product")


def near(a, b, tol=TOL) -> bool:
    return abs(q2(a) - q2(b)) <= tol

ZERO2 = Decimal("0.00")
RATE_TOTAL = Decimal("2.0000")   # 2%
RATE_HALF = Decimal("1.0000")    # 1% + 1%
TWOPLACES = Decimal("0.01")
TDS_TOLERANCE = Decimal("0.02")  # 2 paisa tolerance
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def q2r(x: Decimal) -> Decimal:
    return (x or ZERO2).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DerivedRegime:
    tax_regime: int
    is_igst: bool

@dataclass(frozen=True)
class ChargeComputed:
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_value: Decimal


@dataclass(frozen=True)
class AmendmentWindow:
    amendment_required: bool
    reasons: tuple[str, ...]
    lock_until: Optional[date]
    correction_date: Optional[date]
    gst_period: Optional[str]


class PurchaseInvoiceService:
    """
    Purchase invoice business rules:
    - client may send tax values, but we verify + store computed values only
    - supports free qty, discount, inclusive tax pricing, cess percent
    - persists header totals correctly
    """

    @staticmethod
    def apply_product_line_defaults(
        *,
        header_taxability: int,
        lines: List[Dict[str, Any]],
    ) -> None:
        for line in lines or []:
            if line.get("taxability") in (None, ""):
                product = _line_product_ref(line)
                if product not in (None, "", 0):
                    line["taxability"] = resolve_product_default_taxability(
                        product=product if hasattr(product, "_meta") else None,
                        product_id=getattr(product, "pk", product),
                        fallback=header_taxability,
                    )
                else:
                    line["taxability"] = int(header_taxability)

            line_taxability = int(line.get("taxability") or header_taxability)
            if line_taxability in (int(Taxability.EXEMPT), int(Taxability.NIL_RATED), int(Taxability.NON_GST)):
                if line.get("is_itc_eligible") in (None, ""):
                    line["is_itc_eligible"] = False
                if not (line.get("itc_block_reason") or "").strip():
                    line["itc_block_reason"] = "Not ITC eligible for non-taxable line."

    # ---------------------------
    # Period lock
    # ---------------------------
    @staticmethod
    def _resolve_financial_year(entity_id, entityfinid_id, bill_date) -> Optional[EntityFinancialYear]:
        if entityfinid_id:
            return (
                EntityFinancialYear.objects
                .filter(pk=entityfinid_id, entity_id=entity_id)
                .only(
                    "id",
                    "desc",
                    "year_code",
                    "finstartyear",
                    "finendyear",
                    "period_status",
                    "is_year_closed",
                    "books_locked_until",
                    "gst_locked_until",
                    "inventory_locked_until",
                    "ap_ar_locked_until",
                )
                .first()
            )
        if not entity_id or not bill_date:
            return None
        return (
            EntityFinancialYear.objects
            .filter(
                entity_id=entity_id,
                finstartyear__date__lte=bill_date,
                finendyear__date__gte=bill_date,
            )
            .only(
                "id",
                "desc",
                "year_code",
                "finstartyear",
                "finendyear",
                "period_status",
                "is_year_closed",
                "books_locked_until",
                "gst_locked_until",
                "inventory_locked_until",
                "ap_ar_locked_until",
            )
            .first()
        )

    @staticmethod
    def _build_amendment_window(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        entityfinid_id: Optional[int],
        original_bill_date: date,
    ) -> AmendmentWindow:
        reasons: list[str] = []
        lock_dates: list[date] = []

        purchase_locks = list(
            PurchaseLockPeriod.objects.filter(
                entity_id=entity_id,
                lock_date__gte=original_bill_date,
            ).filter(
                Q(subentity_id=subentity_id) | Q(subentity__isnull=True)
            ).order_by("-lock_date")
        )
        if purchase_locks:
            effective_lock = purchase_locks[0]
            reasons.append(
                f"Purchase period locked up to {effective_lock.lock_date.isoformat()}: "
                f"{(effective_lock.reason or 'Purchase lock active').strip()}"
            )
            lock_dates.append(effective_lock.lock_date)

        fy = PurchaseInvoiceService._resolve_financial_year(entity_id, entityfinid_id, original_bill_date)
        if fy is not None:
            fy_label = (getattr(fy, "desc", None) or getattr(fy, "year_code", None) or str(fy.id))
            if bool(getattr(fy, "is_year_closed", False)) or getattr(fy, "period_status", None) == EntityFinancialYear.PeriodStatus.CLOSED:
                reasons.append(f"Financial year {fy_label} is closed.")
                fy_end = getattr(getattr(fy, "finendyear", None), "date", lambda: None)()
                if fy_end:
                    lock_dates.append(fy_end)

            for attr, label in (
                ("books_locked_until", "Books"),
                ("gst_locked_until", "GST"),
                ("inventory_locked_until", "Inventory"),
                ("ap_ar_locked_until", "AP/AR"),
            ):
                cutoff = getattr(fy, attr, None)
                if cutoff and original_bill_date <= cutoff:
                    reasons.append(f"{label} locked up to {cutoff.isoformat()} in financial year {fy_label}.")
                    lock_dates.append(cutoff)

        if not reasons:
            return AmendmentWindow(
                amendment_required=False,
                reasons=(),
                lock_until=None,
                correction_date=None,
                gst_period=None,
            )

        today = timezone.localdate()
        correction_date = today
        lock_until = max(lock_dates) if lock_dates else original_bill_date
        if correction_date <= lock_until:
            correction_date = lock_until + timedelta(days=1)

        if fy is not None:
            fy_start = getattr(getattr(fy, "finstartyear", None), "date", lambda: None)()
            fy_end = getattr(getattr(fy, "finendyear", None), "date", lambda: None)()
            if fy_start and correction_date < fy_start:
                correction_date = fy_start
            if fy_end and correction_date > fy_end:
                correction_date = None

        return AmendmentWindow(
            amendment_required=True,
            reasons=tuple(reasons),
            lock_until=lock_until,
            correction_date=correction_date,
            gst_period=correction_date.strftime("%Y-%m") if correction_date else None,
        )

    @staticmethod
    def amendment_window_for_header(header: PurchaseInvoiceHeader) -> AmendmentWindow:
        return PurchaseInvoiceService._build_amendment_window(
            entity_id=header.entity_id,
            subentity_id=header.subentity_id,
            entityfinid_id=header.entityfinid_id,
            original_bill_date=header.bill_date,
        )

    @staticmethod
    def assert_note_correction_date_open(
        *,
        ref_document: PurchaseInvoiceHeader,
        correction_date: date,
    ) -> AmendmentWindow:
        window = PurchaseInvoiceService.amendment_window_for_header(ref_document)
        if not correction_date:
            raise ValueError("Correction document date is required.")
        if window.lock_until and correction_date <= window.lock_until:
            raise ValueError(
                "Correction document date must be in a current open period after "
                f"{window.lock_until.isoformat()}."
            )
        fy = PurchaseInvoiceService._resolve_financial_year(
            ref_document.entity_id,
            ref_document.entityfinid_id,
            ref_document.bill_date,
        )
        if fy is not None:
            fy_start = getattr(getattr(fy, "finstartyear", None), "date", lambda: None)()
            fy_end = getattr(getattr(fy, "finendyear", None), "date", lambda: None)()
            if fy_start and correction_date < fy_start:
                raise ValueError(
                    f"Correction document date must be on or after {fy_start.isoformat()} for the selected financial year."
                )
            if fy_end and correction_date > fy_end:
                raise ValueError(
                    f"Correction document date must be on or before {fy_end.isoformat()} for the selected financial year."
                )
        return window

    @staticmethod
    def blocked_edit_message(header: PurchaseInvoiceHeader) -> str:
        window = PurchaseInvoiceService.amendment_window_for_header(header)
        if window.amendment_required:
            return (
                "Purchase invoice belongs to a locked/filed period. Direct edits are blocked. "
                "Create a current-period purchase return, credit note, debit note, or reversal document instead."
            )
        return (
            "Posted purchase invoice cannot be edited. "
            "Create a purchase return, credit note, debit note, or reversal document instead."
        )

    @staticmethod
    def assert_not_locked(entity_id, subentity_id, bill_date, entityfinid_id=None):
        locked, reason = PurchaseSettingsService.is_locked(entity_id, subentity_id, bill_date)
        if locked:
            raise ValueError(f"Purchase period locked. {reason}")
        window = PurchaseInvoiceService._build_amendment_window(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            original_bill_date=bill_date,
        )
        if window.amendment_required:
            joined = " ".join(window.reasons)
            raise ValueError(f"Purchase period locked. {joined}")

    @staticmethod
    def append_correction_audit_event(
        *,
        original: PurchaseInvoiceHeader,
        correction: PurchaseInvoiceHeader,
        correction_type: str,
        reason: Optional[str],
        user_id: Optional[int],
        gst_period_impact: Optional[str],
    ) -> None:
        event = {
            "original_invoice_id": original.id,
            "correction_document_id": correction.id,
            "user_id": user_id,
            "timestamp": timezone.now().isoformat(),
            "reason": (reason or "").strip() or None,
            "correction_type": correction_type,
            "gst_period_impact": gst_period_impact,
            "old_value": {
                "bill_date": original.bill_date.isoformat() if original.bill_date else None,
                "posting_date": original.posting_date.isoformat() if getattr(original, "posting_date", None) else None,
                "grand_total": str(q2(getattr(original, "grand_total", ZERO2) or ZERO2)),
                "itc_claim_status": int(getattr(original, "itc_claim_status", ItcClaimStatus.PENDING)),
                "is_reverse_charge": bool(getattr(original, "is_reverse_charge", False)),
            },
            "new_value": {
                "bill_date": correction.bill_date.isoformat() if correction.bill_date else None,
                "posting_date": correction.posting_date.isoformat() if getattr(correction, "posting_date", None) else None,
                "grand_total": str(q2(getattr(correction, "grand_total", ZERO2) or ZERO2)),
                "itc_claim_status": int(getattr(correction, "itc_claim_status", ItcClaimStatus.PENDING)),
                "is_reverse_charge": bool(getattr(correction, "is_reverse_charge", False)),
            },
        }

        original_notes = dict(getattr(original, "match_notes", {}) or {})
        original_history = list(original_notes.get("correction_history") or [])
        original_history.append(event)
        original_notes["correction_history"] = original_history
        original.match_notes = original_notes
        original.save(update_fields=["match_notes"])

        correction_notes = dict(getattr(correction, "match_notes", {}) or {})
        correction_notes["correction_origin"] = event
        correction.match_notes = correction_notes
        correction.save(update_fields=["match_notes"])

    @staticmethod
    def _set_tds_runtime_snapshot(
        *,
        header: PurchaseInvoiceHeader,
        mode: str,
        enabled: bool,
        reason: Optional[str],
        reason_code: Optional[str],
    ) -> None:
        notes = dict(getattr(header, "match_notes", {}) or {})
        if not enabled:
            notes.pop("withholding_runtime_result", None)
            header.match_notes = notes
            return

        section = getattr(header, "tds_section", None)
        amount = q2(getattr(header, "tds_amount", ZERO2) or ZERO2)
        base_amount = q2(getattr(header, "tds_base_amount", ZERO2) or ZERO2)
        rate = q4(getattr(header, "tds_rate", ZERO4) or ZERO4)

        notes["withholding_runtime_result"] = {
            "enabled": True,
            "mode": str(mode or "AUTO").upper().strip(),
            "section_id": getattr(section, "id", None) if section is not None else None,
            "section_code": str(getattr(section, "section_code", "") or "").strip().upper() or None,
            "rate": str(rate),
            "base_amount": str(base_amount),
            "amount": str(amount),
            "reason": (str(reason or "").strip() or None),
            "reason_code": (str(reason_code or "").strip().upper() or None),
            "deduction_status": "DEDUCTED" if amount > ZERO2 else "NOT_DEDUCTED",
            "zero_deduction": bool(amount <= ZERO2),
            "user_selected_add_tds": bool(getattr(header, "withholding_enabled", False)),
        }
        header.match_notes = notes

    @staticmethod
    def _set_gst_tds_runtime_snapshot(
        *,
        header: PurchaseInvoiceHeader,
        mode: str,
        enabled: bool,
        reason: Optional[str],
        reason_code: Optional[str],
    ) -> None:
        notes = dict(getattr(header, "match_notes", {}) or {})
        if not enabled:
            notes.pop("gst_tds_runtime_result", None)
            header.match_notes = notes
            return

        amount = q2(getattr(header, "gst_tds_amount", ZERO2) or ZERO2)
        base_amount = q2(getattr(header, "gst_tds_base_amount", ZERO2) or ZERO2)
        rate = q4(getattr(header, "gst_tds_rate", ZERO4) or ZERO4)

        notes["gst_tds_runtime_result"] = {
            "enabled": True,
            "mode": str(mode or "AUTO").upper().strip(),
            "contract_ref": normalize_contract_ref(getattr(header, "gst_tds_contract_ref", "")) or None,
            "rate": str(rate),
            "base_amount": str(base_amount),
            "amount": str(amount),
            "cgst_amount": str(q2(getattr(header, "gst_tds_cgst_amount", ZERO2) or ZERO2)),
            "sgst_amount": str(q2(getattr(header, "gst_tds_sgst_amount", ZERO2) or ZERO2)),
            "igst_amount": str(q2(getattr(header, "gst_tds_igst_amount", ZERO2) or ZERO2)),
            "reason": (str(reason or "").strip() or None),
            "reason_code": (str(reason_code or "").strip().upper() or None),
            "deduction_status": "DEDUCTED" if amount > ZERO2 else "NOT_DEDUCTED",
            "zero_deduction": bool(amount <= ZERO2),
            "user_selected_add_gst_tds": bool(getattr(header, "gst_tds_enabled", False)),
        }
        header.match_notes = notes
        
    @staticmethod
    def _apply_gst_tds(*, header: PurchaseInvoiceHeader) -> None:
        """
        GST-TDS u/s 51.
        - If gst_tds_enabled = False -> clear all.
        - If gst_tds_enabled = True:
            - contract_ref required
            - If gst_tds_is_manual = True -> accept user values (validated)
            - Else -> compute from totals + tax_regime/is_igst (existing logic)
        """
        if not getattr(header, "gst_tds_enabled", False):
            header.gst_tds_is_manual = False
            header.gst_tds_contract_ref = normalize_contract_ref(getattr(header, "gst_tds_contract_ref", ""))
            header.gst_tds_reason = (getattr(header, "gst_tds_reason", None) or None)
            header.gst_tds_rate = q4(Decimal("0.0000"))
            header.gst_tds_base_amount = q2(ZERO2)
            header.gst_tds_cgst_amount = q2(ZERO2)
            header.gst_tds_sgst_amount = q2(ZERO2)
            header.gst_tds_igst_amount = q2(ZERO2)
            header.gst_tds_amount = q2(ZERO2)
            header.gst_tds_status = getattr(header.GstTdsStatus, "NA", 0)  # NA
            PurchaseInvoiceService._set_gst_tds_runtime_snapshot(
                header=header,
                mode="AUTO",
                enabled=False,
                reason=None,
                reason_code=None,
            )
            return

        # contract ref required
        contract_ref = normalize_contract_ref(getattr(header, "gst_tds_contract_ref", ""))
        header.gst_tds_contract_ref = contract_ref
        if not contract_ref:
            header.gst_tds_reason = "contract ref missing"
            PurchaseInvoiceService._set_gst_tds_runtime_snapshot(
                header=header,
                mode="AUTO",
                enabled=True,
                reason=header.gst_tds_reason,
                reason_code="CONTRACT_REF_MISSING",
            )
            return  # keep NA (or raise in serializer)

        # base must be taxable value (excluding GST)
        taxable = q2(getattr(header, "total_taxable", None) or ZERO2)
        if taxable <= ZERO2:
            header.gst_tds_reason = "taxable base zero"
            PurchaseInvoiceService._set_gst_tds_runtime_snapshot(
                header=header,
                mode="AUTO",
                enabled=True,
                reason=header.gst_tds_reason,
                reason_code="BASE_ZERO",
            )
            return

        is_inter = (int(getattr(header, "tax_regime", 1)) == int(header.TaxRegime.INTER)) or bool(getattr(header, "is_igst", False))

        # ----------------------------
        # ✅ MANUAL MODE
        # ----------------------------
        if bool(getattr(header, "gst_tds_is_manual", False)):
            rate = q4(getattr(header, "gst_tds_rate", None) or Decimal("0.0000"))
            base = q2(getattr(header, "gst_tds_base_amount", None) or ZERO2)

            cgst = q2(getattr(header, "gst_tds_cgst_amount", None) or ZERO2)
            sgst = q2(getattr(header, "gst_tds_sgst_amount", None) or ZERO2)
            igst = q2(getattr(header, "gst_tds_igst_amount", None) or ZERO2)
            total = q2(getattr(header, "gst_tds_amount", None) or ZERO2)

            if min(rate, base, cgst, sgst, igst, total) < ZERO2:
                raise ValueError("Manual GST-TDS values cannot be negative.")

            # base cannot exceed taxable (tolerance)
            if (base - taxable) > GST_TDS_TOLERANCE:
                raise ValueError("Manual GST-TDS base cannot exceed invoice taxable total.")

            # Validate split rules
            split_sum = q2(cgst + sgst + igst)
            if (total - split_sum).copy_abs() > GST_TDS_TOLERANCE:
                raise ValueError(f"GST-TDS total must equal CGST+SGST+IGST. Got {total} vs {split_sum}.")

            if is_inter:
                # Inter: IGST only
                if (cgst > GST_TDS_TOLERANCE) or (sgst > GST_TDS_TOLERANCE):
                    raise ValueError("For INTER/IGST GST-TDS, CGST/SGST must be 0.")
                if (igst - total).copy_abs() > GST_TDS_TOLERANCE:
                    raise ValueError("For INTER/IGST GST-TDS, IGST must equal total.")
            else:
                # Intra: CGST & SGST only, equal split (within tolerance)
                if igst > GST_TDS_TOLERANCE:
                    raise ValueError("For INTRA GST-TDS, IGST must be 0.")
                if (cgst - sgst).copy_abs() > GST_TDS_TOLERANCE:
                    raise ValueError("For INTRA GST-TDS, CGST and SGST must be equal.")

            # Optional formula check: total ~= base * rate / 100
            expected = q2(base * rate / Decimal("100.00"))
            if (total - expected).copy_abs() > GST_TDS_TOLERANCE:
                raise ValueError(f"GST-TDS amount mismatch. Expected {expected} for base {base} at rate {rate}.")

            header.gst_tds_status = getattr(header.GstTdsStatus, "ELIGIBLE", 1)
            PurchaseInvoiceService._set_gst_tds_runtime_snapshot(
                header=header,
                mode="MANUAL",
                enabled=True,
                reason=(getattr(header, "gst_tds_reason", "") or "").strip() or "MANUAL",
                reason_code="MANUAL" if total > ZERO2 else "MANUAL_ZERO_AMOUNT",
            )
            return

        # ----------------------------
        # ✅ AUTO MODE (source of truth from gst_tds app)
        # ----------------------------
        # Clear stale manual values before auto compute.
        header.gst_tds_rate = q4(Decimal("0.0000"))
        header.gst_tds_base_amount = q2(ZERO2)
        header.gst_tds_cgst_amount = q2(ZERO2)
        header.gst_tds_sgst_amount = q2(ZERO2)
        header.gst_tds_igst_amount = q2(ZERO2)
        header.gst_tds_amount = q2(ZERO2)
        header.gst_tds_status = getattr(header.GstTdsStatus, "NA", 0)
        res = GstTdsService.apply_to_header(header)
        PurchaseInvoiceService._set_gst_tds_runtime_snapshot(
            header=header,
            mode="AUTO",
            enabled=True,
            reason=res.reason,
            reason_code=res.reason_code,
        )

    @staticmethod
    def _apply_vendor_withholding_variance_policy(*, header: PurchaseInvoiceHeader) -> None:
        """
        Compare vendor-declared withholding values against system-computed values.
        Policy keys:
          - vendor_tds_variance_rule: off|warn|hard
          - vendor_gst_tds_variance_rule: off|warn|hard
        """
        policy = PurchaseSettingsService.get_policy(header.entity_id, header.subentity_id)
        warnings: list[str] = []

        def _check(rule_key: str, msg: str) -> None:
            level = policy.level(rule_key, "warn")
            if level == "off":
                return
            if level == "hard":
                raise ValueError(msg)
            warnings.append(msg)

        if bool(getattr(header, "vendor_tds_declared", False)) and bool(getattr(header, "withholding_enabled", False)):
            vb = q2(getattr(header, "vendor_tds_base_amount", ZERO2) or ZERO2)
            vr = q4(getattr(header, "vendor_tds_rate", Decimal("0.0000")) or Decimal("0.0000"))
            va = q2(getattr(header, "vendor_tds_amount", ZERO2) or ZERO2)
            sb = q2(getattr(header, "tds_base_amount", ZERO2) or ZERO2)
            sr = q4(getattr(header, "tds_rate", Decimal("0.0000")) or Decimal("0.0000"))
            sa = q2(getattr(header, "tds_amount", ZERO2) or ZERO2)
            if (vb - sb).copy_abs() > TDS_TOLERANCE or (vr - sr).copy_abs() > Decimal("0.0001") or (va - sa).copy_abs() > TDS_TOLERANCE:
                _check(
                    "vendor_tds_variance_rule",
                    f"Vendor IT-TDS differs from system values (vendor: base={vb}, rate={vr}, amount={va}; system: base={sb}, rate={sr}, amount={sa}).",
                )

        if bool(getattr(header, "vendor_gst_tds_declared", False)) and bool(getattr(header, "gst_tds_enabled", False)):
            vb = q2(getattr(header, "vendor_gst_tds_base_amount", ZERO2) or ZERO2)
            vr = q4(getattr(header, "vendor_gst_tds_rate", Decimal("0.0000")) or Decimal("0.0000"))
            vc = q2(getattr(header, "vendor_gst_tds_cgst_amount", ZERO2) or ZERO2)
            vs = q2(getattr(header, "vendor_gst_tds_sgst_amount", ZERO2) or ZERO2)
            vi = q2(getattr(header, "vendor_gst_tds_igst_amount", ZERO2) or ZERO2)
            vt = q2(getattr(header, "vendor_gst_tds_amount", ZERO2) or ZERO2)

            sb = q2(getattr(header, "gst_tds_base_amount", ZERO2) or ZERO2)
            sr = q4(getattr(header, "gst_tds_rate", Decimal("0.0000")) or Decimal("0.0000"))
            sc = q2(getattr(header, "gst_tds_cgst_amount", ZERO2) or ZERO2)
            ss = q2(getattr(header, "gst_tds_sgst_amount", ZERO2) or ZERO2)
            si = q2(getattr(header, "gst_tds_igst_amount", ZERO2) or ZERO2)
            st = q2(getattr(header, "gst_tds_amount", ZERO2) or ZERO2)

            if (
                (vb - sb).copy_abs() > GST_TDS_TOLERANCE
                or (vr - sr).copy_abs() > Decimal("0.0001")
                or (vc - sc).copy_abs() > GST_TDS_TOLERANCE
                or (vs - ss).copy_abs() > GST_TDS_TOLERANCE
                or (vi - si).copy_abs() > GST_TDS_TOLERANCE
                or (vt - st).copy_abs() > GST_TDS_TOLERANCE
            ):
                _check(
                    "vendor_gst_tds_variance_rule",
                    (
                        "Vendor GST-TDS differs from system values "
                        f"(vendor: base={vb}, rate={vr}, c={vc}, s={vs}, i={vi}, total={vt}; "
                        f"system: base={sb}, rate={sr}, c={sc}, s={ss}, i={si}, total={st})."
                    ),
                )

        notes = dict(getattr(header, "match_notes", {}) or {})
        if warnings:
            notes["withholding_warnings"] = warnings
            if str(getattr(header, "match_status", "na")).lower() == "na":
                header.match_status = getattr(header.MatchStatus, "WARN", "warn")
        else:
            notes.pop("withholding_warnings", None)
        header.match_notes = notes

    # ---------------------------
    # Vendor snapshot
    # ---------------------------

    @staticmethod
    def apply_dates(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        bill_date = attrs.get("bill_date") or (instance.bill_date if instance else None)

        # posting_date default
        if bill_date and not (attrs.get("posting_date") or (instance.posting_date if instance else None)):
            attrs["posting_date"] = bill_date

        # due_date derivation
        credit_days = attrs.get("credit_days")
        existing_due = instance.due_date if instance else None

        if bill_date:
            if attrs.get("due_date") is None:
                # if credit_days provided, derive
                if credit_days is not None:
                    attrs["due_date"] = bill_date + timedelta(days=int(credit_days))
                else:
                    # keep existing if update
                    if existing_due:
                        attrs["due_date"] = existing_due

        # validations
        if bill_date and attrs.get("due_date") and attrs["due_date"] < bill_date:
            raise ValueError("Due date cannot be before bill date.")

        if bill_date and attrs.get("posting_date") and attrs["posting_date"] < bill_date:
            raise ValueError("Posting date cannot be before bill date.")
    @staticmethod
    def validate_vendor_account(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        vendor = attrs.get("vendor") or (instance.vendor if instance else None)
        if not vendor:
            return

        entity_obj = attrs.get("entity") or (instance.entity if instance else None)
        subentity_obj = attrs.get("subentity") or (instance.subentity if instance else None)
        entity_id = getattr(entity_obj, "id", entity_obj)
        subentity_id = getattr(subentity_obj, "id", subentity_obj)
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id) if entity_id else None
        controls = getattr(policy, "controls", {}) if policy else {}

        def _level(key: str, default: str = "hard") -> str:
            raw = str((controls or {}).get(key, default)).strip().lower()
            return raw if raw in {"off", "warn", "hard"} else default

        def _handle(level: str, field: str, message: str) -> None:
            if level == "hard":
                raise ValueError(message)
            if level == "warn":
                notes = dict(attrs.get("match_notes") or (getattr(instance, "match_notes", {}) if instance else {}) or {})
                warnings = list(notes.get("compliance_warnings") or [])
                warnings.append(message)
                notes["compliance_warnings"] = warnings
                attrs["match_notes"] = notes
                if str(attrs.get("match_status") or (getattr(instance, "match_status", "na") if instance else "na")).lower() == "na":
                    attrs["match_status"] = getattr(PurchaseInvoiceHeader.MatchStatus, "WARN", "warn")

        partytype = (account_partytype(vendor) or "").strip()
        allowed_partytypes = {"", "Vendor", "Both", "Bank"}
        if partytype not in allowed_partytypes:
            raise ValueError("Selected vendor account is not marked as Vendor/Both/Bank.")

        if hasattr(vendor, "isactive") and vendor.isactive is False:
            raise ValueError("Selected vendor account is inactive.")

        if not getattr(vendor, "ledger_id", None):
            raise ValueError("Selected vendor account does not have a linked ledger.")

        compliance = account_compliance_profile(vendor)
        gstregtype = str(getattr(compliance, "gstregtype", "") or "").strip()
        registered_types = {"Regular", "Composition", "SEZ", "UIN"}

        gstin_level = _level("vendor_gstin_format_rule", "hard")
        raw_gstin = (
            attrs.get("vendor_gstin")
            or (instance.vendor_gstin if instance else None)
            or account_gstno(vendor)
            or ""
        )
        gstin = str(raw_gstin or "").strip().upper()
        if gstregtype in registered_types and not gstin:
            raise ValueError(f"Vendor GSTIN is required for {gstregtype.lower()} vendors.")
        if gstin:
            try:
                attrs["vendor_gstin"] = validate_financial_gstin(gstin)
            except DjangoValidationError:
                _handle(gstin_level, "vendor_gstin", "Vendor GSTIN format is invalid.")

        if compliance is not None and hasattr(compliance, "isactive") and compliance.isactive is False:
            _handle(_level("vendor_gstin_active_rule", "warn"), "vendor_gstin", "Vendor GSTIN is marked inactive.")

        withholding_enabled = bool(attrs.get("withholding_enabled", getattr(instance, "withholding_enabled", False)))
        if withholding_enabled:
            pan_required_level = _level("withholding_pan_required_rule", "hard")
            pan_format_level = _level("withholding_pan_format_rule", "hard")
            pan = str(account_pan(vendor) or "").strip().upper()
            if not pan:
                _handle(
                    pan_required_level,
                    "vendor_pan",
                    "Vendor PAN is required when Income-tax TDS is enabled.",
                )
            elif not PAN_RE.fullmatch(pan):
                _handle(
                    pan_format_level,
                    "vendor_pan",
                    "Vendor PAN format is invalid for Income-tax TDS.",
                )

    @staticmethod
    def apply_vendor_ledger(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        vendor = attrs.get("vendor") or (instance.vendor if instance else None)
        if vendor:
            attrs["vendor_ledger_id"] = getattr(vendor, "ledger_id", None)

    @staticmethod
    def apply_vendor_snapshot(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        vendor = attrs.get("vendor") or (instance.vendor if instance else None)
        if not vendor:
            return

        if not (attrs.get("vendor_name") or (instance.vendor_name if instance else None)):
            attrs["vendor_name"] = (getattr(vendor, "effective_accounting_name", None) or getattr(vendor, "accountname", None) or str(vendor)).strip()[:200]

        if not (attrs.get("vendor_gstin") or (instance.vendor_gstin if instance else None)):
            gstno = account_gstno(vendor)
            if gstno:
                attrs["vendor_gstin"] = str(gstno).strip()[:15]

        if not (attrs.get("vendor_state") or (instance.vendor_state if instance else None)):
            st = getattr(vendor, "state", None)
            if st:
                attrs["vendor_state"] = st

    @staticmethod
    def is_unregistered_vendor(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> bool:
        gstin = attrs.get("vendor_gstin", (instance.vendor_gstin if instance else None))
        return not bool(str(gstin or "").strip())

    @staticmethod
    def vendor_gst_registration_type(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> str:
        vendor = attrs.get("vendor") or (instance.vendor if instance else None)
        if not vendor:
            return ""
        compliance = account_compliance_profile(vendor)
        return str(getattr(compliance, "gstregtype", "") or "").strip()

    @staticmethod
    def supply_category_value(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> int:
        return int(
            attrs.get(
                "supply_category",
                (instance.supply_category if instance else PurchaseInvoiceHeader.SupplyCategory.DOMESTIC),
            )
        )

    @staticmethod
    def is_composition_vendor(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> bool:
        return PurchaseInvoiceService.vendor_gst_registration_type(attrs, instance=instance).lower() == "composition"

    @staticmethod
    def is_import_goods_supply(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> bool:
        return PurchaseInvoiceService.supply_category_value(attrs, instance=instance) == int(
            PurchaseInvoiceHeader.SupplyCategory.IMPORT_GOODS
        )

    @staticmethod
    def is_import_services_supply(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> bool:
        return PurchaseInvoiceService.supply_category_value(attrs, instance=instance) == int(
            PurchaseInvoiceHeader.SupplyCategory.IMPORT_SERVICES
        )

    @staticmethod
    def is_sez_supply(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> bool:
        return PurchaseInvoiceService.supply_category_value(attrs, instance=instance) == int(
            PurchaseInvoiceHeader.SupplyCategory.SEZ
        )

    @staticmethod
    def should_suppress_supplier_gst(
        *,
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> bool:
        is_rcm = bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False)))
        if is_rcm:
            return True
        if PurchaseInvoiceService.is_unregistered_vendor(attrs, instance=instance):
            return True
        if PurchaseInvoiceService.is_composition_vendor(attrs, instance=instance):
            return True
        if PurchaseInvoiceService.is_import_goods_supply(attrs, instance=instance):
            return True
        if PurchaseInvoiceService.is_import_services_supply(attrs, instance=instance):
            return True
        return False

    @staticmethod
    def supplier_gst_suppression_reason(
        *,
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> str:
        if bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False))):
            return (
                "This purchase is marked as reverse charge, so supplier-billed GST amounts must be 0 on the invoice line. "
                "Keep the GST rate for tax basis if needed, but do not enter CGST/SGST/IGST amounts from the supplier invoice."
            )
        if PurchaseInvoiceService.is_unregistered_vendor(attrs, instance=instance):
            return (
                "This vendor is treated as unregistered, so supplier-billed GST amounts are not allowed on the invoice line. "
                "Set CGST/SGST/IGST amounts to 0, or use a registered vendor / reverse-charge purchase if that is the intended case."
            )
        if PurchaseInvoiceService.is_composition_vendor(attrs, instance=instance):
            return (
                "This vendor is treated as a composition vendor, so supplier-billed GST amounts are not allowed on the invoice line. "
                "Set CGST/SGST/IGST amounts to 0 for this bill."
            )
        if PurchaseInvoiceService.is_import_goods_supply(attrs, instance=instance):
            return (
                "This purchase is classified as import of goods, so supplier-billed GST amounts are not allowed on the invoice line. "
                "Enter the import bill without supplier GST amounts and use the import / bill-of-entry flow for credit handling."
            )
        if PurchaseInvoiceService.is_import_services_supply(attrs, instance=instance):
            return (
                "This purchase is classified as import of services, so supplier-billed GST amounts are not allowed on the invoice line. "
                "Use the reverse-charge flow instead of entering supplier CGST/SGST/IGST amounts."
            )
        return (
            "Supplier-billed GST amounts are not allowed for this purchase tax treatment. "
            "Set CGST/SGST/IGST amounts to 0 and use the correct registered / reverse-charge / import flow for this bill."
        )

    @staticmethod
    def apply_unregistered_vendor_defaults(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> None:
        if not PurchaseInvoiceService.is_unregistered_vendor(attrs, instance=instance):
            return

        is_rcm = bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False)))
        if is_rcm:
            return

        attrs["is_itc_eligible"] = False
        if not str(attrs.get("itc_block_reason", (instance.itc_block_reason if instance else "")) or "").strip():
            attrs["itc_block_reason"] = "ITC not eligible for unregistered vendor purchase."

        claimed_status = int(
            attrs.get(
                "itc_claim_status",
                (instance.itc_claim_status if instance else ItcClaimStatus.PENDING),
            )
        )
        if claimed_status == int(ItcClaimStatus.CLAIMED):
            raise ValueError("Cannot claim ITC on an unregistered vendor purchase unless reverse charge applies.")

    @staticmethod
    def apply_special_tax_treatment_defaults(
        attrs: Dict[str, Any],
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> None:
        PurchaseInvoiceService.apply_unregistered_vendor_defaults(attrs, instance=instance)

        is_rcm = bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False)))
        claimed_status = int(
            attrs.get(
                "itc_claim_status",
                (instance.itc_claim_status if instance else ItcClaimStatus.PENDING),
            )
        )

        if PurchaseInvoiceService.is_composition_vendor(attrs, instance=instance) and not is_rcm:
            attrs["is_itc_eligible"] = False
            if not str(attrs.get("itc_block_reason", (instance.itc_block_reason if instance else "")) or "").strip():
                attrs["itc_block_reason"] = "ITC not eligible for composition vendor purchase."
            if claimed_status == int(ItcClaimStatus.CLAIMED):
                raise ValueError("Cannot claim ITC on a composition vendor purchase.")

        if PurchaseInvoiceService.is_import_goods_supply(attrs, instance=instance):
            attrs["is_itc_eligible"] = False
            attrs["itc_block_reason"] = "Import goods ITC should be claimed through customs or bill-of-entry flow."
            if claimed_status == int(ItcClaimStatus.CLAIMED):
                raise ValueError("Cannot claim ITC from import goods supplier invoice directly.")

        if PurchaseInvoiceService.is_import_services_supply(attrs, instance=instance) and not is_rcm:
            raise ValueError("Import of services purchases must be marked as reverse charge.")

    # ---------------------------
    # Tax regime derivation
    # ---------------------------
    @staticmethod
    def derive_tax_regime(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> DerivedRegime:
        entity_id = attrs.get("entity") or (instance.entity_id if instance else None)
        subentity_id = attrs.get("subentity") or (instance.subentity_id if instance else None)
        if hasattr(entity_id, "id"):
            entity_id = entity_id.id
        if hasattr(subentity_id, "id"):
            subentity_id = subentity_id.id

        auto_derive = True
        if entity_id:
            try:
                auto_derive = PurchaseSettingsService.get_policy(entity_id, subentity_id).auto_derive_tax_regime
            except Exception:
                auto_derive = True

        tax_regime = attrs.get("tax_regime", (instance.tax_regime if instance else int(TaxRegime.INTRA)))
        is_igst = attrs.get("is_igst", (instance.is_igst if instance else int(tax_regime) == int(TaxRegime.INTER)))

        if not auto_derive:
            return DerivedRegime(tax_regime=int(tax_regime), is_igst=bool(is_igst))

        vendor_state = attrs.get("vendor_state") or (instance.vendor_state if instance else None)
        pos_state = attrs.get("place_of_supply_state") or (instance.place_of_supply_state if instance else None)
        supplier_state = attrs.get("supplier_state") or (instance.supplier_state if instance else None)

        compare_state = pos_state or supplier_state

        if vendor_state and compare_state and getattr(vendor_state, "id", None) and getattr(compare_state, "id", None):
            if vendor_state.id == compare_state.id:
                return DerivedRegime(tax_regime=int(TaxRegime.INTRA), is_igst=False)
            return DerivedRegime(tax_regime=int(TaxRegime.INTER), is_igst=True)
        return DerivedRegime(tax_regime=int(tax_regime), is_igst=bool(is_igst))

    # ---------------------------
    # Validations (structure-level)
    # ---------------------------
    @staticmethod
    def validate_header(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        PurchaseInvoiceService.validate_vendor_account(attrs, instance=instance)
        PurchaseInvoiceService.apply_vendor_ledger(attrs, instance=instance)

        supplier_invoice_number = str(
            attrs.get("supplier_invoice_number", (instance.supplier_invoice_number if instance else "")) or ""
        ).strip()
        supplier_invoice_date = attrs.get(
            "supplier_invoice_date",
            (instance.supplier_invoice_date if instance else None),
        )
        if not supplier_invoice_number:
            raise ValueError("supplier_invoice_number is required.")
        if not supplier_invoice_date:
            raise ValueError("supplier_invoice_date is required.")

        supply_category = PurchaseInvoiceService.supply_category_value(attrs, instance=instance)
        tax_regime = int(attrs.get("tax_regime", (instance.tax_regime if instance else TaxRegime.INTRA)))
        place_of_supply_state = attrs.get("place_of_supply_state") or (instance.place_of_supply_state if instance else None)
        is_rcm = bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False)))

        if supply_category in {
            int(PurchaseInvoiceHeader.SupplyCategory.IMPORT_GOODS),
            int(PurchaseInvoiceHeader.SupplyCategory.IMPORT_SERVICES),
            int(PurchaseInvoiceHeader.SupplyCategory.SEZ),
        } and tax_regime != int(TaxRegime.INTER):
            raise ValueError("Import and SEZ purchases must use INTER tax regime.")

        if is_rcm and not place_of_supply_state:
            raise ValueError("place_of_supply_state is required for reverse charge purchases.")

        doc_type = attrs.get("doc_type", DocType.TAX_INVOICE)
        ref_document = attrs.get("ref_document") or (instance.ref_document if instance else None)

        if doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE) and not ref_document:
            raise ValueError("ref_document is required for Credit/Debit Note.")
        if doc_type == DocType.TAX_INVOICE and attrs.get("ref_document"):
            raise ValueError("Tax Invoice should not have ref_document.")
        if doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE) and ref_document:
            correction_bill_date = attrs.get("bill_date") or (instance.bill_date if instance else None)
            PurchaseInvoiceService.assert_note_correction_date_open(
                ref_document=ref_document,
                correction_date=correction_bill_date,
            )

        if instance:
            if int(instance.status) == int(Status.CANCELLED):
                raise ValueError("Cancelled document cannot be edited.")
            new_status = int(attrs.get("status", instance.status))
            if int(instance.status) == int(Status.POSTED) and new_status != int(Status.POSTED):
                raise ValueError("Posted document cannot be moved back to Draft/Confirmed.")

        currency_code = (attrs.get("currency_code") or (instance.currency_code if instance else "INR") or "INR").strip().upper()
        base_currency_code = (
            attrs.get("base_currency_code") or (instance.base_currency_code if instance else "INR") or "INR"
        ).strip().upper()
        exchange_rate = Decimal(attrs.get("exchange_rate", (instance.exchange_rate if instance else Decimal("1.000000"))) or Decimal("1.000000"))
        if len(currency_code) != 3:
            raise ValueError("currency_code must be 3 letters (ISO).")
        if len(base_currency_code) != 3:
            raise ValueError("base_currency_code must be 3 letters (ISO).")
        if exchange_rate <= 0:
            raise ValueError("exchange_rate must be > 0.")
        attrs["currency_code"] = currency_code
        attrs["base_currency_code"] = base_currency_code
        attrs["exchange_rate"] = exchange_rate

    @staticmethod
    def assert_no_duplicate_supplier_invoice(
        *,
        instance: Optional[PurchaseInvoiceHeader],
        attrs: Dict[str, Any],
        grand_total: Decimal,
    ) -> None:
        entity = attrs.get("entity") or (instance.entity if instance else None)
        vendor = attrs.get("vendor") or (instance.vendor if instance else None)
        supplier_invoice_number = str(
            attrs.get("supplier_invoice_number", (instance.supplier_invoice_number if instance else "")) or ""
        ).strip()
        supplier_invoice_date = attrs.get(
            "supplier_invoice_date",
            (instance.supplier_invoice_date if instance else None),
        )

        if not entity or not vendor or not supplier_invoice_number or not supplier_invoice_date:
            return

        entity_id = getattr(entity, "id", entity)
        vendor_id = getattr(vendor, "id", vendor)
        qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            vendor_id=vendor_id,
            supplier_invoice_number__iexact=supplier_invoice_number,
            supplier_invoice_date=supplier_invoice_date,
            grand_total=q2(grand_total),
        ).exclude(status=Status.CANCELLED)
        if instance is not None and getattr(instance, "id", None):
            qs = qs.exclude(pk=instance.id)
        if qs.exists():
            raise ValueError(
                "Duplicate supplier invoice detected for this vendor, invoice number, invoice date, and amount."
            )

    @staticmethod
    def validate_lines_structural(
        attrs: Dict[str, Any],
        lines: List[Dict[str, Any]],
        derived: DerivedRegime,
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> None:
        if not lines:
            raise ValueError("At least one line is required.")

        header_taxability = attrs.get(
            "default_taxability",
            (instance.default_taxability if instance else Taxability.TAXABLE),
        )
        is_rcm = bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False)))

        header_itc = bool(attrs.get("is_itc_eligible", (instance.is_itc_eligible if instance else True)))
        itc_claim_status = int(
            attrs.get("itc_claim_status", (instance.itc_claim_status if instance else ItcClaimStatus.PENDING))
        )

        if header_taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
            if header_itc:
                raise ValueError("ITC cannot be eligible for Exempt/Nil-rated/Non-GST header.")
            if itc_claim_status == int(ItcClaimStatus.CLAIMED):
                raise ValueError("Cannot claim ITC for Exempt/Nil-rated/Non-GST header.")

        if is_rcm and itc_claim_status == int(ItcClaimStatus.CLAIMED):
            raise ValueError("RCM ITC should be claimed only after RCM tax payment (track separately).")

        if PurchaseInvoiceService.is_composition_vendor(attrs, instance=instance):
            if header_itc:
                raise ValueError("ITC cannot be eligible for composition vendor purchase.")
            if itc_claim_status == int(ItcClaimStatus.CLAIMED):
                raise ValueError("Cannot claim ITC for composition vendor purchase.")

        if PurchaseInvoiceService.is_import_goods_supply(attrs, instance=instance) and header_itc:
            raise ValueError("Import goods supplier invoice cannot create normal ITC in this flow.")

        entity_id = attrs.get("entity") or (instance.entity_id if instance else None)
        subentity_id = attrs.get("subentity") or (instance.subentity_id if instance else None)
        if hasattr(entity_id, "id"):
            entity_id = entity_id.id
        if hasattr(subentity_id, "id"):
            subentity_id = subentity_id.id
        if entity_id:
            policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
            if not policy.allow_mixed_taxability:
                for i, ln in enumerate(lines or [], start=1):
                    line_taxability = int(ln.get("taxability", header_taxability))
                    if line_taxability != int(header_taxability):
                        raise ValueError(
                            f"Line {i}: mixed taxability is disabled by purchase settings. "
                            "Keep all purchase lines aligned with the header taxability."
                        )

        doc_type = int(attrs.get("doc_type", (instance.doc_type if instance else DocType.TAX_INVOICE)))
        ref_document = attrs.get("ref_document") or (instance.ref_document if instance else None)
        note_reason = str(attrs.get("note_reason", (instance.note_reason if instance else "")) or "").strip()
        current_location = (
            attrs.get("location")
            or (instance.location if instance else None)
            or (ref_document.location if ref_document else None)
        )
        original_line_qty_by_line_no: Dict[int, Decimal] = {}
        consumed_qty_by_line_no: Dict[int, Decimal] = {}
        inventory_safe_return_base_by_key: Dict[tuple[int, str, int], Decimal] = {}
        inventory_return_requested_by_key: Dict[tuple[int, str, int], Decimal] = {}
        if (
            doc_type in (int(DocType.CREDIT_NOTE), int(DocType.DEBIT_NOTE))
            and ref_document is not None
            and note_reason == PurchaseInvoiceHeader.NoteReason.QUANTITY_RETURN
        ):
            original_line_qty_by_line_no = {
                int(line.line_no): q4(line.qty)
                for line in ref_document.lines.all().order_by("line_no", "id")
            }
            note_qs = PurchaseInvoiceHeader.objects.filter(
                ref_document_id=ref_document.id,
                note_reason=PurchaseInvoiceHeader.NoteReason.QUANTITY_RETURN,
            ).exclude(status=Status.CANCELLED)
            if instance is not None and getattr(instance, "id", None):
                note_qs = note_qs.exclude(pk=instance.id)
            for qty_row in (
                PurchaseInvoiceLine.objects.filter(header_id__in=note_qs.values("id"))
                .values("line_no")
                .annotate(total_qty=Coalesce(Sum("qty"), ZERO4))
            ):
                consumed_qty_by_line_no[int(qty_row["line_no"])] = q4(qty_row["total_qty"])
            inventory_safe_return_base_by_key = PurchaseInvoiceService._inventory_safe_return_base_by_key(
                ref_document=ref_document,
                location=current_location,
            )

        # NOTE: we will validate amounts AFTER we compute authoritative values
        # Here we only check regime consistency if amounts were provided and obviously wrong.
        for i, ln in enumerate(lines, start=1):
            line_no = int(ln.get("line_no") or i)
            product_ref = ln.get("product")
            product_id = getattr(product_ref, "pk", product_ref)
            purchase_account_id = ln.get("purchase_account")
            product_desc = (ln.get("product_desc") or "").strip()
            requested_behavior = ln.get("purchase_behavior")
            if not product_id:
                if requested_behavior and requested_behavior != ProductPurchaseBehavior.EXPENSE:
                    raise ValueError(f"Line {i}: non-product purchase lines can only use expense behavior.")
                if not purchase_account_id:
                    raise ValueError(f"Line {i}: purchase_account is required when product is not provided.")
                if not product_desc:
                    raise ValueError(f"Line {i}: product_desc is required when product is not provided.")
                ln["is_service"] = bool(ln.get("is_service", True))
                ln["purchase_behavior"] = ProductPurchaseBehavior.EXPENSE

            # qty sanity
            qty = q4(ln.get("qty"))
            if qty <= 0:
                raise ValueError(f"Line {i}: qty must be > 0")
            if original_line_qty_by_line_no:
                original_qty = q4(original_line_qty_by_line_no.get(line_no, ZERO4))
                already_consumed = q4(consumed_qty_by_line_no.get(line_no, ZERO4))
                available_qty = q4(original_qty - already_consumed)
                if available_qty < ZERO4:
                    available_qty = ZERO4
                if qty > available_qty:
                    raise ValueError(
                        f"Line {i}: return quantity {qty} exceeds available returnable quantity {available_qty}."
                    )

            free_qty = q4(ln.get("free_qty", ZERO4))
            if free_qty < 0:
                raise ValueError(f"Line {i}: free_qty cannot be negative")

            if product_id:
                product = Product.objects.filter(pk=int(product_id)).only(
                    "id", "is_batch_managed", "is_expiry_tracked", "is_service", "purchase_behavior", "purchase_account_id", "default_asset_category_id"
                ).first()
                if product:
                    if bool(getattr(product, "is_service", False)):
                        ln["is_service"] = True
                        ln["purchase_behavior"] = ProductPurchaseBehavior.EXPENSE
                    else:
                        ln["purchase_behavior"] = (
                            ln.get("purchase_behavior")
                            or getattr(product, "purchase_behavior", ProductPurchaseBehavior.INVENTORY)
                            or ProductPurchaseBehavior.INVENTORY
                        )
                    batch_number = str(ln.get("batch_number") or "").strip()
                    manufacture_date = ln.get("manufacture_date") or None
                    expiry_date = ln.get("expiry_date") or None
                    if bool(getattr(product, "is_batch_managed", False)) and not batch_number:
                        raise ValueError(f"Line {i}: batch_number is required for batch-managed products.")
                    if bool(getattr(product, "is_expiry_tracked", False)) and expiry_date in (None, ""):
                        raise ValueError(f"Line {i}: expiry_date is required for expiry-tracked products.")
                    if manufacture_date and expiry_date and str(manufacture_date) > str(expiry_date):
                        raise ValueError(f"Line {i}: expiry_date must be on or after manufacture_date.")
                    if inventory_safe_return_base_by_key and not bool(getattr(product, "is_service", False)):
                        raw_behavior = (
                            ln.get("purchase_behavior")
                            or getattr(product, "purchase_behavior", ProductPurchaseBehavior.INVENTORY)
                            or ProductPurchaseBehavior.INVENTORY
                        )
                        if raw_behavior == ProductPurchaseBehavior.INVENTORY:
                            _, factor_to_base = resolve_product_uom(
                                product=product,
                                raw_uom_id=getattr(ln.get("uom"), "id", ln.get("uom")),
                            )
                            base_qty = q4(qty * q4(factor_to_base))
                            key = (
                                int(product.id),
                                str(ln.get("batch_number") or "").strip(),
                                PurchaseInvoiceService._return_validation_location_id(
                                    ref_document=ref_document,
                                    location=current_location,
                                ),
                            )
                            available_base_qty = q4(inventory_safe_return_base_by_key.get(key, ZERO4))
                            already_requested_base_qty = q4(inventory_return_requested_by_key.get(key, ZERO4))
                            remaining_safe_base_qty = q4(available_base_qty - already_requested_base_qty)
                            if remaining_safe_base_qty < ZERO4:
                                remaining_safe_base_qty = ZERO4
                            if base_qty > remaining_safe_base_qty:
                                raise ValueError(
                                    f"Line {i}: return quantity {qty} is no longer safely returnable because stock from "
                                    "the original purchase has already been consumed or moved out. Use a value-only note "
                                    "or inventory adjustment flow."
                                )
                            inventory_return_requested_by_key[key] = q4(already_requested_base_qty + base_qty)

            if bool(ln.get("is_service", False)) and ln.get("purchase_behavior") != ProductPurchaseBehavior.EXPENSE:
                ln["purchase_behavior"] = ProductPurchaseBehavior.EXPENSE

            if ln.get("purchase_behavior") == ProductPurchaseBehavior.EXPENSE:
                effective_purchase_account_id = purchase_account_id
                if not effective_purchase_account_id and product_id:
                    effective_purchase_account_id = getattr(product, "purchase_account_id", None) if product else None
                if not effective_purchase_account_id:
                    raise ValueError(
                        f"Line {i}: expense purchase lines require an expense/purchase account on the line or product."
                    )
            elif ln.get("purchase_behavior") == ProductPurchaseBehavior.ASSET:
                if not product_id:
                    raise ValueError(f"Line {i}: asset purchase lines must use a product with a default asset category.")
                if not getattr(product, "default_asset_category_id", None):
                    raise ValueError(
                        f"Line {i}: asset product is missing a default asset category."
                    )

            # discount sanity (if present)
            dt = (ln.get("discount_type") or "N")
            dp = q2(ln.get("discount_percent", ZERO2))
            da = q2(ln.get("discount_amount", ZERO2))
            if dt == "P" and not (ZERO2 <= dp <= Decimal("100.00")):
                raise ValueError(f"Line {i}: discount_percent must be 0..100")
            if dt == "A" and da < 0:
                raise ValueError(f"Line {i}: discount_amount cannot be negative")

            # regime consistency if client sent tax amounts
            cgst = q2(ln.get("cgst_amount"))
            sgst = q2(ln.get("sgst_amount"))
            igst = q2(ln.get("igst_amount"))

            if int(derived.tax_regime) == int(TaxRegime.INTRA) and igst > 0:
                raise ValueError(f"Line {i}: IGST not allowed for INTRA regime.")
            if int(derived.tax_regime) == int(TaxRegime.INTER) and (cgst > 0 or sgst > 0):
                raise ValueError(f"Line {i}: CGST/SGST not allowed for INTER regime.")

            if PurchaseInvoiceService.should_suppress_supplier_gst(attrs=attrs, instance=instance) and (cgst > 0 or sgst > 0 or igst > 0):
                raise ValueError(
                    f"Line {i}: "
                    f"{PurchaseInvoiceService.supplier_gst_suppression_reason(attrs=attrs, instance=instance)}"
                )

            if is_rcm and q2(ln.get("gst_rate", ZERO2)) <= ZERO2:
                raise ValueError(f"Line {i}: gst_rate is required for reverse charge purchases.")

    @staticmethod
    def _return_validation_location_id(
        *,
        ref_document: PurchaseInvoiceHeader,
        location,
    ) -> int | None:
        location_id = getattr(location, "id", location)
        return resolve_posting_location_id(
            entity_id=int(ref_document.entity_id),
            subentity_id=getattr(ref_document, "subentity_id", None),
            location_id=int(location_id) if location_id else None,
        )

    @staticmethod
    def _inventory_safe_return_base_by_key(
        *,
        ref_document: PurchaseInvoiceHeader,
        location,
    ) -> Dict[tuple[int, str, int], Decimal]:
        if int(getattr(ref_document, "status", 0) or 0) != int(Status.POSTED):
            return {}

        location_id = PurchaseInvoiceService._return_validation_location_id(
            ref_document=ref_document,
            location=location,
        )
        if not location_id:
            return {}

        posting_day = getattr(ref_document, "posting_date", None) or getattr(ref_document, "bill_date", None)
        if not posting_day:
            return {}

        source_base_qty_by_key: Dict[tuple[int, str, int], Decimal] = {}
        product_ids: set[int] = set()
        for src_line in ref_document.lines.select_related("product", "uom").order_by("line_no", "id"):
            product = getattr(src_line, "product", None)
            if not product or bool(getattr(src_line, "is_service", False)):
                continue
            purchase_behavior = (
                getattr(src_line, "purchase_behavior", None)
                or getattr(product, "purchase_behavior", ProductPurchaseBehavior.INVENTORY)
                or ProductPurchaseBehavior.INVENTORY
            )
            if purchase_behavior != ProductPurchaseBehavior.INVENTORY:
                continue
            _, factor_to_base = resolve_product_uom(
                product=product,
                raw_uom_id=getattr(src_line, "uom_id", None),
            )
            key = (
                int(src_line.product_id),
                str(getattr(src_line, "batch_number", "") or "").strip(),
                int(location_id),
            )
            source_base_qty_by_key[key] = q4(
                source_base_qty_by_key.get(key, ZERO4) + q4(q4(getattr(src_line, "qty", ZERO4)) * q4(factor_to_base))
            )
            product_ids.add(int(src_line.product_id))

        if not source_base_qty_by_key:
            return {}

        out_totals_by_key: Dict[tuple[int, str, int], Decimal] = {}
        out_rows = (
            InventoryMove.objects.filter(
                entity_id=int(ref_document.entity_id),
                location_id=int(location_id),
                product_id__in=product_ids,
                move_type=InventoryMove.MoveType.OUT,
                posting_date__gte=posting_day,
            )
            .values("product_id", "batch_number")
            .annotate(total_base_qty=Coalesce(Sum("base_qty"), ZERO4))
        )
        for row in out_rows:
            key = (
                int(row["product_id"]),
                str(row.get("batch_number") or "").strip(),
                int(location_id),
            )
            out_totals_by_key[key] = q4(row.get("total_base_qty") or ZERO4)

        safe_base_qty_by_key: Dict[tuple[int, str, int], Decimal] = {}
        for key, source_base_qty in source_base_qty_by_key.items():
            remaining_base_qty = q4(source_base_qty - q4(out_totals_by_key.get(key, ZERO4)))
            if remaining_base_qty < ZERO4:
                remaining_base_qty = ZERO4
            safe_base_qty_by_key[key] = remaining_base_qty
        return safe_base_qty_by_key

    # ---------------------------
    # Authoritative line compute (server)
    # ---------------------------
    @staticmethod
    def _discounted_amount(gross_ex_tax_or_incl: Decimal, dt: str, dp: Decimal, da: Decimal) -> Decimal:
        """
        gross_ex_tax_or_incl = gross amount based on entered rate (might be inclusive or exclusive).
        Apply discount on that gross.
        """
        dt = (dt or "N")
        dp = q2(dp)
        da = q2(da)

        if dt == "P":
            disc = q2(gross_ex_tax_or_incl * dp / Decimal("100"))
            return q2(gross_ex_tax_or_incl - disc)
        if dt == "A":
            disc = min(q2(gross_ex_tax_or_incl), q2(da))
            return q2(gross_ex_tax_or_incl - disc)
        return q2(gross_ex_tax_or_incl)

    @staticmethod
    def _split_gst(taxable_value: Decimal, gst_rate: Decimal, derived: DerivedRegime) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Returns (cgst, sgst, igst)
        """
        taxable_value = q2(taxable_value)
        gst_rate = q2(gst_rate)

        if gst_rate <= 0:
            return ZERO2, ZERO2, ZERO2

        tax_total = q2(taxable_value * gst_rate / Decimal("100"))

        if int(derived.tax_regime) == int(TaxRegime.INTRA):
            cgst = q2(tax_total / Decimal("2"))
            sgst = q2(tax_total - cgst)
            return cgst, sgst, ZERO2

        return ZERO2, ZERO2, tax_total

    @staticmethod
    def compute_line_authoritative(
        header_attrs: Dict[str, Any],
        line: Dict[str, Any],
        derived: DerivedRegime,
    ) -> Dict[str, Any]:
        """
        Returns a new dict with authoritative computed monetary fields.
        Keeps all non-monetary fields from input line.
        """
        ln = dict(line)
        purchase_behavior = (
            ln.get("purchase_behavior")
            or (ProductPurchaseBehavior.EXPENSE if bool(ln.get("is_service", False)) else ProductPurchaseBehavior.INVENTORY)
        )
        ln["purchase_behavior"] = purchase_behavior

        qty = q4(ln.get("qty"))
        rate = q2(ln.get("rate"))
        gst_rate = q2(ln.get("gst_rate", ZERO2))
        taxability = int(
            ln.get(
                "taxability",
                resolve_product_default_taxability(
                    product=ln.get("product") if hasattr(ln.get("product"), "_meta") else None,
                    product_id=getattr(ln.get("product"), "pk", ln.get("product")),
                    fallback=header_attrs.get("default_taxability", Taxability.TAXABLE),
                ),
            )
        )
        is_rcm = bool(header_attrs.get("is_reverse_charge", False))
        suppress_supplier_gst = PurchaseInvoiceService.should_suppress_supplier_gst(attrs=header_attrs)
        is_gst_manual = bool(ln.get("is_gst_manual", False)) and not suppress_supplier_gst

        # inclusive flag fallback: line -> header default -> False
        is_inclusive = ln.get("is_rate_inclusive_of_tax")
        if is_inclusive is None:
            is_inclusive = bool(header_attrs.get("is_rate_inclusive_of_tax_default", False))
        is_inclusive = bool(is_inclusive)

        # compute gross on billable qty only (free_qty doesn't affect billing)
        gross = q2(q2(qty) * rate)

        # apply discount on gross
        dt = (ln.get("discount_type") or "N")
        dp = q2(ln.get("discount_percent", ZERO2))
        da = q2(ln.get("discount_amount", ZERO2))
        after_disc = PurchaseInvoiceService._discounted_amount(gross, dt, dp, da)

        # default cess
        cess_type = str(
            ln.get("cess_type")
            or getattr(PurchaseInvoiceLine, "CessType", None).NONE
        ).strip().lower()
        cess_percent = q2(ln.get("cess_percent", ZERO2))
        if cess_percent < 0:
            cess_percent = ZERO2
        cess_percent = min(cess_percent, Decimal("100.00"))
        cess_specific_amount = q2(ln.get("cess_specific_amount", ZERO2))
        if cess_specific_amount < ZERO2:
            cess_specific_amount = ZERO2

        # If non-taxable buckets => GST 0, cess 0 (unless you explicitly want cess for some cases)
        if taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
            ln["is_itc_eligible"] = False
            if not (ln.get("itc_block_reason") or "").strip():
                ln["itc_block_reason"] = "Not ITC eligible for non-taxable line."
            taxable_value = q2(after_disc) if not is_inclusive else q2(after_disc)  # show as value basis
            cgst = sgst = igst = ZERO2
            cess_amount = ZERO2
            cess_type = PurchaseInvoiceLine.CessType.NONE
            cess_percent = ZERO2
            cess_specific_amount = ZERO2
            cgst_p = sgst_p = igst_p = ZERO2
            gst_rate_eff = ZERO2
        else:
            # Reverse charge invoice: GST amounts must be 0 on invoice,
            # taxable_value remains (for reporting), but tax components 0.
            if suppress_supplier_gst:
                if is_inclusive and gst_rate > 0:
                    # If inclusive+RCM, after_disc includes tax in price but invoice shouldn't show GST.
                    # We still back-calc taxable (recommended), so that taxable_value is correct.
                    taxable_value = q2(after_disc / (Decimal("1") + gst_rate / Decimal("100")))
                else:
                    taxable_value = q2(after_disc)

                cgst = sgst = igst = ZERO2
                cess_amount = ZERO2
                cess_percent = ZERO2
                cess_specific_amount = ZERO2
                raw_cgst_p = q2(ln.get("cgst_percent", ZERO2))
                raw_sgst_p = q2(ln.get("sgst_percent", ZERO2))
                raw_igst_p = q2(ln.get("igst_percent", ZERO2))
                if int(derived.tax_regime) == int(TaxRegime.INTRA):
                    if raw_cgst_p > ZERO2 or raw_sgst_p > ZERO2:
                        cgst_p = raw_cgst_p
                        sgst_p = raw_sgst_p
                    else:
                        cgst_p = q2(gst_rate / Decimal("2"))
                        sgst_p = q2(gst_rate - cgst_p)
                    igst_p = ZERO2
                    gst_rate_eff = gst_rate if gst_rate > ZERO2 else q2(cgst_p + sgst_p)
                else:
                    cgst_p = ZERO2
                    sgst_p = ZERO2
                    igst_p = raw_igst_p if raw_igst_p > ZERO2 else gst_rate
                    gst_rate_eff = gst_rate if gst_rate > ZERO2 else q2(igst_p)
            else:
                # inclusive: after_disc is "total including GST (and not including cess unless you treat it so)"
                if is_inclusive and gst_rate > 0:
                    taxable_value = q2(after_disc / (Decimal("1") + gst_rate / Decimal("100")))
                else:
                    taxable_value = q2(after_disc)

                if is_gst_manual:
                    cgst = q2(ln.get("cgst_amount", ZERO2)) if int(derived.tax_regime) == int(TaxRegime.INTRA) else ZERO2
                    sgst = q2(ln.get("sgst_amount", ZERO2)) if int(derived.tax_regime) == int(TaxRegime.INTRA) else ZERO2
                    igst = q2(ln.get("igst_amount", ZERO2)) if int(derived.tax_regime) == int(TaxRegime.INTER) else ZERO2
                else:
                    cgst, sgst, igst = PurchaseInvoiceService._split_gst(taxable_value, gst_rate, derived)

                if cess_type == PurchaseInvoiceLine.CessType.AD_VALOREM:
                    cess_amount = q2(taxable_value * cess_percent / Decimal("100"))
                    cess_specific_amount = ZERO2
                elif cess_type == PurchaseInvoiceLine.CessType.SPECIFIC:
                    cess_amount = q2(qty * cess_specific_amount)
                    cess_percent = ZERO2
                elif cess_type == PurchaseInvoiceLine.CessType.COMPOSITE:
                    cess_amount = q2((taxable_value * cess_percent / Decimal("100")) + (qty * cess_specific_amount))
                else:
                    cess_type = PurchaseInvoiceLine.CessType.NONE
                    cess_percent = ZERO2
                    cess_specific_amount = ZERO2
                    cess_amount = ZERO2

                if int(derived.tax_regime) == int(TaxRegime.INTRA):
                    cgst_p = q2(gst_rate / Decimal("2"))
                    sgst_p = q2(gst_rate / Decimal("2"))
                    igst_p = ZERO2
                else:
                    cgst_p = ZERO2
                    sgst_p = ZERO2
                    igst_p = gst_rate

                gst_rate_eff = gst_rate

        line_total = q2(taxable_value + cgst + sgst + igst + cess_amount)

        # overwrite authoritative fields (store ONLY these)
        ln["taxable_value"] = taxable_value
        ln["gst_rate"] = q2(gst_rate_eff)
        ln["cgst_percent"] = q2(cgst_p)
        ln["sgst_percent"] = q2(sgst_p)
        ln["igst_percent"] = q2(igst_p)
        ln["cgst_amount"] = q2(cgst)
        ln["sgst_amount"] = q2(sgst)
        ln["igst_amount"] = q2(igst)
        ln["cess_type"] = cess_type
        ln["cess_percent"] = q2(cess_percent)
        ln["cess_specific_amount"] = q2(cess_specific_amount)
        ln["cess_amount"] = q2(cess_amount)
        ln["line_total"] = q2(line_total)
        ln["is_rate_inclusive_of_tax"] = bool(is_inclusive)
        ln["free_qty"] = q4(ln.get("free_qty", ZERO4))
        ln["discount_type"] = dt
        ln["discount_percent"] = q2(dp if dt == "P" else ZERO2)
        ln["discount_amount"] = q2(da if dt == "A" else ZERO2)

        return ln

    @staticmethod
    def verify_client_vs_authoritative(
        client_line: Dict[str, Any],
        auth_line: Dict[str, Any],
        idx: int,
        mismatch_level: str = "hard",
    ) -> None:
        """
        If client sent monetary fields, verify they match computed (within tolerance).
        """
        checks = [
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "cess_amount",
            "line_total",
        ]
        errors = {}
        for f in checks:
            if f in client_line and client_line[f] is not None:
                if not near(client_line[f], auth_line[f]):
                    errors[f] = f"Line {idx}: sent {q2(client_line[f])} but expected {q2(auth_line[f])}"
        if errors and mismatch_level == "hard":
            raise ValueError(errors)

    # ---------------------------
    # Header totals
    # ---------------------------
    @staticmethod
    def compute_totals(lines: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        taxable = ZERO2
        cgst = ZERO2
        sgst = ZERO2
        igst = ZERO2
        cess = ZERO2

        for ln in lines:
            taxable += q2(ln.get("taxable_value"))
            cgst += q2(ln.get("cgst_amount"))
            sgst += q2(ln.get("sgst_amount"))
            igst += q2(ln.get("igst_amount"))
            cess += q2(ln.get("cess_amount"))

        total_gst = q2(cgst + sgst + igst + cess)
        grand = q2(taxable + total_gst)

        return {
            "total_taxable": q2(taxable),
            "total_cgst": q2(cgst),
            "total_sgst": q2(sgst),
            "total_igst": q2(igst),
            "total_cess": q2(cess),
            "total_gst": q2(total_gst),
            "grand_total_base": q2(grand),
        }

    @staticmethod
    def apply_totals_to_header(
        header: PurchaseInvoiceHeader,
        totals: Dict[str, Decimal],
        *,
        round_off_explicit: bool = False,
        grand_total_hint: Optional[Decimal] = None,
    ) -> None:
        header.total_taxable = totals["total_taxable"]
        header.total_cgst = totals["total_cgst"]
        header.total_sgst = totals["total_sgst"]
        header.total_igst = totals["total_igst"]
        header.total_cess = totals["total_cess"]
        header.total_gst = totals["total_gst"]

        base_total = q2(totals["grand_total_base"])
        if round_off_explicit:
            ro = q2(getattr(header, "round_off", ZERO2))
        elif grand_total_hint is not None:
            ro = q2(q2(grand_total_hint) - base_total)
        else:
            nearest_rupee = base_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            ro = q2(nearest_rupee - base_total)
        header.round_off = ro
        header.grand_total = q2(base_total + ro)
        fx = Decimal(getattr(header, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"))
        if fx <= 0:
            fx = Decimal("1.000000")
        header.grand_total_base_currency = q2(header.grand_total * fx)

    # ---------------------------
    # Tax summary rebuild
    # ---------------------------
    @staticmethod
    def rebuild_tax_summary(header: PurchaseInvoiceHeader) -> None:
        PurchaseTaxSummary.objects.filter(header=header).delete()

        buckets: Dict[Tuple[int, Optional[str], bool, Decimal, bool], Dict[str, Decimal]] = {}
        is_rcm = bool(getattr(header, "is_reverse_charge", False))
        derived = DerivedRegime(
            tax_regime=int(getattr(header, "tax_regime", int(TaxRegime.INTRA)) or int(TaxRegime.INTRA)),
            is_igst=bool(getattr(header, "is_igst", False)),
        )

        # --- LINES ---
        for ln in header.lines.all():
            key = (
                int(ln.taxability),
                (ln.hsn_sac or "").strip() or None,
                bool(ln.is_service),
                q2(ln.gst_rate),
                bool(header.is_reverse_charge),
            )

            if key not in buckets:
                buckets[key] = {
                    "taxable_value": ZERO2,
                    "cgst_amount": ZERO2,
                    "sgst_amount": ZERO2,
                    "igst_amount": ZERO2,
                    "cess_amount": ZERO2,
                    "total_value": ZERO2,
                    "itc_eligible_tax": ZERO2,
                    "itc_ineligible_tax": ZERO2,
                }

            taxable_value = q2(ln.taxable_value)
            if is_rcm and int(ln.taxability) == int(Taxability.TAXABLE):
                cgst_amount, sgst_amount, igst_amount = PurchaseInvoiceService._split_gst(
                    taxable_value,
                    q2(ln.gst_rate),
                    derived,
                )
                cess_amount = q2(taxable_value * q2(getattr(ln, "cess_percent", ZERO2) or ZERO2) / Decimal("100"))
            else:
                cgst_amount = q2(ln.cgst_amount)
                sgst_amount = q2(ln.sgst_amount)
                igst_amount = q2(ln.igst_amount)
                cess_amount = q2(ln.cess_amount)

            line_tax = q2(cgst_amount + sgst_amount + igst_amount + cess_amount)
            total_value = q2(taxable_value + line_tax) if is_rcm else q2(ln.line_total)

            buckets[key]["taxable_value"] += taxable_value
            buckets[key]["cgst_amount"] += cgst_amount
            buckets[key]["sgst_amount"] += sgst_amount
            buckets[key]["igst_amount"] += igst_amount
            buckets[key]["cess_amount"] += cess_amount
            buckets[key]["total_value"] += total_value

            if ln.is_itc_eligible:
                buckets[key]["itc_eligible_tax"] += line_tax
            else:
                buckets[key]["itc_ineligible_tax"] += line_tax

        # --- CHARGES (NEW) ---
        for ch in header.charges.all():
            charge_taxability_map = {
                PurchaseChargeLine.Taxability.TAXABLE: int(Taxability.TAXABLE),
                PurchaseChargeLine.Taxability.EXEMPT: int(Taxability.EXEMPT),
                PurchaseChargeLine.Taxability.NIL: int(Taxability.NIL_RATED),
                PurchaseChargeLine.Taxability.NON_GST: int(Taxability.NON_GST),
            }
            key = (
                int(charge_taxability_map.get(ch.taxability, int(Taxability.TAXABLE))),
                (ch.hsn_sac_code or "").strip() or None,
                bool(ch.is_service),
                q2(ch.gst_rate),
                bool(header.is_reverse_charge),
            )

            if key not in buckets:
                buckets[key] = {
                    "taxable_value": ZERO2,
                    "cgst_amount": ZERO2,
                    "sgst_amount": ZERO2,
                    "igst_amount": ZERO2,
                    "cess_amount": ZERO2,   # charges: always 0
                    "total_value": ZERO2,
                    "itc_eligible_tax": ZERO2,
                    "itc_ineligible_tax": ZERO2,
                }

            taxable_value = q2(ch.taxable_value)
            if is_rcm and int(charge_taxability_map.get(ch.taxability, int(Taxability.TAXABLE))) == int(Taxability.TAXABLE):
                cgst_amount, sgst_amount, igst_amount = PurchaseInvoiceService._split_gst(
                    taxable_value,
                    q2(ch.gst_rate),
                    derived,
                )
                ch_tax = q2(cgst_amount + sgst_amount + igst_amount)
                total_value = q2(taxable_value + ch_tax)
            else:
                cgst_amount = q2(ch.cgst_amount)
                sgst_amount = q2(ch.sgst_amount)
                igst_amount = q2(ch.igst_amount)
                ch_tax = q2(cgst_amount + sgst_amount + igst_amount)
                total_value = q2(ch.total_value)

            buckets[key]["taxable_value"] += taxable_value
            buckets[key]["cgst_amount"] += cgst_amount
            buckets[key]["sgst_amount"] += sgst_amount
            buckets[key]["igst_amount"] += igst_amount
            buckets[key]["total_value"] += total_value

            if getattr(ch, "itc_eligible", True):
                buckets[key]["itc_eligible_tax"] += ch_tax
            else:
                buckets[key]["itc_ineligible_tax"] += ch_tax

        objs = []
        for (taxability, hsn_sac, is_service, gst_rate, is_rcm), agg in buckets.items():
            objs.append(
                PurchaseTaxSummary(
                    header=header,
                    taxability=taxability,
                    hsn_sac=hsn_sac,
                    is_service=is_service,
                    gst_rate=gst_rate,
                    is_reverse_charge=is_rcm,
                    taxable_value=q2(agg["taxable_value"]),
                    cgst_amount=q2(agg["cgst_amount"]),
                    sgst_amount=q2(agg["sgst_amount"]),
                    igst_amount=q2(agg["igst_amount"]),
                    cess_amount=q2(agg["cess_amount"]),
                    total_value=q2(agg["total_value"]),
                    itc_eligible_tax=q2(agg["itc_eligible_tax"]),
                    itc_ineligible_tax=q2(agg["itc_ineligible_tax"]),
                )
            )

        if objs:
            PurchaseTaxSummary.objects.bulk_create(objs)

    # ---------------------------
    # Nested line upsert (unchanged but used with AUTH lines)
    # ---------------------------
    @staticmethod
    def upsert_lines(header: PurchaseInvoiceHeader, lines_data: List[Dict[str, Any]]) -> None:
        existing = {obj.id: obj for obj in header.lines.all()}
        retained_ids = {
            int(line_id)
            for line_id in (ln.get("id") for ln in lines_data)
            if line_id and int(line_id) in existing
        }

        # Remove dropped rows before inserts so a replacement line can safely reuse
        # the same line_no within the same header during edit flows.
        for line_id, obj in list(existing.items()):
            if line_id not in retained_ids:
                obj.delete()
                existing.pop(line_id, None)

        max_line_no = header.lines.aggregate(m=Max("line_no")).get("m") or 0
        next_line_no = int(max_line_no) + 1

        for ln in lines_data:
            line_id = ln.get("id")
            if line_id and line_id in existing:
                obj = existing[line_id]
                for k, v in ln.items():
                    if k not in {"id", "is_gst_manual"}:
                        setattr(obj, k, v)
                if not ln.get("line_no"):
                    obj.line_no = obj.line_no
                obj.full_clean()
                obj.save()
            else:
                if not ln.get("line_no"):
                    ln["line_no"] = next_line_no
                    next_line_no += 1
                obj = PurchaseInvoiceLine(
                    header=header,
                    **{k: v for k, v in ln.items() if k not in {"id", "is_gst_manual"}}
                )
                obj.full_clean()
                obj.save()

    # ---------------------------
    # High-level orchestrators
    # ---------------------------

   


    @classmethod
    def _apply_tds(cls, *, header: PurchaseInvoiceHeader) -> None:
        """
        Income-tax Vendor TDS (194C/194J/194Q etc).
        - If withholding_enabled = False -> clear all.
        - If withholding_enabled = True:
            - If tds_is_manual = True -> accept user provided values (validated).
            - Else -> compute from PurchaseWithholdingService.
        Note: TDS does NOT reduce GST and should NOT reduce vendor payable at invoice stage.
        """
        if not getattr(header, "withholding_enabled", False):
            header.tds_is_manual = False
            header.tds_section = None
            header.tds_rate = Decimal("0.0000")
            header.tds_base_amount = ZERO2
            header.tds_amount = ZERO2
            header.tds_reason = None
            PurchaseInvoiceService._set_tds_runtime_snapshot(
                header=header,
                mode="AUTO",
                enabled=False,
                reason=None,
                reason_code=None,
            )
            return

        # ✅ MANUAL MODE
        if bool(getattr(header, "tds_is_manual", False)):
            cfg = WithholdingResolver.get_entity_config(
                entity_id=header.entity_id,
                entityfin_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                doc_date=header.bill_date or timezone.localdate(),
            )
            if cfg and not bool(getattr(cfg, "enable_tds", True)):
                raise ValueError("TDS is disabled in withholding configuration for this scope/date.")

            # In manual mode, explicit section is mandatory.
            if not header.tds_section_id:
                raise ValueError("TDS section is required when withholding_enabled is true.")
            section = getattr(header, "tds_section", None)
            if section is not None and int(getattr(section, "base_rule", 0) or 0) not in {
                int(WithholdingBaseRule.INVOICE_VALUE_EXCL_GST),
                int(WithholdingBaseRule.INVOICE_VALUE_INCL_GST),
            }:
                raise ValueError("Selected TDS section is not invoice-based for purchase invoice context.")
            if section is not None:
                applicable, applicability_reason, _ = WithholdingResolver.evaluate_section_applicability(
                    section=section,
                    party_account_id=getattr(header, "vendor_id", None),
                )
                if not applicable:
                    raise ValueError(applicability_reason or "Selected TDS section is not applicable for this vendor.")

            rate = q4(getattr(header, "tds_rate", None) or Decimal("0.0000"))
            base = q2(getattr(header, "tds_base_amount", None) or ZERO2)
            amt  = q2(getattr(header, "tds_amount", None) or ZERO2)

            if base < ZERO2 or amt < ZERO2 or rate < Decimal("0.0000"):
                raise ValueError("Manual TDS values cannot be negative.")

            # base should not exceed taxable (you can relax if needed)
            taxable = q2(getattr(header, "total_taxable", ZERO2) or ZERO2)
            if base - taxable > TDS_TOLERANCE:
                raise ValueError("Manual TDS base cannot exceed invoice taxable total.")

            expected = q2(base * rate / Decimal("100.00"))
            if (amt - expected).copy_abs() > TDS_TOLERANCE:
                raise ValueError(f"Manual TDS amount mismatch. Expected {expected} for base {base} at rate {rate}.")

            # keep section as selected + keep reason (manual/audit)
            header.tds_rate = rate
            header.tds_base_amount = base
            header.tds_amount = amt
            header.tds_reason = (getattr(header, "tds_reason", "") or "").strip() or "MANUAL"
            PurchaseInvoiceService._set_tds_runtime_snapshot(
                header=header,
                mode="MANUAL",
                enabled=True,
                reason=header.tds_reason,
                reason_code="MANUAL" if amt > ZERO2 else "MANUAL_ZERO_AMOUNT",
            )
            return

        # ✅ AUTO MODE (source of truth)
        res = PurchaseWithholdingService.compute_tds(
            header=header,
            vendor_account_id=header.vendor_id,
            bill_date=header.bill_date or timezone.localdate(),
            taxable_total=q2(getattr(header, "total_taxable", ZERO2) or ZERO2),
            gross_total=q2(getattr(header, "grand_total", ZERO2) or ZERO2),
        )

        header.tds_section = res.section
        header.tds_rate = res.rate
        header.tds_base_amount = res.base_amount
        header.tds_amount = res.amount
        header.tds_reason = res.reason
        PurchaseInvoiceService._set_tds_runtime_snapshot(
            header=header,
            mode="AUTO",
            enabled=True,
            reason=res.reason,
            reason_code=res.reason_code,
        )
        if not res.section:
            raise ValueError("Provide tds_section or configure default TDS section for this entity.")
    @staticmethod
    def compute_charge_amounts(*, header: PurchaseInvoiceHeader, row: Dict[str, Any]) -> ChargeComputed:
        """
        Server-side computation for a single charge row.
        Respects header.tax_regime (INTRA => CGST+SGST, INTER => IGST).
        Respects is_rate_inclusive_of_tax.
        """
        taxability = str(row.get("taxability") or PurchaseChargeLine.Taxability.TAXABLE)
        gst_rate = q2(row.get("gst_rate") or ZERO2)
        taxable = q2(row.get("taxable_value") or ZERO2)
        inclusive = bool(row.get("is_rate_inclusive_of_tax") or False)

        # RCM normalization: purchase invoice charges should also carry zero GST amounts.
        if PurchaseInvoiceService.should_suppress_supplier_gst(
            attrs={
                "is_reverse_charge": getattr(header, "is_reverse_charge", False),
                "vendor_gstin": getattr(header, "vendor_gstin", ""),
                "supply_category": getattr(header, "supply_category", PurchaseInvoiceHeader.SupplyCategory.DOMESTIC),
                "vendor": getattr(header, "vendor", None),
            }
        ):
            taxable2 = q2r(taxable)
            return ChargeComputed(
                taxable_value=taxable2,
                cgst_amount=ZERO2,
                sgst_amount=ZERO2,
                igst_amount=ZERO2,
                total_value=taxable2,
            )

        # Non-taxable => force GST = 0, total = taxable
        if taxability != str(PurchaseChargeLine.Taxability.TAXABLE) or gst_rate <= ZERO2 or taxable <= ZERO2:
            taxable2 = q2r(taxable)
            return ChargeComputed(
                taxable_value=taxable2,
                cgst_amount=ZERO2,
                sgst_amount=ZERO2,
                igst_amount=ZERO2,
                total_value=taxable2,
            )

        rate = q2(gst_rate)

        # Inclusive: taxable passed might actually be "total"; if you want UI to send total when inclusive,
        # then interpret taxable_value as gross. If you prefer separate gross field, tell me.
        if inclusive:
            gross = q2(taxable)
            taxable_calc = gross / (Decimal("1.00") + (rate / Decimal("100.00")))
            taxable = q2(taxable_calc)

        taxable2 = q2r(taxable)

        gst_amt = q2r(taxable2 * rate / Decimal("100.00"))
        cgst = sgst = igst = ZERO2

        if int(getattr(header, "tax_regime", int(TaxRegime.INTRA))) == int(TaxRegime.INTRA):
            cgst = q2r(gst_amt / Decimal("2.00"))
            sgst = q2r(gst_amt - cgst)  # handle odd paise
        else:
            igst = gst_amt

        total = q2r(taxable2 + cgst + sgst + igst)

        return ChargeComputed(
            taxable_value=taxable2,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            total_value=total,
        )

    @staticmethod
    def _resolve_charge_master(*, header: PurchaseInvoiceHeader, row: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(row or {})
        raw_id = data.pop("charge_type_id", None)
        raw_type = data.get("charge_type")
        master = None

        qs = PurchaseChargeType.objects.filter(is_active=True).filter(
            Q(entity_id=header.entity_id) | Q(entity__isnull=True)
        ).order_by("-entity_id", "id")

        if raw_id not in (None, ""):
            try:
                master = qs.filter(id=int(raw_id)).first()
            except (TypeError, ValueError):
                raise ValueError(f"Invalid charge_type_id '{raw_id}'.")
            if not master:
                raise ValueError(f"Charge type id {raw_id} not found for this entity.")
        elif raw_type not in (None, ""):
            raw = str(raw_type).strip()
            normalized = raw.upper().replace("-", "_").replace(" ", "_")
            valid_enum_map = {
                str(value): value
                for value, _label in PurchaseChargeLine.ChargeType.choices
            }
            valid_enum_map.update({
                str(label).upper().replace("-", "_").replace(" ", "_"): value
                for value, label in PurchaseChargeLine.ChargeType.choices
            })

            if normalized in valid_enum_map:
                data["charge_type"] = valid_enum_map[normalized]
            else:
                master = qs.filter(code__iexact=raw).first() or qs.filter(name__iexact=raw).first()
                if not master:
                    raise ValueError(
                        f"Invalid charge_type '{raw}'. Provide charge_type_id or a valid charge type code/name."
                    )

        if master:
            base_map = {
                PurchaseChargeType.BaseCategory.FREIGHT: PurchaseChargeLine.ChargeType.FREIGHT,
                PurchaseChargeType.BaseCategory.PACKING: PurchaseChargeLine.ChargeType.PACKING,
                PurchaseChargeType.BaseCategory.INSURANCE: PurchaseChargeLine.ChargeType.INSURANCE,
                PurchaseChargeType.BaseCategory.OTHER: PurchaseChargeLine.ChargeType.OTHER,
            }
            data["charge_type"] = base_map.get(master.base_category, PurchaseChargeLine.ChargeType.OTHER)
            if not (data.get("description") or "").strip():
                data["description"] = master.name or master.description or ""
            if data.get("is_service") in (None, ""):
                data["is_service"] = bool(master.is_service)
            if not (data.get("hsn_sac_code") or "").strip():
                data["hsn_sac_code"] = (master.hsn_sac_code_default or "").strip()
            if data.get("gst_rate") in (None, ""):
                data["gst_rate"] = q2(master.gst_rate_default or ZERO2)
            if data.get("itc_eligible") in (None, ""):
                data["itc_eligible"] = bool(master.itc_eligible_default)

        if data.get("charge_type") in (None, ""):
            data["charge_type"] = PurchaseChargeLine.ChargeType.OTHER
        return data
    


    @staticmethod
    def validate_charges(*, header: PurchaseInvoiceHeader, charges: List[Dict[str, Any]]) -> None:
        policy = PurchaseSettingsService.get_policy(header.entity_id, header.subentity_id)
        header_taxability = int(getattr(header, "default_taxability", PurchaseInvoiceHeader.Taxability.TAXABLE))
        header_charge_taxability = {
            int(PurchaseInvoiceHeader.Taxability.TAXABLE): PurchaseChargeLine.Taxability.TAXABLE,
            int(PurchaseInvoiceHeader.Taxability.EXEMPT): PurchaseChargeLine.Taxability.EXEMPT,
            int(PurchaseInvoiceHeader.Taxability.NIL_RATED): PurchaseChargeLine.Taxability.NIL,
            int(PurchaseInvoiceHeader.Taxability.NON_GST): PurchaseChargeLine.Taxability.NON_GST,
        }.get(header_taxability, PurchaseChargeLine.Taxability.TAXABLE)

        seen_line_no: set[int] = set()
        for i, row in enumerate(charges or [], start=1):
            row = PurchaseInvoiceService._resolve_charge_master(header=header, row=row)
            charges[i - 1] = row
            line_no_raw = row.get("line_no")
            if line_no_raw not in (None, ""):
                try:
                    line_no = int(line_no_raw)
                except (TypeError, ValueError):
                    raise ValueError(f"Charge row {i}: line_no must be an integer.")
                if line_no <= 0:
                    raise ValueError(f"Charge row {i}: line_no must be > 0.")
                if line_no in seen_line_no:
                    raise ValueError(f"Charge row {i}: duplicate line_no {line_no}.")
                seen_line_no.add(line_no)

            taxable = q2(row.get("taxable_value") or ZERO2)
            gst_rate = q2(row.get("gst_rate") or ZERO2)
            taxability = str(row.get("taxability") or PurchaseChargeLine.Taxability.TAXABLE)
            hsn = (row.get("hsn_sac_code") or "").strip()

            if not policy.allow_mixed_taxability and taxability != header_charge_taxability:
                raise ValueError(
                    f"Charge row {i}: mixed taxability is disabled by purchase settings. "
                    "Keep all additional charges aligned with the header taxability."
                )

            if taxable < ZERO2:
                raise ValueError(f"Charge row {i}: taxable_value must be >= 0.")
            if gst_rate < ZERO2 or gst_rate > Decimal("100.00"):
                raise ValueError(f"Charge row {i}: gst_rate must be 0..100.")

            if taxability != str(PurchaseChargeLine.Taxability.TAXABLE) and gst_rate > ZERO2:
                raise ValueError(f"Charge row {i}: gst_rate must be 0 for non-taxable charges.")

            if gst_rate > ZERO2 and taxable > ZERO2 and not hsn:
                raise ValueError(f"Charge row {i}: HSN/SAC is required when GST is applied.")

            itc_eligible = bool(row.get("itc_eligible", True))
            reason = (row.get("itc_block_reason") or "").strip()
            if not itc_eligible and not reason:
                row["itc_block_reason"] = "Blocked ITC"

    
    @staticmethod
    def upsert_charges(
        *,
        header: PurchaseInvoiceHeader,
        charges_client: List[Dict[str, Any]],
    ) -> None:
        """
        Nested upsert:
        - id missing or 0 => insert
        - id matches existing => update
        - existing not present in payload => delete
        """
        charges_client = charges_client or []

        existing_qs = header.charges.all()
        existing_by_id = {c.id: c for c in existing_qs}
        existing_by_line = {}
        for c in existing_qs:
            if c.line_no is not None and c.line_no not in existing_by_line:
                existing_by_line[int(c.line_no)] = c
        seen_ids: set[int] = set()

        # recompute & upsert
        for idx, row in enumerate(charges_client, start=1):
            row = PurchaseInvoiceService._resolve_charge_master(header=header, row=row)
            cid = int(row.get("id") or 0)
            row["header"] = header
            line_no_for_insert = int(row.get("line_no") or idx)

            # normalize ITC reason; avoid nulls in DB
            reason_str = (row.get("itc_block_reason") or "").strip()
            itc_eligible_flag = bool(row.get("itc_eligible", True))
            if not itc_eligible_flag and not reason_str:
                reason_str = "Blocked ITC"
            row["itc_eligible"] = itc_eligible_flag
            row["itc_block_reason"] = reason_str

            # compute amounts server-side
            comp = PurchaseInvoiceService.compute_charge_amounts(header=header, row=row)
            row["taxable_value"] = comp.taxable_value
            row["cgst_amount"] = comp.cgst_amount
            row["sgst_amount"] = comp.sgst_amount
            row["igst_amount"] = comp.igst_amount
            row["total_value"] = comp.total_value

            if cid and cid in existing_by_id:
                obj = existing_by_id[cid]
                seen_ids.add(cid)

                # update fields
                for f in [
                    "line_no",
                    "charge_type",
                    "description",
                    "taxability",
                    "is_service",
                    "hsn_sac_code",
                    "is_rate_inclusive_of_tax",
                    "taxable_value",
                    "gst_rate",
                    "cgst_amount",
                    "sgst_amount",
                    "igst_amount",
                    "total_value",
                    "itc_eligible",
                    "itc_block_reason",
                ]:
                    if f in row:
                        setattr(obj, f, row[f])
                obj.save(update_fields=[
                    "line_no", "charge_type", "description", "taxability",
                    "is_service", "hsn_sac_code", "is_rate_inclusive_of_tax",
                    "taxable_value", "gst_rate",
                    "cgst_amount", "sgst_amount", "igst_amount",
                    "total_value", "itc_eligible", "itc_block_reason",
                    "updated_at",
                ])
            else:
                # insert or upsert by line_no to avoid unique constraint clashes
                existing_line_obj = existing_by_line.get(line_no_for_insert)
                if existing_line_obj:
                    seen_ids.add(existing_line_obj.id)
                    for f in [
                        "line_no",
                        "charge_type",
                        "description",
                        "taxability",
                        "is_service",
                        "hsn_sac_code",
                        "is_rate_inclusive_of_tax",
                        "taxable_value",
                        "gst_rate",
                        "cgst_amount",
                        "sgst_amount",
                        "igst_amount",
                        "total_value",
                        "itc_eligible",
                        "itc_block_reason",
                    ]:
                        if f in row:
                            setattr(existing_line_obj, f, row[f])
                    existing_line_obj.save(update_fields=[
                        "line_no", "charge_type", "description", "taxability",
                        "is_service", "hsn_sac_code", "is_rate_inclusive_of_tax",
                        "taxable_value", "gst_rate",
                        "cgst_amount", "sgst_amount", "igst_amount",
                        "total_value", "itc_eligible", "itc_block_reason",
                        "updated_at",
                    ])
                    continue

                # insert fresh
                PurchaseChargeLine.objects.create(
                    header=header,
                    line_no=line_no_for_insert,
                    charge_type=row.get("charge_type") or PurchaseChargeLine.ChargeType.OTHER,
                    description=row.get("description") or "",
                    taxability=row.get("taxability") or PurchaseChargeLine.Taxability.TAXABLE,
                    is_service=bool(row.get("is_service", True)),
                    hsn_sac_code=(row.get("hsn_sac_code") or "").strip(),
                    is_rate_inclusive_of_tax=bool(row.get("is_rate_inclusive_of_tax", False)),
                    taxable_value=row["taxable_value"],
                    gst_rate=q2(row.get("gst_rate") or ZERO2),
                    cgst_amount=row["cgst_amount"],
                    sgst_amount=row["sgst_amount"],
                    igst_amount=row["igst_amount"],
                    total_value=row["total_value"],
                    itc_eligible=bool(row.get("itc_eligible", True)),
                    itc_block_reason=(row.get("itc_block_reason") or "").strip(),
                )

        # delete missing
        for obj in existing_qs:
            if obj.id not in seen_ids:
                obj.delete()


    @staticmethod
    def compute_totals_with_charges(lines_rows: List[Dict[str, Any]], charge_rows: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        taxable = cgst = sgst = igst = cess = ZERO2

        for ln in lines_rows:
            taxable += q2(ln.get("taxable_value"))
            cgst += q2(ln.get("cgst_amount"))
            sgst += q2(ln.get("sgst_amount"))
            igst += q2(ln.get("igst_amount"))
            cess += q2(ln.get("cess_amount"))

        for ch in charge_rows:
            taxable += q2(ch.get("taxable_value"))
            cgst += q2(ch.get("cgst_amount"))
            sgst += q2(ch.get("sgst_amount"))
            igst += q2(ch.get("igst_amount"))
            # charges have no cess in your model, so skip

        total_gst = q2(cgst + sgst + igst + cess)
        grand = q2(taxable + total_gst)

        return {
            "total_taxable": q2(taxable),
            "total_cgst": q2(cgst),
            "total_sgst": q2(sgst),
            "total_igst": q2(igst),
            "total_cess": q2(cess),
            "total_gst": q2(total_gst),
            "grand_total_base": q2(grand),
        }
    


    @staticmethod
    @transaction.atomic
    def create_with_lines(validated_data: Dict[str, Any]) -> PurchaseInvoiceHeader:
        round_off_explicit = "round_off" in validated_data
        grand_total_hint = validated_data.get("grand_total") if "grand_total" in validated_data else None
        lines_client = validated_data.pop("lines", []) or []
        charges_client = validated_data.pop("charges", []) or []
        # Numbering is controlled by allocation services on confirm/post.
        # Ignore any client-sent values to avoid duplicate unique-key conflicts.
        validated_data.pop("doc_no", None)
        validated_data.pop("purchase_number", None)

        PurchaseInvoiceService.assert_not_locked(
            entity_id=(validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data.get("entity")),
            subentity_id=(validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity")),
            bill_date=validated_data.get("bill_date"),
            entityfinid_id=(validated_data.get("entityfinid").id if hasattr(validated_data.get("entityfinid"), "id") else validated_data.get("entityfinid")),
        )

        PurchaseInvoiceService.apply_vendor_snapshot(validated_data)
        PurchaseInvoiceService.apply_special_tax_treatment_defaults(validated_data)
        PurchaseInvoiceService.apply_dates(validated_data)

        derived = PurchaseInvoiceService.derive_tax_regime(validated_data)
        validated_data["tax_regime"] = derived.tax_regime
        validated_data["is_igst"] = derived.is_igst
        PurchaseInvoiceService.apply_product_line_defaults(
            header_taxability=int(validated_data.get("default_taxability", Taxability.TAXABLE)),
            lines=lines_client,
        )

        PurchaseInvoiceService.validate_header(validated_data)
        PurchaseInvoiceService.validate_lines_structural(validated_data, lines_client, derived)

        policy = PurchaseSettingsService.get_policy(
            entity_id=(validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data.get("entity")),
            subentity_id=(validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity")),
        )
        mismatch_level = policy.level("line_amount_mismatch", "hard")

        # authoritative lines
        lines_auth: List[Dict[str, Any]] = []
        for i, ln in enumerate(lines_client, start=1):
            auth = PurchaseInvoiceService.compute_line_authoritative(validated_data, ln, derived)
            PurchaseInvoiceService.verify_client_vs_authoritative(ln, auth, i, mismatch_level=mismatch_level)
            lines_auth.append(auth)

        header = PurchaseInvoiceHeader.objects.create(**validated_data)

        # save lines
        max_ln = 0
        objs = []
        for ln in lines_auth:
            ln_no = ln.get("line_no") or 0
            if ln_no == 0:
                max_ln += 1
                ln_no = max_ln
            else:
                max_ln = max(max_ln, int(ln_no))
            ln["line_no"] = ln_no
            obj = PurchaseInvoiceLine(
                header=header,
                **{k: v for k, v in ln.items() if k != "is_gst_manual"}
            )
            obj.full_clean()
            objs.append(obj)
        if objs:
            PurchaseInvoiceLine.objects.bulk_create(objs)

        # ✅ charges (NEW) - insert/update/delete
        PurchaseInvoiceService.validate_charges(header=header, charges=charges_client)
        PurchaseInvoiceService.upsert_charges(header=header, charges_client=charges_client)

        # ✅ totals MUST include charges
        db_lines = list(header.lines.values("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount"))
        db_charges = list(header.charges.values("taxable_value", "cgst_amount", "sgst_amount", "igst_amount"))
        totals = PurchaseInvoiceService.compute_totals_with_charges(db_lines, db_charges)
        preview_grand_total = grand_total_hint if grand_total_hint is not None else totals["grand_total_base"]
        PurchaseInvoiceService.assert_no_duplicate_supplier_invoice(
            instance=None,
            attrs=validated_data,
            grand_total=preview_grand_total,
        )
        PurchaseInvoiceService.apply_totals_to_header(
            header,
            totals,
            round_off_explicit=round_off_explicit,
            grand_total_hint=grand_total_hint,
        )

        # ✅ TDS AFTER totals (now includes charges)
        PurchaseInvoiceService._apply_tds(header=header)
        PurchaseInvoiceService._apply_gst_tds(header=header)
        PurchaseInvoiceService._apply_vendor_withholding_variance_policy(header=header)

        update_fields = [
            "total_taxable", "total_cgst", "total_sgst", "total_igst",
            "total_cess", "total_gst", "round_off", "grand_total", "grand_total_base_currency",

            "tds_section", "tds_rate", "tds_base_amount", "tds_amount", "tds_reason",

            "gst_tds_enabled", "gst_tds_is_manual", "gst_tds_contract_ref", "gst_tds_reason",
            "gst_tds_rate", "gst_tds_base_amount",
            "gst_tds_cgst_amount", "gst_tds_sgst_amount", "gst_tds_igst_amount",
            "gst_tds_amount", "gst_tds_status",
            "match_status", "match_notes",
        ]
        if hasattr(header, "vendor_payable"):
            update_fields.append("vendor_payable")

        header.save(update_fields=update_fields)

        # ✅ tax summary now includes charges
        PurchaseInvoiceService.rebuild_tax_summary(header)
        GstTdsService.sync_contract_ledger_for_header(header)
        return header

    @staticmethod
    @transaction.atomic
    def update_with_lines(instance: PurchaseInvoiceHeader, validated_data: Dict[str, Any]) -> PurchaseInvoiceHeader:
        old_scope_key = GstTdsService._scope_key_for_header(instance)
        round_off_explicit = "round_off" in validated_data
        grand_total_hint = validated_data.get("grand_total") if "grand_total" in validated_data else None
        lines_provided = "lines" in validated_data
        lines_client = validated_data.pop("lines", None)
        # Never allow replacing allocated numbering from update payload.
        validated_data.pop("doc_no", None)
        validated_data.pop("purchase_number", None)
        if lines_provided:
            lines_client = lines_client or []

        # IMPORTANT: None means "not provided" so DO NOT delete existing charges
        charges_client = validated_data.pop("charges", None)

        if int(instance.status) == int(Status.CANCELLED):
            raise ValueError("Cancelled purchase invoices cannot be edited.")
        if int(instance.status) == int(Status.POSTED):
            raise ValueError(PurchaseInvoiceService.blocked_edit_message(instance))
        if int(instance.status) == int(Status.CONFIRMED):
            policy = PurchaseSettingsService.get_policy(instance.entity_id, instance.subentity_id)
            allow_edit_confirmed = str(policy.controls.get("allow_edit_confirmed", "on")).lower().strip()
            if allow_edit_confirmed == "off":
                raise ValueError("Confirmed purchase invoice editing is disabled by purchase policy.")

        PurchaseInvoiceService.assert_not_locked(
            entity_id=instance.entity_id,
            subentity_id=instance.subentity_id,
            bill_date=(validated_data.get("bill_date") or instance.bill_date),
            entityfinid_id=instance.entityfinid_id,
        )

        PurchaseInvoiceService.apply_vendor_snapshot(validated_data, instance=instance)
        PurchaseInvoiceService.apply_special_tax_treatment_defaults(validated_data, instance=instance)
        PurchaseInvoiceService.apply_dates(validated_data, instance=instance)

        derived = PurchaseInvoiceService.derive_tax_regime(validated_data, instance=instance)
        validated_data["tax_regime"] = derived.tax_regime
        validated_data["is_igst"] = derived.is_igst
        PurchaseInvoiceService.apply_product_line_defaults(
            header_taxability=int(validated_data.get("default_taxability", instance.default_taxability)),
            lines=lines_client or [],
        )

        PurchaseInvoiceService.validate_header(validated_data, instance=instance)
        if lines_provided:
            PurchaseInvoiceService.validate_lines_structural(validated_data, lines_client, derived, instance=instance)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        header_ctx = {
            "default_taxability": instance.default_taxability,
            "is_reverse_charge": instance.is_reverse_charge,
            "vendor_gstin": instance.vendor_gstin,
            "is_rate_inclusive_of_tax_default": getattr(instance, "is_rate_inclusive_of_tax_default", False),
        }

        policy = PurchaseSettingsService.get_policy(instance.entity_id, instance.subentity_id)
        mismatch_level = policy.level("line_amount_mismatch", "hard")

        if lines_provided:
            # authoritative lines
            lines_auth: List[Dict[str, Any]] = []
            for i, ln in enumerate(lines_client, start=1):
                auth = PurchaseInvoiceService.compute_line_authoritative(header_ctx, ln, derived)
                PurchaseInvoiceService.verify_client_vs_authoritative(ln, auth, i, mismatch_level=mismatch_level)
                lines_auth.append(auth)

            PurchaseInvoiceService.upsert_lines(instance, lines_auth)

        # charges only if provided
        if charges_client is not None:
            PurchaseInvoiceService.validate_charges(header=instance, charges=charges_client)
            PurchaseInvoiceService.upsert_charges(header=instance, charges_client=charges_client)

        # totals include charges (existing or updated)
        db_lines = list(instance.lines.values("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount"))
        db_charges = list(instance.charges.values("taxable_value", "cgst_amount", "sgst_amount", "igst_amount"))
        totals = PurchaseInvoiceService.compute_totals_with_charges(db_lines, db_charges)
        preview_grand_total = grand_total_hint if grand_total_hint is not None else totals["grand_total_base"]
        PurchaseInvoiceService.assert_no_duplicate_supplier_invoice(
            instance=instance,
            attrs=validated_data,
            grand_total=preview_grand_total,
        )
        PurchaseInvoiceService.apply_totals_to_header(
            instance,
            totals,
            round_off_explicit=round_off_explicit,
            grand_total_hint=grand_total_hint,
        )

        # TDS AFTER totals
        PurchaseInvoiceService._apply_tds(header=instance)
        PurchaseInvoiceService._apply_gst_tds(header=instance)
        PurchaseInvoiceService._apply_vendor_withholding_variance_policy(header=instance)

        update_fields = [
            "total_taxable", "total_cgst", "total_sgst", "total_igst",
            "total_cess", "total_gst", "round_off", "grand_total", "grand_total_base_currency",

            "tds_section", "tds_rate", "tds_base_amount", "tds_amount", "tds_reason",

            "gst_tds_enabled", "gst_tds_is_manual", "gst_tds_contract_ref", "gst_tds_reason",
            "gst_tds_rate", "gst_tds_base_amount",
            "gst_tds_cgst_amount", "gst_tds_sgst_amount", "gst_tds_igst_amount",
            "gst_tds_amount", "gst_tds_status",
            "match_status", "match_notes",
        ]
        if hasattr(instance, "vendor_payable"):
            update_fields.append("vendor_payable")

        instance.save(update_fields=update_fields)

        PurchaseInvoiceService.rebuild_tax_summary(instance)
        GstTdsService.sync_contract_ledger_for_header(instance, old_scope_key=old_scope_key)
        return instance
