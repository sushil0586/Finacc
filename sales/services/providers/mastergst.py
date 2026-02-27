from __future__ import annotations

from typing import Any, Dict, Tuple, Optional

from sales.services.providers.base import IRNResult
from sales.services.providers.credential_resolver import CredentialResolver
from sales.services.providers.mastergst_client import MasterGSTClient


def _as_dict(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"_list": raw}
    return {"_raw": raw}

def _extract_error(raw_any):
    raw = _as_dict(raw_any)

    # direct message fields
    msg = raw.get("message") or raw.get("ErrorMessage")

    # MasterGST common
    err = raw.get("error") or raw.get("Error") or {}
    if isinstance(err, dict):
        msg = msg or err.get("message")
        code = err.get("error_cd") or raw.get("error_cd") or raw.get("ErrorCode")
    else:
        code = raw.get("error_cd") or raw.get("ErrorCode")

    # non-json case
    msg = msg or raw.get("_text") or raw.get("_raw")

    return (str(code) if code else None, str(msg) if msg else None)


def _pick(raw: Dict[str, Any], *keys: str):
    """
    Try keys in raw, then in raw['data'] if present.
    """
    for k in keys:
        if k in raw and raw[k] not in (None, ""):
            return raw[k]
    data = raw.get("data") or {}
    for k in keys:
        if k in data and data[k] not in (None, ""):
            return data[k]
    return None


class MasterGSTProvider:
    name = "mastergst"

    def generate_irn(self, *, invoice, payload: Dict[str, Any]) -> IRNResult:
        cred = CredentialResolver.mastergst_for_invoice(invoice)
        client = MasterGSTClient(cred)

        raw = client.generate_irn(payload)

        # ---- success fields (vary by response shape) ----
        irn = _pick(raw, "Irn", "irn")
        ack_no = _pick(raw, "AckNo", "ackNo")
        ack_date = _pick(raw, "AckDt", "ackDt")
        signed_invoice = _pick(raw, "SignedInvoice", "signedInvoice")
        signed_qr = _pick(raw, "SignedQRCode", "signedQRCode")

        # Some responses wrap in Result/Info
        if not irn:
            irn = _pick(raw, "IRN", "IrnNo")

        if not irn:
            code, msg = _extract_error(raw)
            return IRNResult(
                ok=False,
                error_code=code or "IRN_FAILED",
                error_message=msg or "IRN generation failed.",
                raw=_as_dict(raw),
            )

        return IRNResult(
            ok=True,
            irn=str(irn),
            ack_no=str(ack_no) if ack_no else None,
            ack_date=ack_date,
            signed_invoice=signed_invoice,
            signed_qr_code=signed_qr,
            raw=raw,
        )

    def cancel_irn(self, *, invoice, irn: str, reason_code: str, remarks: str | None = None) -> IRNResult:
        # We'll wire cancel later.
        return IRNResult(
            ok=False,
            error_code="NOT_IMPLEMENTED",
            error_message="Cancel IRN not wired yet.",
            raw={"irn": irn, "reason_code": reason_code, "remarks": remarks},
        )