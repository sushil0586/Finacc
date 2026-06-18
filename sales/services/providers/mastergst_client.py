from __future__ import annotations

from typing import Any, Dict
import uuid
import requests
from urllib.parse import quote
from datetime import timedelta
import json
import ipaddress

from django.utils import timezone

from sales.models.mastergst_models import SalesMasterGSTCredential, SalesMasterGSTToken

from sales.services.providers.config import provider_base_url, provider_debug_enabled, provider_ip_address
from sales.services.providers.provider_specs import get_provider_spec


class MasterGSTClient:
    def __init__(self, cred: SalesMasterGSTCredential, *, provider_name: str = "mastergst"):
        self.cred = cred
        self.provider_name = (provider_name or "mastergst").strip().lower()
        self.base_url = provider_base_url(self.provider_name)
        self.spec = get_provider_spec(self.provider_name)
        self._eway_auth_valid_till = None
        self._eway_auth_token = None
        self._eway_cookies = None

    # ----------------------------
    # Common helpers
    # ----------------------------
    def _debug_enabled(self) -> bool:
        return provider_debug_enabled(self.provider_name)

    def _resolve_ip(self) -> str:
        ip = self.cred.resolve_ip_address() or provider_ip_address(self.provider_name)
        if ip:
            ip = str(ip).strip()
            try:
                ipaddress.ip_address(ip)  # ✅ validate
            except ValueError:
                raise RuntimeError(f"Invalid MasterGST ip_address: {ip}")
            return ip

        if self.cred.allow_all_ips:
            return "0.0.0.0"

        raise RuntimeError("MasterGST ip_address missing (set MASTERGST_IP_ADDRESS or store in credential).")

    def _build_url(self, endpoint_key: str, *, query: str = "") -> str:
        return f"{self.base_url}{self.spec.endpoint_path(endpoint_key)}{query}"

    @staticmethod
    def _quote_value(value: Any, *, upper: bool = False) -> str:
        text = str(value or "").strip()
        if upper:
            text = text.upper()
        return quote(text)

    def _email_query(self) -> str:
        return self._quote_value(self.cred.email or "")

    def _build_query_string(self, **params: Any) -> str:
        filtered = [(key, value) for key, value in params.items() if value not in (None, "")]
        if not filtered:
            return ""
        parts = [f"{key}={self._quote_value(value)}" for key, value in filtered]
        return f"?{'&'.join(parts)}"

    def _einvoice_headers(self, *, auth_token: str | None = None, json_content: bool = False, include_txn: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "*/*",
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "ip_address": self._resolve_ip(),
            "username": self.cred.gst_username,
        }
        if json_content:
            headers["Content-Type"] = "application/json"
        if auth_token:
            headers["auth-token"] = auth_token
        if include_txn:
            headers["txn"] = uuid.uuid4().hex
        return headers

    def _eway_direct_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "ip_address": str(self._resolve_ip()).strip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "username": self.cred.get_eway_username() or self.cred.gstin,
            "password": self.cred.get_eway_password(),
            "txn": uuid.uuid4().hex,
        }

    def _has_invalid_token_error(self, data: Dict[str, Any]) -> bool:
        if str(data.get("status_cd") or "") != "0":
            return False
        status_desc = str(data.get("status_desc") or "")
        return any(marker in status_desc for marker in self.spec.invalid_token_markers)

    @staticmethod
    def _debug_response(resp: requests.Response, *, url: str, payload: Dict[str, Any] | None = None, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        debug = {
            "_url": url,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
        }
        if payload is not None:
            debug["_payload_sent"] = payload
        if extra:
            debug.update(extra)
        return debug

    def _einvoice_get_with_retry(
        self,
        *,
        endpoint_key: str,
        query: str,
        extra_headers: Dict[str, str] | None = None,
        debug_extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        token = self.get_token(force=False)
        url = self._build_url(endpoint_key, query=query)
        headers = self._einvoice_headers(auth_token=token)
        if extra_headers:
            headers.update(extra_headers)
        resp = requests.get(url, headers=headers, timeout=60)
        data = self._safe_json(resp)

        try:
            if self._has_invalid_token_error(data):
                token = self.get_token(force=True)
                headers["auth-token"] = token
                resp = requests.get(url, headers=headers, timeout=60)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = self._debug_response(resp, url=url, extra=debug_extra)
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    @staticmethod
    def _safe_json(resp: requests.Response) -> Dict[str, Any]:
        try:
            if resp.content:
                data = resp.json()
            else:
                data = {"_empty": True}
        except Exception:
            return {
                "_not_json": True,
                "_http_status": resp.status_code,
                "_raw_text": resp.text,
            }

        if isinstance(data, dict):
            data["_http_status"] = resp.status_code
            data["_raw_text"] = resp.text
            return data

        return {
            "_json": data,
            "_http_status": resp.status_code,
            "_raw_text": resp.text,
        }

    # ----------------------------
    # EINVOICE token (stored)
    # ----------------------------
    def _token_row(self) -> SalesMasterGSTToken:
        tok, _ = SalesMasterGSTToken.objects.get_or_create(credential=self.cred)
        return tok

    def get_token(self, force: bool = False) -> str:
        tok = self._token_row()
        if not force and tok.is_valid():
            return tok.get_auth_token()  # type: ignore

        ip = self._resolve_ip()
        url = self._build_url("einvoice_auth", query=self._build_query_string(email=self.cred.email))

        headers = {
            "Accept": "*/*",
            "username": self.cred.gst_username,
            "password": self.cred.get_gst_password(),
            "ip_address": ip,
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
        }

        resp = requests.get(url, headers=headers, timeout=30)
        data = self._safe_json(resp)

        tok.last_auth_at = timezone.now()
        tok.last_response_json = {
            "url": url,
            "headers_sent": {k: ("***" if k in {"password", "client_secret"} else v) for k, v in headers.items()},
            "response": data,
            "http_status": resp.status_code,
        }
        tok.last_error_message = None

        if resp.status_code >= 400:
            tok.auth_token = None
            tok.token_expiry = None
            tok.last_error_message = f"AUTH_HTTP_{resp.status_code}"
            tok.save()
            raise RuntimeError(f"MasterGST auth failed: HTTP {resp.status_code} {data}")

        data_block = data.get("data") or {}
        token = (
            next((data_block.get(key) for key in self.spec.einvoice_auth_token_keys if data_block.get(key)), None)
            or next((data.get(key) for key in self.spec.einvoice_auth_token_keys if data.get(key)), None)
        )

        if not token:
            tok.auth_token = None
            tok.token_expiry = None
            tok.last_error_message = "AUTH_NO_TOKEN"
            tok.save()
            raise RuntimeError(f"MasterGST auth token missing: {data}")

        tok.auth_token = token
        tok.set_expiry_default()  # 5h45m
        tok.save()
        return token

    # ----------------------------
    # IRN
    # ----------------------------
    def generate_irn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def _post(tok_value: str) -> requests.Response:
            url = self._build_url("einvoice_generate", query=self._build_query_string(email=self.cred.email))
            headers = self._einvoice_headers(auth_token=tok_value, json_content=True, include_txn=True)

            if self._debug_enabled():
                print("\n\n================ MASTERGST IRN PAYLOAD ================")
                print(json.dumps(payload, indent=2, default=str))
                print("=======================================================\n\n")

            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp._mastergst_debug = {  # type: ignore[attr-defined]
                "_url": url,
                "_headers_sent": {k: ("***" if k in {"client_secret", "auth-token"} else v) for k, v in headers.items()},
            }
            return resp

        token = self.get_token(force=False)
        resp = _post(token)
        data = self._safe_json(resp)

        # Retry once on invalid token (1005)
        try:
            if self._has_invalid_token_error(data):
                token = self.get_token(force=True)
                resp = _post(token)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = self._debug_response(
            resp,
            url=getattr(resp, "_mastergst_debug", {}).get("_url"),  # type: ignore[attr-defined]
            payload=payload,
        )
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def cancel_irn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self.get_token(force=False)
        url = self._build_url("einvoice_cancel", query=self._build_query_string(email=self.cred.email))
        headers = self._einvoice_headers(auth_token=token, json_content=True, include_txn=True)
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        data = self._safe_json(resp)
        debug = self._debug_response(resp, url=url, payload=payload)
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def get_irn_details(self, *, irn: str, supplier_gstin: str | None = None) -> Dict[str, Any]:
        email_q = quote(self.cred.email)
        supplier = (supplier_gstin or self.cred.gstin or "").strip().upper()
        return self._einvoice_get_with_retry(
            endpoint_key="einvoice_get_irn",
            query=self._build_query_string(param1=irn, email=self.cred.email, supplier_gstn=supplier),
            debug_extra={"_supplier_gstin": supplier, "_irn": str(irn)},
        )

    def get_irn_details_by_doc(self, *, doc_type: str, doc_number: str, doc_date: str) -> Dict[str, Any]:
        doc_type_value = (doc_type or "").strip().upper()
        doc_number_value = str(doc_number or "").strip()
        doc_date_value = str(doc_date or "").strip()
        return self._einvoice_get_with_retry(
            endpoint_key="einvoice_get_irn_by_doc_details",
            query=self._build_query_string(param1=doc_type_value, email=self.cred.email),
            extra_headers={"docnum": doc_number_value, "docdate": doc_date_value},
            debug_extra={
                "_doc_type": doc_type_value,
                "_doc_number": doc_number_value,
                "_doc_date": doc_date_value,
            },
        )

    def get_gstn_details(self, *, gstin: str) -> Dict[str, Any]:
        gstin_value = (gstin or "").strip().upper()
        return self._einvoice_get_with_retry(
            endpoint_key="einvoice_get_gstn_details",
            query=self._build_query_string(param1=gstin_value, email=self.cred.email),
            debug_extra={"_lookup_gstin": gstin_value},
        )

    def sync_gstin_from_cp(self, *, gstin: str) -> Dict[str, Any]:
        gstin_value = (gstin or "").strip().upper()
        return self._einvoice_get_with_retry(
            endpoint_key="einvoice_sync_gstin_from_cp",
            query=self._build_query_string(param1=gstin_value, email=self.cred.email),
            debug_extra={"_lookup_gstin": gstin_value},
        )

    def get_b2c_qrcode(self, *, payload: Dict[str, Any]) -> Dict[str, Any]:
        email_q = quote(self.cred.email or "")
        url = self._build_url("einvoice_b2c_qrcode", query=f"?email={email_q}")

        headers = {
            "Accept": "*/*",
            "ip_address": self._resolve_ip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "username": self.cred.gst_username,
        }
        headers.update({k: str(v) for k, v in payload.items() if v not in (None, "")})

        resp = requests.get(url, headers=headers, timeout=60)
        data = self._safe_json(resp)

        debug = {
            "_url": url,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
            "_request_headers": {k: ("***" if k in {"client_secret"} else v) for k, v in headers.items()},
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def get_eway_details_by_irn(self, *, irn: str, supplier_gstin: str | None = None) -> Dict[str, Any]:
        supplier = (supplier_gstin or self.cred.gstin or "").strip().upper()
        return self._einvoice_get_with_retry(
            endpoint_key="einvoice_get_eway_by_irn",
            query=self._build_query_string(param1=irn, supplier_gstn=supplier, email=self.cred.email),
            debug_extra={"_supplier_gstin": supplier, "_irn": str(irn)},
        )

    # ----------------------------
    # B2B EWB (IRN based)
    # ----------------------------
    def generate_ewaybill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self.get_token(force=False)

        url = self._build_url("einvoice_generate_ewaybill", query=self._build_query_string(email=self.cred.email))
        headers = self._einvoice_headers(auth_token=token, json_content=True, include_txn=True)

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        data = self._safe_json(resp)

        # Retry once on invalid token (1005)
        try:
            if self._has_invalid_token_error(data):
                token = self.get_token(force=True)
                headers["auth-token"] = token
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = self._debug_response(resp, url=url, payload=payload)
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    # ----------------------------
    # B2C Direct EWB (no token returned)
    # ----------------------------
    def _eway_auth_session(self, force: bool = False) -> Dict[str, Any]:
        # in-memory reuse
        if not force and getattr(self, "_eway_auth_token", None) and getattr(self, "_eway_auth_valid_till", None):
            if timezone.now() < self._eway_auth_valid_till:
                return {"token": self._eway_auth_token, "cookies": self._eway_cookies, "cached": True}

        # DB reuse (optional but recommended)
        tok = self._token_row()
        ewb_token = tok.get_eway_auth_token()
        ewb_expiry = getattr(tok, "eway_token_expiry", None)
        if not force and ewb_token and ewb_expiry and timezone.now() < ewb_expiry:
            self._eway_auth_token = ewb_token
            self._eway_auth_valid_till = ewb_expiry
            self._eway_cookies = None
            return {"token": ewb_token, "cookies": None, "cached": True}

        url = self._build_url(
            "eway_auth",
            query=self._build_query_string(
                email=self.cred.email or "",
                username=self.cred.get_eway_username() or self.cred.gstin or "",
                password=self.cred.get_eway_password() or "",
            ),
        )

        headers = {
            "Accept": "application/json",
            "ip_address": self._resolve_ip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
        }

        resp = requests.get(url, headers=headers, timeout=30)
        data = self._safe_json(resp)

        status_cd = str(data.get("status_cd") or "")
        if resp.status_code >= 400 or status_cd != "1":
            raise RuntimeError(f"MasterGST E-Way auth failed: HTTP={resp.status_code} data={data}")

        # ✅ Token is NOT in JSON body in your case. Read from headers.
        # Common header keys used by MasterGST/NIC proxy:
        token = next((resp.headers.get(key) for key in self.spec.eway_auth_token_header_keys if resp.headers.get(key)), None)

        if not token:
            # helpful debug if token missing
            raise RuntimeError(
                "E-Way auth succeeded but token not found in response headers. "
                f"Headers keys={list(resp.headers.keys())} data={data}"
            )

        valid_till = timezone.now() + timedelta(hours=6, minutes=-5)

        # persist (add these fields to SalesMasterGSTToken)
        tok.eway_auth_token = token
        tok.eway_token_expiry = valid_till
        tok.save(update_fields=["eway_auth_token", "eway_token_expiry", "updated_at"])

        self._eway_auth_token = token
        self._eway_auth_valid_till = valid_till
        self._eway_cookies = resp.cookies

        return {
            "token": token,
            "cookies": resp.cookies,
            "raw": data,
            "resp_headers": dict(resp.headers),
            "cached": False,
        }
    def generate_eway_direct(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self._build_url("eway_generate_direct", query=self._build_query_string(email=self.cred.email or ""))
        headers = self._eway_direct_headers()

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        data = self._safe_json(resp)

        debug = self._debug_response(resp, url=url, payload=payload)
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def _eway_direct_post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self._build_url(endpoint, query=self._build_query_string(email=self.cred.email or ""))
        resp = requests.post(url, json=payload, headers=self._eway_direct_headers(), timeout=60)
        data = self._safe_json(resp)
        debug = self._debug_response(resp, url=url, payload=payload)
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def _eway_direct_get(self, endpoint: str, *, query: str = "", **params: Any) -> Dict[str, Any]:
        resolved_query = query or self._build_query_string(**params)
        url = self._build_url(endpoint, query=resolved_query)
        resp = requests.get(url, headers=self._eway_direct_headers(), timeout=60)
        data = self._safe_json(resp)
        debug = self._debug_response(resp, url=url)
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def get_eway_details(self, *, ewb_no: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_details", email=self.cred.email or "", ewbNo=str(ewb_no or "").strip())

    def get_transporter_details(self, *, transporter_id: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_transporter_details", email=self.cred.email or "", trn_no=str(transporter_id or "").strip())

    def get_gstin_details(self, *, gstin: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_gstin_details", email=self.cred.email or "", GSTIN=str(gstin or "").strip().upper())

    def get_hsn_details(self, *, hsn_code: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_hsn_details", email=self.cred.email or "", hsncode=str(hsn_code or "").strip())

    def get_error_list(self) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_error_list", email=self.cred.email or "")

    def reject_eway(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_reject", payload)

    def get_trip_sheet(self, *, trip_sheet_no: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_trip_sheet", email=self.cred.email or "", tripSheetNo=str(trip_sheet_no or "").strip())

    def get_eway_by_document(self, *, doc_type: str, doc_no: str) -> Dict[str, Any]:
        return self._eway_direct_get(
            "eway_get_by_document",
            email=self.cred.email or "",
            docType=str(doc_type or "").strip(),
            docNo=str(doc_no or "").strip(),
        )

    def get_eway_bills_for_transporter(self, *, date: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_bills_for_transporter", email=self.cred.email or "", date=str(date or "").strip())

    def get_eway_bill_report_by_transporter_assigned_date(self, *, date: str, state_code: str) -> Dict[str, Any]:
        return self._eway_direct_get(
            "eway_get_bill_report_by_transporter_assigned_date",
            email=self.cred.email or "",
            date=str(date or "").strip(),
            stateCode=str(state_code or "").strip(),
        )

    def get_eway_bills_by_date(self, *, date: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_bills_by_date", email=self.cred.email or "", date=str(date or "").strip())

    def get_eway_bills_rejected_by_others(self, *, date: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_bills_rejected_by_others", email=self.cred.email or "", date=str(date or "").strip())

    def get_eway_bills_for_transporter_by_gstin(self, *, gen_gstin: str, date: str) -> Dict[str, Any]:
        return self._eway_direct_get(
            "eway_get_bills_for_transporter_by_gstin",
            email=self.cred.email or "",
            Gen_gstin=str(gen_gstin or "").strip().upper(),
            date=str(date or "").strip(),
        )

    def get_eway_bills_for_transporter_by_state(self, *, state_code: str, date: str) -> Dict[str, Any]:
        return self._eway_direct_get(
            "eway_get_bills_for_transporter_by_state",
            email=self.cred.email or "",
            stateCode=str(state_code or "").strip(),
            date=str(date or "").strip(),
        )

    def get_eway_bills_of_other_party(self, *, date: str) -> Dict[str, Any]:
        return self._eway_direct_get("eway_get_bills_of_other_party", email=self.cred.email or "", date=str(date or "").strip())

    def generate_consolidated_eway(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_generate_consolidated", payload)

    def regenerate_trip_sheet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_regenerate_trip_sheet", payload)

    def initiate_multi_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_initiate_multi_vehicle", payload)

    def add_multi_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_add_multi_vehicle", payload)

    def update_multi_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_update_multi_vehicle", payload)

    def cancel_eway_direct(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_cancel", payload)

    def update_eway_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # MasterGST commonly exposes vehicle update as `vehewb`.
        # Keep a fallback to older `updvehicle` route for compatibility.
        primary = self._eway_direct_post("eway_update_vehicle", payload)
        if str(primary.get("status_cd") or "") == "1":
            return primary
        fallback = self._eway_direct_post("eway_update_vehicle_fallback", payload)
        if str(fallback.get("status_cd") or "") == "1":
            return fallback
        # Return primary failure by default (more canonical endpoint for this API)
        return primary

    def update_eway_transporter(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_update_transporter", payload)

    def extend_eway_validity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("eway_extend_validity", payload)
