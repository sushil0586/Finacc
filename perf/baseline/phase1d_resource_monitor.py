#!/usr/bin/env python3
"""Collect local Finacc process and PostgreSQL telemetry during Locust runs."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FA.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402


APP_PATTERNS = ("gunicorn FA.wsgi",)
LOAD_PATTERNS = ("locust",)


def _pgrep(pattern: str) -> list[int]:
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True)
    except subprocess.CalledProcessError:
        return []
    return [int(line) for line in out.splitlines() if line.strip().isdigit()]


def _ps_rows(pids: set[int], role: str) -> list[dict[str, object]]:
    if not pids:
        return []
    cmd = ["ps", "-o", "pid=,ppid=,%cpu=,%mem=,rss=,state=,command=", "-p", ",".join(str(pid) for pid in sorted(pids))]
    try:
        out = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError:
        return []
    rows: list[dict[str, object]] = []
    for line in out.splitlines():
        parts = line.strip().split(None, 6)
        if len(parts) < 7:
            continue
        pid, ppid, cpu, mem, rss, state, command = parts
        rows.append(
            {
                "role": role,
                "pid": pid,
                "ppid": ppid,
                "cpu_pct": cpu,
                "mem_pct": mem,
                "rss_kb": rss,
                "state": state,
                "command": command[:180],
            }
        )
    return rows


def _process_rows() -> list[dict[str, object]]:
    app_pids: set[int] = set()
    load_pids: set[int] = set()
    for pattern in APP_PATTERNS:
        app_pids.update(_pgrep(pattern))
    for pattern in LOAD_PATTERNS:
        load_pids.update(pid for pid in _pgrep(pattern) if pid not in app_pids)
    rows = _ps_rows(app_pids, "app")
    rows.extend(_ps_rows(load_pids, "loadgen"))
    return rows


def _postgres_snapshot() -> dict[str, object]:
    data: dict[str, object] = {
        "pg_total_connections": "",
        "pg_active_connections": "",
        "pg_idle_in_txn": "",
        "pg_waiting_connections": "",
        "pg_oldest_active_seconds": "",
        "pg_locks_not_granted": "",
        "pg_database_conflicts": "",
        "pg_deadlocks": "",
        "pg_blks_read": "",
        "pg_blks_hit": "",
        "pg_temp_bytes": "",
    }
    if connection.vendor != "postgresql":
        return data
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_connections,
                COUNT(*) FILTER (WHERE state = 'active') AS active_connections,
                COUNT(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_txn,
                COUNT(*) FILTER (WHERE wait_event IS NOT NULL) AS waiting_connections,
                COALESCE(MAX(EXTRACT(EPOCH FROM now() - query_start)) FILTER (WHERE state = 'active'), 0) AS oldest_active_seconds
            FROM pg_stat_activity
            WHERE datname = current_database()
            """
        )
        total, active, idle_txn, waiting, oldest = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM pg_locks WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database()) AND NOT granted")
        not_granted = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT conflicts, deadlocks, blks_read, blks_hit, temp_bytes
            FROM pg_stat_database
            WHERE datname = current_database()
            """
        )
        db_stats = cursor.fetchone() or (0, 0, 0, 0, 0)
    data.update(
        {
            "pg_total_connections": total,
            "pg_active_connections": active,
            "pg_idle_in_txn": idle_txn,
            "pg_waiting_connections": waiting,
            "pg_oldest_active_seconds": round(float(oldest or 0), 3),
            "pg_locks_not_granted": not_granted,
            "pg_database_conflicts": db_stats[0],
            "pg_deadlocks": db_stats[1],
            "pg_blks_read": db_stats[2],
            "pg_blks_hit": db_stats[3],
            "pg_temp_bytes": db_stats[4],
        }
    )
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp",
        "role",
        "pid",
        "ppid",
        "cpu_pct",
        "mem_pct",
        "rss_kb",
        "state",
        "command",
        "pg_total_connections",
        "pg_active_connections",
        "pg_idle_in_txn",
        "pg_waiting_connections",
        "pg_oldest_active_seconds",
        "pg_locks_not_granted",
        "pg_database_conflicts",
        "pg_deadlocks",
        "pg_blks_read",
        "pg_blks_hit",
        "pg_temp_bytes",
    ]
    deadline = time.monotonic() + args.duration
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        while time.monotonic() < deadline:
            ts = datetime.now(timezone.utc).isoformat()
            pg = _postgres_snapshot()
            process_rows = _process_rows() or [{"role": "none", "pid": "", "ppid": "", "cpu_pct": "", "mem_pct": "", "rss_kb": "", "state": "", "command": ""}]
            for proc in process_rows:
                writer.writerow({"timestamp": ts, **proc, **pg})
            fh.flush()
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
