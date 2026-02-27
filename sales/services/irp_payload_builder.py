from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional
import re


Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
Q4 = Decimal("0.0001")


def q2(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def q3(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q3, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.000")


def q4(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.0000")


def clean_hsn(hsn: Optional[str]) -> str:
    s = (hsn or "").strip()
    s = re.sub(r"\D", "", s)  # digits only
    if not (4 <= len(s) <= 8):
        raise ValueError(f"HSN/SAC is required (4..8 digits). Got: {hsn!r}")
    return s


def clean_uom_code(line) -> str:
    # Prefer your UOM FK
    u = getattr(line, "uom", None)
    code = getattr(u, "code", None) or getattr(u, "uom_code", None) or getattr(u, "uomcode", None)
    code = (str(code).strip() if code else "")[:8]
    return code or "NOS"


class IRPPayloadBuilder:
    """
    Minimal but NIC/MasterGST-valid payload builder for SalesInvoiceHeader + SalesInvoiceLine.

    IMPORTANT: assumes line computed fields are already correct:
      - taxable_value, cgst_amount, sgst_amount, igst_amount, line_total
    """

    def __init__(self, invoice):
        self.invoice = invoice

    def build(self) -> Dict[str, Any]:
        inv = self.invoice

        doc_no = (
            getattr(inv, "sales_number", None)
            or getattr(inv, "invoice_number", None)
            or getattr(inv, "doc_no", None)
            or getattr(inv, "voucher_no", None)
            or str(inv.id)
        )

        inv_date = getattr(inv, "bill_date", None) or getattr(inv, "invoice_date", None) or getattr(inv, "doc_date", None)
        if not inv_date:
            raise ValueError("Invoice date field not found (bill_date/invoice_date/doc_date).")

        return {
            "Version": "1.1",
            "TranDtls": {
                "TaxSch": "GST",
                "SupTyp": "B2B",  # map later from supply_category
            },
            "DocDtls": {
                "Typ": "INV",  # map later from doc_type
                "No": str(doc_no),
                "Dt": inv_date.strftime("%d/%m/%Y"),
            },
            "SellerDtls": {},  # injected later
            "BuyerDtls": {},   # injected later
            "ItemList": self._items(),
            "ValDtls": self._values_from_lines(),  # reliable if header totals not present yet
        }

    def _items(self) -> list[dict]:
        inv = self.invoice
        lines = list(inv.lines.all())
        if not lines:
            raise ValueError("Invoice has no SalesInvoiceLine rows; cannot generate IRN.")

        items: list[dict] = []

        for idx, line in enumerate(lines, start=1):
            qty = q3(line.qty)
            free_qty = q3(line.free_qty)
            rate = q4(line.rate)

            # Required TotAmt = UnitPrice * Qty
            tot_amt = q2(qty * rate)

            # Use service-computed values (best)
            ass_amt = q2(line.taxable_value)
            cgst = q2(line.cgst_amount)
            sgst = q2(line.sgst_amount)
            igst = q2(line.igst_amount)
            cess = q2(line.cess_amount)

            disc = q2(line.discount_amount)

            # Required TotItemVal → line_total (computed by service)
            tot_item_val = q2(line.line_total)

            # HSN/SAC resolution: prefer line.hsn_sac_code, else product fields
            product = line.product
            hsn_raw = (line.hsn_sac_code or "").strip()
            if not hsn_raw:
                hsn_raw = (
                    getattr(product, "hsn_code", None)
                    or getattr(product, "sac_code", None)
                    or getattr(product, "hsn_sac_code", None)
                    or getattr(product, "hsn_sac", None)
                    or ""
                )
            hsn = clean_hsn(str(hsn_raw))

            desc = (getattr(product, "name", None) or "Item")
            desc = str(desc).strip() or "Item"

            item = {
                "SlNo": str(idx),
                "IsServc": "Y" if line.is_service else "N",
                "PrdDesc": desc[:300],
                "HsnCd": hsn,  # ✅ required
                "Qty": float(qty),
                "FreeQty": float(free_qty) if free_qty > 0 else 0,
                "Unit": clean_uom_code(line),
                "UnitPrice": float(q2(rate)),  # send 2-dec unit price commonly accepted
                "TotAmt": float(tot_amt),      # ✅ required
                "Discount": float(disc) if disc > 0 else 0,
                "AssAmt": float(ass_amt),
                "GstRt": float(q2(line.gst_rate)),
                "CgstAmt": float(cgst) if cgst > 0 else 0,
                "SgstAmt": float(sgst) if sgst > 0 else 0,
                "IgstAmt": float(igst) if igst > 0 else 0,
                "CesAmt": float(cess) if cess > 0 else 0,
                "TotItemVal": float(tot_item_val),  # ✅ required
            }

            # Small guardrails to fail fast with a better error than MasterGST 5002
            if len(item["PrdDesc"]) < 1:
                raise ValueError(f"Line {line.line_no}: PrdDesc missing.")
            if item["Qty"] <= 0:
                raise ValueError(f"Line {line.line_no}: Qty must be > 0.")
            if item["TotAmt"] <= 0:
                raise ValueError(f"Line {line.line_no}: TotAmt must be > 0.")
            if item["TotItemVal"] <= 0:
                raise ValueError(f"Line {line.line_no}: TotItemVal must be > 0.")

            items.append(item)

        return items

    def _values_from_lines(self) -> dict:
        inv = self.invoice
        lines = list(inv.lines.all())

        ass = q2(sum((l.taxable_value for l in lines), Decimal("0.00")))
        cgst = q2(sum((l.cgst_amount for l in lines), Decimal("0.00")))
        sgst = q2(sum((l.sgst_amount for l in lines), Decimal("0.00")))
        igst = q2(sum((l.igst_amount for l in lines), Decimal("0.00")))
        cess = q2(sum((l.cess_amount for l in lines), Decimal("0.00")))
        tot = q2(sum((l.line_total for l in lines), Decimal("0.00")))

        return {
            "AssVal": float(ass),
            "CgstVal": float(cgst),
            "SgstVal": float(sgst),
            "IgstVal": float(igst),
            "CesVal": float(cess),
            "TotInvVal": float(tot),
        }