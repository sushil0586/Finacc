from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional
import re


Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
Q4 = Decimal("0.0001")
DOC_NO_RE = re.compile(r"^[A-Za-z1-9][A-Za-z0-9/-]{0,15}$")
NOTIFIED_GST_SLABS = {
    Decimal("0.00"),
    Decimal("0.10"),
    Decimal("0.25"),
    Decimal("1.00"),
    Decimal("1.50"),
    Decimal("3.00"),
    Decimal("5.00"),
    Decimal("6.00"),
    Decimal("7.50"),
    Decimal("12.00"),
    Decimal("18.00"),
    Decimal("28.00"),
}


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


def clean_doc_no(doc_no: Any) -> str:
    s = str(doc_no or "").strip()
    if not s:
        raise ValueError("Document number is required for IRN payload.")
    if not DOC_NO_RE.fullmatch(s):
        raise ValueError(
            "Document number must be 1..16 chars, start with alphanumeric (not 0), and contain only [A-Z0-9/-]."
        )
    return s


def clean_uom_code(line) -> str:
    # Prefer your UOM FK
    u = getattr(line, "uom", None)
    code = getattr(u, "code", None) or getattr(u, "uom_code", None) or getattr(u, "uomcode", None)
    code = (str(code).strip() if code else "")[:8]
    return code or "NOS"


def validate_notified_gst_rate(*, line_no: int, gst_rate: Decimal) -> None:
    r = q2(gst_rate)
    if r not in NOTIFIED_GST_SLABS:
        raise ValueError(
            f"Line {line_no}: gst_rate={r} is not a standard notified GST slab for IRN. "
            "Use total GST rate (e.g., 5, 12, 18, 28), not component rate."
        )


def _clean_pin(v: Any) -> Optional[int]:
    s = re.sub(r"\D", "", str(v or "").strip())
    if len(s) != 6:
        return None
    return int(s)


def _stcd(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    if not s:
        return None
    if s.isdigit():
        s = s.zfill(2)
    if s == "00":
        return None
    return s


def _state_code_from_obj(state_obj: Any) -> Optional[str]:
    if not state_obj:
        return None
    for field in ("gst_state_code", "gststatecode", "statecode", "code"):
        raw = getattr(state_obj, field, None)
        if raw not in (None, ""):
            return _stcd(raw)
    return None


class IRPPayloadBuilder:
    """
    Minimal but NIC/MasterGST-valid payload builder for SalesInvoiceHeader + SalesInvoiceLine.

    IMPORTANT: assumes line computed fields are already correct:
      - taxable_value, cgst_amount, sgst_amount, igst_amount, line_total
    """

    def __init__(self, invoice):
        self.invoice = invoice

    @staticmethod
    def _map_doc_type(inv) -> str:
        doc_type = int(getattr(inv, "doc_type", 1) or 1)
        if doc_type == 2:
            return "CRN"
        if doc_type == 3:
            return "DBN"
        return "INV"

    @staticmethod
    def _map_supply_type(inv) -> str:
        # SalesInvoiceHeader.SupplyCategory
        # 1 DOMESTIC_B2B, 2 DOMESTIC_B2C, 3 EXPORT_WITH_IGST, 4 EXPORT_WITHOUT_IGST,
        # 5 SEZ_WITH_IGST, 6 SEZ_WITHOUT_IGST, 7 DEEMED_EXPORT
        sc = int(getattr(inv, "supply_category", 1) or 1)
        if sc == 2:
            return "B2C"
        if sc == 3:
            return "EXPWP"
        if sc == 4:
            return "EXPWOP"
        if sc == 5:
            return "SEZWP"
        if sc == 6:
            return "SEZWOP"
        if sc == 7:
            return "DEXP"
        return "B2B"

    @staticmethod
    def _is_export_supply(inv) -> bool:
        sc = int(getattr(inv, "supply_category", 1) or 1)
        return sc in (3, 4)

    @staticmethod
    def _reverse_charge_flag(inv) -> str:
        return "Y" if bool(getattr(inv, "is_reverse_charge", False)) else "N"

    def _effective_line_tax_split(self, line) -> tuple[Decimal, Decimal, Decimal]:
        """
        For reverse-charge invoices our stored line tax can be zero by design.
        IRP payload validation still expects tax amount consistency with GST rate,
        so derive tax split from taxable value + GST rate for payload only.
        """
        inv = self.invoice
        stored_cgst = q2(getattr(line, "cgst_amount", Decimal("0.00")))
        stored_sgst = q2(getattr(line, "sgst_amount", Decimal("0.00")))
        stored_igst = q2(getattr(line, "igst_amount", Decimal("0.00")))
        if not bool(getattr(inv, "is_reverse_charge", False)):
            return stored_cgst, stored_sgst, stored_igst

        taxable = q2(getattr(line, "taxable_value", Decimal("0.00")))
        gst_rate = q2(getattr(line, "gst_rate", Decimal("0.00")))
        if taxable <= Decimal("0.00") or gst_rate <= Decimal("0.00"):
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

        tax_total = q2(taxable * gst_rate / Decimal("100.00"))
        if bool(getattr(inv, "is_igst", False)):
            return Decimal("0.00"), Decimal("0.00"), tax_total

        cgst = q2(tax_total / Decimal("2.00"))
        sgst = q2(tax_total - cgst)
        return cgst, sgst, Decimal("0.00")

    def build(self) -> Dict[str, Any]:
        inv = self.invoice

        doc_no_raw = (
            getattr(inv, "invoice_number", None)
            or getattr(inv, "doc_no", None)
            or getattr(inv, "sales_number", None)
            or getattr(inv, "voucher_no", None)
            or str(inv.id)
        )
        doc_no = clean_doc_no(doc_no_raw)

        inv_date = getattr(inv, "bill_date", None) or getattr(inv, "invoice_date", None) or getattr(inv, "doc_date", None)
        if not inv_date:
            raise ValueError("Invoice date field not found (bill_date/invoice_date/doc_date).")
        sup_typ = self._map_supply_type(inv)
        if sup_typ == "B2C":
            raise ValueError("IRN cannot be generated for B2C invoices (SupTyp=B2C).")

        payload = {
            "Version": "1.1",
            "TranDtls": self._tran_dtls(inv, sup_typ),
            "DocDtls": {
                "Typ": self._map_doc_type(inv),
                "No": doc_no,
                "Dt": inv_date.strftime("%d/%m/%Y"),
            },
            "SellerDtls": {},  # injected later
            "BuyerDtls": {},   # injected later
            "ItemList": self._items(),
            "ValDtls": self._values_from_lines(),  # reliable if header totals not present yet
        }
        ref_dtls = self._ref_dtls(inv)
        if ref_dtls:
            payload["RefDtls"] = ref_dtls
        exp_dtls = self._exp_dtls(inv)
        if exp_dtls:
            payload["ExpDtls"] = exp_dtls
        disp_dtls = self._disp_dtls(inv)
        if disp_dtls:
            payload["DispDtls"] = disp_dtls
        ship_dtls = self._ship_dtls(inv)
        if ship_dtls:
            payload["ShipDtls"] = ship_dtls
        ewb_dtls = self._ewb_dtls(inv)
        if ewb_dtls:
            payload["EwbDtls"] = ewb_dtls
        return payload

    @staticmethod
    def _tran_dtls(inv, sup_typ: str) -> Dict[str, Any]:
        ecm = str(getattr(inv, "ecm_gstin", "") or "").strip().upper()
        igst_on_intra = getattr(inv, "igst_on_intra", None)

        out: Dict[str, Any] = {
            "TaxSch": "GST",
            "SupTyp": sup_typ,
            "RegRev": "Y" if bool(getattr(inv, "is_reverse_charge", False)) else "N",
            # Keep key explicit to match NIC schema across providers.
            "EcmGstin": ecm or None,
            # Default to "N" unless explicitly set true on invoice.
            "IgstOnIntra": "Y" if bool(igst_on_intra) else "N",
        }
        return out

    def _ref_dtls(self, inv) -> Optional[Dict[str, Any]]:
        doc_type = int(getattr(inv, "doc_type", 1) or 1)
        if doc_type not in (2, 3):
            return None

        original = getattr(inv, "original_invoice", None)
        if not original:
            raise ValueError("Credit Note/Debit Note requires original_invoice for RefDtls.")

        orig_no_raw = (
            getattr(original, "doc_no", None)
            or getattr(original, "invoice_number", None)
            or getattr(original, "sales_number", None)
            or str(getattr(original, "id", ""))
        )
        orig_no = clean_doc_no(orig_no_raw)
        orig_dt = getattr(original, "bill_date", None) or getattr(original, "invoice_date", None) or getattr(original, "doc_date", None)
        if not orig_dt:
            raise ValueError("Original invoice date is required for CN/DN RefDtls.")
        return {
            "PrecDocDtls": [
                {
                    "InvNo": orig_no,
                    "InvDt": orig_dt.strftime("%d/%m/%Y"),
                }
            ]
        }

    @staticmethod
    def _country_code_from_invoice(inv) -> str:
        customer = getattr(inv, "customer", None)
        country = getattr(customer, "country", None) if customer else None
        code = getattr(country, "countrycode", None) if country else None
        s = str(code or "").strip().upper()
        if len(s) < 2:
            raise ValueError("Export invoices require buyer country code (customer.country.countrycode).")
        return s[:2]

    def _exp_dtls(self, inv) -> Optional[Dict[str, Any]]:
        if not self._is_export_supply(inv):
            return None
        return {"CntCode": self._country_code_from_invoice(inv)}

    def _disp_dtls(self, inv) -> Optional[Dict[str, Any]]:
        # Preferred source: selected subentity (dispatch from branch/plant)
        if getattr(inv, "subentity_id", None):
            sub = getattr(inv, "subentity", None)
            if sub is not None:
                addr = (
                    sub.addresses.filter(isactive=True, is_primary=True).select_related("state", "city").first()
                    or sub.addresses.filter(isactive=True).select_related("state", "city").first()
                )
                if addr:
                    pin = _clean_pin(getattr(addr, "pincode", None))
                    stcd = _state_code_from_obj(getattr(addr, "state", None))
                    nm = str(getattr(sub, "subentityname", "") or "").strip()
                    addr1 = str(getattr(addr, "line1", "") or "").strip()
                    loc = str(getattr(getattr(addr, "city", None), "cityname", "") or "").strip()
                    if nm and addr1 and loc and pin and stcd:
                        return {
                            "Nm": nm[:100],
                            "Addr1": addr1[:100],
                            "Addr2": (str(getattr(addr, "line2", "") or "").strip() or None),
                            "Loc": loc[:50],
                            "Pin": pin,
                            "Stcd": stcd,
                        }

        # Fallback: legacy eway artifact json
        art = getattr(inv, "eway_artifact", None)
        src = getattr(art, "disp_dtls_json", None) if art else None
        if not isinstance(src, dict):
            return None
        pin = _clean_pin(src.get("Pin") or src.get("pin"))
        stcd = _stcd(src.get("Stcd") or src.get("stcd") or src.get("state_code"))
        nm = str(src.get("Nm") or src.get("nm") or src.get("name") or "").strip()
        addr1 = str(src.get("Addr1") or src.get("addr1") or "").strip()
        loc = str(src.get("Loc") or src.get("loc") or "").strip()
        if not (nm and addr1 and loc and pin and stcd):
            return None
        return {
            "Nm": nm[:100],
            "Addr1": addr1[:100],
            "Addr2": (str(src.get("Addr2") or src.get("addr2") or "").strip() or None),
            "Loc": loc[:50],
            "Pin": pin,
            "Stcd": stcd,
        }

    def _ship_dtls(self, inv) -> Optional[Dict[str, Any]]:
        # Preferred source: selected shipping detail on invoice (ship-to)
        sd = getattr(inv, "shipping_detail", None)
        if sd is not None:
            pin = _clean_pin(getattr(sd, "pincode", None))
            stcd = _state_code_from_obj(getattr(sd, "state", None))
            lgl = str(getattr(sd, "full_name", "") or "").strip() or str(getattr(inv, "customer_name", "") or "").strip()
            addr1 = str(getattr(sd, "address1", "") or "").strip()
            loc = str(getattr(getattr(sd, "city", None), "cityname", "") or "").strip()
            gstin = str(getattr(sd, "gstno", "") or getattr(inv, "customer_gstin", "") or "").strip().upper()
            if lgl and addr1 and loc and pin and stcd:
                out = {
                    "LglNm": lgl[:100],
                    "Addr1": addr1[:100],
                    "Addr2": (str(getattr(sd, "address2", "") or "").strip() or None),
                    "Loc": loc[:50],
                    "Pin": pin,
                    "Stcd": stcd,
                }
                if gstin and (gstin == "URP" or re.fullmatch(r"^[0-9A-Z]{15}$", gstin)):
                    out["Gstin"] = gstin
                trd = str(getattr(inv, "customer_name", "") or "").strip()
                if trd:
                    out["TrdNm"] = trd[:100]
                return out

        # Fallback: legacy eway artifact json
        art = getattr(inv, "eway_artifact", None)
        src = getattr(art, "exp_ship_dtls_json", None) if art else None
        if not isinstance(src, dict):
            return None
        pin = _clean_pin(src.get("Pin") or src.get("pin"))
        stcd = _stcd(src.get("Stcd") or src.get("stcd") or src.get("state_code"))
        lgl = str(src.get("LglNm") or src.get("lgl_nm") or src.get("name") or "").strip()
        addr1 = str(src.get("Addr1") or src.get("addr1") or "").strip()
        loc = str(src.get("Loc") or src.get("loc") or "").strip()
        gstin = str(src.get("Gstin") or src.get("gstin") or getattr(inv, "customer_gstin", "") or "").strip().upper()
        if not (lgl and addr1 and loc and pin and stcd):
            return None
        out = {
            "LglNm": lgl[:100],
            "Addr1": addr1[:100],
            "Addr2": (str(src.get("Addr2") or src.get("addr2") or "").strip() or None),
            "Loc": loc[:50],
            "Pin": pin,
            "Stcd": stcd,
        }
        if gstin and (gstin == "URP" or re.fullmatch(r"^[0-9A-Z]{15}$", gstin)):
            out["Gstin"] = gstin
        trd = str(src.get("TrdNm") or src.get("trd_nm") or "").strip()
        if trd:
            out["TrdNm"] = trd[:100]
        return out

    def _ewb_dtls(self, inv) -> Optional[Dict[str, Any]]:
        art = getattr(inv, "eway_artifact", None)
        if not art:
            return None
        trans_mode = str(getattr(art, "transport_mode", "") or "").strip()
        distance = getattr(art, "distance_km", None)
        if not (trans_mode and distance is not None):
            return None
        out: Dict[str, Any] = {
            "TransMode": trans_mode,
            "Distance": int(distance),
        }
        trans_id = (getattr(art, "transporter_id", None) or "").strip()
        trans_name = (getattr(art, "transporter_name", None) or "").strip()
        trans_doc_no = (getattr(art, "doc_no", None) or "").strip()
        trans_doc_date = getattr(art, "doc_date", None)
        veh_no = (getattr(art, "vehicle_no", None) or "").strip()
        veh_type = (getattr(art, "vehicle_type", None) or "").strip().upper()
        if trans_id:
            out["TransId"] = trans_id[:15]
        if trans_name:
            out["TransName"] = trans_name[:100]
        if trans_doc_no:
            out["TransDocNo"] = trans_doc_no[:15]
        if trans_doc_date:
            out["TransDocDt"] = trans_doc_date.strftime("%d/%m/%Y")
        if veh_no:
            out["VehNo"] = veh_no[:20]
        if veh_type in {"R", "O"}:
            out["VehType"] = veh_type
        return out

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
            validate_notified_gst_rate(line_no=getattr(line, "line_no", idx), gst_rate=q2(line.gst_rate))

            # Required TotAmt = UnitPrice * Qty
            tot_amt = q2(qty * rate)

            # Use service-computed values (best)
            ass_amt = q2(line.taxable_value)
            cgst, sgst, igst = self._effective_line_tax_split(line)
            cess = q2(line.cess_amount)

            disc = q2(line.discount_amount)

            # Required TotItemVal → line_total (computed by service)
            tot_item_val = q2(ass_amt + cgst + sgst + igst + cess)

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

            desc = (
                (line.productDesc or "").strip()
                or getattr(product, "productname", None)
                or getattr(product, "name", None)
                or "Item"
            )
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

        ass = cgst = sgst = igst = cess = Decimal("0.00")
        for line in lines:
            ass_amt = q2(line.taxable_value)
            cg, sg, ig = self._effective_line_tax_split(line)
            ce = q2(line.cess_amount)
            ass += ass_amt
            cgst += cg
            sgst += sg
            igst += ig
            cess += ce
        ass = q2(ass)
        cgst = q2(cgst)
        sgst = q2(sgst)
        igst = q2(igst)
        cess = q2(cess)
        tot = q2(ass + cgst + sgst + igst + cess)

        return {
            "AssVal": float(ass),
            "CgstVal": float(cgst),
            "SgstVal": float(sgst),
            "IgstVal": float(igst),
            "CesVal": float(cess),
            "Discount": float(q2(getattr(inv, "total_discount", Decimal("0.00")))),
            "OthChrg": float(q2(getattr(inv, "total_other_charges", Decimal("0.00")))),
            "RndOffAmt": float(q2(getattr(inv, "round_off", Decimal("0.00")))),
            "TotInvVal": float(
                tot if bool(getattr(inv, "is_reverse_charge", False))
                else q2(getattr(inv, "grand_total", None) or tot)
            ),
        }
