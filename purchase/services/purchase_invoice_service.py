from __future__ import annotations
from purchase.services.purchase_settings_service import PurchaseSettingsService
from decimal import Decimal, ROUND_HALF_UP

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Tuple, Optional

from django.db import transaction
from django.db.models import Max

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


def q2(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC2, rounding=ROUND_HALF_UP)


def q4(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC4, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DerivedRegime:
    tax_regime: int
    is_igst: bool


class PurchaseInvoiceService:
    """
    Common reusable business rules for PurchaseInvoiceHeader + Lines.
    """

    # ---------------------------
    # Vendor snapshot (your Account model)
    # ---------------------------

    @staticmethod
    def assert_not_locked(entity_id, subentity_id, bill_date):
        locked, reason = PurchaseSettingsService.is_locked(entity_id, subentity_id, bill_date)
        if locked:
            raise ValueError(f"Purchase period locked. {reason}")

    @staticmethod
    def apply_rounding(grand_total: Decimal, decimals: int) -> Decimal:
        q = Decimal("1." + ("0" * decimals))
        return (grand_total or Decimal("0")).quantize(q, rounding=ROUND_HALF_UP)
    
    
    @staticmethod
    def apply_vendor_snapshot(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        """
        vendor is financial.account with fields:
          - accountname
          - gstno
          - state
        """
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

        # fallback to provided/instance
        tax_regime = attrs.get("tax_regime", (instance.tax_regime if instance else int(TaxRegime.INTRA)))
        is_igst = attrs.get("is_igst", (instance.is_igst if instance else False))
        return DerivedRegime(tax_regime=int(tax_regime), is_igst=bool(is_igst))

    # ---------------------------
    # Totals
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
            "grand_total_base": q2(grand),  # without round_off
        }

    @staticmethod
    def apply_totals(attrs: Dict[str, Any], totals: Dict[str, Decimal]) -> None:
        attrs["total_taxable"] = totals["total_taxable"]
        attrs["total_cgst"] = totals["total_cgst"]
        attrs["total_sgst"] = totals["total_sgst"]
        attrs["total_igst"] = totals["total_igst"]
        attrs["total_cess"] = totals["total_cess"]
        attrs["total_gst"] = totals["total_gst"]

        round_off = q2(attrs.get("round_off", ZERO2))
        attrs["round_off"] = round_off
        attrs["grand_total"] = q2(totals["grand_total_base"] + round_off)

    # ---------------------------
    # Validations (header + lines)
    # ---------------------------
    @staticmethod
    def validate_header(attrs: Dict[str, Any], instance: Optional[PurchaseInvoiceHeader] = None) -> None:
        # CN/DN must reference, Tax Invoice must not
        doc_type = attrs.get("doc_type", DocType.TAX_INVOICE)
        ref_document = attrs.get("ref_document") or (instance.ref_document if instance else None)

        if doc_type in (DocType.CREDIT_NOTE, DocType.DEBIT_NOTE) and not ref_document:
            raise ValueError("ref_document is required for Credit/Debit Note.")
        if doc_type == DocType.TAX_INVOICE and attrs.get("ref_document"):
            raise ValueError("Tax Invoice should not have ref_document.")

        # Status transitions
        if instance:
            if int(instance.status) == int(Status.CANCELLED):
                raise ValueError("Cancelled document cannot be edited.")
            new_status = int(attrs.get("status", instance.status))
            if int(instance.status) == int(Status.POSTED) and new_status != int(Status.POSTED):
                raise ValueError("Posted document cannot be moved back to Draft/Confirmed.")

    @staticmethod
    def validate_lines(
        attrs: Dict[str, Any],
        lines: List[Dict[str, Any]],
        derived: DerivedRegime,
        instance: Optional[PurchaseInvoiceHeader] = None,
    ) -> None:
        if not lines:
            raise ValueError("At least one line is required.")

        header_taxability = attrs.get("default_taxability", (instance.default_taxability if instance else Taxability.TAXABLE))
        is_rcm = bool(attrs.get("is_reverse_charge", (instance.is_reverse_charge if instance else False)))

        header_itc = bool(attrs.get("is_itc_eligible", (instance.is_itc_eligible if instance else True)))
        itc_claim_status = int(attrs.get("itc_claim_status", (instance.itc_claim_status if instance else ItcClaimStatus.PENDING)))

        # Header taxability constraints
        if header_taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
            if header_itc:
                raise ValueError("ITC cannot be eligible for Exempt/Nil-rated/Non-GST header.")
            if itc_claim_status == int(ItcClaimStatus.CLAIMED):
                raise ValueError("Cannot claim ITC for Exempt/Nil-rated/Non-GST header.")

        if is_rcm and itc_claim_status == int(ItcClaimStatus.CLAIMED):
            raise ValueError("RCM ITC should be claimed only after RCM tax payment (track separately).")

        # Line validation vs regime + RCM + taxability
        for i, ln in enumerate(lines, start=1):
            ln_taxability = ln.get("taxability", header_taxability)

            cgst = q2(ln.get("cgst_amount"))
            sgst = q2(ln.get("sgst_amount"))
            igst = q2(ln.get("igst_amount"))

            if ln_taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
                if bool(ln.get("is_itc_eligible", True)):
                    raise ValueError(f"Line {i}: ITC not allowed for Exempt/Nil/Non-GST.")
                if cgst > 0 or sgst > 0 or igst > 0:
                    raise ValueError(f"Line {i}: GST amounts must be 0 for Exempt/Nil/Non-GST.")

            if int(derived.tax_regime) == int(TaxRegime.INTRA):
                if igst > 0:
                    raise ValueError(f"Line {i}: IGST not allowed for INTRA regime.")
            else:
                if cgst > 0 or sgst > 0:
                    raise ValueError(f"Line {i}: CGST/SGST not allowed for INTER regime.")

            if is_rcm and (cgst > 0 or sgst > 0 or igst > 0):
                raise ValueError(f"Line {i}: GST amounts must be 0 for Reverse Charge invoice.")

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

        PurchaseTaxSummary.objects.bulk_create(objs)

    # ---------------------------
    # Nested line upsert
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
    @staticmethod
    @transaction.atomic
    def create_with_lines(validated_data: Dict[str, Any]) -> PurchaseInvoiceHeader:
        lines = validated_data.pop("lines", [])
        header = PurchaseInvoiceHeader.objects.create(**validated_data)

        # create lines
        max_ln = 0
        objs = []
        for ln in lines:
            ln_no = ln.get("line_no") or 0
            if ln_no == 0:
                max_ln += 1
                ln_no = max_ln
            else:
                max_ln = max(max_ln, int(ln_no))
            ln["line_no"] = ln_no
            objs.append(PurchaseInvoiceLine(header=header, **ln))

        PurchaseInvoiceLine.objects.bulk_create(objs)
        PurchaseInvoiceService.rebuild_tax_summary(header)
        return header

    @staticmethod
    @transaction.atomic
    def update_with_lines(instance: PurchaseInvoiceHeader, validated_data: Dict[str, Any]) -> PurchaseInvoiceHeader:
        lines = validated_data.pop("lines", [])
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        PurchaseInvoiceService.upsert_lines(instance, lines)
        PurchaseInvoiceService.rebuild_tax_summary(instance)
        return instance
