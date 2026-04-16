from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from entity.models import EntityFinancialYear

from posting.adapters.year_opening import YearOpeningPostingAdapter
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy
from reports.services.controls.year_end_close import build_year_end_close_preview


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return None


def _decimal_str(value) -> str:
    return f"{Decimal(str(value or 0)):.2f}"


def _fy_label_from_dates(start_date: date | None, end_date: date | None, fallback: str = "Opening Year") -> str:
    if not start_date or not end_date:
        return fallback
    return f"FY {start_date.year}-{str(end_date.year)[-2:]}"


def _sum_rows(rows: list[dict]) -> Decimal:
    total = Decimal("0.00")
    for row in rows or []:
        try:
            total += Decimal(str(row.get("amount") or 0))
        except Exception:
            continue
    return total


def _build_opening_history(destination_fy: EntityFinancialYear | None) -> dict[str, object] | None:
    if destination_fy is None:
        return None
    metadata = getattr(destination_fy, "metadata", None) or {}
    opening = metadata.get("opening_carry_forward")
    if not isinstance(opening, dict):
        return None
    return {
        "status": opening.get("status", "generated"),
        "generated_at": opening.get("generated_at"),
        "generated_by": opening.get("generated_by") or {"id": None, "username": None, "name": None},
        "source_year": opening.get("source_year") or {},
        "destination_year": opening.get("destination_year") or {},
        "summary": opening.get("summary") or {},
        "batch": opening.get("batch") or {},
        "sections": opening.get("sections") or [],
        "opening_lines": opening.get("opening_lines") or [],
        "policy_snapshot": opening.get("policy_snapshot") or {},
        "constitution_source": opening.get("constitution_source"),
        "constitution_notes": opening.get("constitution_notes") or [],
        "validation_issues": opening.get("validation_issues") or [],
        "equity_allocation_mode": opening.get("equity_allocation_mode"),
    }


def _resolve_destination_year(entity_id: int, source_fy: EntityFinancialYear | None) -> dict[str, object]:
    if source_fy and source_fy.finendyear:
        source_end = _as_date(source_fy.finendyear)
        planned_start = source_end + timedelta(days=1) if source_end else None
    else:
        planned_start = None

    existing = None
    if source_end := (_as_date(source_fy.finendyear) if source_fy and source_fy.finendyear else None):
        existing = (
            EntityFinancialYear.objects.filter(entity_id=entity_id, finstartyear__date__gte=source_end + timedelta(days=1))
            .order_by("finstartyear", "id")
            .first()
        )

    if existing:
        start_date = _as_date(existing.finstartyear)
        end_date = _as_date(existing.finendyear)
        return {
            "id": existing.id,
            "name": existing.desc or existing.year_code or _fy_label_from_dates(start_date, end_date, fallback=f"FY {existing.id}"),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "status": existing.period_status or "open",
            "is_planned": False,
        }

    if planned_start is not None:
        try:
            planned_end = date(planned_start.year + 1, planned_start.month, planned_start.day) - timedelta(days=1)
        except ValueError:
            planned_end = planned_start + timedelta(days=364)
        return {
            "id": None,
            "name": _fy_label_from_dates(planned_start, planned_end, fallback="Planned Opening Year"),
            "start_date": planned_start.isoformat(),
            "end_date": planned_end.isoformat(),
            "status": "planned",
            "is_planned": True,
        }

    return {
        "id": None,
        "name": "Planned Opening Year",
        "start_date": None,
        "end_date": None,
        "status": "planned",
        "is_planned": True,
    }


def build_opening_preview(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None, reporting_policy: dict | None = None) -> dict:
    close_preview = build_year_end_close_preview(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        reporting_policy=reporting_policy,
    )
    opening_policy = resolve_opening_policy(entity_id)
    source_close_state = close_preview["close_state"]
    opening_balance_preview = close_preview["opening_balance_preview"]

    assets_rows = opening_balance_preview.get("assets") or []
    liabilities_rows = opening_balance_preview.get("liabilities_and_equity") or []
    assets_total = _sum_rows(assets_rows)
    liabilities_total = _sum_rows(liabilities_rows)
    difference = liabilities_total - assets_total

    source_year = {
        "id": close_preview.get("entityfin_id"),
        "name": close_preview.get("entityfin_name") or "Financial Year",
        "status": source_close_state.get("period_status") or "open",
        "is_closed": bool(source_close_state.get("is_year_closed")),
        "is_audit_closed": bool(source_close_state.get("is_audit_closed")),
        "books_locked_until": source_close_state.get("books_locked_until"),
        "gst_locked_until": source_close_state.get("gst_locked_until"),
        "inventory_locked_until": source_close_state.get("inventory_locked_until"),
        "ap_ar_locked_until": source_close_state.get("ap_ar_locked_until"),
    }

    source_fy_obj = EntityFinancialYear.objects.filter(pk=close_preview.get("entityfin_id"), entity_id=entity_id).first()
    destination_year = _resolve_destination_year(entity_id, source_fy_obj)

    carry_forward = opening_policy.get("carry_forward") or {}
    reset = opening_policy.get("reset") or {}
    enabled_carry = [key for key, value in carry_forward.items() if value]
    enabled_reset = [key for key, value in reset.items() if value]

    equity_context = {}
    if source_close_state.get("is_year_closed") or opening_policy.get("require_closed_source_year", True):
        try:
            adapter = YearOpeningPostingAdapter(entity_id=entity_id, opening_policy=opening_policy)
            equity_context = adapter.build_context(
                net_profit=Decimal(str(opening_balance_preview.get("summary", {}).get("net_profit_brought_to_equity") or 0))
            )
        except Exception:
            equity_context = {}
    constitution = equity_context.get("constitution") or {}
    validation_issues = equity_context.get("validation_issues") or []
    constitution_is_valid = bool(constitution.get("is_valid", True)) and not any(
        issue.get("severity") == "error" for issue in validation_issues
    )

    preview_ready = bool(assets_total or liabilities_total)
    destination_year_obj = None
    if destination_year.get("id"):
        destination_year_obj = EntityFinancialYear.objects.filter(pk=destination_year.get("id"), entity_id=entity_id).first()
    opening_history = _build_opening_history(destination_year_obj)
    generation_ready = bool(source_close_state.get("is_year_closed")) if opening_policy.get("require_closed_source_year", True) else True
    can_generate = bool(preview_ready and generation_ready and constitution_is_valid and not opening_history)

    checks = [
        {
            "key": "policy_loaded",
            "label": "Opening policy resolved",
            "status": "pass",
            "detail": "Entity policy is being read from FinancialSettings.reporting_policy.",
            "tone": "available",
        },
        {
            "key": "source_closed",
            "label": "Source year closed",
            "status": "pass" if source_close_state.get("is_year_closed") else "warning",
            "detail": "The source year is already closed and ready for carry-forward." if source_close_state.get("is_year_closed") else "Preview is based on an open year; opening generation will wait for close.",
            "tone": "available" if source_close_state.get("is_year_closed") else "warning",
        },
        {
            "key": "destination_year",
            "label": "Destination year",
            "status": "pass" if not destination_year.get("is_planned") else "info",
            "detail": f"Opening target resolved as {destination_year.get('name')}." if not destination_year.get("is_planned") else "No next FY record found yet; using a planned destination year.",
            "tone": "neutral",
        },
        {
            "key": "preview_ready",
            "label": "Carry-forward snapshot",
            "status": "pass" if preview_ready else "warning",
            "detail": "Opening balances were derived from the closing preview snapshot." if preview_ready else "No opening balances were returned for the current scope.",
            "tone": "accent" if preview_ready else "warning",
        },
        {
            "key": "generation_ready",
            "label": "Generation readiness",
            "status": "pass" if generation_ready and preview_ready and constitution_is_valid else "warning",
            "detail": (
                "The entity is ready for opening generation."
                if generation_ready and preview_ready and constitution_is_valid
                else "Opening generation will require the source year to be closed, the carry-forward snapshot to be available, and constitution validation to pass."
            ),
            "tone": "available" if generation_ready and preview_ready and constitution_is_valid else "warning",
        },
    ]

    summary_cards = [
        {"label": "Opening assets", "value": _decimal_str(assets_total), "note": "Balance sheet assets to carry forward", "tone": "accent"},
        {"label": "Opening liabilities", "value": _decimal_str(liabilities_total), "note": "Balance sheet liabilities and equity to carry forward", "tone": "neutral"},
        {"label": "Difference", "value": _decimal_str(difference), "note": "Should trend to zero after close completion", "tone": "warning" if difference else "accent"},
        {"label": "Enabled carry-forward", "value": len(enabled_carry), "note": "Policy buckets switched on for this entity", "tone": "neutral"},
        {"label": "Constitution source", "value": constitution.get("constitution_source") or "ownership rows", "note": "What determined the opening allocation rule", "tone": "neutral"},
        {"label": "Validation issues", "value": len(validation_issues), "note": "Blocking or caution items carried into opening preview", "tone": "warning" if validation_issues else "neutral"},
    ]

    return {
        "report_code": "opening_preview",
        "report_name": "Opening Carry Forward Preview",
        "report_eyebrow": "Financial Controls",
        "entity_id": entity_id,
        "entity_name": close_preview["entity_name"],
        "entityfin_id": close_preview["entityfin_id"],
        "entityfin_name": close_preview["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": close_preview["subentity_name"],
        "generated_at": close_preview["generated_at"],
        "opening_policy": opening_policy,
        "opening_policy_summary": summarize_opening_policy(opening_policy),
        "source_year": source_year,
        "destination_year": destination_year,
        "summary_cards": summary_cards,
        "checks": checks,
        "carry_forward_rules": [
            {"label": key.replace("_", " "), "enabled": bool(value)}
            for key, value in carry_forward.items()
        ],
        "reset_rules": [
            {"label": key.replace("_", " "), "enabled": bool(value)}
            for key, value in reset.items()
        ],
        "opening_balance_preview": opening_balance_preview,
        "opening_history": opening_history,
        "equity_targets": equity_context.get("equity_targets") or [],
        "missing_equity_codes": equity_context.get("missing_equity_codes") or [],
        "equity_allocation_mode": equity_context.get("equity_allocation_mode"),
        "constitution": constitution,
        "validation_issues": validation_issues,
        "book_boundary": close_preview["book_boundary"],
        "warnings": close_preview.get("warnings") or [],
        "next_steps": [
            "Validate the source year close status",
            "Confirm the destination FY",
            "Use Phase 3 to generate the opening batch",
        ],
        "actions": {
            "can_preview": True,
            "can_print": True,
            "can_refresh": True,
            "can_generate": can_generate,
        },
        "preview_state": "generated" if opening_history else "ready" if can_generate else "review" if preview_ready and constitution_is_valid else "blocked",
    }
