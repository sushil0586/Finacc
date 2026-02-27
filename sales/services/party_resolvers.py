from __future__ import annotations

from typing import Any, Dict, Optional
import re


def _name(x) -> Optional[str]:
    if not x:
        return None
    return getattr(x, "name", None) or getattr(x, "cityname", None) or str(x)


def _clean_loc(x: Optional[str]) -> str:
    """
    MasterGST validation:
      - Loc must be a string length 3..100
    """
    s = (x or "").strip()
    if len(s) < 3:
        return "UNK"  # 3 chars, safe default
    return s[:100]


def _clean_addr(x: Optional[str]) -> str:
    """
    Keep address non-empty. MasterGST/NIC typically dislikes null/empty.
    """
    s = (x or "").strip()
    return s if s else "NA"


def _clean_pin(pin) -> Optional[int]:
    if not pin:
        return None
    s = str(pin).strip()
    s = re.sub(r"\D", "", s)  # keep digits only
    if len(s) != 6:
        return None
    return int(s)


def _state_gst_code(state) -> str:
    # try common field names
    for f in ("gst_code", "gststatecode", "statecode", "tin", "code"):
        if hasattr(state, f) and getattr(state, f):
            s = str(getattr(state, f)).strip()
            # Many DBs store statecode like "29" already; ensure 2 digits
            return s.zfill(2)

    raise ValueError("State must have GST code field (gst_code/gststatecode/statecode/tin/code).")


def seller_from_entity(entity) -> Dict[str, Any]:
    if not entity.gstno:
        raise ValueError("Entity gstno is required.")

    return {
        "Gstin": str(entity.gstno).strip(),
        "LglNm": (entity.legalname or entity.entityname or "").strip() or "NA",
        "Addr1": _clean_addr(getattr(entity, "address", None)),
        "Addr2": (getattr(entity, "address2", None) or "").strip() or None,
        "Loc": _clean_loc(_name(getattr(entity, "city", None))),
        "Pin": _clean_pin(getattr(entity, "pincode", None)),
        "Stcd": _state_gst_code(entity.state),
        # Optional fields if you have them:
        # "Ph": str(entity.phone).strip()[:12] if getattr(entity, "phone", None) else None,
        # "Em": str(entity.email).strip()[:50] if getattr(entity, "email", None) else None,
    }


def buyer_from_account(acct, pos_state=None) -> Dict[str, Any]:
    stcd = _state_gst_code(acct.state) if getattr(acct, "state", None) else "00"
    pos = _state_gst_code(pos_state) if pos_state else stcd

    gstin = (getattr(acct, "gstno", None) or "").strip()
    if not gstin:
        gstin = "URP"

    return {
        "Gstin": gstin,
        "LglNm": (getattr(acct, "legalname", None) or getattr(acct, "accountname", None) or "").strip() or "NA",
        "Addr1": _clean_addr(getattr(acct, "address1", None)),
        "Addr2": (getattr(acct, "address2", None) or "").strip() or None,
        "Loc": _clean_loc(_name(getattr(acct, "city", None))),
        "Pin": _clean_pin(getattr(acct, "pincode", None)),
        "Stcd": stcd,
        "Pos": pos,
        # Optional:
        # "Ph": str(acct.phone).strip()[:12] if getattr(acct, "phone", None) else None,
        # "Em": str(acct.email).strip()[:50] if getattr(acct, "email", None) else None,
    }