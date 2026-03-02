# sales/services/mastergst_eway_token_service.py
from __future__ import annotations
from typing import Any, Dict
from django.utils import timezone
from django.db import transaction
import requests
from urllib.parse import quote

from sales.models.mastergst_models import MasterGSTToken

class MasterGSTEWayTokenService:
    def __init__(self, *, base_url: str, cred: Any):
        self.base_url = base_url.rstrip("/")
        self.cred = cred  # your credential object

    def _resolve_ip(self) -> str:
        # you already have this logic somewhere; keep it consistent
        return "127.0.0.1"

    def _token_row(self) -> MasterGSTToken:
        row, _ = MasterGSTToken.objects.get_or_create(
            entity_id=self.cred.entity_id,
            gstin=self.cred.gstin,
            module=MasterGSTToken.Module.EWB,
            defaults={"auth_token": None, "token_created_at": None},
        )
        return row

    @transaction.atomic
    def get_token(self, *, force: bool = False) -> str:
        row = self._token_row()
        if not force and row.is_valid():
            return row.auth_token  # type: ignore

        email_q = quote(self.cred.email)

        # ✅ Use the correct E-Way auth endpoint you are using in your project.
        # MasterGST commonly has a separate authenticate for eway.
        url = f"{self.base_url}/ewaybillapi/v1.03/ewayapi/authenticate?email={email_q}"

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "ip_address": self._resolve_ip(),
            "client_id": self.cred.client_id,
            "client_secret": self.cred.client_secret,
            "gstin": self.cred.gstin,
            "username": self.cred.gst_username,
            "password": self.cred.gst_password,
        }

        resp = requests.get(url, headers=headers, timeout=30)
        data: Dict[str, Any] = resp.json() if resp.content else {}

        # MasterGST returns token under one of these keys depending on API version
        token = (
            data.get("authtoken")
            or data.get("AuthToken")
            or data.get("token")
            or data.get("data", {}).get("authtoken")
        )
        if not token:
            row.last_response_json = {"url": url, "http": resp.status_code, "json": data}
            row.save(update_fields=["last_response_json", "updated_at"])
            raise ValueError(f"EWB authenticate failed: {data}")

        row.auth_token = token
        row.token_created_at = timezone.now()
        row.last_response_json = {"url": url, "http": resp.status_code, "json": data}
        row.save(update_fields=["auth_token", "token_created_at", "last_response_json", "updated_at"])

        return token