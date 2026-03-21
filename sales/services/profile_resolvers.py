from __future__ import annotations

from typing import Optional

from financial.profile_access import account_primary_address


def entity_primary_gstin(entity) -> Optional[str]:
    if not entity:
        return None
    gst = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
    return (getattr(gst, "gstin", None) or "").strip().upper() or None


def entity_primary_address(entity):
    if not entity:
        return None
    return entity.addresses.filter(isactive=True, is_primary=True).select_related("state", "city").first()


def entity_primary_state(entity):
    addr = entity_primary_address(entity)
    return getattr(addr, "state", None)


def account_primary_state(acc):
    addr = account_primary_address(acc)
    return getattr(addr, "state", None)
