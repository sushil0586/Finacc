from __future__ import annotations

from typing import Any, Dict, Tuple, Optional
import json

from sales.services.providers.base import IRNResult, EWayResult
from sales.services.providers.credential_resolver import CredentialResolver
from sales.services.providers.mastergst_client import MasterGSTClient
from sales.services.compliance_error_catalog_service import ComplianceErrorCatalogService


def _as_dict(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"_list": raw}
    return {"_raw": raw}

def _extract_error(raw_any):
    raw = _as_dict(raw_any)

    # direct message fields
    msg = raw.get("message") or raw.get("Message") or raw.get("ErrorMessage")
    code = raw.get("error_cd") or raw.get("ErrorCode") or raw.get("code")

    # MasterGST/NIC often returns status_desc='[{"ErrorCode":"xxxx","ErrorMessage":"..."}]'
    status_desc = raw.get("status_desc")
    if isinstance(status_desc, str):
        s = status_desc.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and arr:
                    first = arr[0] if isinstance(arr[0], dict) else {}
                    code = code or first.get("ErrorCode") or first.get("error_code") or first.get("code")
                    msg = msg or first.get("ErrorMessage") or first.get("error_message") or first.get("message")
            except Exception:
                pass

    # MasterGST common
    err = raw.get("error") or raw.get("Error") or {}
    if isinstance(err, dict):
        msg = msg or err.get("message")
        code = code or err.get("error_cd") or err.get("ErrorCode")

    # non-json case
    msg = msg or raw.get("_text") or raw.get("_raw")

    code_s = str(code) if code else None
    msg_s = str(msg) if msg else None
    info = ComplianceErrorCatalogService.resolve(code=code_s, message=msg_s)
    return (info.code, info.message, info.reason, info.resolution)


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
    client_provider_name = "mastergst"

    def generate_irn(self, *, invoice, payload: Dict[str, Any]) -> IRNResult:
        cred = CredentialResolver.provider_for_invoice(invoice, provider_name=self.name)
        client = MasterGSTClient(cred, provider_name=self.client_provider_name)

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
            code, msg, reason, resolution = _extract_error(raw)
            return IRNResult(
                ok=False,
                error_code=code or "IRN_FAILED",
                error_message=msg or "IRN generation failed.",
                error_reason=reason,
                error_resolution=resolution,
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
        cred = CredentialResolver.provider_for_invoice(invoice, provider_name=self.name)
        client = MasterGSTClient(cred, provider_name=self.client_provider_name)
        payload = {
            "Irn": irn,
            "CnlRsn": str(reason_code),
            "CnlRem": (remarks or "Cancelled from system")[:100],
        }
        raw = client.cancel_irn(payload)
        status_cd = str(raw.get("status_cd") or "")
        if status_cd == "1":
            return IRNResult(ok=True, irn=irn, raw=raw)
        code, msg, reason, resolution = _extract_error(raw)
        return IRNResult(
            ok=False,
            error_code=code or "IRN_CANCEL_FAILED",
            error_message=msg or "IRN cancellation failed.",
            error_reason=reason,
            error_resolution=resolution,
            raw=raw,
        )

    def get_irn_details(self, *, invoice, irn: str, supplier_gstin: str | None = None) -> IRNResult:
        cred = CredentialResolver.provider_for_invoice(invoice, provider_name=self.name)
        client = MasterGSTClient(cred, provider_name=self.client_provider_name)
        raw = client.get_irn_details(irn=irn, supplier_gstin=supplier_gstin)

        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return IRNResult(
                ok=False,
                error_code=code or "IRN_GET_FAILED",
                error_message=msg or "IRN details fetch failed.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        irn_out = _pick(raw, "Irn", "IRN", "irn")
        if not irn_out:
            code, msg, reason, resolution = _extract_error(raw)
            return IRNResult(
                ok=False,
                error_code=code or "IRN_GET_FAILED",
                error_message=msg or "IRN missing in response.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        return IRNResult(
            ok=True,
            irn=str(irn_out),
            ack_no=str(_pick(raw, "AckNo", "ackNo")) if _pick(raw, "AckNo", "ackNo") else None,
            ack_date=_pick(raw, "AckDt", "ackDt"),
            signed_invoice=_pick(raw, "SignedInvoice", "signedInvoice"),
            signed_qr_code=_pick(raw, "SignedQRCode", "signedQRCode"),
            ewb_no=str(_pick(raw, "EwbNo", "ewayBillNo")) if _pick(raw, "EwbNo", "ewayBillNo") else None,
            ewb_date=_pick(raw, "EwbDt", "ewayBillDate"),
            ewb_valid_upto=_pick(raw, "EwbValidTill", "validUpto"),
            raw=raw,
        )

    def get_eway_details_by_irn(self, *, invoice, irn: str, supplier_gstin: str | None = None) -> EWayResult:
        cred = CredentialResolver.provider_for_invoice(invoice, provider_name=self.name)
        client = MasterGSTClient(cred, provider_name=self.client_provider_name)
        raw = client.get_eway_details_by_irn(irn=irn, supplier_gstin=supplier_gstin)

        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return EWayResult(
                ok=False,
                error_code=code or "EWB_GET_FAILED",
                error_message=msg or "EWB details by IRN fetch failed.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        ewb_no = _pick(raw, "EwbNo", "ewayBillNo", "ewbNo")
        if not ewb_no:
            code, msg, reason, resolution = _extract_error(raw)
            return EWayResult(
                ok=False,
                error_code=code or "EWB_GET_FAILED",
                error_message=msg or "EWB number missing in response.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        return EWayResult(
            ok=True,
            ewb_no=str(ewb_no),
            ewb_date=_pick(raw, "EwbDt", "ewayBillDate"),
            valid_upto=_pick(raw, "EwbValidTill", "validUpto"),
            raw=raw,
        )


class WhitebooksProvider(MasterGSTProvider):
    # Whitebooks currently follows the same contract and payloads.
    # Keeping this as an alias provider allows a clean runtime switch.
    name = "whitebooks"
    client_provider_name = "whitebooks"
