#!/usr/bin/env python3
"""Phase 1 Finacc API baseline probe.

Runs a single-user, read-only API pass and records response time, Django SQL
query count, SQL duration, and slow query samples. This is a discovery probe,
not a load test.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = BACKEND_ROOT / "docs" / "qa" / "performance" / "evidence"
sys.path.insert(0, str(BACKEND_ROOT))


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_env() -> None:
    load_dotenv(BACKEND_ROOT / "perf" / "locust" / ".env")
    load_dotenv(BACKEND_ROOT / ".env", override=False)


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FA.settings")
    import django

    django.setup()


def scope() -> dict[str, str]:
    entity = env("FINACC_ENTITY_ID", "10")
    entity_fin = env("FINACC_ENTITY_FIN_ID", "8")
    subentity = env("FINACC_SUBENTITY_ID", "8")
    as_of_date = env("FINACC_BASELINE_AS_OF_DATE", "") or env("FINACC_REPORT_AS_OF_DATE", str(date.today()))
    from_date = env("FINACC_FINANCIAL_REPORT_FROM_DATE", f"{as_of_date[:4]}-04-01")
    to_date = env("FINACC_FINANCIAL_REPORT_TO_DATE", as_of_date)
    params = {
        "entity": entity,
        "entity_id": entity,
        "entityfinid": entity_fin,
        "subentity": subentity,
        "subentity_id": subentity,
        "as_of_date": as_of_date,
        "from_date": from_date,
        "to_date": to_date,
    }
    return {key: value for key, value in params.items() if value}


def endpoint_catalog() -> list[dict[str, Any]]:
    s = scope()
    entity_scope = {"entity": s["entity"], "entityfinid": s["entityfinid"]}
    if s.get("subentity"):
        entity_scope["subentity"] = s["subentity"]
    invoice_scope = {"entity_id": s["entity_id"], "entityfinid": s["entityfinid"], "page": "1", "page_size": "25"}
    if s.get("subentity_id"):
        invoice_scope["subentity_id"] = s["subentity_id"]
    purchase_scope = {"entity": s["entity"], "entityfinid": s["entityfinid"], "page": "1", "page_size": "25"}
    if s.get("subentity"):
        purchase_scope["subentity"] = s["subentity"]
    period_scope = {**entity_scope, "from_date": s["from_date"], "to_date": s["to_date"], "page": "1", "page_size": "50"}
    asof_scope = {**entity_scope, "as_of_date": s["as_of_date"], "page": "1", "page_size": "50"}
    financial_scope = {
        **period_scope,
        "scope_mode": "custom",
        "group_by": "ledger",
        "account_group": "ledger",
        "view_type": "summary",
        "posted_only": "true",
        "include_opening": "true",
        "include_zero_balances": "false",
    }
    gst_period = {
        "entity": s["entity"],
        "entityfinid": s["entityfinid"],
        "from_date": s["from_date"],
        "to_date": s["to_date"],
        "period": s["to_date"][:7],
    }
    return [
        {"name": "auth/me", "path": "/api/auth/me", "params": {}},
        {"name": "dashboard/home-meta", "path": "/api/dashboard/home/meta/", "params": entity_scope},
        {"name": "sales/invoices", "path": "/api/sales/invoices/", "params": invoice_scope},
        {"name": "sales/invoices-lookup", "path": "/api/sales/invoices/lookup/", "params": invoice_scope},
        {"name": "sales/service-invoices-lookup", "path": "/api/sales/service-invoices/lookup/", "params": invoice_scope},
        {"name": "purchase/invoices", "path": "/api/purchase/purchase-invoices/", "params": purchase_scope},
        {"name": "purchase/invoices-lookup", "path": "/api/purchase/purchase-invoices/lookup/", "params": purchase_scope},
        {"name": "purchase/service-invoices-lookup", "path": "/api/purchase/purchase-service-invoices/lookup/", "params": purchase_scope},
        {"name": "payments/vouchers-lookup", "path": "/api/payments/payment-vouchers/lookup/", "params": purchase_scope},
        {"name": "receipts/vouchers-lookup", "path": "/api/receipts/receipt-vouchers/lookup/", "params": purchase_scope},
        {"name": "reports/payables/meta", "path": "/api/reports/payables/meta/", "params": entity_scope},
        {"name": "reports/payables/aging", "path": "/api/reports/payables/aging/", "params": {**asof_scope, "view": "summary"}},
        {"name": "reports/payables/vendor-outstanding", "path": "/api/reports/payables/vendor-outstanding/", "params": asof_scope},
        {"name": "reports/receivables/customer-outstanding", "path": "/api/reports/receivables/customer-outstanding/", "params": asof_scope},
        {"name": "reports/receivables/aging", "path": "/api/reports/receivables/aging/", "params": {**asof_scope, "view": "summary"}},
        {"name": "reports/receivables/open-items", "path": "/api/reports/receivables/open-items/", "params": asof_scope},
        {"name": "reports/financial/trial-balance", "path": "/api/reports/financial/trial-balance/", "params": financial_scope},
        {"name": "reports/financial/ledger-summary", "path": "/api/reports/financial/ledger-summary/", "params": financial_scope},
        {"name": "reports/financial/daybook", "path": "/api/reports/financial/daybook/", "params": period_scope},
        {"name": "reports/gstr1/summary", "path": "/api/reports/gstr1/summary/", "params": gst_period},
    ]


def login_client():
    import jwt
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from django.test import Client

    email = env("FINACC_USER_EMAIL")
    password = env("FINACC_USER_PASSWORD")
    if not email or not password:
        raise RuntimeError("Set FINACC_USER_EMAIL and FINACC_USER_PASSWORD in perf/locust/.env")
    client = Client(HTTP_HOST="localhost")
    response = client.post(
        env("FINACC_LOGIN_PATH", "/api/auth/login"),
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
    )
    token = None
    if response.status_code < 400:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        token = payload.get("access") or payload.get("access_token") or payload.get("token")
    else:
        user_id = env("FINACC_BASELINE_USER_ID", "")
        users = get_user_model().objects.filter(is_active=True)
        user = users.get(pk=user_id) if user_id else users.order_by("-is_superuser", "-is_staff", "id").first()
        if not user:
            raise RuntimeError("No active user found for baseline auth fallback.")
        now = timezone.now()
        from Authentication.services import AuthSettings

        payload = {
            "user_id": user.pk,
            "email": user.email,
            "username": user.username,
            "ver": user.token_version,
            "type": "access",
            "iss": AuthSettings.ISSUER,
            "aud": AuthSettings.AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + timezone.timedelta(minutes=15)).timestamp()),
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("utf-8")
    if token:
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client


def run_django_probe(*, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = login_client()
    results: list[dict[str, Any]] = []
    exclude = exclude or set()
    for item in endpoint_catalog():
        if item["name"] in exclude:
            results.append(
                {
                    "name": item["name"],
                    "method": "GET",
                    "path": item["path"],
                    "status_code": "SKIPPED",
                    "elapsed_ms": None,
                    "query_count": None,
                    "sql_ms": None,
                    "response_bytes": 0,
                    "slow_queries": [],
                    "note": "Skipped by --exclude after earlier Phase 1 probe exceeded the manual stop threshold.",
                }
            )
            continue
        with CaptureQueriesContext(connection) as queries:
            started = time.perf_counter()
            response = client.get(item["path"], data=item["params"])
            elapsed_ms = (time.perf_counter() - started) * 1000
        sql_ms = sum(float(query.get("time") or 0) * 1000 for query in queries.captured_queries)
        slow_queries = [
            {
                "sql_ms": round(float(query.get("time") or 0) * 1000, 2),
                "sql": " ".join(str(query.get("sql", "")).split())[:500],
            }
            for query in queries.captured_queries
            if float(query.get("time") or 0) >= 0.1
        ][:5]
        results.append(
            {
                "name": item["name"],
                "method": "GET",
                "path": item["path"],
                "status_code": response.status_code,
                "elapsed_ms": round(elapsed_ms, 2),
                "query_count": len(queries),
                "sql_ms": round(sql_ms, 2),
                "response_bytes": len(response.content or b""),
                "slow_queries": slow_queries,
            }
        )
    return results


def db_snapshot() -> dict[str, Any]:
    from django.conf import settings
    from django.db import connection

    snapshot: dict[str, Any] = {
        "debug": settings.DEBUG,
        "db_engine": settings.DATABASES["default"]["ENGINE"],
        "db_name": settings.DATABASES["default"].get("NAME"),
        "db_host": settings.DATABASES["default"].get("HOST"),
        "db_conn_max_age": settings.DATABASES["default"].get("CONN_MAX_AGE"),
        "db_conn_health_checks": settings.DATABASES["default"].get("CONN_HEALTH_CHECKS"),
        "cache_backend": settings.CACHES["default"]["BACKEND"],
        "cache_location": settings.CACHES["default"].get("LOCATION"),
        "db_pool_enabled": getattr(settings, "DB_POOL_ENABLED", None),
        "meta_cache_enabled": getattr(settings, "META_CACHE_ENABLED", None),
        "payables_meta_cache_enabled": getattr(settings, "PAYABLES_META_CACHE_ENABLED", None),
    }
    with connection.cursor() as cur:
        cur.execute("select version()")
        snapshot["postgres_version"] = cur.fetchone()[0]
        cur.execute("select current_setting('max_connections'), current_setting('shared_buffers')")
        max_connections, shared_buffers = cur.fetchone()
        snapshot["postgres_max_connections"] = max_connections
        snapshot["postgres_shared_buffers"] = shared_buffers
        cur.execute(
            """
            select relname, n_live_tup, n_dead_tup
            from pg_stat_user_tables
            order by n_live_tup desc nulls last
            limit 20
            """
        )
        snapshot["largest_tables"] = [
            {"table": row[0], "live_rows_est": row[1], "dead_rows_est": row[2]} for row in cur.fetchall()
        ]
        cur.execute(
            """
            select mode, granted, count(*)
            from pg_locks
            group by mode, granted
            order by mode, granted
            """
        )
        snapshot["lock_summary"] = [
            {"mode": row[0], "granted": row[1], "count": row[2]} for row in cur.fetchall()
        ]
    return snapshot


def write_artifacts(results: list[dict[str, Any]], snapshot: dict[str, Any], label: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "label": label,
        "generated_at_epoch": int(time.time()),
        "scope": scope(),
        "db_snapshot": snapshot,
        "results": results,
    }
    path = EVIDENCE_DIR / f"{label}.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    csv_path = EVIDENCE_DIR / f"{label}.csv"
    lines = ["name,path,status_code,elapsed_ms,query_count,sql_ms,response_bytes"]
    for row in results:
        lines.append(
            ",".join(
                [
                    row["name"],
                    row["path"],
                    str(row["status_code"]),
                    str(row["elapsed_ms"]),
                    str(row["query_count"]),
                    str(row["sql_ms"]),
                    str(row["response_bytes"]),
                ]
            )
        )
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=f"phase1_api_baseline_{date.today().isoformat()}")
    parser.add_argument("--exclude", default="", help="Comma-separated endpoint names to skip.")
    args = parser.parse_args()
    load_env()
    setup_django()
    exclude = {item.strip() for item in args.exclude.split(",") if item.strip()}
    results = run_django_probe(exclude=exclude)
    artifact = write_artifacts(results, db_snapshot(), args.label)
    print(f"Wrote {artifact}")
    sortable = [row for row in results if isinstance(row["elapsed_ms"], (int, float))]
    for row in sorted(sortable, key=lambda item: item["elapsed_ms"], reverse=True):
        print(
            f"{row['elapsed_ms']:8.2f} ms | {row['query_count']:4d} q | "
            f"{row['sql_ms']:8.2f} sql ms | {row['status_code']} | {row['name']}"
        )


if __name__ == "__main__":
    main()
