from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import date
import re


def _clean_loc(s: Optional[str]) -> str:
    s = (s or "").strip()
    return s[:100] if len(s) >= 3 else "UNK"


def _clean_addr(s: Optional[str]) -> str:
    s = (s or "").strip()
    return s if s else "NA"


def _pin(pin: Optional[str]) -> Optional[int]:
    if not pin:
        return None
    s = re.sub(r"\D", "", str(pin))
    if len(s) != 6:
        return None
    return int(s)


def _stcd(st: Optional[str]) -> str:
    s = (st or "").strip()
    if not s:
        return "00"
    return s.zfill(2)


def _fmt_dt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def build_disp_dtls(
    name: Optional[str],
    addr1: Optional[str],
    addr2: Optional[str],
    loc: Optional[str],
    pin: Optional[str],
    stcd: Optional[str],
) -> Dict[str, Any]:
    out = {
        "Nm": (name or "").strip()[:100] or "NA",
        "Addr1": _clean_addr(addr1),
        "Addr2": (addr2 or "").strip() or None,
        "Loc": _clean_loc(loc),
        "Pin": _pin(pin),
        "Stcd": _stcd(stcd),
    }
    return {k: v for k, v in out.items() if v is not None}


def build_exp_ship_dtls(
    addr1: Optional[str],
    addr2: Optional[str],
    loc: Optional[str],
    pin: Optional[str],
    stcd: Optional[str],
) -> Dict[str, Any]:
    out = {
        "Addr1": _clean_addr(addr1),
        "Addr2": (addr2 or "").strip() or None,
        "Loc": _clean_loc(loc),
        "Pin": _pin(pin),
        "Stcd": _stcd(stcd),
    }
    return {k: v for k, v in out.items() if v is not None}


@dataclass(frozen=True)
class EWayInput:
    distance_km: int
    trans_mode: str            # "1"/"2"/"3"/"4"
    transporter_id: str        # GSTIN
    transporter_name: str
    trans_doc_no: str
    trans_doc_date: Optional[date]
    vehicle_no: Optional[str]
    vehicle_type: Optional[str]  # "R"/"O"
    disp_dtls: Optional[Dict[str, Any]] = None
    exp_ship_dtls: Optional[Dict[str, Any]] = None


def build_generate_eway_payload(irn: str, x: EWayInput) -> Dict[str, Any]:
    trans_mode = str(x.trans_mode or "").strip()
    trans_doc_no = (x.trans_doc_no or "").strip()
    transporter_id = (x.transporter_id or "").strip()
    transporter_name = (x.transporter_name or "").strip()
    payload: Dict[str, Any] = {
        "Irn": irn,
        "Distance": int(x.distance_km),
        "TransMode": trans_mode,
    }
    if transporter_id:
        payload["TransId"] = transporter_id[:15]
    if transporter_name:
        payload["TransName"] = transporter_name[:100]
    if trans_doc_no:
        payload["TransDocNo"] = trans_doc_no[:15]
    if x.trans_doc_date:
        payload["TransDocDt"] = _fmt_dt(x.trans_doc_date)

    # Road: include vehicle details (as in curl)
    if trans_mode == "1":
        veh_no = (x.vehicle_no or "").strip()
        veh_type = (x.vehicle_type or "").strip().upper()
        if not veh_no:
            raise ValueError("VehNo is required for road transport (TransMode=1).")
        if veh_type not in {"R", "O"}:
            raise ValueError("VehType must be R/O for road transport.")
        payload["VehNo"] = veh_no[:20]
        payload["VehType"] = veh_type
    else:
        # Rail/Air/Ship => transport document is mandatory.
        if not trans_doc_no or not x.trans_doc_date:
            raise ValueError("TransDocNo and TransDocDt are required for Rail/Air/Ship transport.")

    if x.exp_ship_dtls:
        payload["ExpShipDtls"] = x.exp_ship_dtls
    if x.disp_dtls:
        payload["DispDtls"] = x.disp_dtls

    return payload
