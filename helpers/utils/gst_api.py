import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad as pkcs7_pad

from entity.models import MasterGstDetail

logger = logging.getLogger(__name__)


# -----------------------------
# Configuration
# -----------------------------

DEFAULT_TIMEOUT = (10, 45)  # (connect, read)
DEFAULT_IP_EINVOICE = "49.43.101.20"
DEFAULT_IP_EWAY = "10.178.787.78"

BASE_URL = "https://api.mastergst.com"

URLS = {
    "einvoice_auth": f"{BASE_URL}/einvoice/authenticate",
    "einvoice_generate": f"{BASE_URL}/einvoice/type/GENERATE/version/V1_03",
    "einvoice_cancel": f"{BASE_URL}/einvoice/type/CANCEL/version/V1_03",
    "einvoice_gstndetails": f"{BASE_URL}/einvoice/type/GSTNDETAILS/version/V1_03",
    "einvoice_generate_ewaybill": f"{BASE_URL}/einvoice/type/GENERATE_EWAYBILL/version/V1_03",
    "eway_auth": f"{BASE_URL}/ewaybillapi/v1.03/authenticate",
    "eway_gen": f"{BASE_URL}/ewaybillapi/v1.03/ewayapi/genewaybill",
}


# -----------------------------
# HTTP Utilities
# -----------------------------

def _build_session() -> requests.Session:
    """
    Build a requests session with retries for transient failures.
    """
    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_SESSION = _build_session()


def _safe_json(response: requests.Response) -> Dict[str, Any]:
    """
    Parse JSON safely; return structured error on parse issues.
    """
    try:
        return response.json()
    except Exception:
        text = (response.text or "")[:1000]
        return {
            "error": "Invalid JSON response from MasterGST",
            "http_status": response.status_code,
            "raw": text,
        }


def _is_success_status_cd(value: Any) -> bool:
    """
    MasterGST sometimes returns:
    - "1" for success
    - "Sucess" (typo) or "Success" for success
    """
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("1", "success", "sucess")


def _api_error(resp: Dict[str, Any], fallback: str) -> Dict[str, Any]:
    """
    Normalize error shape across calls.
    """
    return {
        "error": resp.get("status_desc") or resp.get("message") or fallback,
        "details": resp,
    }


def _get_gst_details_or_error() -> Union[MasterGstDetail, Dict[str, Any]]:
    gst_details = MasterGstDetail.objects.first()
    if not gst_details:
        return {"error": "GST configuration not found in database (Mastergstdetails is empty)."}
    return gst_details


# -----------------------------
# Auth
# -----------------------------

def authenticate_gst(gst_details: MasterGstDetail) -> Union[str, Dict[str, Any]]:
    """
    Authenticate with the e-Invoice API and return AuthToken string.
    """
    url = URLS["einvoice_auth"]
    headers = {
        "accept": "*/*",
        "username": gst_details.username,
        "password": gst_details.password,
        "ip_address": DEFAULT_IP_EINVOICE,
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "gstin": gst_details.gstin,
    }
    params = {"email": gst_details.email}

    try:
        resp = _SESSION.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        data = _safe_json(resp)

        if isinstance(data, dict) and _is_success_status_cd(data.get("status_cd")):
            token = (data.get("data") or {}).get("AuthToken")
            if token:
                return token
            return {"error": "Authentication succeeded but AuthToken missing", "details": data}

        return _api_error(data if isinstance(data, dict) else {}, "Authentication failed")

    except requests.RequestException as e:
        return {"error": "Network error during GST authentication", "details": str(e)}


def authenticate_ewaybill(gst_details: MasterGstDetail) -> Union[Dict[str, Any], Dict[str, Any]]:
    """
    Authenticate with the e-Way Bill API.
    Returns a dict containing headers returned by MasterGST (often includes auth-token, sek, etc.),
    OR an error dict.

    NOTE: Your old code returned response_data.get("header") but later treated it like a string token.
    This version returns the header dict and downstream uses it correctly.
    """
    url = URLS["eway_auth"]
    headers = {
        "accept": "application/json",
        "ip_address": DEFAULT_IP_EWAY,
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "gstin": gst_details.gstin,
    }
    params = {
        "email": gst_details.email,
        "username": gst_details.username,
        "password": gst_details.password,
    }

    try:
        resp = _SESSION.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        data = _safe_json(resp)

        if isinstance(data, dict) and _is_success_status_cd(data.get("status_cd")):
            hdr = data.get("header")
            if isinstance(hdr, dict) and hdr:
                return hdr
            # Some implementations may return token inside data; keep fallback
            return {"error": "e-Way authentication succeeded but header missing", "details": data}

        return _api_error(data if isinstance(data, dict) else {}, "Authentication failed")

    except requests.RequestException as e:
        return {"error": "Network error during e-Way authentication", "details": str(e)}


# -----------------------------
# Common header builders
# -----------------------------

def _einvoice_headers(gst_details: MasterGstDetail, auth_token: str) -> Dict[str, str]:
    return {
        "accept": "*/*",
        "Content-Type": "application/json",
        "ip_address": DEFAULT_IP_EINVOICE,
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "username": gst_details.username,
        "auth-token": auth_token,
        "gstin": gst_details.gstin,
    }


def _eway_headers(gst_details: MasterGstDetail, eway_auth_header: Dict[str, Any]) -> Dict[str, str]:
    """
    MasterGST eway authenticate returns a header dict.
    Typically contains an 'auth-token' key; we pass it through.
    """
    auth_token = eway_auth_header.get("auth-token") or eway_auth_header.get("AuthToken") or eway_auth_header.get("token")
    if not auth_token:
        # Still return something useful for debugging (without secrets)
        raise ValueError("Missing auth-token in eway authentication header.")

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "ip_address": DEFAULT_IP_EWAY,
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "gstin": gst_details.gstin,
        "username": gst_details.username,
        "auth-token": str(auth_token),
    }


# -----------------------------
# APIs
# -----------------------------

def get_gst_details(entitygst: str) -> Dict[str, Any]:
    """
    Fetch GSTN details using the authentication token.
    """
    gst_details = _get_gst_details_or_error()
    if isinstance(gst_details, dict):
        return gst_details

    auth_token = authenticate_gst(gst_details)
    if isinstance(auth_token, dict) and "error" in auth_token:
        return auth_token

    url = URLS["einvoice_gstndetails"]
    headers = _einvoice_headers(gst_details, auth_token)
    params = {"param1": entitygst, "email": gst_details.email}

    try:
        resp = _SESSION.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        data = _safe_json(resp)

        if isinstance(data, dict) and _is_success_status_cd(data.get("status_cd")):
            return data.get("data") or {}

        return _api_error(data if isinstance(data, dict) else {}, "Request failed")

    except requests.RequestException as e:
        return {"error": "Network error while fetching GST details", "details": str(e)}


def gstinvoice(order, json_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate E-Invoice (Invoice / DN / CN) via MasterGST.
    `json_data` can be a dict OR a pre-serialized JSON string.
    """
    try:
        gst_details = _get_gst_details_or_error()
        if isinstance(gst_details, dict):
            return gst_details

        auth_token = authenticate_gst(gst_details)
        if isinstance(auth_token, dict) and auth_token.get("error"):
            return {"error": "Authentication failed", "details": auth_token}

        url = URLS["einvoice_generate"]
        headers = _einvoice_headers(gst_details, auth_token)
        params = {"email": gst_details.email}

        payload = json_data if isinstance(json_data, (str, bytes)) else json.dumps(json_data)

        resp = _SESSION.post(url, headers=headers, params=params, data=payload, timeout=DEFAULT_TIMEOUT)
        data = _safe_json(resp)

        # Update order on success
        if isinstance(data, dict) and _is_success_status_cd(data.get("status_cd")):
            api_data = data.get("data") or {}
            if api_data.get("Irn"):
                order.irn = api_data.get("Irn")
                order.ackno = api_data.get("AckNo")
                order.ackdt = api_data.get("AckDt")
                order.signed_invoice = api_data.get("SignedInvoice")
                order.qr_code = api_data.get("SignedQRCode")
                order.save()

        return data if isinstance(data, dict) else {"error": "Unexpected response type", "details": str(data)}

    except Exception as e:
        logger.exception("Exception in gstinvoice")
        return {"error": "Exception occurred during e-invoice generation", "details": str(e)}


def create_ewaybill(order, json_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create an e-Way Bill using the MasterGST eWay API (v1.03).
    `json_data` can be a dict OR a pre-serialized JSON string.
    """
    try:
        gst_details = _get_gst_details_or_error()
        if isinstance(gst_details, dict):
            return gst_details

        eway_header = authenticate_ewaybill(gst_details)
        if isinstance(eway_header, dict) and eway_header.get("error"):
            return {"error": "Authentication failed", "details": eway_header}

        url = URLS["eway_gen"]
        headers = _eway_headers(gst_details, eway_header)
        params = {"email": gst_details.email}

        payload = json_data if isinstance(json_data, (str, bytes)) else json.dumps(json_data)

        resp = _SESSION.post(url, headers=headers, params=params, data=payload, timeout=DEFAULT_TIMEOUT)
        data = _safe_json(resp)

        if isinstance(data, dict) and _is_success_status_cd(data.get("status_cd")):
            api_data = data.get("data") or {}
            if api_data.get("ewayBillNo"):
                order.ewaybill_no = api_data.get("ewayBillNo")
                order.ewaybill_date = api_data.get("ewayBillDate")
                order.valid_upto = api_data.get("validUpto")
                # keep your qr_code update (if your model expects it)
                if "qrCode" in api_data:
                    order.qr_code = api_data.get("qrCode")
                order.save()

        return data if isinstance(data, dict) else {"error": "Unexpected response type", "details": str(data)}

    except Exception as e:
        logger.exception("Exception in create_ewaybill")
        return {"error": "Exception occurred during e-Way Bill generation", "details": str(e)}


# -----------------------------
# Encryption helpers (kept compatible with your logic)
# -----------------------------

def encrypt_payload(json_string: str, client_secret: str) -> str:
    """
    Encrypt payload using AES-256 ECB with SHA-256 derived key.
    Output: base64 string.
    """
    key = hashlib.sha256(client_secret.encode("utf-8")).digest()  # 32-byte key
    cipher = AES.new(key, AES.MODE_ECB)
    padded = pkcs7_pad(json_string.encode("utf-8"), 16)
    encrypted_bytes = cipher.encrypt(padded)
    return base64.b64encode(encrypted_bytes).decode("utf-8")


def gst_ewaybill(order, payload: dict):
    """
    Generate E-Way Bill from IRN via MasterGST.
    IMPORTANT: send plain JSON (no encryption).
    """
    gst_details = MasterGstDetail.objects.first()
    if not gst_details:
        return {"status_cd": "0", "status_desc": "GST configuration not found."}

    auth_token = authenticate_gst(gst_details)
    if isinstance(auth_token, dict) and auth_token.get("error"):
        return {"status_cd": "0", "status_desc": "Authentication failed", "details": auth_token}

    url = "https://api.mastergst.com/einvoice/type/GENERATE_EWAYBILL/version/V1_03"
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
        "ip_address": "49.43.101.20",
        "client_id": gst_details.client_id,
        "client_secret": gst_details.client_secret,
        "username": gst_details.username,
        "auth-token": auth_token,
        "gstin": gst_details.gstin,
    }
    params = {"email": gst_details.email}

    print(headers)

    resp = requests.post(url, headers=headers, params=params, json=payload, timeout=60)

    # Defensive JSON parsing
    try:
        return resp.json()
    except Exception:
        return {
            "status_cd": "0",
            "status_desc": "Non-JSON response from MasterGST",
            "http_status": resp.status_code,
            "raw": (resp.text or "")[:2000],
        }



def cancel_gst_invoice(irn: str, cancel_reason_code: Union[int, str], cancel_remark: str) -> Dict[str, Any]:
    """
    Cancel E-Invoice via MasterGST API using IRN.
    """
    try:
        if not irn:
            return {"error": "IRN is required to cancel E-Invoice."}

        gst_details = _get_gst_details_or_error()
        if isinstance(gst_details, dict):
            return gst_details

        auth_token = authenticate_gst(gst_details)
        if isinstance(auth_token, dict) and auth_token.get("error"):
            return {"error": "Authentication failed", "details": auth_token}

        url = URLS["einvoice_cancel"]
        headers = _einvoice_headers(gst_details, auth_token)
        params = {"email": gst_details.email}

        payload = {"Irn": irn, "CnlRsn": str(cancel_reason_code), "CnlRem": cancel_remark}

        resp = _SESSION.post(url, headers=headers, params=params, json=payload, timeout=DEFAULT_TIMEOUT)
        data = _safe_json(resp)

        return data if isinstance(data, dict) else {"error": "Unexpected response type", "details": str(data)}

    except Exception as e:
        logger.exception("Exception in cancel_gst_invoice")
        return {"error": "Exception occurred during e-invoice cancellation", "details": str(e)}
