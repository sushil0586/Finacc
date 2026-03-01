from __future__ import annotations
from typing import Any, Dict, List

def _ddmmyyyy(d) -> str:
    return d.strftime("%d/%m/%Y")

def _float(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def build_b2c_direct_payload(*, invoice: Any, ewb: Any, entity_gstin: str) -> Dict[str, Any]:
    """
    Build direct EWB payload for B2C (no IRN).
    Uses:
      FROM: invoice.entity.pincode
      TO  : invoice.ship_to_snapshot.pincode/state_code
      Transport: saved in SalesEWayBill (ewb)
    """

    if str(getattr(invoice, "supply_category", "")).upper() != "B2C":
        raise ValueError("B2C payload builder called for non-B2C invoice.")

    ent = getattr(invoice, "entity", None)
    if not ent or not getattr(ent, "pincode", None):
        raise ValueError("Entity pincode missing (invoice.entity.pincode).")

    ship = getattr(invoice, "ship_to_snapshot", None)
    if not ship:
        raise ValueError("Ship-to snapshot missing (invoice.ship_to_snapshot).")
    if not getattr(ship, "pincode", None):
        raise ValueError("Ship-to pincode missing (invoice.ship_to_snapshot.pincode).")
    if not getattr(ship, "state_code", None):
        raise ValueError("Ship-to state_code missing (invoice.ship_to_snapshot.state_code).")

    if not getattr(invoice, "bill_date", None):
        raise ValueError("Invoice bill_date missing.")
    doc_no = getattr(invoice, "doc_no", None) or getattr(invoice, "invoice_no", None)
    if not doc_no:
        raise ValueError("Invoice doc_no missing.")

    # transport validations (from your SalesEWayBill)
    if not ewb.distance_km:
        raise ValueError("EWB distance_km missing (set in SalesEWayBill).")
    if ewb.transport_mode == 1 and not ewb.vehicle_no:
        raise ValueError("vehicle_no required for Road (transport_mode=1).")

    # totals (adjust if your field names differ)
    total_taxable = _float(getattr(invoice, "total_taxable_value", None))
    total_cgst = _float(getattr(invoice, "total_cgst_amount", None))
    total_sgst = _float(getattr(invoice, "total_sgst_amount", None))
    total_igst = _float(getattr(invoice, "total_igst_amount", None))
    total_cess = _float(getattr(invoice, "total_cess_amount", None))
    total_value = _float(getattr(invoice, "grand_total", None) or getattr(invoice, "total_invoice_value", None))

    if total_value <= 0:
        raise ValueError("Invoice grand_total/total_invoice_value must be > 0.")

    # lines
    lines = list(invoice.lines.all())
    if not lines:
        raise ValueError("Invoice lines missing.")

    item_list: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines, start=1):
        hsn = getattr(ln, "hsn_sac_code", None)
        if not hsn:
            raise ValueError(f"Line {idx}: hsn_sac_code missing.")

        qty = _float(getattr(ln, "qty", None)) + _float(getattr(ln, "free_qty", None))
        if qty <= 0:
            raise ValueError(f"Line {idx}: qty + free_qty must be > 0.")

        taxable = _float(getattr(ln, "taxable_value", None))
        gst_rate = _float(getattr(ln, "gst_rate", None))
        cgst = _float(getattr(ln, "cgst_amount", None))
        sgst = _float(getattr(ln, "sgst_amount", None))
        igst = _float(getattr(ln, "igst_amount", None))
        cess = _float(getattr(ln, "cess_amount", None))

        # uom / desc
        uom = getattr(getattr(ln, "uom", None), "code", None) or "NOS"
        desc = getattr(getattr(ln, "product", None), "name", None) or "Item"

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

    payload = {
        "supplyType": "O",
        "subSupplyType": 1,
        "docType": (ewb.doc_type or "INV"),
        "docNo": (ewb.doc_no or str(doc_no)),
        "docDate": _ddmmyyyy(ewb.doc_date or invoice.bill_date),

        "fromGstin": entity_gstin,
        "toGstin": "URP",
        "toStateCode": int(ship.state_code),

        "fromPincode": int(ent.pincode),
        "toPincode": int(ship.pincode),

        "totalValue": total_value,
        "taxableAmount": total_taxable,
        "cgstValue": total_cgst,
        "sgstValue": total_sgst,
        "igstValue": total_igst,
        "cessValue": total_cess,

        "transMode": str(ewb.transport_mode) if ewb.transport_mode is not None else None,
        "transDistance": int(ewb.distance_km),

        "transporterId": ewb.transporter_id,
        "transporterName": ewb.transporter_name,
        "vehicleNo": ewb.vehicle_no,
        "vehicleType": ewb.vehicle_type,

        "transDocNo": ewb.doc_no,
        "transDocDate": _ddmmyyyy(ewb.doc_date) if ewb.doc_date else None,

        "itemList": item_list,
    }

    # remove null keys
    payload = {k: v for k, v in payload.items() if v is not None and v != ""}
    return payload