from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import requests
from django.conf import settings


REDACTED = "***redacted***"
SENSITIVE_KEYS = {"api_secret", "client_secret", "otp", "evc_otp", "evcotp", "authorization", "auth_token", "sek", "token", "session_key"}


class WhiteboxConfigurationError(RuntimeError):
    pass


class WhiteboxRequestError(RuntimeError):
    def __init__(self, *, status_code: int | None, message: str, response_payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_payload = response_payload


@dataclass(frozen=True)
class WhiteboxContext:
    email: str
    gstin: str = ""
    gst_username: str = ""
    state_cd: str = ""
    ip_address: str = ""
    txn: str = ""


@dataclass(frozen=True)
class WhiteboxResponse:
    status_code: int
    payload: Any
    txn: str


class WhiteboxGstClient:
    """
    Thin server-side client for Whitebox GST APIs.

    Client id/secret stay in Django settings/env and never travel to the browser.
    """

    def __init__(self, *, base_url: str | None = None, client_id: str | None = None, client_secret: str | None = None, timeout: int | None = None, session=None):
        self.base_url = (base_url if base_url is not None else _setting("WHITEBOOKS_BASE_URL", "WHITEBOX_GST_BASE_URL")).strip().rstrip("/")
        self.client_id = (client_id if client_id is not None else _setting("WHITEBOOKS_API_KEY", "WHITEBOX_GST_CLIENT_ID")).strip()
        self.client_secret = (client_secret if client_secret is not None else _setting("WHITEBOOKS_API_SECRET", "WHITEBOX_GST_CLIENT_SECRET")).strip()
        self.contact_email = _setting("WHITEBOOKS_CONTACT_EMAIL", "WHITEBOX_GST_CONTACT_EMAIL")
        self.gst_username = _setting("WHITEBOOKS_GST_USERNAME", "WHITEBOX_GST_USERNAME")
        self.state_cd = _setting("WHITEBOOKS_STATE_CODE", "WHITEBOX_GST_STATE_CODE")
        self.ip_address = _setting("WHITEBOOKS_IP_ADDRESS", "WHITEBOX_GST_IP_ADDRESS", "MASTERGST_IP_ADDRESS")
        self.timeout = timeout if timeout is not None else int(_setting("WHITEBOOKS_TIMEOUT_SECONDS", "WHITEBOX_GST_TIMEOUT_SECONDS") or 30)
        self.session = session or requests.Session()

    def ensure_configured(self):
        missing = []
        if not self.base_url:
            missing.append("WHITEBOOKS_BASE_URL")
        if not self.client_id:
            missing.append("WHITEBOOKS_API_KEY")
        if not self.client_secret:
            missing.append("WHITEBOOKS_API_SECRET")
        if missing:
            raise WhiteboxConfigurationError(f"Whitebox GST is not configured. Missing: {', '.join(missing)}")

    def request_otp(self, *, context: WhiteboxContext) -> WhiteboxResponse:
        return self._request("GET", "/authentication/otprequest", context=context, params={"email": context.email}, include_txn=False, include_gstin_headers=False)

    def auth_token(self, *, context: WhiteboxContext, otp: str) -> WhiteboxResponse:
        return self._request("GET", "/authentication/authtoken", context=context, params={"email": context.email, "otp": otp}, include_gstin_headers=False)

    def refresh_token(self, *, context: WhiteboxContext) -> WhiteboxResponse:
        return self._request("GET", "/authentication/refreshtoken", context=context, params={"email": context.email}, include_gstin_headers=False)

    def logout(self, *, context: WhiteboxContext) -> WhiteboxResponse:
        return self._request("GET", "/authentication/logout", context=context, params={"email": context.email}, include_gstin_headers=False)

    def request_evc_otp(self, *, context: WhiteboxContext, pan: str, form_type: str) -> WhiteboxResponse:
        return self._request(
            "GET",
            "/authentication/otpforevc",
            context=context,
            params={"email": context.email, "gstin": context.gstin, "pan": pan, "form_type": form_type},
            include_gstin_headers=False,
        )

    def save_gstr1(self, *, context: WhiteboxContext, ret_period: str, payload: dict) -> WhiteboxResponse:
        return self._request("PUT", "/gstr1/retsave", context=context, ret_period=ret_period, params={"email": context.email}, json=payload)

    def gstr1_summary(self, *, context: WhiteboxContext, ret_period: str, summary_type: str = "") -> WhiteboxResponse:
        return self._request(
            "GET",
            "/gstr1/retsum",
            context=context,
            ret_period=ret_period,
            params={"gstin": context.gstin, "retperiod": ret_period, "email": context.email, "smrytyp": summary_type},
        )

    def proceed_to_file(self, *, context: WhiteboxContext, ret_period: str, return_type: str, is_nil: bool = False) -> WhiteboxResponse:
        params = {
            "gstin": context.gstin,
            "retperiod": ret_period,
            "type": return_type.upper().replace("-", ""),
            "isNil": "Y" if is_nil else "N",
            "email": context.email,
        }
        try:
            return self._request("GET", "/all/newproceedfile", context=context, ret_period=ret_period, params=params, include_gstin_headers=False)
        except WhiteboxRequestError as exc:
            if not _should_try_legacy_endpoint(exc):
                raise
        legacy_params = {key: value for key, value in params.items() if key != "isNil"}
        return self._request("GET", "/all/proceedfile", context=context, ret_period=ret_period, params=legacy_params, include_gstin_headers=False)

    def file_gstr1(self, *, context: WhiteboxContext, ret_period: str, pan: str, payload: dict) -> WhiteboxResponse:
        return self._request("POST", "/gstr1/retfile", context=context, ret_period=ret_period, params={"email": context.email, "pan": pan}, json=payload)

    def evc_file_gstr1(self, *, context: WhiteboxContext, ret_period: str, pan: str, evc_otp: str) -> WhiteboxResponse:
        return self._request("POST", "/gstr1/retevcfile", context=context, ret_period=ret_period, params={"email": context.email, "pan": pan, "evcotp": evc_otp})

    def save_gstr3b(self, *, context: WhiteboxContext, ret_period: str, payload: dict) -> WhiteboxResponse:
        return self._request("PUT", "/gstr3b/retsave", context=context, ret_period=ret_period, params={"email": context.email}, json=payload)

    def gstr3b_summary(self, *, context: WhiteboxContext, ret_period: str) -> WhiteboxResponse:
        return self._request("GET", "/gstr3b/retsum", context=context, ret_period=ret_period, params={"gstin": context.gstin, "retperiod": ret_period, "email": context.email})

    def offset_gstr3b(self, *, context: WhiteboxContext, ret_period: str, payload: dict) -> WhiteboxResponse:
        return self._request("PUT", "/gstr3b/retoffset", context=context, ret_period=ret_period, params={"email": context.email}, json=payload)

    def file_gstr3b(self, *, context: WhiteboxContext, ret_period: str, pan: str, payload: dict) -> WhiteboxResponse:
        return self._request("POST", "/gstr3b/retfile", context=context, ret_period=ret_period, params={"email": context.email, "pan": pan}, json=payload)

    def evc_file_gstr3b(self, *, context: WhiteboxContext, ret_period: str, pan: str, evc_otp: str) -> WhiteboxResponse:
        return self._request("POST", "/gstr3b/retevcfile", context=context, ret_period=ret_period, params={"email": context.email, "pan": pan, "evcotp": evc_otp})

    def return_status(self, *, context: WhiteboxContext, ret_period: str, ref_id: str, return_type: str) -> WhiteboxResponse:
        try:
            return self._request(
                "GET",
                "/all/newretstatus",
                context=context,
                ret_period=ret_period,
                params={"gstin": context.gstin, "returnperiod": ret_period, "refid": ref_id, "rettype": return_type, "email": context.email},
            )
        except WhiteboxRequestError as exc:
            if not _should_try_legacy_endpoint(exc):
                raise
        return self._request(
            "GET",
            "/gstr/retstatus",
            context=context,
            ret_period=ret_period,
            params={"gstin": context.gstin, "returnperiod": ret_period, "refid": ref_id, "email": context.email},
        )

    def fetch_gstr2b(self, *, context: WhiteboxContext, ret_period: str, file_number: str = "") -> WhiteboxResponse:
        return self._request("GET", "/gstr2b/all", context=context, ret_period=ret_period, params={"gstin": context.gstin, "rtnprd": ret_period, "filenum": file_number, "email": context.email})

    def generate_gstr2b(self, *, context: WhiteboxContext, ret_period: str) -> WhiteboxResponse:
        return self._request("PUT", "/gstr2b/gen2b", context=context, ret_period=ret_period, params={"email": context.email})

    def _request(
        self,
        method: str,
        path: str,
        *,
        context: WhiteboxContext,
        params: dict | None = None,
        json: dict | None = None,
        ret_period: str = "",
        include_txn: bool = True,
        include_gstin_headers: bool = True,
    ) -> WhiteboxResponse:
        self.ensure_configured()
        txn = context.txn or uuid4().hex
        headers = self._headers(context=context, txn=txn, ret_period=ret_period, include_txn=include_txn, include_gstin_headers=include_gstin_headers)
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                params=params or {},
                json=json,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise WhiteboxRequestError(
                status_code=None,
                message=f"Whitebox GST request could not be completed for {path}.",
                response_payload={"error": str(exc)},
            ) from exc
        payload = self._response_payload(response)
        response_txn = str(response.headers.get("txn") or txn).strip()
        if response.status_code >= 400:
            raise WhiteboxRequestError(status_code=response.status_code, message=_provider_error_message(payload, default=f"Whitebox GST request failed for {path}."), response_payload=payload)
        _raise_for_provider_error(payload, path=path)
        return WhiteboxResponse(status_code=response.status_code, payload=payload, txn=response_txn)

    def _headers(self, *, context: WhiteboxContext, txn: str, ret_period: str, include_txn: bool, include_gstin_headers: bool) -> dict:
        headers = {
            "accept": "*/*",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "Content-Type": "application/json",
        }
        ip_address = context.ip_address or self.ip_address
        gst_username = context.gst_username or self.gst_username
        state_cd = context.state_cd or self.state_cd
        if ip_address:
            headers["ip_address"] = ip_address
        if gst_username:
            headers["gst_username"] = gst_username
        if state_cd:
            headers["state_cd"] = state_cd
        if include_txn:
            headers["txn"] = txn
        if include_gstin_headers:
            headers.update(
                {
                    "gstin": context.gstin,
                    "ret_period": ret_period,
                }
            )
        return headers

    def _response_payload(self, response):
        try:
            payload = response.json()
        except ValueError:
            preview = str(response.text or "").strip()[:240].replace("\n", " ")
            return {
                "status_cd": "0",
                "message": "Whitebox GST returned a non-JSON response.",
                "response_preview": preview,
            }
        if isinstance(payload, dict):
            txn = response.headers.get("txn")
            if txn:
                header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
                header.setdefault("txn", txn)
                payload["header"] = header
        return payload


def redacted_whitebox_snapshot(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = REDACTED
            else:
                redacted[key] = redacted_whitebox_snapshot(item)
        return redacted
    if isinstance(value, list):
        return [redacted_whitebox_snapshot(item) for item in value]
    return value


def _setting(*names: str) -> str:
    for name in names:
        value = str(getattr(settings, name, "") or "").strip()
        if value:
            return value
    return ""


def _raise_for_provider_error(payload: Any, *, path: str):
    if not isinstance(payload, dict):
        return
    status_cd = str(payload.get("status_cd") or "").strip()
    if not status_cd or status_cd == "1":
        return
    raise WhiteboxRequestError(
        status_code=None,
        message=_provider_error_message(payload, default=f"Whitebox GST rejected the request for {path}."),
        response_payload=payload,
    )


def _provider_error_message(payload: Any, *, default: str) -> str:
    if not isinstance(payload, dict):
        return default
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    error_code = str(error.get("error_cd") or error.get("errorCode") or "").strip()
    error_message = str(
        error.get("message")
        or error.get("errorMessage")
        or payload.get("status_desc")
        or payload.get("message")
        or default
    ).strip()
    return f"{error_code}: {error_message}" if error_code else error_message


def _should_try_legacy_endpoint(exc: WhiteboxRequestError) -> bool:
    return exc.status_code in {404, 405, 501}
