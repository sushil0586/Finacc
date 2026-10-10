from __future__ import annotations

import itertools
import os
import random
from dataclasses import dataclass, field
from typing import Any

from locust import HttpUser, between, events, task


AS_OF_DATE = "2026-10-10"
FROM_DATE = "2026-04-01"


@dataclass(frozen=True)
class Tenant:
    label: str
    email: str
    entity: int
    entityfinid: int
    subentity: int
    denied_entity: int


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    params_style: str
    weight: int
    expected_status: int = 200
    expected_min_rows: int = 0
    extra_params: dict[str, Any] = field(default_factory=dict)


TENANTS = [
    Tenant("small", "perf-api-small@local.invalid", 5, 5, 5, 6),
    Tenant("medium", "perf-api-medium@local.invalid", 6, 6, 6, 5),
    Tenant("large", "perf-api-large@local.invalid", 7, 7, 7, 5),
]
TENANT_CYCLE = itertools.cycle(TENANTS)


ENDPOINTS = [
    Endpoint("auth/me", "/api/auth/me", "none", weight=1),
    Endpoint("entity/context", "/api/entity/me/entities", "none", weight=2, expected_min_rows=1, extra_params={"include": "financial_years,subentities"}),
    Endpoint("dashboard/home-meta", "/api/dashboard/home/meta/", "entity", weight=5),
    Endpoint("sales/invoices/lookup", "/api/sales/invoices/lookup/", "entity", weight=6, expected_min_rows=1, extra_params={"limit": 100}),
    Endpoint("sales/invoices/list", "/api/sales/invoices/", "scope", weight=2, expected_min_rows=1, extra_params={"limit": 100}),
    Endpoint("purchase/invoices/lookup", "/api/purchase/purchase-invoices/lookup/", "entity", weight=6, expected_min_rows=1, extra_params={"limit": 100}),
    Endpoint("purchase/invoices/list", "/api/purchase/purchase-invoices/", "entity", weight=2, expected_min_rows=1),
    Endpoint("reports/financial/daybook", "/api/reports/financial/daybook/", "entity", weight=5, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "page": 1, "page_size": 50}),
    Endpoint("reports/financial/ledger-summary", "/api/reports/financial/ledger-summary/", "entity", weight=3, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "group_by": "ledger", "account_group": "ledger", "view_type": "summary", "posted_only": "true", "include_zero_balances": "false", "include_opening": "true", "page": 1, "page_size": 100}),
    Endpoint("reports/receivables/aging-summary", "/api/reports/receivables/aging/", "entity", weight=3, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "as_of_date": AS_OF_DATE, "view": "summary", "page": 1, "page_size": 100}),
    Endpoint("reports/receivables/aging-invoice", "/api/reports/receivables/aging/", "entity", weight=3, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "as_of_date": AS_OF_DATE, "view": "invoice", "page": 1, "page_size": 100}),
    Endpoint("reports/receivables/open-items", "/api/reports/receivables/open-items/", "entity", weight=4, expected_min_rows=1, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "as_of_date": AS_OF_DATE, "page": 1, "page_size": 100}),
    Endpoint("reports/payables/vendor-outstanding", "/api/reports/payables/vendor-outstanding/", "entity", weight=4, expected_min_rows=1, extra_params={"as_of_date": AS_OF_DATE, "view": "summary", "page": 1, "page_size": 100}),
    Endpoint("reports/payables/vendor-outstanding-voucher", "/api/reports/payables/vendor-outstanding/", "entity", weight=2, expected_min_rows=1, extra_params={"as_of_date": AS_OF_DATE, "view": "summary", "voucher_type": "PINV", "page": 1, "page_size": 100}),
    Endpoint("reports/gstr1/summary", "/api/reports/gstr1/summary/", "entity", weight=2, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "page": 1, "page_size": 100}),
    Endpoint("reports/gstr1/readiness", "/api/reports/gstr1/readiness/", "entity", weight=2, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE}),
    Endpoint("reports/gstr3b/summary", "/api/reports/gstr3b/summary/", "entity", weight=2, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE}),
    Endpoint("reports/sales/gstin", "/api/reports/sales/gstin/", "entity", weight=1, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "page": 1, "page_size": 100}),
]
WEIGHTED_ENDPOINTS = [endpoint for endpoint in ENDPOINTS for _ in range(endpoint.weight)]


def params_for(endpoint: Endpoint, tenant: Tenant, *, denied: bool = False) -> dict[str, Any]:
    entity = tenant.denied_entity if denied else tenant.entity
    if endpoint.params_style == "none":
        return dict(endpoint.extra_params)
    if endpoint.params_style == "scope":
        params = {"entity_id": entity, "entityfinid": tenant.entityfinid, "subentity_id": tenant.subentity}
    else:
        params = {"entity": entity, "entityfinid": tenant.entityfinid, "subentity": tenant.subentity}
    params.update(endpoint.extra_params)
    return params


def rows_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("results", "items", "rows", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("results", "items", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


class Phase2B3C2ReadReportUser(HttpUser):
    wait_time = between(1.0, 3.0)
    host = os.getenv("LOCUST_HOST", "http://localhost:18080").strip()
    password = os.getenv("FINACC_PERF_AUTH_PASSWORD", "")

    def on_start(self) -> None:
        if not self.password:
            raise RuntimeError("FINACC_PERF_AUTH_PASSWORD is required and must not be logged.")
        self.tenant = next(TENANT_CYCLE)
        with self.client.post(
            "/api/auth/login",
            json={"email": self.tenant.email, "password": self.password},
            name="auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login status {response.status_code}")
                return
            response.success()
        self._assert_context()
        self._assert_cross_tenant_denial()

    def _assert_context(self) -> None:
        with self.client.get(
            "/api/entity/me/entities",
            params={"include": "financial_years,subentities"},
            name="entity/context [startup]",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"context status {response.status_code}")
                return
            try:
                payload = response.json()
            except ValueError:
                response.failure("context invalid json")
                return
            ids = sorted(row.get("entityid") for row in payload if isinstance(row, dict))
            if ids != [self.tenant.entity]:
                response.failure(f"tenant isolation mismatch: {ids}")
                return
            response.success()

    def _assert_cross_tenant_denial(self) -> None:
        with self.client.get(
            f"/api/entity/me/entities/{self.tenant.denied_entity}/financial-years",
            name="cross-tenant/financial-years [denied]",
            catch_response=True,
        ) as response:
            if response.status_code not in (403, 404):
                response.failure(f"cross-tenant denial returned {response.status_code}")
                return
            response.success()

    @task
    def mixed_read_report(self) -> None:
        endpoint = random.choice(WEIGHTED_ENDPOINTS)
        with self.client.get(
            endpoint.path,
            params=params_for(endpoint, self.tenant),
            name=endpoint.name,
            catch_response=True,
        ) as response:
            if response.status_code != endpoint.expected_status:
                response.failure(f"status {response.status_code} != {endpoint.expected_status}: {response.text[:200]}")
                return
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                response.failure(f"non-json response: {content_type}")
                return
            try:
                payload = response.json()
            except ValueError:
                response.failure("invalid json")
                return
            rows = rows_from_payload(payload)
            if endpoint.expected_min_rows and len(rows) < endpoint.expected_min_rows:
                response.failure(f"rows {len(rows)} < {endpoint.expected_min_rows}")
                return
            response.success()


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    environment.parsed_options.tags = None
