from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from typing import TypeVar

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


T = TypeVar("T")
REPORT_RESPONSE_CACHE_GENERATION_KEY = "report-response:generation"


def report_response_cache_enabled() -> bool:
    return int(getattr(settings, "REPORT_RESPONSE_CACHE_TTL_SECONDS", 0) or 0) > 0


def current_report_response_cache_generation() -> str:
    generation = cache.get(REPORT_RESPONSE_CACHE_GENERATION_KEY)
    if generation is None:
        generation = "1"
        cache.set(REPORT_RESPONSE_CACHE_GENERATION_KEY, generation, None)
    return str(generation)


def bump_report_response_cache_generation(*, reason: str | None = None) -> str:
    """Invalidate report response payloads without scanning/deleting cache keys."""
    generation = timezone.now().strftime("%Y%m%d%H%M%S%f")
    cache.set(REPORT_RESPONSE_CACHE_GENERATION_KEY, generation, None)
    return generation


def _request_cache_fingerprint(request, *, report_code: str, entity_id: int | None) -> str:
    query_items = sorted((key, request.query_params.getlist(key)) for key in request.query_params.keys())
    payload = {
        "version": getattr(settings, "REPORT_RESPONSE_CACHE_VERSION", "v1"),
        "generation": current_report_response_cache_generation(),
        "report_code": report_code,
        "user_id": getattr(request.user, "id", None),
        "entity_id": entity_id,
        "path": request.path,
        "query": query_items,
    }
    raw = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_build_report_response(
    request,
    *,
    report_code: str,
    entity_id: int | None,
    builder: Callable[[], T],
) -> tuple[T, bool]:
    """Cache already-authorized read-only report payloads for a short, configured TTL.

    Call this only after scope, subscription, and RBAC checks have passed. The cache
    key includes user, entity, path, and full query string to avoid cross-tenant or
    cross-user reuse. Disabled by default unless REPORT_RESPONSE_CACHE_TTL_SECONDS > 0.
    """
    ttl = int(getattr(settings, "REPORT_RESPONSE_CACHE_TTL_SECONDS", 0) or 0)
    if ttl <= 0 or request.method != "GET":
        return builder(), False

    key = f"report-response:{_request_cache_fingerprint(request, report_code=report_code, entity_id=entity_id)}"
    cached = cache.get(key)
    if cached is not None:
        return deepcopy(cached), True

    payload = builder()
    cache.set(key, deepcopy(payload), ttl)
    return payload, False
