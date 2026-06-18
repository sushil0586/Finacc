from __future__ import annotations

from typing import Any, Dict, Tuple, Optional
import json

from sales.services.providers.base import IRNResult, EWayResult, GSTNDetailsResult, QRCodeResult, LookupResult
from sales.services.providers.credential_resolver import CredentialResolver
from sales.services.providers.mastergst_client import MasterGSTClient
from sales.services.compliance_error_catalog_service import ComplianceErrorCatalogService
from sales.models.mastergst_models import MasterGSTServiceScope


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
    client_class = MasterGSTClient

    def _client_for_invoice(self, invoice, *, service_scope: int = MasterGSTServiceScope.EINVOICE):
        cred = CredentialResolver.provider_for_invoice(
            invoice,
            provider_name=self.name,
            service_scope=service_scope,
        )
        return self.client_class(cred, provider_name=self.client_provider_name)

    @staticmethod
    def _normalize_irn_lookup_result(raw: Dict[str, Any], *, failed_code: str, failed_message: str) -> IRNResult:
        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return IRNResult(
                ok=False,
                error_code=code or failed_code,
                error_message=msg or failed_message,
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        irn_out = _pick(raw, "Irn", "IRN", "irn")
        if not irn_out:
            code, msg, reason, resolution = _extract_error(raw)
            return IRNResult(
                ok=False,
                error_code=code or failed_code,
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

    @staticmethod
    def _normalize_lookup_result(raw: Dict[str, Any], *, failed_code: str, failed_message: str) -> LookupResult:
        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return LookupResult(
                ok=False,
                error_code=code or failed_code,
                error_message=msg or failed_message,
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        data = raw.get("data")
        if data in (None, "", []):
            data = raw.get("_json")
        if data in (None, "", []):
            data = raw
        return LookupResult(ok=True, data=data, raw=raw)

    def generate_irn(self, *, invoice, payload: Dict[str, Any]) -> IRNResult:
        client = self._client_for_invoice(invoice)
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
        client = self._client_for_invoice(invoice)
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
        client = self._client_for_invoice(invoice)
        raw = client.get_irn_details(irn=irn, supplier_gstin=supplier_gstin)
        return self._normalize_irn_lookup_result(
            raw,
            failed_code="IRN_GET_FAILED",
            failed_message="IRN details fetch failed.",
        )

    def get_irn_details_by_doc(self, *, invoice, doc_type: str, doc_number: str, doc_date: str) -> IRNResult:
        client = self._client_for_invoice(invoice)
        raw = client.get_irn_details_by_doc(doc_type=doc_type, doc_number=doc_number, doc_date=doc_date)
        return self._normalize_irn_lookup_result(
            raw,
            failed_code="IRN_GET_BY_DOC_FAILED",
            failed_message="IRN details by document fetch failed.",
        )

    def get_gstn_details(self, *, invoice, gstin: str) -> GSTNDetailsResult:
        client = self._client_for_invoice(invoice)
        raw = client.get_gstn_details(gstin=gstin)

        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return GSTNDetailsResult(
                ok=False,
                error_code=code or "GSTN_GET_FAILED",
                error_message=msg or "GSTN details fetch failed.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        return GSTNDetailsResult(
            ok=True,
            gstin=str(
                data.get("Gstin")
                or data.get("gstin")
                or data.get("GSTIN")
                or gstin
            ),
            legal_name=(
                data.get("LegalName")
                or data.get("lgnm")
                or data.get("legal_name")
                or data.get("Legalname")
            ),
            trade_name=(
                data.get("TradeName")
                or data.get("tradeNam")
                or data.get("trade_name")
                or data.get("TradeName")
            ),
            status=(
                data.get("Status")
                or data.get("sts")
                or data.get("status")
            ),
            raw=raw,
        )

    def sync_gstin_from_cp(self, *, invoice, gstin: str) -> GSTNDetailsResult:
        client = self._client_for_invoice(invoice)
        raw = client.sync_gstin_from_cp(gstin=gstin)

        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return GSTNDetailsResult(
                ok=False,
                error_code=code or "GSTN_SYNC_FAILED",
                error_message=msg or "GSTIN sync from CP failed.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        return GSTNDetailsResult(
            ok=True,
            gstin=str(
                data.get("Gstin")
                or data.get("gstin")
                or data.get("GSTIN")
                or gstin
            ),
            legal_name=(
                data.get("LegalName")
                or data.get("lgnm")
                or data.get("legal_name")
                or data.get("Legalname")
            ),
            trade_name=(
                data.get("TradeName")
                or data.get("tradeNam")
                or data.get("trade_name")
                or data.get("TradeName")
            ),
            status=(
                data.get("Status")
                or data.get("sts")
                or data.get("status")
            ),
            raw=raw,
        )

    def get_b2c_qrcode(self, *, invoice, payload: Dict[str, Any]) -> QRCodeResult:
        client = self._client_for_invoice(invoice)
        raw = client.get_b2c_qrcode(payload=payload)

        status_cd = str(raw.get("status_cd") or "")
        qr_code = _pick(raw, "qrCode", "QRCode", "SignedQRCode", "signedQRCode")
        if not qr_code and raw.get("_raw_text") and not raw.get("_not_json"):
            qr_code = raw.get("_raw_text")
        if not qr_code and raw.get("_raw_text") and str(raw.get("_http_status") or "") == "200":
            qr_code = raw.get("_raw_text")

        if status_cd and status_cd != "1" and not qr_code:
            code, msg, reason, resolution = _extract_error(raw)
            return QRCodeResult(
                ok=False,
                error_code=code or "B2C_QRCODE_FAILED",
                error_message=msg or "B2C QR code fetch failed.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        if not qr_code:
            code, msg, reason, resolution = _extract_error(raw)
            return QRCodeResult(
                ok=False,
                error_code=code or "B2C_QRCODE_FAILED",
                error_message=msg or "QR code missing in response.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        return QRCodeResult(
            ok=True,
            qr_code=str(qr_code),
            raw=raw,
        )

    def get_eway_details_by_irn(self, *, invoice, irn: str, supplier_gstin: str | None = None) -> EWayResult:
        client = self._client_for_invoice(invoice)
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

    def get_eway_details(self, *, invoice, ewb_no: str) -> EWayResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_details(ewb_no=ewb_no)

        status_cd = str(raw.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = _extract_error(raw)
            return EWayResult(
                ok=False,
                error_code=code or "EWB_GET_FAILED",
                error_message=msg or "EWB details fetch failed.",
                error_reason=reason,
                error_resolution=resolution,
                raw=_as_dict(raw),
            )

        resolved_ewb_no = _pick(raw, "ewayBillNo", "EwbNo", "ewbNo") or ewb_no
        return EWayResult(
            ok=True,
            ewb_no=str(resolved_ewb_no),
            ewb_date=_pick(raw, "ewayBillDate", "EwbDt"),
            valid_upto=_pick(raw, "validUpto", "EwbValidTill"),
            raw=raw,
        )

    def get_transporter_details(self, *, invoice, transporter_id: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_transporter_details(transporter_id=transporter_id)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_TRANSPORTER_DETAILS_FAILED",
            failed_message="Transporter details fetch failed.",
        )

    def get_gstin_details(self, *, invoice, gstin: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_gstin_details(gstin=gstin)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_GSTIN_DETAILS_FAILED",
            failed_message="GSTIN details fetch failed.",
        )

    def get_hsn_details(self, *, invoice, hsn_code: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_hsn_details(hsn_code=hsn_code)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_HSN_DETAILS_FAILED",
            failed_message="HSN details fetch failed.",
        )

    def get_error_list(self, *, invoice) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_error_list()
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_ERROR_LIST_FAILED",
            failed_message="E-Way error list fetch failed.",
        )

    def reject_eway(self, *, invoice, ewb_no: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        ewb_no_value = str(ewb_no or "").strip()
        payload = {"ewbNo": int(ewb_no_value) if ewb_no_value.isdigit() else ewb_no_value}
        raw = client.reject_eway(payload)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_REJECT_FAILED",
            failed_message="E-Way rejection failed.",
        )

    def get_trip_sheet(self, *, invoice, trip_sheet_no: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_trip_sheet(trip_sheet_no=trip_sheet_no)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_TRIP_SHEET_FAILED",
            failed_message="Trip sheet fetch failed.",
        )

    def get_eway_by_document(self, *, invoice, doc_type: str, doc_no: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_by_document(doc_type=doc_type, doc_no=doc_no)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_GET_BY_DOC_FAILED",
            failed_message="E-Way document lookup failed.",
        )

    def get_eway_bills_for_transporter(self, *, invoice, date: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bills_for_transporter(date=date)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_FOR_TRANSPORTER_FAILED",
            failed_message="Transporter E-Way list fetch failed.",
        )

    def get_eway_bill_report_by_transporter_assigned_date(self, *, invoice, date: str, state_code: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bill_report_by_transporter_assigned_date(date=date, state_code=state_code)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_TRANSPORTER_REPORT_FAILED",
            failed_message="Transporter assigned-date report fetch failed.",
        )

    def get_eway_bills_by_date(self, *, invoice, date: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bills_by_date(date=date)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_BY_DATE_FAILED",
            failed_message="E-Way date-wise list fetch failed.",
        )

    def get_eway_bills_rejected_by_others(self, *, invoice, date: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bills_rejected_by_others(date=date)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_REJECTED_BY_OTHERS_FAILED",
            failed_message="Rejected E-Way list fetch failed.",
        )

    def get_eway_bills_for_transporter_by_gstin(self, *, invoice, gen_gstin: str, date: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bills_for_transporter_by_gstin(gen_gstin=gen_gstin, date=date)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_FOR_TRANSPORTER_GSTIN_FAILED",
            failed_message="Transporter GSTIN/date report fetch failed.",
        )

    def get_eway_bills_for_transporter_by_state(self, *, invoice, state_code: str, date: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bills_for_transporter_by_state(state_code=state_code, date=date)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_FOR_TRANSPORTER_STATE_FAILED",
            failed_message="Transporter state/date report fetch failed.",
        )

    def get_eway_bills_of_other_party(self, *, invoice, date: str) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.get_eway_bills_of_other_party(date=date)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_OTHER_PARTY_FAILED",
            failed_message="Other party E-Way list fetch failed.",
        )

    def generate_consolidated_eway(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.generate_consolidated_eway(payload)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_CONSOLIDATED_FAILED",
            failed_message="Consolidated E-Way generation failed.",
        )

    def regenerate_trip_sheet(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.regenerate_trip_sheet(payload)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_TRIP_SHEET_REGENERATE_FAILED",
            failed_message="Trip sheet regeneration failed.",
        )

    def initiate_multi_vehicle(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.initiate_multi_vehicle(payload)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_MULTI_INIT_FAILED",
            failed_message="Multi vehicle initiation failed.",
        )

    def add_multi_vehicle(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.add_multi_vehicle(payload)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_MULTI_ADD_FAILED",
            failed_message="Add multi vehicle failed.",
        )

    def update_multi_vehicle(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        client = self._client_for_invoice(invoice, service_scope=MasterGSTServiceScope.EWAY)
        raw = client.update_multi_vehicle(payload)
        return self._normalize_lookup_result(
            raw,
            failed_code="EWB_MULTI_UPDATE_FAILED",
            failed_message="Update multi vehicle failed.",
        )
