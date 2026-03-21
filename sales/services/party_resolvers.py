from __future__ import annotations

from typing import Any, Dict, Optional
import re
from financial.profile_access import account_gstno

GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")


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


def _clean_pin_required(pin, field_label: str) -> int:
    v = _clean_pin(pin)
    if v is None:
        raise ValueError(f"{field_label} must be a valid 6-digit pincode.")
    return v


def _state_gst_code(state) -> str:
    if state is None:
        raise ValueError("State is required.")
    if isinstance(state, str):
        s = state.strip()
        if s.isdigit():
            return s.zfill(2)
        raise ValueError("State code string must be numeric.")

    # try common field names
    for f in ("gst_code", "gststatecode", "statecode", "tin", "code"):
        if hasattr(state, f) and getattr(state, f):
            s = str(getattr(state, f)).strip()
            # Many DBs store statecode like "29" already; ensure 2 digits
            s = s.zfill(2)
            if s == "00":
                raise ValueError("State code cannot be 00.")
            return s

    raise ValueError("State must have GST code field (gst_code/gststatecode/statecode/tin/code).")


def _normalize_gstin(gstin: Optional[str], *, allow_urp: bool = False) -> str:
    s = (gstin or "").strip().upper()
    if allow_urp and s == "URP":
        return "URP"
    if not GSTIN_RE.fullmatch(s):
        raise ValueError("GSTIN must be 15 uppercase alphanumeric characters.")
    return s


def seller_from_entity(entity) -> Dict[str, Any]:
    gst_row = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
    if not gst_row:
        raise ValueError("Entity gstno is required.")
    gstin = _normalize_gstin(getattr(gst_row, "gstin", None), allow_urp=False)
    addr = (
        entity.addresses.filter(isactive=True, is_primary=True)
        .select_related("state", "city")
        .first()
    )
    contact = entity.contacts.filter(isactive=True, is_primary=True).first()

    out = {
        "Gstin": gstin,
        "LglNm": (entity.legalname or entity.entityname or "").strip() or "NA",
        "Addr1": _clean_addr(getattr(addr, "line1", None)),
        "Addr2": (getattr(addr, "line2", None) or "").strip() or None,
        "Loc": _clean_loc(_name(getattr(addr, "city", None))),
        "Pin": _clean_pin_required(getattr(addr, "pincode", None), "Seller pincode"),
        "Stcd": _state_gst_code(getattr(addr, "state", None)),
        # Optional fields if you have them:
        # "Ph": str(entity.phone).strip()[:12] if getattr(entity, "phone", None) else None,
        # "Em": str(entity.email).strip()[:50] if getattr(entity, "email", None) else None,
    }
    trd = (getattr(entity, "entityname", None) or "").strip()
    ph = (getattr(contact, "mobile", None) or getattr(entity, "contactno", None) or getattr(entity, "phone", None) or "").strip()
    em = (getattr(contact, "email", None) or getattr(entity, "emailid", None) or getattr(entity, "email", None) or "").strip()
    if trd:
        out["TrdNm"] = trd[:100]
    if ph:
        out["Ph"] = re.sub(r"\D", "", ph)[:12]
    if em:
        out["Em"] = em[:100]
    return out


def buyer_from_account(acct, pos_state=None) -> Dict[str, Any]:
    stcd = _state_gst_code(acct.state) if getattr(acct, "state", None) else "00"
    pos = _state_gst_code(pos_state) if pos_state else stcd

    gstin = (account_gstno(acct) or "").strip()
    if not gstin:
        gstin = "URP"
    gstin = _normalize_gstin(gstin, allow_urp=True)
    if stcd == "00" and gstin != "URP":
        raise ValueError("Buyer state code is required for registered GSTIN buyer.")

    out = {
        "Gstin": gstin,
        "LglNm": (getattr(acct, "legalname", None) or getattr(acct, "accountname", None) or "").strip() or "NA",
        "Addr1": _clean_addr(getattr(acct, "address1", None)),
        "Addr2": (getattr(acct, "address2", None) or "").strip() or None,
        "Loc": _clean_loc(_name(getattr(acct, "city", None))),
        "Pin": _clean_pin_required(getattr(acct, "pincode", None), "Buyer pincode"),
        "Stcd": stcd,
        "Pos": pos,
        # Optional:
        # "Ph": str(acct.phone).strip()[:12] if getattr(acct, "phone", None) else None,
        # "Em": str(acct.email).strip()[:50] if getattr(acct, "email", None) else None,
    }
    trd = (getattr(acct, "accountname", None) or "").strip()
    ph = (getattr(acct, "contactno", None) or getattr(acct, "phone", None) or "").strip()
    em = (getattr(acct, "emailid", None) or getattr(acct, "email", None) or "").strip()
    if trd:
        out["TrdNm"] = trd[:100]
    if ph:
        out["Ph"] = re.sub(r"\D", "", ph)[:12]
    if em:
        out["Em"] = em[:100]
    return out
