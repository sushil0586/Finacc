from __future__ import annotations

from typing import Any, Dict, Optional
from django.utils import timezone


def _fmt_dt(d) -> str:
    # MasterGST expects dd/mm/YYYY
    return d.strftime("%d/%m/%Y")


def _clean_loc(s: Optional[str]) -> str:
    s = (s or "").strip()
    return (s[:100] if len(s) >= 3 else "UNK")


def _clean_addr(s: Optional[str]) -> str:
    s = (s or "").strip()
    return s if s else "NA"


def _pin(pin) -> Optional[int]:
    if not pin:
        return None
    try:
        x = int(str(pin).strip())
        return x
    except Exception:
        return None


def build_addr_block(name: Optional[str], addr1: Optional[str], addr2: Optional[str], loc: Optional[str], pin, stcd: str) -> Dict[str, Any]:
    out = {
        "Addr1": _clean_addr(addr1),
        "Addr2": (addr2 or "").strip() or None,
        "Loc": _clean_loc(loc),
        "Pin": _pin(pin),
        "Stcd": str(stcd).zfill(2),
    }
    if name:
        out["Nm"] = str(name).strip()[:100]
    # Remove None values to keep payload clean
    return {k: v for k, v in out.items() if v is not None}


class EWayPayloadBuilder:
    """
    Builds payload for MasterGST GENERATE_EWAYBILL (V1_03) based on:
      - IRN stored in SalesEInvoice
      - Transport details from invoice / UI
    """

    def __init__(
        self,
        irn: str,
        distance: int,
        trans_mode: str,
        trans_id: str,
        trans_name: str,
        trans_doc_no: str,
        trans_doc_date,   # date
        veh_no: str,
        veh_type: str,
        exp_ship_dtls: Optional[Dict[str, Any]] = None,
        disp_dtls: Optional[Dict[str, Any]] = None,
    ):
        self.irn = irn
        self.distance = distance
        self.trans_mode = trans_mode
        self.trans_id = trans_id
        self.trans_name = trans_name
        self.trans_doc_no = trans_doc_no
        self.trans_doc_date = trans_doc_date
        self.veh_no = veh_no
        self.veh_type = veh_type
        self.exp_ship_dtls = exp_ship_dtls
        self.disp_dtls = disp_dtls

    def build(self) -> Dict[str, Any]:
        payload = {
            "Irn": self.irn,
            "Distance": int(self.distance),
            "TransMode": str(self.trans_mode),
            "TransId": str(self.trans_id).strip(),
            "TransName": str(self.trans_name).strip()[:100],
            "TransDocDt": _fmt_dt(self.trans_doc_date),
            "TransDocNo": str(self.trans_doc_no).strip()[:15],
            "VehNo": str(self.veh_no).strip()[:20],
            "VehType": str(self.veh_type).strip(),
        }
        if self.exp_ship_dtls:
            payload["ExpShipDtls"] = self.exp_ship_dtls
        if self.disp_dtls:
            payload["DispDtls"] = self.disp_dtls
        return payload