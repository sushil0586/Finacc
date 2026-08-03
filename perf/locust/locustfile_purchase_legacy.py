import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from locust import HttpUser, between, task

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent.parent

load_dotenv(CURRENT_DIR / ".env")
load_dotenv(BACKEND_ROOT / ".env", override=False)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class PurchaseLegacyUser(HttpUser):
    wait_time = between(1, 3)

    host = env("LOCUST_HOST", "")
    email = env("FINACC_USER_EMAIL", "")
    password = env("FINACC_USER_PASSWORD", "")

    entity_id = env("FINACC_ENTITY_ID", "1")
    entity_fin_id = env("FINACC_ENTITY_FIN_ID", "1")
    subentity_id = env("FINACC_SUBENTITY_ID", "")

    login_path = env("FINACC_LOGIN_PATH", "/api/auth/login")
    me_path = env("FINACC_ME_PATH", "/api/auth/me")
    purchase_invoice_search_path = env("FINACC_PURCHASE_INVOICE_SEARCH_PATH", "/api/purchase/purchase-invoices/search/")
    purchase_service_invoice_search_path = env(
        "FINACC_PURCHASE_SERVICE_INVOICE_SEARCH_PATH",
        "/api/purchase/purchase-service-invoices/search/",
    )

    def on_start(self) -> None:
        if not self.email or not self.password:
            raise RuntimeError("Set FINACC_USER_EMAIL and FINACC_USER_PASSWORD in .env")

        payload = {"email": self.email, "password": self.password}
        response = self.client.post(self.login_path, json=payload, name="auth/login")
        if response.status_code >= 400:
            raise RuntimeError(f"Login failed ({response.status_code}): {response.text[:200]}")

        token = self._extract_token(response)
        if token:
            self.client.headers.update({"Authorization": f"Bearer {token}"})

        me_response = self.client.get(self.me_path, name="auth/me")
        if me_response.status_code >= 400:
            raise RuntimeError(
                f"Post-login auth validation failed ({me_response.status_code}): {me_response.text[:200]}"
            )

    @staticmethod
    def _extract_token(response) -> str:
        try:
            data = response.json()
        except Exception:
            return ""

        if not isinstance(data, dict):
            return ""

        return str(data.get("access") or data.get("access_token") or data.get("token") or "")

    def _entity_scope_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "entity": self.entity_id,
            "entityfinid": self.entity_fin_id,
        }
        if self.subentity_id:
            params["subentity"] = self.subentity_id
        return params

    @task(4)
    def search_purchase_invoices_legacy(self) -> None:
        self.client.get(
            self.purchase_invoice_search_path,
            params=self._entity_scope_params(),
            name="purchase/purchase-invoices/search [legacy]",
        )

    @task(3)
    def search_purchase_service_invoices_legacy(self) -> None:
        self.client.get(
            self.purchase_service_invoice_search_path,
            params=self._entity_scope_params(),
            name="purchase/purchase-service-invoices/search [legacy]",
        )
