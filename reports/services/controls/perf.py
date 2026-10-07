from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, reset_queries


logger = logging.getLogger("controls.perf")


def controls_perf_enabled() -> bool:
    return bool(getattr(settings, "CONTROLS_PERF_LOGGING", False))


def log_controls_perf(event: str, **fields) -> None:
    if not controls_perf_enabled():
        return
    payload = " ".join(f"{key}={value}" for key, value in sorted(fields.items()) if value is not None)
    logger.info("%s %s", event, payload)


@contextmanager
def profile_controls_block(event: str, **fields):
    if not controls_perf_enabled():
        yield {}
        return

    start = time.perf_counter()
    original_force_debug_cursor = connection.force_debug_cursor
    reset_queries()
    connection.force_debug_cursor = True
    state = {"status": "ok"}
    try:
        yield state
    except Exception as exc:
        state["status"] = "error"
        state["error_type"] = exc.__class__.__name__
        raise
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
        log_controls_perf(
            event,
            duration_ms=duration_ms,
            query_count=query_count,
            slowest_query_ms=round(slowest_query_ms, 2),
            **fields,
            **state,
        )


def controls_scope_fields(*, request=None, entity_id=None, entityfin_id=None, subentity_id=None, **extra) -> dict:
    user = getattr(request, "user", None) if request is not None else None
    return {
        "entity": entity_id,
        "entityfinid": entityfin_id,
        "subentity": subentity_id,
        "user": getattr(user, "id", None),
        **extra,
    }
