from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

SALES_META_NAMESPACES = [
    "sales.invoice_form_meta",
    "sales.settings_meta",
]

PURCHASE_META_NAMESPACES = [
    "purchase.invoice_form_meta",
    "purchase.settings_meta",
]

CACHE_EVENT_HIT = "hit"
CACHE_EVENT_MISS = "miss"
CACHE_EVENT_STORE = "store"
CACHE_EVENT_DISABLED = "disabled"
CACHE_EVENT_INVALIDATE = "invalidate"


def emit_meta_cache_event(event: str, **details: Any) -> None:
    if not getattr(settings, "META_CACHE_OBSERVABILITY_ENABLED", False):
        return
    level_name = str(getattr(settings, "META_CACHE_LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.log(level, "meta_cache.%s", event, extra={"meta_cache": {"event": event, **details}})


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def build_meta_cache_key(namespace: str, *, entity_id: int, entityfinid_id: int | None, subentity_id: int | None, extra: dict | None = None) -> str:
    payload = {
        "namespace": namespace,
        "entity_id": int(entity_id),
        "entityfinid_id": int(entityfinid_id) if entityfinid_id is not None else None,
        "subentity_id": int(subentity_id) if subentity_id is not None else None,
        "extra": extra or {},
    }
    stable = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    digest = hashlib.sha1(stable.encode("utf-8")).hexdigest()
    return f"meta:{namespace}:{digest}"


def get_or_set_meta_cache(key: str, builder: Callable[[], Any], *, timeout: int) -> Any:
    cached = cache.get(key)
    if cached is not None:
        emit_meta_cache_event(CACHE_EVENT_HIT, key=key, timeout=timeout)
        return cached
    emit_meta_cache_event(CACHE_EVENT_MISS, key=key, timeout=timeout)
    payload = builder()
    cache.set(key, payload, timeout=timeout)
    emit_meta_cache_event(CACHE_EVENT_STORE, key=key, timeout=timeout)
    return payload


def _namespace_version_key(namespace: str) -> str:
    return f"meta:nsver:{namespace}"


def get_meta_namespace_version(namespace: str, *, base_version: str = "1") -> str:
    value = cache.get(_namespace_version_key(namespace), 0)
    try:
        counter = int(value or 0)
    except (TypeError, ValueError):
        counter = 0
    return f"{base_version}.{counter}"


def bump_meta_namespace_version(namespace: str) -> int:
    key = _namespace_version_key(namespace)
    try:
        next_value = int(cache.incr(key))
    except Exception:
        # Key may not exist yet or backend may not support incr on missing key.
        current = cache.get(key, 0)
        try:
            next_value = int(current or 0) + 1
        except (TypeError, ValueError):
            next_value = 1
        cache.set(key, next_value, timeout=None)
    emit_meta_cache_event(CACHE_EVENT_INVALIDATE, namespace=namespace, version=next_value)
    return next_value


def bump_meta_namespaces(namespaces: list[str]) -> None:
    for namespace in namespaces:
        bump_meta_namespace_version(namespace)
