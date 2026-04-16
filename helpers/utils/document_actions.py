from __future__ import annotations

from typing import Any, Dict, Optional


def build_document_action_flags(
    *,
    status_value: int,
    draft_status: int,
    confirmed_status: int,
    posted_status: int,
    cancelled_status: int,
    status_name: str,
    allow_edit_confirmed: bool = False,
    allow_unpost_posted: bool = True,
    include_reverse: bool = False,
    include_rebuild_tax_summary: bool = False,
    can_delete: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    is_draft = int(status_value) == int(draft_status)
    is_confirmed = int(status_value) == int(confirmed_status)
    is_posted = int(status_value) == int(posted_status)
    is_cancelled = int(status_value) == int(cancelled_status)

    payload: Dict[str, Any] = {
        "can_edit": (is_draft or (is_confirmed and allow_edit_confirmed)) and not is_cancelled,
        "can_confirm": is_draft,
        "can_post": is_confirmed,
        "can_cancel": is_draft or is_confirmed,
        "can_unpost": is_posted and allow_unpost_posted,
        "status": int(status_value),
        "status_name": status_name,
    }

    if include_reverse:
        payload["can_reverse"] = is_posted and allow_unpost_posted
    if include_rebuild_tax_summary:
        payload["can_rebuild_tax_summary"] = not is_cancelled
    if can_delete is not None:
        payload["can_delete"] = bool(can_delete)
    if extra:
        payload.update(extra)
    return payload
