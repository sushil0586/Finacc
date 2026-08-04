from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, reset_queries


logger = logging.getLogger("payables.perf")


def payables_perf_enabled() -> bool:
    return bool(getattr(settings, "PAYABLES_PERF_LOGGING", False))


def log_payables_perf(event: str, **fields) -> None:
    if not payables_perf_enabled():
        return
    payload = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    logger.info("%s %s", event, payload)


@contextmanager
def profile_payables_block(event: str, **fields):
    if not payables_perf_enabled():
        yield None
        return

    start = time.perf_counter()
    original_force_debug_cursor = connection.force_debug_cursor
    reset_queries()
    connection.force_debug_cursor = True
    state = {}
    try:
        yield state
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        query_count = len(connection.queries)
        slowest_query_ms = 0.0
        for query in connection.queries:
            try:
                slowest_query_ms = max(slowest_query_ms, float(query.get("time", 0)) * 1000)
            except (TypeError, ValueError):
                continue
        connection.force_debug_cursor = original_force_debug_cursor
        log_payables_perf(
            event,
            duration_ms=duration_ms,
            query_count=query_count,
            slowest_query_ms=round(slowest_query_ms, 2),
            **fields,
            **state,
        )
