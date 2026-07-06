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
    sales_invoice_lookup_path = env("FINACC_SALES_INVOICE_LOOKUP_PATH", "/api/sales/invoices/lookup/")
    sales_service_invoice_lookup_path = env("FINACC_SALES_SERVICE_INVOICE_LOOKUP_PATH", "/api/sales/service-invoices/lookup/")
    purchase_invoice_path = env("FINACC_PURCHASE_INVOICE_PATH", "/api/purchase/purchase-invoices/")
    purchase_service_invoice_path = env("FINACC_PURCHASE_SERVICE_INVOICE_PATH", "/api/purchase/purchase-service-invoices/")
    purchase_invoice_search_path = env("FINACC_PURCHASE_INVOICE_SEARCH_PATH", "/api/purchase/purchase-invoices/search/")
    purchase_service_invoice_search_path = env("FINACC_PURCHASE_SERVICE_INVOICE_SEARCH_PATH", "/api/purchase/purchase-service-invoices/search/")
    purchase_invoice_lookup_path = env("FINACC_PURCHASE_INVOICE_LOOKUP_PATH", "/api/purchase/purchase-invoices/lookup/")
    purchase_service_invoice_lookup_path = env("FINACC_PURCHASE_SERVICE_INVOICE_LOOKUP_PATH", "/api/purchase/purchase-service-invoices/lookup/")
    sales_settings_path = env("FINACC_SALES_SETTINGS_PATH", "/api/sales/settings/")
    payables_meta_path = env("FINACC_PAYABLES_META_PATH", "/api/reports/payables/meta/")
    ap_aging_path = env("FINACC_AP_AGING_PATH", "/api/reports/payables/aging/")
    bank_reco_meta_path = env("FINACC_BANK_RECO_META_PATH", "/api/bank-reconciliation/meta/")
    bank_reco_sessions_path = env("FINACC_BANK_RECO_SESSIONS_PATH", "/api/bank-reconciliation/sessions/")
    sales_invoice_confirm_suffix = env("FINACC_SALES_INVOICE_CONFIRM_SUFFIX", "/confirm/")
    sales_invoice_post_suffix = env("FINACC_SALES_INVOICE_POST_SUFFIX", "/post/")
    sales_invoice_reverse_suffix = env("FINACC_SALES_INVOICE_REVERSE_SUFFIX", "/reverse/")
    report_as_of_date = env("FINACC_REPORT_AS_OF_DATE", "")
    ap_aging_view = env("FINACC_AP_AGING_VIEW", "summary")

    enable_writes = env("FINACC_ENABLE_WRITE_TESTS", "false").lower() == "true"
    enable_lifecycle = env("FINACC_ENABLE_LIFECYCLE_TESTS", "false").lower() == "true"
    _seed_invoice_id: int | None = None
    _seed_service_invoice_id: int | None = None
    _seed_purchase_invoice_id: int | None = None
    _seed_purchase_service_invoice_id: int | None = None

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

    def _entity_scope_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "entity": self.entity_id,
            "entityfinid": self.entity_fin_id,
        }
        if self.subentity_id:
            params["subentity"] = self.subentity_id
        return params

    def _ap_aging_params(self) -> Dict[str, Any]:
        params = self._entity_scope_params()
        params["view"] = self.ap_aging_view or "summary"
        params["include_trace"] = "true"
        if self.report_as_of_date:
            params["as_of_date"] = self.report_as_of_date
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

    def _extract_lookup_invoice_id(self, payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
                return int(first["id"])
        return None

    def _fetch_any_invoice_id(self) -> int | None:
        if self._seed_invoice_id:
            return self._seed_invoice_id
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
            self._seed_invoice_id = invoice_id
            response.success()
            return invoice_id

    def _fetch_lookup_invoice_id(self, *, line_mode: str = "goods") -> int | None:
        cache_attr = "_seed_service_invoice_id" if line_mode == "service" else "_seed_invoice_id"
        cached_id = getattr(self, cache_attr, None)
        if cached_id:
            return cached_id

        path = self.sales_service_invoice_lookup_path if line_mode == "service" else self.sales_invoice_lookup_path
        with self.client.get(
            path,
            params={**self._entity_scope_params(), "limit": 1},
            name=f"sales/{line_mode}-lookup [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Lookup seed fetch failed ({response.status_code})")
                return None
            try:
                invoice_id = self._extract_lookup_invoice_id(response.json())
            except Exception:
                invoice_id = None
            if not invoice_id:
                response.failure("No invoice id found for lookup/navigation seed")
                return None
            setattr(self, cache_attr, invoice_id)
            response.success()
            return invoice_id

    def _fetch_purchase_lookup_invoice_id(self, *, line_mode: str = "goods") -> int | None:
        cache_attr = "_seed_purchase_service_invoice_id" if line_mode == "service" else "_seed_purchase_invoice_id"
        cached_id = getattr(self, cache_attr, None)
        if cached_id:
            return cached_id

        path = self.purchase_service_invoice_lookup_path if line_mode == "service" else self.purchase_invoice_lookup_path
        with self.client.get(
            path,
            params={**self._entity_scope_params(), "limit": 1},
            name=f"purchase/{line_mode}-lookup [seed-id]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Purchase lookup seed fetch failed ({response.status_code})")
                return None
            try:
                invoice_id = self._extract_lookup_invoice_id(response.json())
            except Exception:
                invoice_id = None
            if not invoice_id:
                response.failure("No purchase invoice id found for lookup/navigation seed")
                return None
            setattr(self, cache_attr, invoice_id)
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

    @tag("read", "read-modern")
    @task(4)
    def lookup_sales_invoices(self) -> None:
        with self.client.get(
            self.sales_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="sales/invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "read-modern")
    @task(2)
    def lookup_service_invoices(self) -> None:
        with self.client.get(
            self.sales_service_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="sales/service-invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "read-modern")
    @task(2)
    def cross_mode_navigation_from_goods(self) -> None:
        invoice_id = self._fetch_lookup_invoice_id(line_mode="goods")
        if not invoice_id:
            return
        with self.client.get(
            f"{self.sales_invoice_path}{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "service", "direction": "next"},
            name="sales/invoices/cross-mode-nav [goods->service]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read", "read-modern")
    @task(2)
    def cross_mode_navigation_from_service(self) -> None:
        invoice_id = self._fetch_lookup_invoice_id(line_mode="service")
        if not invoice_id:
            return
        with self.client.get(
            f"/api/sales/service-invoices/{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "goods", "direction": "next"},
            name="sales/service-invoices/cross-mode-nav [service->goods]",
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

    @tag("read-modern", "purchase-modern")
    @task(4)
    def lookup_purchase_invoices(self) -> None:
        with self.client.get(
            self.purchase_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="purchase/purchase-invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("purchase-legacy")
    @task(4)
    def search_purchase_invoices_legacy(self) -> None:
        with self.client.get(
            self.purchase_invoice_search_path,
            params=self._entity_scope_params(),
            name="purchase/purchase-invoices/search [legacy]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("purchase-legacy")
    @task(3)
    def search_purchase_service_invoices_legacy(self) -> None:
        with self.client.get(
            self.purchase_service_invoice_search_path,
            params=self._entity_scope_params(),
            name="purchase/purchase-service-invoices/search [legacy]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read-modern", "purchase-modern")
    @task(2)
    def lookup_purchase_service_invoices(self) -> None:
        with self.client.get(
            self.purchase_service_invoice_lookup_path,
            params={**self._entity_scope_params(), "limit": 100},
            name="purchase/purchase-service-invoices/lookup [list]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read-modern", "purchase-modern")
    @task(2)
    def cross_mode_navigation_from_purchase_goods(self) -> None:
        invoice_id = self._fetch_purchase_lookup_invoice_id(line_mode="goods")
        if not invoice_id:
            return
        with self.client.get(
            f"{self.purchase_invoice_path}{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "service", "direction": "next"},
            name="purchase/purchase-invoices/cross-mode-nav [goods->service]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read-modern", "purchase-modern")
    @task(2)
    def cross_mode_navigation_from_purchase_service(self) -> None:
        invoice_id = self._fetch_purchase_lookup_invoice_id(line_mode="service")
        if not invoice_id:
            return
        with self.client.get(
            f"{self.purchase_service_invoice_path}{invoice_id}/cross-mode-nav/",
            params={**self._entity_scope_params(), "target_line_mode": "goods", "direction": "next"},
            name="purchase/purchase-service-invoices/cross-mode-nav [service->goods]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read")
    @task(2)
    def get_payables_meta(self) -> None:
        with self.client.get(
            self.payables_meta_path,
            params=self._entity_scope_params(),
            name="reports/payables/meta [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read")
    @task(3)
    def get_ap_aging(self) -> None:
        with self.client.get(
            self.ap_aging_path,
            params=self._ap_aging_params(),
            name="reports/payables/aging [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read")
    @task(2)
    def get_bank_reconciliation_meta(self) -> None:
        with self.client.get(
            self.bank_reco_meta_path,
            params=self._entity_scope_params(),
            name="bank-reconciliation/meta [get]",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"{response.status_code}: {response.text[:200]}")
            else:
                response.success()

    @tag("read")
    @task(2)
    def list_bank_reconciliation_sessions(self) -> None:
        with self.client.get(
            self.bank_reco_sessions_path,
            params=self._entity_scope_params(),
            name="bank-reconciliation/sessions [list]",
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
