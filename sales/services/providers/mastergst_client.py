from __future__ import annotations

from typing import Any, Dict
import uuid
import requests
from urllib.parse import quote
import json
from pprint import pprint

from django.conf import settings
from django.utils import timezone

from sales.models.mastergst_models import SalesMasterGSTCredential, SalesMasterGSTToken


class MasterGSTClient:
    def __init__(self, cred: SalesMasterGSTCredential):
        self.cred = cred
        self.base_url = getattr(settings, "MASTERGST_BASE_URL", "https://api.mastergst.com").rstrip("/")

    def _resolve_ip(self) -> str:
        ip = getattr(settings, "MASTERGST_IP_ADDRESS", None) or self.cred.ip_address
        if ip:
            return str(ip).strip()
        if self.cred.allow_all_ips:
            return "0.0.0.0"
        raise RuntimeError("MasterGST ip_address missing (set MASTERGST_IP_ADDRESS or store in credential).")

    def _token_row(self) -> SalesMasterGSTToken:
        tok, _ = SalesMasterGSTToken.objects.get_or_create(credential=self.cred)
        return tok

    def get_token(self, force: bool = False) -> str:
        tok = self._token_row()
        if not force and tok.is_valid():
            return tok.auth_token  # type: ignore

        ip = self._resolve_ip()
        email_q = quote(self.cred.email)
        url = f"{self.base_url}/einvoice/authenticate?email={email_q}"

        headers = {
            "accept": "*/*",
            "username": self.cred.gst_username,
            "password": self.cred.gst_password,
            "ip_address": ip,
            "client_id": self.cred.client_id,
            "client_secret": self.cred.client_secret,
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

        # Prefer standard MasterGST shape: data.AuthToken
        data_block = data.get("data") or {}
        token = (
            data_block.get("AuthToken")
            or data_block.get("auth_token")
            or data.get("auth_token")
            or data.get("AuthToken")
            or data.get("token")
            or data.get("Token")
        )

        # Persist optional fields if present (safe; doesn’t break if model lacks)
        sek = data_block.get("Sek") or data.get("Sek")
        issued_client_id = data_block.get("ClientId") or data.get("ClientId")
        if hasattr(tok, "sek"):
            tok.sek = sek
        if hasattr(tok, "gsp_client_id"):
            tok.gsp_client_id = issued_client_id

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

    def generate_irn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST Generate IRN (V1_03)
        - Uses dashboard client_id/client_secret (UUID pair) ✅
        - Uses auth-token header ✅
        - Retries once on ErrorCode 1005 (Invalid Token) ✅
        """

        def _post(tok_value: str) -> requests.Response:
            email_q = quote(self.cred.email)
            url = f"{self.base_url}/einvoice/type/GENERATE/version/V1_03?email={email_q}"

            # ✅ IMPORTANT: For GENERATE, use the dashboard UUID client_id/client_secret
            client_id_to_use = self.cred.client_id
            client_secret_to_use = self.cred.client_secret

            headers = {
                "accept": "*/*",
                "Content-Type": "application/json",
                "auth-token": tok_value,
                "client_id": client_id_to_use,
                "client_secret": client_secret_to_use,
                "gstin": self.cred.gstin,
                "ip_address": self._resolve_ip(),
                "username": self.cred.gst_username,
                "txn": uuid.uuid4().hex,
            }

            # DEBUG: print payload before sending
            print("\n\n================ MASTERGST PAYLOAD ================")
            print(json.dumps(payload, indent=2, default=str))
            print("===================================================\n\n")


            resp = requests.post(url, json=payload, headers=headers, timeout=60)

            debug = {
                "_url": url,
                "_http_status": resp.status_code,
                "_content_length": int(resp.headers.get("Content-Length") or 0),
                "_content_type": resp.headers.get("Content-Type"),
                "_resp_headers": dict(resp.headers),
                "_client_id_used": client_id_to_use,
            }

            resp._mastergst_debug = {  # type: ignore[attr-defined]
                "_url": url,
                "_client_id_used": client_id_to_use,
                "_headers_sent": {
                    k: ("***" if k in {"client_secret", "auth-token"} else v) for k, v in headers.items()
                },
            }
            return resp

        # 1) attempt with cached token
        token = self.get_token(force=False)
        resp = _post(token)
        data = self._safe_json(resp)

        # 2) retry once if invalid token
        try:
            if str(data.get("status_cd")) == "0" and "1005" in str(data.get("status_desc", "")):
                token = self.get_token(force=True)
                resp = _post(token)
                data = self._safe_json(resp)
        except Exception:
            pass

        debug = {
            "_url": getattr(resp, "_mastergst_debug", {}).get("_url"),  # type: ignore[attr-defined]
            "_http_status": "200" if resp is None else str(resp.status_code),
            "_payload_sent": payload,        # ✅ ADD THIS LINE
            "_content_length": str(len(resp.content or b"")),
            "_content_type": resp.headers.get("Content-Type"),
            "_resp_headers": dict(resp.headers),
            "_client_id_used": getattr(resp, "_mastergst_debug", {}).get("_client_id_used"),  # type: ignore[attr-defined]
        }

        if isinstance(data, dict):
            data.update(debug)
            return data

        return {**debug, "_not_dict": True, "_raw": data}

    @staticmethod
    def _safe_json(resp: requests.Response) -> Dict[str, Any]:
        """
        Always return something useful.
        If JSON parse fails, include raw text + status.
        """
        try:
            if resp.content:
                return resp.json()
            return {"_empty": True, "_status": resp.status_code}
        except Exception:
            return {
                "_not_json": True,
                "_status": resp.status_code,
                "_text": resp.text,
            }