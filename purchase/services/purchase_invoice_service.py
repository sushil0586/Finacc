from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Max
from django.utils import timezone


from purchase.services.purchase_settings_service import PurchaseSettingsService
from purchase.services.purchase_withholding_service import PurchaseWithholdingService
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

# paisa tolerance: allows tiny rounding differences from UI (e.g. 0.01–0.02)
TOL = Decimal("0.02")


def q2(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC2, rounding=ROUND_HALF_UP)


def q4(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC4, rounding=ROUND_HALF_UP)


def near(a, b, tol=TOL) -> bool:
    return abs(q2(a) - q2(b)) <= tol


@dataclass(frozen=True)
class DerivedRegime:
    tax_regime: int
    is_igst: bool


class PurchaseInvoiceService:
    """
    Purchase invoice business rules:
    - client may send tax values, but we verify + store computed values only
    - supports free qty, discount, inclusive tax pricing, cess percent
    - persists header totals correctly
    """

    # ---------------------------
    # Period lock
    # ---------------------------
    @staticmethod
    def assert_not_locked(entity_id, subentity_id, bill_date):
        locked, reason = PurchaseSettingsService.is_locked(entity_id, subentity_id, bill_date)
        if locked:
            raise ValueError(f"Purchase period locked. {reason}")

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
    def apply_vendor_snapshot(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        vendor = attrs.get("vendor") or (instance.vendor if instance else None)
        if not vendor:
            return

        if not (attrs.get("vendor_name") or (instance.vendor_name if instance else None)):
            attrs["vendor_name"] = (getattr(vendor, "accountname", None) or str(vendor)).strip()[:200]

        if not (attrs.get("vendor_gstin") or (instance.vendor_gstin if instance else None)):
            gstno = getattr(vendor, "gstno", None)
            if gstno:
                attrs["vendor_gstin"] = str(gstno).strip()[:15]

        if not (attrs.get("vendor_state") or (instance.vendor_state if instance else None)):
            st = getattr(vendor, "state", None)
            if st:
                attrs["vendor_state"] = st

    # ---------------------------
    # Tax regime derivation
    # ---------------------------
    @staticmethod
    def derive_tax_regime(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> DerivedRegime:
        vendor_state = attrs.get("vendor_state") or (instance.vendor_state if instance else None)
        pos_state = attrs.get("place_of_supply_state") or (instance.place_of_supply_state if instance else None)
        supplier_state = attrs.get("supplier_state") or (instance.supplier_state if instance else None)

        compare_state = pos_state or supplier_state

        if vendor_state and compare_state and getattr(vendor_state, "id", None) and getattr(compare_state, "id", None):
            if vendor_state.id == compare_state.id:
                return DerivedRegime(tax_regime=int(TaxRegime.INTRA), is_igst=False)
            return DerivedRegime(tax_regime=int(TaxRegime.INTER), is_igst=True)

        tax_regime = attrs.get("tax_regime", (instance.tax_regime if instance else int(TaxRegime.INTRA)))
        is_igst = attrs.get("is_igst", (instance.is_igst if instance else False))
        return DerivedRegime(tax_regime=int(tax_regime), is_igst=bool(is_igst))

    # ---------------------------
    # Validations (structure-level)
    # ---------------------------
    @staticmethod
    def validate_header(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        doc_type = attrs.get("doc_type", DocType.TAX_INVOICE)
        ref_document = attrs.get("ref_document") or (instance.ref_document if instance else None)

        if doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE) and not ref_document:
            raise ValueError("ref_document is required for Credit/Debit Note.")
        if doc_type == DocType.TAX_INVOICE and attrs.get("ref_document"):
            raise ValueError("Tax Invoice should not have ref_document.")

        if instance:
            if int(instance.status) == int(Status.CANCELLED):
                raise ValueError("Cancelled document cannot be edited.")
            new_status = int(attrs.get("status", instance.status))
            if int(instance.status) == int(Status.POSTED) and new_status != int(Status.POSTED):
                raise ValueError("Posted document cannot be moved back to Draft/Confirmed.")

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

        # NOTE: we will validate amounts AFTER we compute authoritative values
        # Here we only check regime consistency if amounts were provided and obviously wrong.
        for i, ln in enumerate(lines, start=1):
            # qty sanity
            qty = q4(ln.get("qty"))
            if qty <= 0:
                raise ValueError(f"Line {i}: qty must be > 0")

            free_qty = q4(ln.get("free_qty", ZERO4))
            if free_qty < 0:
                raise ValueError(f"Line {i}: free_qty cannot be negative")

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

            if is_rcm and (cgst > 0 or sgst > 0 or igst > 0):
                raise ValueError(f"Line {i}: GST amounts must be 0 for Reverse Charge invoice.")

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

        qty = q4(ln.get("qty"))
        rate = q2(ln.get("rate"))
        gst_rate = q2(ln.get("gst_rate", ZERO2))
        taxability = int(ln.get("taxability", header_attrs.get("default_taxability", Taxability.TAXABLE)))
        is_rcm = bool(header_attrs.get("is_reverse_charge", False))

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
        cess_percent = q2(ln.get("cess_percent", ZERO2))
        if cess_percent < 0:
            cess_percent = ZERO2
        cess_percent = min(cess_percent, Decimal("100.00"))

        # If non-taxable buckets => GST 0, cess 0 (unless you explicitly want cess for some cases)
        if taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
            taxable_value = q2(after_disc) if not is_inclusive else q2(after_disc)  # show as value basis
            cgst = sgst = igst = ZERO2
            cess_amount = ZERO2
            cgst_p = sgst_p = igst_p = ZERO2
            gst_rate_eff = ZERO2
        else:
            # Reverse charge invoice: GST amounts must be 0 on invoice,
            # taxable_value remains (for reporting), but tax components 0.
            if is_rcm:
                if is_inclusive and gst_rate > 0:
                    # If inclusive+RCM, after_disc includes tax in price but invoice shouldn't show GST.
                    # We still back-calc taxable (recommended), so that taxable_value is correct.
                    taxable_value = q2(after_disc / (Decimal("1") + gst_rate / Decimal("100")))
                else:
                    taxable_value = q2(after_disc)

                cgst = sgst = igst = ZERO2
                cess_amount = ZERO2
                cgst_p = sgst_p = igst_p = ZERO2
                gst_rate_eff = gst_rate  # keep rate for reporting
            else:
                # inclusive: after_disc is "total including GST (and not including cess unless you treat it so)"
                if is_inclusive and gst_rate > 0:
                    taxable_value = q2(after_disc / (Decimal("1") + gst_rate / Decimal("100")))
                else:
                    taxable_value = q2(after_disc)

                cgst, sgst, igst = PurchaseInvoiceService._split_gst(taxable_value, gst_rate, derived)

                # cess calculated on taxable_value
                cess_amount = q2(taxable_value * cess_percent / Decimal("100"))

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
        ln["cess_percent"] = q2(cess_percent)
        ln["cess_amount"] = q2(cess_amount)
        ln["line_total"] = q2(line_total)
        ln["is_rate_inclusive_of_tax"] = bool(is_inclusive)
        ln["free_qty"] = q4(ln.get("free_qty", ZERO4))
        ln["discount_type"] = dt
        ln["discount_percent"] = q2(dp if dt == "P" else ZERO2)
        ln["discount_amount"] = q2(da if dt == "A" else ZERO2)

        return ln

    @staticmethod
    def verify_client_vs_authoritative(client_line: Dict[str, Any], auth_line: Dict[str, Any], idx: int) -> None:
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
        if errors:
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
    def apply_totals_to_header(header: PurchaseInvoiceHeader, totals: Dict[str, Decimal]) -> None:
        header.total_taxable = totals["total_taxable"]
        header.total_cgst = totals["total_cgst"]
        header.total_sgst = totals["total_sgst"]
        header.total_igst = totals["total_igst"]
        header.total_cess = totals["total_cess"]
        header.total_gst = totals["total_gst"]

        ro = q2(getattr(header, "round_off", ZERO2))
        header.round_off = ro
        header.grand_total = q2(totals["grand_total_base"] + ro)

    # ---------------------------
    # Tax summary rebuild
    # ---------------------------
    @staticmethod
    def rebuild_tax_summary(header: PurchaseInvoiceHeader) -> None:
        PurchaseTaxSummary.objects.filter(header=header).delete()

        buckets: Dict[Tuple[int, Optional[str], bool, Decimal, bool], Dict[str, Decimal]] = {}

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

            buckets[key]["taxable_value"] += q2(ln.taxable_value)
            buckets[key]["cgst_amount"] += q2(ln.cgst_amount)
            buckets[key]["sgst_amount"] += q2(ln.sgst_amount)
            buckets[key]["igst_amount"] += q2(ln.igst_amount)
            buckets[key]["cess_amount"] += q2(ln.cess_amount)
            buckets[key]["total_value"] += q2(ln.line_total)

            line_tax = q2(ln.cgst_amount + ln.sgst_amount + ln.igst_amount + ln.cess_amount)
            if ln.is_itc_eligible:
                buckets[key]["itc_eligible_tax"] += line_tax
            else:
                buckets[key]["itc_ineligible_tax"] += line_tax

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
        sent_ids = set()

        max_line_no = header.lines.aggregate(m=Max("line_no")).get("m") or 0
        next_line_no = int(max_line_no) + 1

        for ln in lines_data:
            line_id = ln.get("id")
            if line_id and line_id in existing:
                obj = existing[line_id]
                for k, v in ln.items():
                    if k != "id":
                        setattr(obj, k, v)
                if not ln.get("line_no"):
                    obj.line_no = obj.line_no
                obj.save()
                sent_ids.add(line_id)
            else:
                if not ln.get("line_no"):
                    ln["line_no"] = next_line_no
                    next_line_no += 1
                obj = PurchaseInvoiceLine.objects.create(header=header, **{k: v for k, v in ln.items() if k != "id"})
                sent_ids.add(obj.id)

        for line_id, obj in existing.items():
            if line_id not in sent_ids:
                obj.delete()

    # ---------------------------
    # High-level orchestrators
    # ---------------------------

    @classmethod
    def _apply_tds(cls, *, header: PurchaseInvoiceHeader) -> None:
        """
        Enforce: only ONE TDS section at a time (tds_section FK).
        Compute TDS AFTER totals are available.
        """
        if not getattr(header, "withholding_enabled", False):
            header.tds_section = None
            header.tds_rate = Decimal("0.0000")
            header.tds_base_amount = ZERO2
            header.tds_amount = ZERO2
            header.tds_reason = None
            return

        if not header.tds_section_id:
            raise ValueError("TDS section is required when withholding_enabled is true (only one allowed).")

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

        if hasattr(header, "vendor_payable"):
            header.vendor_payable = q2((header.grand_total or ZERO2) - (header.tds_amount or ZERO2))


    @staticmethod
    @transaction.atomic
    def create_with_lines(validated_data: Dict[str, Any]) -> PurchaseInvoiceHeader:
        lines_client = validated_data.pop("lines", []) or []

        PurchaseInvoiceService.assert_not_locked(
            entity_id=(validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data.get("entity")),
            subentity_id=(validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity")),
            bill_date=validated_data.get("bill_date"),
        )

        PurchaseInvoiceService.apply_vendor_snapshot(validated_data)
        PurchaseInvoiceService.apply_dates(validated_data)

        derived = PurchaseInvoiceService.derive_tax_regime(validated_data)
        validated_data["tax_regime"] = derived.tax_regime
        validated_data["is_igst"] = derived.is_igst

        PurchaseInvoiceService.validate_header(validated_data)
        PurchaseInvoiceService.validate_lines_structural(validated_data, lines_client, derived)

        lines_auth: List[Dict[str, Any]] = []
        for i, ln in enumerate(lines_client, start=1):
            auth = PurchaseInvoiceService.compute_line_authoritative(validated_data, ln, derived)
            PurchaseInvoiceService.verify_client_vs_authoritative(ln, auth, i)
            lines_auth.append(auth)

        header = PurchaseInvoiceHeader.objects.create(**validated_data)

        # lines
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
            objs.append(PurchaseInvoiceLine(header=header, **ln))
        if objs:
            PurchaseInvoiceLine.objects.bulk_create(objs)

        # totals
        db_lines = list(header.lines.values("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount"))
        totals = PurchaseInvoiceService.compute_totals(db_lines)
        PurchaseInvoiceService.apply_totals_to_header(header, totals)

        # ✅ apply tds AFTER totals
        PurchaseInvoiceService._apply_tds(header=header)

        # ✅ single save for totals + tds (+ vendor_payable if exists)
        update_fields = [
            "total_taxable", "total_cgst", "total_sgst", "total_igst",
            "total_cess", "total_gst", "round_off", "grand_total",
            "tds_section", "tds_rate", "tds_base_amount", "tds_amount", "tds_reason",
        ]
        if hasattr(header, "vendor_payable"):
            update_fields.append("vendor_payable")

        header.save(update_fields=update_fields)

        PurchaseInvoiceService.rebuild_tax_summary(header)
        return header

    @staticmethod
    @transaction.atomic
    def update_with_lines(instance: PurchaseInvoiceHeader, validated_data: Dict[str, Any]) -> PurchaseInvoiceHeader:
        lines_client = validated_data.pop("lines", []) or []

        PurchaseInvoiceService.assert_not_locked(
            entity_id=instance.entity_id,
            subentity_id=instance.subentity_id,
            bill_date=(validated_data.get("bill_date") or instance.bill_date),
        )

        PurchaseInvoiceService.apply_vendor_snapshot(validated_data, instance=instance)
        PurchaseInvoiceService.apply_dates(validated_data, instance=instance)

        derived = PurchaseInvoiceService.derive_tax_regime(validated_data, instance=instance)
        validated_data["tax_regime"] = derived.tax_regime
        validated_data["is_igst"] = derived.is_igst

        PurchaseInvoiceService.validate_header(validated_data, instance=instance)
        PurchaseInvoiceService.validate_lines_structural(validated_data, lines_client, derived, instance=instance)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        header_ctx = {
            "default_taxability": instance.default_taxability,
            "is_reverse_charge": instance.is_reverse_charge,
            "is_rate_inclusive_of_tax_default": getattr(instance, "is_rate_inclusive_of_tax_default", False),
        }

        lines_auth: List[Dict[str, Any]] = []
        for i, ln in enumerate(lines_client, start=1):
            auth = PurchaseInvoiceService.compute_line_authoritative(header_ctx, ln, derived)
            PurchaseInvoiceService.verify_client_vs_authoritative(ln, auth, i)
            lines_auth.append(auth)

        PurchaseInvoiceService.upsert_lines(instance, lines_auth)

        # totals
        db_lines = list(instance.lines.values("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount"))
        totals = PurchaseInvoiceService.compute_totals(db_lines)
        PurchaseInvoiceService.apply_totals_to_header(instance, totals)

        # ✅ apply tds AFTER totals
        PurchaseInvoiceService._apply_tds(header=instance)

        update_fields = [
            "total_taxable", "total_cgst", "total_sgst", "total_igst",
            "total_cess", "total_gst", "round_off", "grand_total",
            "tds_section", "tds_rate", "tds_base_amount", "tds_amount", "tds_reason",
        ]
        if hasattr(instance, "vendor_payable"):
            update_fields.append("vendor_payable")

        instance.save(update_fields=update_fields)

        PurchaseInvoiceService.rebuild_tax_summary(instance)
        return instance
