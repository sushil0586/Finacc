import os
import random
from typing import Any, Dict
from pathlib import Path

from dotenv import load_dotenv
from locust import HttpUser, between, task, tag

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent.parent

# Prefer local perf/locust/.env, then fallback to backend root .env.
load_dotenv(CURRENT_DIR / ".env")
load_dotenv(BACKEND_ROOT / ".env", override=False)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class FinaccDjangoUser(HttpUser):
    wait_time = between(1, 3)

    host = env("LOCUST_HOST", "")
    email = env("FINACC_USER_EMAIL", "")
    password = env("FINACC_USER_PASSWORD", "")

    entity_id = env("FINACC_ENTITY_ID", "1")
    entity_fin_id = env("FINACC_ENTITY_FIN_ID", "1")
    subentity_id = env("FINACC_SUBENTITY_ID", "")

    login_path = env("FINACC_LOGIN_PATH", "/api/auth/login")
    me_path = env("FINACC_ME_PATH", "/api/auth/me")
    sales_invoice_path = env("FINACC_SALES_INVOICE_PATH", "/api/sales/invoices/")
    sales_settings_path = env("FINACC_SALES_SETTINGS_PATH", "/api/sales/settings/")
    sales_invoice_confirm_suffix = env("FINACC_SALES_INVOICE_CONFIRM_SUFFIX", "/confirm/")
    sales_invoice_post_suffix = env("FINACC_SALES_INVOICE_POST_SUFFIX", "/post/")
    sales_invoice_reverse_suffix = env("FINACC_SALES_INVOICE_REVERSE_SUFFIX", "/reverse/")

    enable_writes = env("FINACC_ENABLE_WRITE_TESTS", "false").lower() == "true"
    enable_lifecycle = env("FINACC_ENABLE_LIFECYCLE_TESTS", "false").lower() == "true"

    def on_start(self) -> None:
        if not self.email or not self.password:
            raise RuntimeError("Set FINACC_USER_EMAIL and FINACC_USER_PASSWORD in .env")

        payload = {"email": self.email, "password": self.password}
        with self.client.post(self.login_path, json=payload, name="auth/login", catch_response=True) as response:
            if response.status_code >= 400:
                response.failure(f"Login failed ({response.status_code}): {response.text[:200]}")
                return

            token = self._extract_token(response)
            if token:
                self.client.headers.update({"Authorization": f"Bearer {token}"})
            response.success()

        # Finacc may authenticate using httpOnly auth cookies even when token is
        # not included in JSON response. Validate the session either way.
        with self.client.get(self.me_path, name="auth/me", catch_response=True) as me_response:
            if me_response.status_code >= 400:
                me_response.failure(
                    f"Post-login auth validation failed ({me_response.status_code}): {me_response.text[:200]}"
                )
            else:
                me_response.success()

    @staticmethod
    def _extract_token(response) -> str:
        try:
            data = response.json()
        except Exception:
            return ""

        if not isinstance(data, dict):
            return ""

        return str(data.get("access") or data.get("access_token") or data.get("token") or "")

    def _scope_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "entity_id": self.entity_id,
            "entityfinid": self.entity_fin_id,
        }
        if self.subentity_id:
            params["subentity_id"] = self.subentity_id
        return params

    def _extract_invoice_id(self, payload: Any) -> int | None:
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict) and first.get("id"):
                return int(first["id"])

        if isinstance(payload, dict):
            for key in ("results", "data", "items"):
                if isinstance(payload.get(key), list) and payload[key]:
                    first = payload[key][0]
                    if isinstance(first, dict) and first.get("id"):
                        return int(first["id"])
        return None

    def _fetch_any_invoice_id(self) -> int | None:
        with self.client.get(
            self.sales_invoice_path,
            params=self._scope_params(),
            name="sales/invoices [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Invoice seed fetch failed ({response.status_code})")
                return None
            try:
                invoice_id = self._extract_invoice_id(response.json())
            except Exception:
                invoice_id = None
            if not invoice_id:
                response.failure("No invoice id found for lifecycle test")
                return None
            response.success()
            return invoice_id

    @tag("read")
    @task(5)
    def list_sales_invoices(self) -> None:
        with self.client.get(
            self.sales_invoice_path,
            params=self._scope_params(),
            name="sales/invoices [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read")
    @task(3)
    def get_sales_settings(self) -> None:
        with self.client.get(
            self.sales_settings_path,
            params=self._scope_params(),
            name="sales/settings [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("write")
    @task(1)
    def patch_sales_settings_optional(self) -> None:
        if not self.enable_writes:
            return

        payload = {
            "settings": {
                "workflow_mode": random.choice(["STRICT", "RELAXED"]),
                "allow_negative_stock": random.choice([True, False]),
            }
        }
        self.client.patch(
            self.sales_settings_path,
            params=self._scope_params(),
            json=payload,
            name="sales/settings [patch]",
        )

    @tag("lifecycle", "write")
    @task(1)
    def invoice_lifecycle_optional(self) -> None:
        if not self.enable_lifecycle:
            return

        invoice_id = self._fetch_any_invoice_id()
        if not invoice_id:
            return

        base = f"{self.sales_invoice_path}{invoice_id}"

        self.client.post(
            f"{base}{self.sales_invoice_confirm_suffix}",
            name="sales/invoices [confirm]",
        )
        self.client.post(
            f"{base}{self.sales_invoice_post_suffix}",
            name="sales/invoices [post]",
        )
        self.client.post(
            f"{base}{self.sales_invoice_reverse_suffix}",
            json={"reason": "Locust lifecycle perf test"},
            name="sales/invoices [reverse]",
        )
