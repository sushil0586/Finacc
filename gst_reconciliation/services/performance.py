from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger("gst_reconciliation.performance")


@dataclass(frozen=True)
class TimedResult:
    value: Any
    duration_ms: float
    cache_hit: bool = False


def is_perf_logging_enabled() -> bool:
    return bool(getattr(settings, "GST_RECON_PERF_LOGGING", False))


def is_perf_cache_enabled() -> bool:
    return bool(getattr(settings, "GST_RECON_CACHE_ENABLED", True))


def default_cache_ttl() -> int:
    return int(getattr(settings, "GST_RECON_CACHE_TTL_SECONDS", 60))


@contextmanager
def timed_block(event: str, **metadata: Any):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if is_perf_logging_enabled():
            logger.info("gst_reconciliation.%s", event, extra={"gst_reconciliation": {"duration_ms": duration_ms, **metadata}})


def timed_call(event: str, builder: Callable[[], Any], **metadata: Any) -> TimedResult:
    start = time.perf_counter()
    value = builder()
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    if is_perf_logging_enabled():
        logger.info("gst_reconciliation.%s", event, extra={"gst_reconciliation": {"duration_ms": duration_ms, **metadata}})
    return TimedResult(value=value, duration_ms=duration_ms)


def run_cache_key(*, run, suffix: str) -> str:
    version = getattr(run, "updated_at", None)
    version_key = int(version.timestamp()) if version else 0
    return f"gst-recon:run:{run.id}:{suffix}:v{version_key}"


def cached_run_computation(*, run, suffix: str, builder: Callable[[], Any], ttl: int | None = None, log_event: str | None = None) -> TimedResult:
    if not is_perf_cache_enabled():
        result = timed_call(log_event or suffix, builder, run_id=run.id, cache_hit=False)
        return result
    key = run_cache_key(run=run, suffix=suffix)
    cached = cache.get(key)
    if cached is not None:
        if log_event and is_perf_logging_enabled():
            logger.info(
                "gst_reconciliation.%s",
                log_event,
                extra={"gst_reconciliation": {"run_id": run.id, "cache_hit": True, "duration_ms": 0.0}},
            )
        return TimedResult(value=cached, duration_ms=0.0, cache_hit=True)
    result = timed_call(log_event or suffix, builder, run_id=run.id, cache_hit=False)
    cache.set(key, result.value, timeout=ttl or default_cache_ttl())
    return result


def optional_async_matching_enabled() -> bool:
    return bool(getattr(settings, "GST_RECON_ASYNC_MATCH_ENABLED", False))
