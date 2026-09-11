from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar, Token


_CORRELATION_ID = ContextVar("capital_distribution_correlation_id", default="")
_STARTED_AT = ContextVar("capital_distribution_started_at", default=None)
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def normalize_correlation_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if _SAFE_CORRELATION_ID.fullmatch(candidate) else uuid.uuid4().hex


def bind_operation_context(value: str | None) -> tuple[Token, Token]:
    return (
        _CORRELATION_ID.set(normalize_correlation_id(value)),
        _STARTED_AT.set(time.perf_counter()),
    )


def reset_operation_context(tokens: tuple[Token, Token]) -> None:
    correlation_token, started_token = tokens
    _STARTED_AT.reset(started_token)
    _CORRELATION_ID.reset(correlation_token)


def current_correlation_id() -> str:
    return _CORRELATION_ID.get() or uuid.uuid4().hex


def operation_metadata(**extra) -> dict:
    metadata = dict(extra)
    started_at = _STARTED_AT.get()
    if started_at is not None:
        metadata["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 3)
    return metadata
