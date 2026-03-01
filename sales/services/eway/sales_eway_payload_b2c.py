from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple, Optional

def _ddmmyyyy(d) -> str:
    return d.strftime("%d/%m/%Y")

def _float(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def _int(x) -> int:
    try:
        return int(x)
    except Exception:
        return 0

def build_b2c_direct_eway_payload(*, inv: Any, ewb_artifact: Any, entity_gstin: str) -> Dict[str, Any]:
    """
    Build direct EWB payload for B2C (no IRN).
    Reads transport details from your SalesEWayBill artifact fields.
    Reads totals/lines from invoice.
    """

    # ---- validations (hard) ----
    supply_category = getattr(inv, "supply_category", None)
    if str(supply_category).upper() != "B2C":
        raise ValueError("B2C direct EWB allowed only when invoice.supply_category == B2C.")

    if not entity_gstin:
        raise ValueError("Entity GSTIN is required for EWB generation.")

    if not getattr(inv, "bill_date", None):
        raise ValueError("Invoice bill_date is required.")

    doc_no = getattr(inv, "doc_no", None) or getattr(inv, "invoice_no", None)
    if not doc_no:
        raise ValueError("Invoice doc_no is required.")

    # transport details from artifact (your design)
    if not ewb_artifact.distance_km:
        raise ValueError("distance_km is required (set in SalesEWayBill before generation).")

    # ---- address fields (map to your invoice fields) ----
    # You must ensure these exist on SalesInvoiceHeader (or adjust mapping)
    from_pin = getattr(inv, "dispatch_from_pincode", None) or getattr(inv, "from_pincode", None)
    to_pin = getattr(inv, "ship_to_pincode", None) or getattr(inv, "to_pincode", None)
    to_state = getattr(inv, "ship_to_state_code", None) or getattr(inv, "place_of_supply_state_code", None)

     # FROM: entity pincode
    ent = getattr(inv, "entity", None)
    from_pin = getattr(ent, "pincode", None) if ent else None
    if not from_pin:
        raise ValueError("Entity pincode missing (invoice.entity.pincode).")

    # TO: ship-to snapshot pincode + state_code
    ship = getattr(inv, "ship_to_snapshot", None)
    to_pin = getattr(ship, "pincode", None) if ship else None
    to_state = getattr(ship, "state_code", None) if ship else None

    if not from_pin:
        raise ValueError("From pincode missing (dispatch_from_pincode/from_pincode).")
    if not to_pin:
        raise ValueError("To pincode missing (ship_to_pincode/to_pincode).")
    if not to_state:
        raise ValueError("To state code missing (ship_to_state_code/place_of_supply_state_code).")

    # ---- totals from invoice ----
    # adjust names if your header uses different fields
    total_taxable = _float(getattr(inv, "total_taxable_value", None))
    total_cgst = _float(getattr(inv, "total_cgst_amount", None))
    total_sgst = _float(getattr(inv, "total_sgst_amount", None))
    total_igst = _float(getattr(inv, "total_igst_amount", None))
    total_cess = _float(getattr(inv, "total_cess_amount", None))
    total_value = _float(getattr(inv, "grand_total", None) or getattr(inv, "total_invoice_value", None))

    if total_value <= 0:
        raise ValueError("Invoice total (grand_total/total_invoice_value) must be > 0.")

    # ---- lines ----
    # ensure your related_name is "lines"
    lines = list(inv.lines.all()) if hasattr(getattr(inv, "lines", None), "all") else (getattr(inv, "lines", []) or [])
    if not lines:
        raise ValueError("Invoice lines missing.")

    item_list: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines, start=1):
        hsn = getattr(ln, "hsn_sac_code", None) or getattr(ln, "hsn", None)
        if not hsn:
            raise ValueError(f"Line {idx}: HSN/SAC missing.")

        qty = _float(getattr(ln, "qty", None)) + _float(getattr(ln, "free_qty", None))
        if qty <= 0:
            raise ValueError(f"Line {idx}: qty must be > 0 (qty + free_qty).")

        # Names: pick your actual computed fields
        taxable = _float(getattr(ln, "taxable_value", None) or getattr(ln, "ass_amt", None))
        gst_rate = _float(getattr(ln, "gst_rate", None))
        cgst = _float(getattr(ln, "cgst_amount", None))
        sgst = _float(getattr(ln, "sgst_amount", None))
        igst = _float(getattr(ln, "igst_amount", None))
        cess = _float(getattr(ln, "cess_amount", None))

        # product/uom display (optional)
        uom = None
        if getattr(ln, "uom", None):
            uom = getattr(ln.uom, "code", None)
        uom = uom or getattr(ln, "uom_code", None) or "NOS"

        desc = None
        if getattr(ln, "product", None):
            desc = getattr(ln.product, "name", None)
        desc = desc or getattr(ln, "product_name", None) or "Item"

        item_list.append({
            "itemNo": idx,
            "productName": desc[:100],
            "productDesc": desc[:100],
            "hsnCode": str(hsn),
            "quantity": qty,
            "qtyUnit": uom,
            "taxableAmount": taxable,
            "gstRate": gst_rate,
            "cgstAmount": cgst,
            "sgstAmount": sgst,
            "igstAmount": igst,
            "cessAmount": cess,
        })

    payload: Dict[str, Any] = {
        "supplyType": "O",
        "subSupplyType": 1,

        "docType": (ewb_artifact.doc_type or "INV"),
        "docNo": (ewb_artifact.doc_no or str(doc_no)),
        "docDate": _ddmmyyyy(ewb_artifact.doc_date or inv.bill_date),

        "fromGstin": entity_gstin,
        "toGstin": "URP",  # B2C
        "toStateCode": _int(to_state),

        "fromPincode": _int(from_pin),
        "toPincode": _int(to_pin),

        "totalValue": total_value,
        "taxableAmount": total_taxable,
        "cgstValue": total_cgst,
        "sgstValue": total_sgst,
        "igstValue": total_igst,
        "cessValue": total_cess,

        # transport from artifact fields
        "transMode": str(ewb_artifact.transport_mode) if ewb_artifact.transport_mode is not None else None,
        "transDistance": _int(ewb_artifact.distance_km),

        "transporterId": ewb_artifact.transporter_id,
        "transporterName": ewb_artifact.transporter_name,

        "vehicleNo": ewb_artifact.vehicle_no,
        "vehicleType": ewb_artifact.vehicle_type,  # "R" or "O"

        # doc fields (LR/GR etc if applicable)
        "transDocNo": ewb_artifact.doc_no,
        "transDocDate": _ddmmyyyy(ewb_artifact.doc_date) if ewb_artifact.doc_date else None,

        "itemList": item_list,
    }

    # remove nulls (MasterGST often rejects nulls)
    payload = {k: v for k, v in payload.items() if v is not None and v != ""}
    return payload