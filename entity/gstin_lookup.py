from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from rest_framework.exceptions import ValidationError

from entity.models import EntityGstRegistration, SubEntityGstRegistration
from financial.models import account
from geography.models import City, State
from sales.services.providers.credential_resolver import CredentialResolver
from sales.services.providers.mastergst import _extract_error
from sales.services.providers.whitebooks_client import WhitebooksClient


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
SANDBOX_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$")


def _pick(data: dict[str, Any], *keys: str):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _provider_data(raw: dict[str, Any]) -> dict[str, Any]:
    data: Any = raw.get("data", raw)
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    return data if isinstance(data, dict) else {}


def lookup_gstin(*, gstin: str, credential_entity_id: int, duplicate_entity_id: int | None = None) -> dict[str, Any]:
    normalized = str(gstin or "").strip().upper()
    allow_sandbox_gstin = bool(getattr(settings, "WHITEBOOKS_SANDBOX_MODE", False)) and bool(
        getattr(settings, "ALLOW_RELAXED_GSTIN_FOR_SANDBOX", False)
    )
    valid_pattern = SANDBOX_GSTIN_RE if allow_sandbox_gstin else GSTIN_RE
    if not valid_pattern.fullmatch(normalized):
        raise ValidationError({"gstno": "Enter a valid 15-character GSTIN."})
    if not credential_entity_id:
        raise ValidationError({"gstno": "GSTIN lookup is not configured. Please enter the details manually."})

    credential = CredentialResolver.provider_for_entity(credential_entity_id, provider_name="whitebooks")
    raw = WhitebooksClient(credential).get_gstn_details(gstin=normalized)
    if str(raw.get("status_cd") or "") != "1":
        _, message, _, _ = _extract_error(raw)
        raise ValidationError({"gstno": message or "GSTIN details could not be fetched."})

    data = _provider_data(raw)
    returned_gstin = str(_pick(data, "Gstin", "gstin", "GSTIN") or normalized).strip().upper()
    registration_status = str(_pick(data, "Status", "sts", "status") or "").strip()
    state_code = str(_pick(data, "StateCode", "stjCd", "state_code") or returned_gstin[:2]).strip().zfill(2)
    pincode = _pick(data, "AddrPncd", "pncd", "pincode")
    state = State.objects.filter(isactive=True, statecode=state_code).first()
    cities = City.objects.filter(isactive=True, pincode=pincode)
    if state:
        cities = cities.filter(distt__state=state, distt__isactive=True)
    city = cities.select_related("distt", "distt__state", "distt__state__country").order_by("id").first()
    district = city.distt if city else None
    country = state.country if state else None

    duplicate: dict[str, Any] | None = None
    if duplicate_entity_id:
        existing = account.objects.filter(
            entity_id=duplicate_entity_id,
            compliance_profile__gstno__iexact=returned_gstin,
        ).only("id", "accountname", "accountcode").first()
        if existing:
            duplicate = {"type": "account", "id": existing.id, "name": existing.accountname, "code": existing.accountcode}
    else:
        entity_registration = EntityGstRegistration.objects.filter(gstin__iexact=returned_gstin, isactive=True).first()
        branch_registration = SubEntityGstRegistration.objects.filter(gstin__iexact=returned_gstin, isactive=True).first()
        registration = entity_registration or branch_registration
        if registration:
            owner_entity_id = (
                registration.entity_id
                if entity_registration
                else registration.subentity.entity_id
            )
            duplicate = {"type": "entity", "id": owner_entity_id}

    legal_name = _pick(data, "LegalName", "lgnm", "legal_name", "Legalname")
    block_status = _pick(data, "BlkStatus", "blkStatus")
    return {
        "gstno": returned_gstin,
        "gstin": returned_gstin,
        "entityname": _pick(data, "TradeName", "tradeNam", "trade_name") or _pick(data, "LegalName", "lgnm", "legal_name"),
        "legalname": legal_name,
        "legalName": legal_name,
        "address": _pick(data, "AddrBnm", "bnm", "address1"),
        "address2": _pick(data, "AddrBno", "bno", "address2"),
        "addressfloorno": _pick(data, "AddrFlno", "flno"),
        "addressstreet": _pick(data, "AddrSt", "st", "street"),
        "stateid": state.id if state else None,
        "cityid": city.id if city else None,
        "countryid": country.id if country else None,
        "disttid": district.id if district else None,
        "pincode": pincode,
        "gstintype": _pick(data, "TxpType", "dty", "taxpayer_type"),
        "dateofreg": _pick(data, "DtReg", "rgdt"),
        "dateofdreg": _pick(data, "DtDReg", "cxdt"),
        "blockstatus": block_status,
        "blkStatus": block_status,
        "status": registration_status,
        "is_active": registration_status.strip().lower() in {"active", "act"},
        "pan": returned_gstin[2:12],
        "duplicate": duplicate,
        "source": "whitebooks",
    }


def public_lookup_entity_id() -> int:
    return int(getattr(settings, "WHITEBOOKS_GST_LOOKUP_ENTITY_ID", 0) or 0)
