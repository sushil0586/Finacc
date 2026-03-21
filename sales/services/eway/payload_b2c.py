# sales/builders/eway_payload_builder.py

from __future__ import annotations
from typing import Any, Dict, List,Tuple
from datetime import date
from datetime import date, datetime
from sales.services.profile_resolvers import entity_primary_address, entity_primary_state

def _float(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def _int(x, default: int = 0) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default

def _ddmmyyyy(d: Any) -> str:
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)

def _state_code_from_entity(ent: Any) -> int:
    """
    Reads GST state code from Entity.state FK.
    Update the attr list to match your State master.
    """
    st = entity_primary_state(ent)
    if not st:
        return 0
    for attr in ("gst_state_code", "state_code", "code", "gstcode", "tin_code", "statecode"):
        v = getattr(st, attr, None)
        if v is not None and str(v).strip():
            return _int(v, 0)
    s = str(st).strip()
    return _int(s, 0) if s.isdigit() else 0

def _q2(x: float) -> float:
    # quantize to 2 decimals safely
    return round(float(x or 0.0), 2)

def _compute_tax_from_items(items: List[Dict[str, Any]]) -> Tuple[float, float, float, float, float]:
    """
    Returns: (taxable_total, cgst_total, sgst_total, igst_total, cess_total)
    Computed from itemList (taxableAmount + rates).
    """
    taxable_total = 0.0
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0
    cess_total = 0.0

    for it in items:
        taxable = _float(it.get("taxableAmount"))
        taxable_total += taxable

        cgst_total += taxable * (_float(it.get("cgstRate")) / 100.0)
        sgst_total += taxable * (_float(it.get("sgstRate")) / 100.0)
        igst_total += taxable * (_float(it.get("igstRate")) / 100.0)
        cess_total += taxable * (_float(it.get("cessRate")) / 100.0)

    return (
        _q2(taxable_total),
        _q2(cgst_total),
        _q2(sgst_total),
        _q2(igst_total),
        _q2(cess_total),
    )

def _as_date(v: Any) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        # ISO YYYY-MM-DD
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            pass
        # DD/MM/YYYY
        try:
            return datetime.strptime(s, "%d/%m/%Y").date()
        except Exception:
            pass
    raise ValueError(f"Invalid date: {v!r}")

def _ddmmyyyy(v: Any) -> str:
    d = _as_date(v)
    if not d:
        raise ValueError("Date missing.")
    return d.strftime("%d/%m/%Y")

def _sanitize_doc_no(s: str) -> str:
    return (s or "").strip().replace(" ", "").replace("-", "")[:15]

def _sanitize_vehicle_no(s: str) -> str:
    return (s or "").strip().replace(" ", "").replace("-", "").upper()[:20]


def build_b2c_direct_payload(*, invoice: Any, ewb: Any, entity_gstin: str) -> Dict[str, Any]:
    if str(getattr(invoice, "supply_category", "")).upper() != "2":
        raise ValueError("B2C payload builder called for non-B2C invoice.")

    ent = getattr(invoice, "entity", None)
    ent_addr = entity_primary_address(ent) if ent else None
    if not ent:
        raise ValueError("Invoice.entity missing.")
    if not getattr(ent_addr, "pincode", None):
        raise ValueError("Entity pincode missing (invoice.entity.pincode).")

    ship = getattr(invoice, "shipto_snapshot", None)
    if not ship:
        raise ValueError("Ship-to snapshot missing (invoice.shipto_snapshot).")
    if not getattr(ship, "pincode", None):
        raise ValueError("Ship-to pincode missing (invoice.shipto_snapshot.pincode).")
    if not getattr(ship, "state_code", None):
        raise ValueError("Ship-to state_code missing (invoice.shipto_snapshot.state_code).")
    if not getattr(invoice, "bill_date", None):
        raise ValueError("Invoice bill_date missing.")

    inv_doc_no = getattr(invoice, "doc_no", None) or getattr(invoice, "invoice_no", None)
    if not inv_doc_no:
        raise ValueError("Invoice doc_no missing.")

    if not getattr(ewb, "distance_km", None):
        raise ValueError("EWB distance_km missing (set in SalesEWayBill).")

    transport_mode = int(getattr(ewb, "transport_mode", 0) or 0)
    if transport_mode == 1 and not getattr(ewb, "vehicle_no", None):
        raise ValueError("vehicle_no required for Road (transport_mode=1).")

    from_state_code = _state_code_from_entity(ent)
    if not from_state_code:
        raise ValueError("Entity GST state code missing (from Entity.state master).")

    to_state_code = _int(getattr(ship, "state_code", None), 0)
    if not to_state_code:
        raise ValueError("Ship-to state_code must be numeric (e.g. '05','06').")

    is_interstate = (int(from_state_code) != int(to_state_code))

    # ---------- items ----------
    lines = list(invoice.lines.all())
    if not lines:
        raise ValueError("Invoice lines missing.")

    item_list: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines, start=1):
        hsn = getattr(ln, "hsn_sac_code", None)
        if not hsn:
            raise ValueError(f"Line {idx}: hsn_sac_code missing.")

        qty = _q2(getattr(ln, "qty", None)) + _q2(getattr(ln, "free_qty", None))
        if qty <= 0:
            raise ValueError(f"Line {idx}: qty + free_qty must be > 0.")

        taxable = _q2(getattr(ln, "taxable_value", None))
        gst_rate_total = _q2(getattr(ln, "gst_rate", None))
        cess_rate = _q2(getattr(ln, "cess_percent", None) or 0.0)

        uom = getattr(getattr(ln, "uom", None), "code", None) or "NOS"
        desc = getattr(getattr(ln, "product", None), "name", None) or "Item"

        if is_interstate:
            cgst_rate = 0.0
            sgst_rate = 0.0
            igst_rate = _q2(gst_rate_total)
        else:
            igst_rate = 0.0
            cgst_rate = _q2(gst_rate_total / 2.0)
            sgst_rate = _q2(gst_rate_total / 2.0)

        item_list.append({
            "productName": desc[:100],
            "productDesc": desc[:100],
            "hsnCode": _int(hsn, 0) if str(hsn).isdigit() else str(hsn),
            "quantity": _q2(qty),
            "qtyUnit": str(uom)[:10],
            "taxableAmount": _q2(taxable),
            "sgstRate": _q2(sgst_rate),
            "cgstRate": _q2(cgst_rate),
            "igstRate": _q2(igst_rate),
            "cessRate": _q2(cess_rate),
        })

    total_taxable = _q2(sum(i["taxableAmount"] for i in item_list))
    total_cgst = _q2(sum(i["taxableAmount"] * i["cgstRate"] / 100 for i in item_list))
    total_sgst = _q2(sum(i["taxableAmount"] * i["sgstRate"] / 100 for i in item_list))
    total_igst = _q2(sum(i["taxableAmount"] * i["igstRate"] / 100 for i in item_list))
    total_cess = _q2(sum(i["taxableAmount"] * i["cessRate"] / 100 for i in item_list))
    tot_inv_value = _q2(total_taxable + total_cgst + total_sgst + total_igst + total_cess)

    inv_doc_date = _as_date(invoice.bill_date)
    if not inv_doc_date:
        raise ValueError("Invoice bill_date missing/invalid.")
    inv_doc_date_ddmmyyyy = inv_doc_date.strftime("%d/%m/%Y")

    # ✅ use transport doc date saved from POST (ewb.doc_date is now trans_doc_date)
    trans_dt = _as_date(getattr(ewb, "doc_date", None))
    if trans_dt and trans_dt < inv_doc_date:
        # ✅ hard guard against 362
        trans_dt = inv_doc_date

    payload: Dict[str, Any] = {
        "supplyType": "O",
        "subSupplyType": "1",
        "subSupplyDesc": " ",

        "docType": "INV",
        "docNo": str(inv_doc_no),
        "docDate": inv_doc_date_ddmmyyyy,

        "fromGstin": entity_gstin,
        "fromTrdName": (getattr(ent, "legalname", None) or getattr(ent, "entityname", None) or "Supplier")[:100],
        "fromAddr1": (getattr(ent_addr, "line1", None) or "")[:100],
        "fromAddr2": (getattr(ent_addr, "line2", None) or "")[:100],
        "fromPlace": (str(getattr(getattr(ent_addr, "city", None), "cityname", "")) if ent_addr else "")[:50] or "NA",
        "actFromStateCode": int(from_state_code),
        "fromPincode": _int(getattr(ent_addr, "pincode", None), 0),
        "fromStateCode": int(from_state_code),

        "toGstin": "URP",
        "toTrdName": (getattr(ship, "full_name", None) or "Customer")[:100],
        "toAddr1": (getattr(ship, "address1", None) or "")[:255],
        "toAddr2": (getattr(ship, "address2", None) or "")[:255],
        "toPlace": (getattr(ship, "city", None) or "NA")[:50],
        "toPincode": _int(ship.pincode, 0),
        "actToStateCode": int(to_state_code),
        "toStateCode": int(to_state_code),

        "transactionType": 1,

        "totalValue": total_taxable,
        "cgstValue": total_cgst,
        "sgstValue": total_sgst,
        "igstValue": total_igst,
        "cessValue": total_cess,
        "totInvValue": tot_inv_value,

        "transMode": str(int(transport_mode)),
        "transDistance": str(int(getattr(ewb, "distance_km"))),

        "transporterName": (getattr(ewb, "transporter_name", None) or "")[:100],
        "transporterId": (getattr(ewb, "transporter_id", None) or "")[:15],

        "transDocNo": _sanitize_doc_no(getattr(ewb, "doc_no", None) or ""),
        "transDocDate": trans_dt.strftime("%d/%m/%Y") if trans_dt else None,

        "vehicleNo": _sanitize_vehicle_no(getattr(ewb, "vehicle_no", None) or ""),
        "vehicleType": (getattr(ewb, "vehicle_type", None) or "R")[:1],

        "itemList": item_list,
    }

    # Remove transDocDate if None (some validators dislike nulls)
    if not payload.get("transDocDate"):
        payload.pop("transDocDate", None)

    return payload
