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
    trans_doc_date: date
    vehicle_no: Optional[str]
    vehicle_type: Optional[str]  # "R"/"O"
    disp_dtls: Optional[Dict[str, Any]] = None
    exp_ship_dtls: Optional[Dict[str, Any]] = None


def build_generate_eway_payload(irn: str, x: EWayInput) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "Irn": irn,
        "Distance": int(x.distance_km),
        "TransMode": str(x.trans_mode),
        "TransId": x.transporter_id.strip(),
        "TransName": x.transporter_name.strip()[:100],
        "TransDocDt": _fmt_dt(x.trans_doc_date),
        "TransDocNo": x.trans_doc_no.strip()[:32],
    }

    # Road: include vehicle details (as in curl)
    if x.trans_mode == "1":
        if x.vehicle_no:
            payload["VehNo"] = x.vehicle_no.strip()[:20]
        if x.vehicle_type:
            payload["VehType"] = x.vehicle_type.strip()[:1]  # "R"/"O"

    if x.exp_ship_dtls:
        payload["ExpShipDtls"] = x.exp_ship_dtls
    if x.disp_dtls:
        payload["DispDtls"] = x.disp_dtls

    return payload