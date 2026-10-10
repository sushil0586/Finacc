from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests


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
    expected_status: int = 200
    expected_min_rows: int = 0
    notes: str = ""
    extra_params: dict[str, Any] = field(default_factory=dict)


TENANTS = [
    Tenant("small", "perf-api-small@local.invalid", 5, 5, 5, 6),
    Tenant("medium", "perf-api-medium@local.invalid", 6, 6, 6, 5),
    Tenant("large", "perf-api-large@local.invalid", 7, 7, 7, 5),
]


ENDPOINTS = [
    Endpoint("auth/me", "/api/auth/me", "none"),
    Endpoint("entity/context", "/api/entity/me/entities", "none", expected_min_rows=1, extra_params={"include": "financial_years,subentities"}),
    Endpoint("dashboard/home-meta", "/api/dashboard/home/meta/", "entity", notes="Dashboard command center contract."),
    Endpoint("sales/invoices/lookup", "/api/sales/invoices/lookup/", "entity", expected_min_rows=1, extra_params={"limit": 100}),
    Endpoint("sales/invoices/list", "/api/sales/invoices/", "scope", expected_min_rows=1, extra_params={"limit": 100}),
    Endpoint("purchase/invoices/lookup", "/api/purchase/purchase-invoices/lookup/", "entity", expected_min_rows=1, extra_params={"limit": 100}),
    Endpoint("purchase/invoices/list", "/api/purchase/purchase-invoices/", "entity", expected_min_rows=1),
    Endpoint("reports/financial/daybook", "/api/reports/financial/daybook/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "page": 1, "page_size": 50}),
    Endpoint("reports/financial/ledger-summary", "/api/reports/financial/ledger-summary/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "group_by": "ledger", "account_group": "ledger", "view_type": "summary", "posted_only": "true", "include_zero_balances": "false", "include_opening": "true", "page": 1, "page_size": 100}),
    Endpoint("reports/receivables/aging-summary", "/api/reports/receivables/aging/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "as_of_date": AS_OF_DATE, "view": "summary", "page": 1, "page_size": 100}),
    Endpoint("reports/receivables/aging-invoice", "/api/reports/receivables/aging/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "as_of_date": AS_OF_DATE, "view": "invoice", "page": 1, "page_size": 100}),
    Endpoint("reports/receivables/open-items", "/api/reports/receivables/open-items/", "entity", expected_min_rows=1, extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "as_of_date": AS_OF_DATE, "page": 1, "page_size": 100}),
    Endpoint("reports/payables/vendor-outstanding", "/api/reports/payables/vendor-outstanding/", "entity", expected_min_rows=1, extra_params={"as_of_date": AS_OF_DATE, "view": "summary", "page": 1, "page_size": 100}),
    Endpoint("reports/payables/vendor-outstanding-voucher", "/api/reports/payables/vendor-outstanding/", "entity", expected_min_rows=1, extra_params={"as_of_date": AS_OF_DATE, "view": "summary", "voucher_type": "PINV", "page": 1, "page_size": 100}),
    Endpoint("reports/gstr1/summary", "/api/reports/gstr1/summary/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "page": 1, "page_size": 100}),
    Endpoint("reports/gstr1/readiness", "/api/reports/gstr1/readiness/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE}),
    Endpoint("reports/gstr3b/summary", "/api/reports/gstr3b/summary/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE}),
    Endpoint("reports/sales/gstin", "/api/reports/sales/gstin/", "entity", extra_params={"from_date": FROM_DATE, "to_date": AS_OF_DATE, "page": 1, "page_size": 100}),
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


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


def payload_total(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in ("count", "total", "total_count", "matched_count", "recordsTotal"):
        if key in payload:
            return payload[key]
    meta = payload.get("meta")
    if isinstance(meta, dict):
        for key in ("count", "total", "total_count", "matched_count"):
            if key in meta:
                return meta[key]
    return None


def login(base_url: str, tenant: Tenant, password: str) -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{base_url}/api/auth/login",
        json={"email": tenant.email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    me = session.get(f"{base_url}/api/auth/me", timeout=30)
    me.raise_for_status()
    return session


def request_once(session: requests.Session, base_url: str, endpoint: Endpoint, tenant: Tenant, *, denied: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    response = session.get(
        f"{base_url}{endpoint.path}",
        params=params_for(endpoint, tenant, denied=denied),
        timeout=60,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    content_type = response.headers.get("content-type", "")
    payload: Any = None
    parse_error = ""
    if "json" in content_type:
        try:
            payload = response.json()
        except ValueError as exc:
            parse_error = str(exc)
    rows = rows_from_payload(payload)
    validation_errors = []
    if response.status_code != endpoint.expected_status:
        validation_errors.append(f"status {response.status_code} != {endpoint.expected_status}")
    if parse_error:
        validation_errors.append("invalid_json")
    if endpoint.expected_min_rows and len(rows) < endpoint.expected_min_rows:
        validation_errors.append(f"rows {len(rows)} < {endpoint.expected_min_rows}")
    return {
        "status": response.status_code,
        "elapsed_ms": round(elapsed_ms, 3),
        "bytes": len(response.content),
        "row_count": len(rows),
        "total": payload_total(payload),
        "validation_errors": validation_errors,
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    timings = [sample["elapsed_ms"] for sample in samples]
    sizes = [sample["bytes"] for sample in samples]
    statuses: dict[str, int] = {}
    errors = 0
    row_counts = []
    totals = []
    for sample in samples:
        statuses[str(sample["status"])] = statuses.get(str(sample["status"]), 0) + 1
        if sample["validation_errors"]:
            errors += 1
        row_counts.append(sample["row_count"])
        totals.append(sample["total"])
    return {
        "samples": len(samples),
        "status_counts": statuses,
        "errors": errors,
        "min_ms": round(min(timings), 3),
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(percentile(timings, 0.95), 3),
        "p99_ms": round(percentile(timings, 0.99), 3),
        "max_ms": round(max(timings), 3),
        "avg_bytes": round(statistics.mean(sizes), 1),
        "min_rows": min(row_counts),
        "max_rows": max(row_counts),
        "observed_totals": sorted({str(total) for total in totals if total is not None})[:5],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"Missing {args.password_env}; password is required but will not be logged.")

    all_results = []
    tenant_sessions = {}
    for tenant in TENANTS:
        tenant_sessions[tenant.label] = login(args.base_url, tenant, password)

    for tenant in TENANTS:
        session = tenant_sessions[tenant.label]
        for endpoint in ENDPOINTS:
            samples = []
            cold = request_once(session, args.base_url, endpoint, tenant)
            samples.append(cold)
            time.sleep(args.pause)
            for _ in range(args.warm_samples):
                samples.append(request_once(session, args.base_url, endpoint, tenant))
                time.sleep(args.pause)
            all_results.append(
                {
                    "tenant": tenant.label,
                    "entity": tenant.entity,
                    "endpoint": endpoint.name,
                    "path": endpoint.path,
                    "params": params_for(endpoint, tenant),
                    "notes": endpoint.notes,
                    "cold_sample": cold,
                    "summary": summarize(samples),
                    "samples": samples,
                }
            )

    denial_results = []
    for tenant in TENANTS:
        endpoint = Endpoint("cross-tenant/entity-fy-denial", f"/api/entity/me/entities/{tenant.denied_entity}/financial-years", "none", expected_status=404)
        sample = request_once(tenant_sessions[tenant.label], args.base_url, endpoint, tenant, denied=True)
        denial_results.append({"tenant": tenant.label, "authorized_entity": tenant.entity, "denied_entity": tenant.denied_entity, "sample": sample})

    return {
        "base_url": args.base_url,
        "samples_per_endpoint_per_tenant": args.warm_samples + 1,
        "warm_samples_per_endpoint_per_tenant": args.warm_samples,
        "p95_p99_note": "Indicative only: bounded single-user sample counts are intentionally small in Phase 2B.3C.1B.",
        "secret_values_logged": False,
        "tenants": [tenant.__dict__ for tenant in TENANTS],
        "endpoint_count": len(ENDPOINTS),
        "results": all_results,
        "cross_tenant_denials": denial_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:18080")
    parser.add_argument("--password-env", default="FINACC_PERF_AUTH_PASSWORD")
    parser.add_argument("--warm-samples", type=int, default=5)
    parser.add_argument("--pause", type=float, default=0.05)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = run(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
