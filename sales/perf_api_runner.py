import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def _load_payload(payload_raw: str):
    if not payload_raw:
        return None
    try:
        return json.loads(payload_raw)
    except json.JSONDecodeError:
        with open(payload_raw, "r", encoding="utf-8") as f:
            return json.load(f)


def _call_once(session, method, url, headers, payload, timeout):
    start = time.perf_counter()
    try:
        resp = session.request(method=method, url=url, headers=headers, json=payload, timeout=timeout)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": 200 <= resp.status_code < 300, "status": resp.status_code, "ms": elapsed_ms}
    except requests.RequestException:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "status": 0, "ms": elapsed_ms}


def _percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * p
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac


def run_perf(base_url, endpoint, method, token, payload, requests_count, concurrency, timeout):
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    outcomes = []
    started_at = time.perf_counter()

    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(_call_once, session, method, url, headers, payload, timeout)
                for _ in range(requests_count)
            ]
            for future in as_completed(futures):
                outcomes.append(future.result())

    total_sec = max(time.perf_counter() - started_at, 0.001)
    latencies = sorted(x["ms"] for x in outcomes)
    ok_count = sum(1 for x in outcomes if x["ok"])
    err_count = len(outcomes) - ok_count

    report = {
        "url": url,
        "method": method,
        "requests": len(outcomes),
        "concurrency": concurrency,
        "success_count": ok_count,
        "error_count": err_count,
        "error_rate_pct": round((err_count / len(outcomes)) * 100, 2) if outcomes else 0.0,
        "throughput_rps": round(len(outcomes) / total_sec, 2),
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else 0.0,
            "avg": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p50": round(_percentile(latencies, 0.50), 2) if latencies else 0.0,
            "p95": round(_percentile(latencies, 0.95), 2) if latencies else 0.0,
            "p99": round(_percentile(latencies, 0.99), 2) if latencies else 0.0,
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Simple performance runner for Sale module APIs.")
    parser.add_argument("--base-url", required=True, help="Example: http://127.0.0.1:8000")
    parser.add_argument("--endpoint", required=True, help="Example: /api/sales/choices/?entity_id=1")
    parser.add_argument("--method", default="GET", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    parser.add_argument("--token", default="", help="Bearer token value only.")
    parser.add_argument("--payload", default="", help="Inline JSON or path to JSON file.")
    parser.add_argument("--requests", type=int, default=100, help="Total request count.")
    parser.add_argument("--concurrency", type=int, default=10, help="Parallel worker count.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")

    args = parser.parse_args()
    payload = _load_payload(args.payload)

    result = run_perf(
        base_url=args.base_url,
        endpoint=args.endpoint,
        method=args.method,
        token=args.token,
        payload=payload,
        requests_count=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
