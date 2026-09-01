from __future__ import annotations

from typing import Optional

from entity.models import SubEntity
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


def subentity_primary_gstin(subentity) -> Optional[str]:
    if not subentity:
        return None
    gst = subentity.gst_registrations.filter(isactive=True, is_primary=True).first()
    return (getattr(gst, "gstin", None) or "").strip().upper() or None


def subentity_primary_state(subentity):
    if not subentity:
        return None
    gst = subentity.gst_registrations.filter(isactive=True, is_primary=True).select_related("state").first()
    if gst and getattr(gst, "state", None):
        return gst.state
    addr = subentity.addresses.filter(isactive=True, is_primary=True).select_related("state").first()
    return getattr(addr, "state", None)


def seller_gstin_for_scope(entity, subentity=None, subentity_id: Optional[int] = None) -> Optional[str]:
    resolved_subentity = subentity
    if not resolved_subentity and subentity_id:
        resolved_subentity = SubEntity.objects.filter(id=subentity_id, entity=entity).first()
    return subentity_primary_gstin(resolved_subentity) or entity_primary_gstin(entity)


def seller_state_for_scope(entity, subentity=None, subentity_id: Optional[int] = None):
    resolved_subentity = subentity
    if not resolved_subentity and subentity_id:
        resolved_subentity = SubEntity.objects.filter(id=subentity_id, entity=entity).first()
    return subentity_primary_state(resolved_subentity) or entity_primary_state(entity)


def entity_primary_bank_account(entity):
    if not entity:
        return None
    return entity.bank_accounts_v2.filter(isactive=True, is_primary=True).first()


def entity_primary_contact(entity):
    if not entity:
        return None
    return entity.contacts.filter(isactive=True, is_primary=True).first()


def account_primary_state(acc):
    addr = account_primary_address(acc)
    return getattr(addr, "state", None)
