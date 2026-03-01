from __future__ import annotations

import requests
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class MasterGSTResult:
    ok: bool
    data: Dict[str, Any]
    error_code: Optional[str] = None
    error_message: Optional[str] = None

class MasterGSTEWayClient:
    def __init__(self, *, base_url: str, email: str, gstin: str, auth_token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.gstin = gstin
        self.auth_token = auth_token
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "accept": "application/json",
            "Content-Type": "application/json",
            "gstin": self.gstin,
            "auth-token": self.auth_token,
        }

    def generate_eway_direct(self, payload: Dict[str, Any]) -> MasterGSTResult:
        # This is the same style you already used in logs
        url = f"{self.base_url}/einvoice/type/GENERATE_EWAYBILL/version/V1_03?email={self.email}"

        resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        try:
            data = resp.json()
        except Exception:
            return MasterGSTResult(ok=False, data={"raw_text": resp.text}, error_code="BAD_JSON", error_message="Non-JSON response")

        status_cd = str(data.get("status_cd") or data.get("status") or "")
        if status_cd in {"1", "SUCCESS", "Success"}:
            return MasterGSTResult(ok=True, data=data)

        # normalize error fields
        return MasterGSTResult(
            ok=False,
            data=data,
            error_code=str(data.get("error_code") or "EWB_VALIDATION"),
            error_message=str(data.get("status_desc") or data.get("error_message") or "E-Way generation failed"),
        )