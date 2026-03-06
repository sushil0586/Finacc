from __future__ import annotations

from typing import Any, Dict
import uuid
import requests
from urllib.parse import quote
from datetime import timedelta
import json
import ipaddress

from django.conf import settings
from django.utils import timezone

from sales.models.mastergst_models import SalesMasterGSTCredential, SalesMasterGSTToken

from sales.services.mastergst_eway_token_service import MasterGSTEWayTokenService


class MasterGSTClient:
    def __init__(self, cred: SalesMasterGSTCredential):
        self.cred = cred
        self.base_url = getattr(settings, "MASTERGST_BASE_URL", "https://api.mastergst.com").rstrip("/")
        self._eway_auth_valid_till = None
        self._eway_auth_token = None
        self._eway_cookies = None

    # ----------------------------
    # Common helpers
    # ----------------------------
    def _debug_enabled(self) -> bool:
        return bool(getattr(settings, "MASTERGST_DEBUG", False))

    def _resolve_ip(self) -> str:
        ip = "127.0.0.1"
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
        email_q = quote(self.cred.email)
        url = f"{self.base_url}/einvoice/authenticate?email={email_q}"

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
            data_block.get("AuthToken")
            or data_block.get("auth_token")
            or data.get("auth_token")
            or data.get("AuthToken")
            or data.get("token")
            or data.get("Token")
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
            email_q = quote(self.cred.email)
            url = f"{self.base_url}/einvoice/type/GENERATE/version/V1_03?email={email_q}"

            headers = {
                "Accept": "*/*",
                "Content-Type": "application/json",
                "auth-token": tok_value,
                "client_id": self.cred.client_id,
                "client_secret": self.cred.get_client_secret(),
                "gstin": self.cred.gstin,
                "ip_address": self._resolve_ip(),
                "username": self.cred.gst_username,
                "txn": uuid.uuid4().hex,
            }

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
            if str(data.get("status_cd")) == "0" and "1005" in str(data.get("status_desc", "")):
                token = self.get_token(force=True)
                resp = _post(token)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = {
            "_url": getattr(resp, "_mastergst_debug", {}).get("_url"),  # type: ignore[attr-defined]
            "_payload_sent": payload,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def cancel_irn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self.get_token(force=False)
        email_q = quote(self.cred.email)
        url = f"{self.base_url}/einvoice/type/CANCEL/version/V1_03?email={email_q}"
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "auth-token": token,
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "ip_address": self._resolve_ip(),
            "username": self.cred.gst_username,
            "txn": uuid.uuid4().hex,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        data = self._safe_json(resp)
        debug = {
            "_url": url,
            "_payload_sent": payload,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def get_irn_details(self, *, irn: str, supplier_gstin: str | None = None) -> Dict[str, Any]:
        token = self.get_token(force=False)
        email_q = quote(self.cred.email)
        supplier = (supplier_gstin or self.cred.gstin or "").strip().upper()
        supplier_q = quote(supplier)
        irn_q = quote(str(irn).strip())
        url = (
            f"{self.base_url}/einvoice/type/GETIRN/version/V1_03"
            f"?param1={irn_q}&email={email_q}&supplier_gstn={supplier_q}"
        )
        headers = {
            "Accept": "*/*",
            "auth-token": token,
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "ip_address": self._resolve_ip(),
            "username": self.cred.gst_username,
        }
        resp = requests.get(url, headers=headers, timeout=60)
        data = self._safe_json(resp)

        # Retry once on invalid token (1005)
        try:
            if str(data.get("status_cd")) == "0" and "1005" in str(data.get("status_desc", "")):
                token = self.get_token(force=True)
                headers["auth-token"] = token
                resp = requests.get(url, headers=headers, timeout=60)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = {
            "_url": url,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
            "_supplier_gstin": supplier,
            "_irn": str(irn),
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def get_eway_details_by_irn(self, *, irn: str, supplier_gstin: str | None = None) -> Dict[str, Any]:
        token = self.get_token(force=False)
        email_q = quote(self.cred.email)
        supplier = (supplier_gstin or self.cred.gstin or "").strip().upper()
        supplier_q = quote(supplier)
        irn_q = quote(str(irn).strip())
        url = (
            f"{self.base_url}/einvoice/type/GETEWAYBILLIRN/version/V1_03"
            f"?param1={irn_q}&supplier_gstn={supplier_q}&email={email_q}"
        )
        headers = {
            "Accept": "*/*",
            "auth-token": token,
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "ip_address": self._resolve_ip(),
            "username": self.cred.gst_username,
        }
        resp = requests.get(url, headers=headers, timeout=60)
        data = self._safe_json(resp)

        # Retry once on invalid token (1005)
        try:
            if str(data.get("status_cd")) == "0" and "1005" in str(data.get("status_desc", "")):
                token = self.get_token(force=True)
                headers["auth-token"] = token
                resp = requests.get(url, headers=headers, timeout=60)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = {
            "_url": url,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
            "_supplier_gstin": supplier,
            "_irn": str(irn),
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    # ----------------------------
    # B2B EWB (IRN based)
    # ----------------------------
    def generate_ewaybill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self.get_token(force=False)

        email_q = quote(self.cred.email)
        url = f"{self.base_url}/einvoice/type/GENERATE_EWAYBILL/version/V1_03?email={email_q}"

        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "auth-token": token,
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "ip_address": self._resolve_ip(),
            "username": self.cred.gst_username,
            "txn": uuid.uuid4().hex,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        data = self._safe_json(resp)

        # Retry once on invalid token (1005)
        try:
            if str(data.get("status_cd")) == "0" and "1005" in str(data.get("status_desc", "")):
                token = self.get_token(force=True)
                headers["auth-token"] = token
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = {
            "_url": url,
            "_payload_sent": payload,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
        }
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

        email_q = quote(self.cred.email or "")
        user_q = quote(self.cred.gstin or "")  # as per your curl
        pass_q = quote(getattr(self.cred, "eway_password", None) or self.cred.get_gst_password() or "")

        url = f"{self.base_url}/ewaybillapi/v1.03/authenticate?email={email_q}&username={user_q}&password={pass_q}"

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
        token = (
            resp.headers.get("authtoken")
            or resp.headers.get("AuthToken")
            or resp.headers.get("Auth-Token")
            or resp.headers.get("auth-token")
            or resp.headers.get("authorization")
            or resp.headers.get("Authorization")
        )

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
    

    def _headers(self, token: str) -> Dict[str, str]:
        # ✅ token MUST be in headers (not in payload)
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "ip_address": self._resolve_ip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "authtoken": token,  # <- if your integration uses a different header key, change it here
        }

    def generate_eway_direct(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        email_q = quote(self.cred.email or "")
        url = f"{self.base_url}/ewaybillapi/v1.03/ewayapi/genewaybill?email={email_q}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",

            "ip_address": str(self._resolve_ip()).strip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,

            # ✅ Add these (EWB portal creds)
            "username": (getattr(self.cred, "eway_username", None) or self.cred.gstin),
            "password": (getattr(self.cred, "eway_password", None) or self.cred.get_gst_password()),

            # ✅ Add txn like your IRN flow (many MasterGST routes expect it)
            "txn": uuid.uuid4().hex,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        data = self._safe_json(resp)

        debug = {
            "_url": url,
            "_payload_sent": payload,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def _eway_direct_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "ip_address": str(self._resolve_ip()).strip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.get_client_secret(),
            "gstin": self.cred.gstin,
            "username": (getattr(self.cred, "eway_username", None) or self.cred.gstin),
            "password": (getattr(self.cred, "eway_password", None) or self.cred.get_gst_password()),
            "txn": uuid.uuid4().hex,
        }

    def _eway_direct_post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        email_q = quote(self.cred.email or "")
        url = f"{self.base_url}{endpoint}?email={email_q}"
        resp = requests.post(url, json=payload, headers=self._eway_direct_headers(), timeout=60)
        data = self._safe_json(resp)
        debug = {
            "_url": url,
            "_payload_sent": payload,
            "_http_status": str(resp.status_code),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
        }
        if isinstance(data, dict):
            data.update(debug)
            return data
        return {**debug, "_not_dict": True, "_raw": data}

    def cancel_eway_direct(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("/ewaybillapi/v1.03/ewayapi/canewb", payload)

    def update_eway_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # MasterGST commonly exposes vehicle update as `vehewb`.
        # Keep a fallback to older `updvehicle` route for compatibility.
        primary = self._eway_direct_post("/ewaybillapi/v1.03/ewayapi/vehewb", payload)
        if str(primary.get("status_cd") or "") == "1":
            return primary
        fallback = self._eway_direct_post("/ewaybillapi/v1.03/ewayapi/updvehicle", payload)
        if str(fallback.get("status_cd") or "") == "1":
            return fallback
        # Return primary failure by default (more canonical endpoint for this API)
        return primary

    def update_eway_transporter(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("/ewaybillapi/v1.03/ewayapi/updatetransporter", payload)

    def extend_eway_validity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._eway_direct_post("/ewaybillapi/v1.03/ewayapi/extendvalidity", payload)
