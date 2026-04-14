from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import FinancialSettings
from posting.models import Entry, EntryStatus
from reports.services.financial.statements import build_balance_sheet, build_profit_and_loss


def _safe_label(value, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _resolve_scope(entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None) -> dict[str, str]:
    entity = Entity.objects.filter(pk=entity_id).only("id", "entityname", "trade_name", "short_name").first()
    entity_fin = (
        EntityFinancialYear.objects.filter(pk=entityfin_id, entity_id=entity_id).only("id", "desc", "year_code", "finstartyear", "finendyear", "period_status", "is_year_closed", "is_audit_closed").first()
        if entityfin_id
        else None
    )
    if entity_fin is None:
        entity_fin = (
            EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-finstartyear")
            .only("id", "desc", "year_code", "finstartyear", "finendyear", "period_status", "is_year_closed", "is_audit_closed")
            .first()
        )
    subentity = (
        SubEntity.objects.filter(pk=subentity_id, entity_id=entity_id).only("id", "subentityname").first()
        if subentity_id
        else None
    )

    entity_name = _safe_label(entity.trade_name or entity.short_name or entity.entityname if entity else None, f"Entity {entity_id}")
    entityfin_name = _safe_label(entity_fin.desc if entity_fin else None, f"FY {entity_fin.id}" if entity_fin else "Financial Year")
    subentity_name = _safe_label(subentity.subentityname if subentity else None, "All subentities")

    return {
        "entity_name": entity_name,
        "entityfin_name": entityfin_name,
        "subentity_name": subentity_name,
        "entityfin_status": getattr(entity_fin, "period_status", None) or "open",
        "is_year_closed": bool(getattr(entity_fin, "is_year_closed", False)),
        "is_audit_closed": bool(getattr(entity_fin, "is_audit_closed", False)),
        "books_locked_until": getattr(entity_fin, "books_locked_until", None),
        "gst_locked_until": getattr(entity_fin, "gst_locked_until", None),
        "inventory_locked_until": getattr(entity_fin, "inventory_locked_until", None),
        "ap_ar_locked_until": getattr(entity_fin, "ap_ar_locked_until", None),
        "entityfin_object": entity_fin,
    }


def _decimal_str(value) -> str:
    return f"{Decimal(str(value or 0)):.2f}"


def _as_date(value):
    if not value:
        return None
    if hasattr(value, "date"):
        return value.date()
    return value


def _build_checks(*, scope: dict[str, str], draft_count: int, balance_difference: Decimal, net_profit: Decimal) -> list[dict[str, object]]:
    checks = []
    checks.append(
        {
            "key": "year_not_closed",
            "label": "Financial year is open",
            "status": "fail" if scope["is_year_closed"] else "pass",
            "detail": "This year is already marked as closed." if scope["is_year_closed"] else "Year is open for review and preview.",
            "tone": "blocked" if scope["is_year_closed"] else "available",
        }
    )
    checks.append(
        {
            "key": "drafts",
            "label": "Draft postings",
            "status": "warning" if draft_count else "pass",
            "detail": f"{draft_count} draft entry/entries are still pending." if draft_count else "No draft postings were found for the selected scope.",
            "tone": "warning" if draft_count else "available",
        }
    )
    checks.append(
        {
            "key": "balance_sheet",
            "label": "Balance sheet difference",
            "status": "pass" if balance_difference == 0 else "warning",
            "detail": f"Balance difference is {_decimal_str(abs(balance_difference))}." if balance_difference else "Balance sheet is aligned.",
            "tone": "available" if balance_difference == 0 else "warning",
        }
    )
    checks.append(
        {
            "key": "profit_transfer",
            "label": "Profit transfer preview",
            "status": "pass",
            "detail": (
                "Current year shows a profit that will flow to equity."
                if net_profit > 0
                else "Current year shows a loss that will flow to equity."
                if net_profit < 0
                else "Current year is break even."
            ),
            "tone": "accent",
        }
    )
    checks.append(
        {
            "key": "close_policy",
            "label": "Opening balance policy",
            "status": "pass",
            "detail": f"Opening balances are currently editable mode '{scope.get('opening_balance_edit_mode')}'.",
            "tone": "neutral",
        }
    )
    return checks


def _flatten_rows(rows: list[dict], *, section: str) -> list[dict[str, object]]:
    flat: list[dict[str, object]] = []
    for row in rows or []:
        flat.append(
            {
                "section": section,
                "label": row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name"),
                "amount": _decimal_str(row.get("amount_decimal") or row.get("amount") or row.get("closing_value") or 0),
                "can_drilldown": bool(row.get("can_drilldown", False)),
                "drilldown_target": row.get("drilldown_target"),
                "depth": row.get("depth", 0),
                "children": len(row.get("children") or []),
            }
        )
        for child in row.get("children") or []:
            flat.extend(_flatten_rows([child], section=section))
    return flat


def _compute_snapshot(entity_id: int, entityfin_id: int | None, subentity_id: int | None, reporting_policy: dict | None) -> dict[str, object]:
    fy = None
    if entityfin_id:
        fy = EntityFinancialYear.objects.filter(pk=entityfin_id, entity_id=entity_id).first()
    if fy is None:
        fy = EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True).order_by("-finstartyear").first()

    if fy and fy.finstartyear and fy.finendyear:
        from_date = _as_date(fy.finstartyear)
        to_date = _as_date(fy.finendyear)
    else:
        from_date = None
        to_date = None

    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("opening_balance_edit_mode", "reporting_policy").first()
    settings_policy = (settings.reporting_policy if settings else {}) or {}
    merged_policy = {**settings_policy, **(reporting_policy or {})}

    draft_count = 0
    posted_count = 0
    reversed_count = 0
    total_entries = 0
    first_posting_date = None
    last_posting_date = None
    entries = Entry.objects.filter(entity_id=entity_id)
    if fy:
        entries = entries.filter(entityfin_id=fy.id)
    if subentity_id is not None:
        entries = entries.filter(subentity_id=subentity_id)

    total_entries = entries.count()
    draft_count = entries.filter(status=EntryStatus.DRAFT).count()
    posted_count = entries.filter(status=EntryStatus.POSTED).count()
    reversed_count = entries.filter(status=EntryStatus.REVERSED).count()
    first_obj = entries.order_by("posting_date", "id").only("posting_date").first()
    last_obj = entries.order_by("-posting_date", "-id").only("posting_date").first()
    if first_obj:
        first_posting_date = first_obj.posting_date
    if last_obj:
        last_posting_date = last_obj.posting_date

    pnl = {}
    pnl_error = None
    bs = {}
    bs_error = None
    if fy and from_date and to_date:
        try:
            pnl = build_profit_and_loss(
                entity_id=entity_id,
                entityfin_id=fy.id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=to_date,
                group_by="accounthead",
                include_zero_balances=False,
                search=None,
                sort_by=None,
                sort_order="asc",
                page=1,
                page_size=100,
                period_by=None,
                stock_valuation_mode="auto",
                stock_valuation_method="fifo",
                view_type="summary",
                posted_only=True,
                hide_zero_rows=True,
                reporting_policy=merged_policy,
            )
        except Exception as exc:  # pragma: no cover - defensive
            pnl_error = str(exc)
            pnl = {}
        try:
            bs = build_balance_sheet(
                entity_id=entity_id,
                entityfin_id=fy.id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=to_date,
                group_by="accounthead",
                view_type="summary",
                posted_only=True,
                hide_zero_rows=True,
                include_zero_balances=False,
                account_group="accounthead",
                ledger_ids=None,
                search=None,
                sort_by=None,
                sort_order="asc",
                page=1,
                page_size=100,
                period_by=None,
                stock_valuation_mode="auto",
                stock_valuation_method="fifo",
                reporting_policy=merged_policy,
            )
        except Exception as exc:  # pragma: no cover - defensive
            bs_error = str(exc)
            bs = {}

    net_profit = Decimal(str(((pnl.get("totals") or {}).get("net_profit")) or 0))
    income_total = Decimal(str(((pnl.get("totals") or {}).get("income")) or 0))
    expense_total = Decimal(str(((pnl.get("totals") or {}).get("expense")) or 0))
    assets_total = Decimal(str(((bs.get("totals") or {}).get("assets")) or 0))
    liabilities_total = Decimal(str(((bs.get("totals") or {}).get("liabilities_and_equity")) or 0))
    balance_difference = assets_total - liabilities_total

    checks = _build_checks(
        scope={
            "is_year_closed": bool(getattr(fy, "is_year_closed", False)),
            "opening_balance_edit_mode": getattr(settings, "opening_balance_edit_mode", "before_posting"),
        },
        draft_count=draft_count,
        balance_difference=balance_difference,
        net_profit=net_profit,
    )
    pass_count = sum(1 for item in checks if item["status"] == "pass")
    warning_count = sum(1 for item in checks if item["status"] == "warning")
    fail_count = sum(1 for item in checks if item["status"] == "fail")

    close_state = {
        "period_status": getattr(fy, "period_status", "open"),
        "is_year_closed": bool(getattr(fy, "is_year_closed", False)),
        "is_audit_closed": bool(getattr(fy, "is_audit_closed", False)),
        "books_locked_until": getattr(fy, "books_locked_until", None),
        "gst_locked_until": getattr(fy, "gst_locked_until", None),
        "inventory_locked_until": getattr(fy, "inventory_locked_until", None),
        "ap_ar_locked_until": getattr(fy, "ap_ar_locked_until", None),
        "opening_balance_edit_mode": getattr(settings, "opening_balance_edit_mode", "before_posting"),
        "readiness_state": "blocked" if fail_count else "review" if warning_count else "ready",
    }

    return {
        "financial_year": fy,
        "from_date": from_date,
        "to_date": to_date,
        "first_posting_date": first_posting_date,
        "last_posting_date": last_posting_date,
        "settings": settings,
        "pnl": pnl,
        "bs": bs,
        "pnl_error": pnl_error,
        "bs_error": bs_error,
        "close_state": close_state,
        "checks": checks,
        "summary": {
            "total_entries": total_entries,
            "draft_entries": draft_count,
            "posted_entries": posted_count,
            "reversed_entries": reversed_count,
            "income_total": income_total,
            "expense_total": expense_total,
            "net_profit": net_profit,
            "assets_total": assets_total,
            "liabilities_total": liabilities_total,
            "balance_difference": balance_difference,
        },
    }


def _build_close_metadata(*, entity_id: int, fy: EntityFinancialYear, subentity_id: int | None, snapshot: dict, preview: dict, executed_by) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    close_date = _as_date(fy.finendyear) or now.date()
    user_id = getattr(executed_by, "id", None)
    username = getattr(executed_by, "get_username", lambda: None)()
    full_name = " ".join(part for part in [getattr(executed_by, "first_name", ""), getattr(executed_by, "last_name", "")] if part).strip() or None

    return {
        "status": "closed",
        "closed_at": now.isoformat(),
        "closed_on": close_date.isoformat(),
        "closed_by": {
            "id": user_id,
            "username": username,
            "name": full_name,
        },
        "scope": {
            "entity_id": entity_id,
            "entityfin_id": fy.id,
            "subentity_id": subentity_id,
            "entity_name": preview["entity_name"],
            "entityfin_name": preview["entityfin_name"],
            "subentity_name": preview["subentity_name"],
        },
        "summary": {
            "entries": snapshot["summary"]["total_entries"],
            "draft_entries": snapshot["summary"]["draft_entries"],
            "posted_entries": snapshot["summary"]["posted_entries"],
            "reversed_entries": snapshot["summary"]["reversed_entries"],
            "income_total": _decimal_str(snapshot["summary"]["income_total"]),
            "expense_total": _decimal_str(snapshot["summary"]["expense_total"]),
            "net_profit": _decimal_str(snapshot["summary"]["net_profit"]),
            "assets_total": _decimal_str(snapshot["summary"]["assets_total"]),
            "liabilities_total": _decimal_str(snapshot["summary"]["liabilities_total"]),
            "balance_difference": _decimal_str(snapshot["summary"]["balance_difference"]),
        },
        "checks": preview["checks"],
        "book_boundary": preview["book_boundary"],
        "carry_forward_buckets": preview["carry_forward_buckets"],
        "carry_forward_notes": preview["carry_forward_notes"],
        "closing_entries": preview["closing_entries"],
        "source_summary": preview["source_summary"],
    }


def _apply_close_stamp(fy: EntityFinancialYear, close_metadata: dict[str, object]) -> None:
    close_date = datetime.fromisoformat(close_metadata["closed_at"]).date()
    metadata = dict(getattr(fy, "metadata", None) or {})
    metadata["year_end_close"] = close_metadata
    fy.metadata = metadata
    fy.period_status = EntityFinancialYear.PeriodStatus.CLOSED
    fy.is_year_closed = True
    fy.books_locked_until = close_date
    fy.gst_locked_until = close_date
    fy.inventory_locked_until = close_date
    fy.ap_ar_locked_until = close_date
    fy.save(
        update_fields=[
            "metadata",
            "period_status",
            "is_year_closed",
            "books_locked_until",
            "gst_locked_until",
            "inventory_locked_until",
            "ap_ar_locked_until",
        ]
    )


def _build_close_history(fy: EntityFinancialYear | None) -> dict[str, object] | None:
    if fy is None:
        return None
    metadata = getattr(fy, "metadata", None) or {}
    history = metadata.get("year_end_close")
    if not isinstance(history, dict):
        return None
    return {
        "status": history.get("status", "closed"),
        "closed_at": history.get("closed_at"),
        "closed_on": history.get("closed_on"),
        "closed_by": history.get("closed_by") or {"id": None, "username": None, "name": None},
        "scope": history.get("scope") or {},
        "summary": history.get("summary") or {},
        "checks": history.get("checks") or [],
        "book_boundary": history.get("book_boundary") or {},
        "carry_forward_buckets": history.get("carry_forward_buckets") or [],
        "carry_forward_notes": history.get("carry_forward_notes") or [],
        "closing_entries": history.get("closing_entries") or [],
        "source_summary": history.get("source_summary") or [],
    }


def build_year_end_close_preview(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None, reporting_policy: dict | None = None) -> dict:
    scope = _resolve_scope(entity_id, entityfin_id, subentity_id)
    snapshot = _compute_snapshot(entity_id, entityfin_id, subentity_id, reporting_policy)
    fy = snapshot["financial_year"]
    summary = snapshot["summary"]
    balance_difference = summary["balance_difference"]
    net_profit = summary["net_profit"]

    carry_forward_buckets = [
        {
            "key": "permanent_accounts",
            "title": "Permanent accounts",
            "value": 6,
            "note": "Assets, liabilities, and equity roll forward to the new year.",
        },
        {
            "key": "temporary_accounts",
            "title": "Temporary accounts",
            "value": 3,
            "note": "Revenue, expenses, and trading movements reset through the close entry.",
        },
        {
            "key": "opening_balance_batch",
            "title": "Opening balance batch",
            "value": 1,
            "note": "A single opening batch can seed the next FY after approval.",
        },
    ]

    source_summary = [
        {
            "label": "Income",
            "value": _decimal_str(summary["income_total"]),
            "tone": "accent",
        },
        {
            "label": "Expense",
            "value": _decimal_str(summary["expense_total"]),
            "tone": "neutral",
        },
        {
            "label": "Net Profit",
            "value": _decimal_str(net_profit),
            "tone": "warning" if net_profit < 0 else "accent" if net_profit > 0 else "neutral",
        },
        {
            "label": "Balance Difference",
            "value": _decimal_str(balance_difference),
            "tone": "warning" if balance_difference else "accent",
        },
    ]

    return {
        "report_code": "year_end_close_preview",
        "report_name": "Year-End Close",
        "report_eyebrow": "Financial Controls",
        "entity_id": entity_id,
        "entity_name": scope["entity_name"],
        "entityfin_id": getattr(fy, "id", entityfin_id),
        "entityfin_name": scope["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope["subentity_name"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "close_state": snapshot["close_state"],
        "close_history": _build_close_history(fy),
        "summary_cards": [
            {"label": "Entries", "value": summary["total_entries"], "note": "Scope posting headers", "tone": "neutral"},
            {"label": "Drafts", "value": summary["draft_entries"], "note": "Pending vouchers to review", "tone": "warning" if summary["draft_entries"] else "accent"},
            {"label": "Posted", "value": summary["posted_entries"], "note": "Finalized accounting postings", "tone": "accent"},
            {"label": "Readiness", "value": snapshot["close_state"]["readiness_state"].title(), "note": "Blockers and warnings distilled", "tone": "neutral"},
        ],
        "checks": snapshot["checks"],
        "source_summary": source_summary,
        "carry_forward_buckets": carry_forward_buckets,
        "carry_forward_notes": [
            "Assets and liabilities carry forward to the next financial year.",
            "Revenue and expense accounts reset through close transfer entries.",
            "Net profit or loss moves into retained earnings / capital continuity.",
        ],
        "closing_entries": [
            {
                "label": "Transfer P&L to equity",
                "direction": "debit_equity_credit_pnl" if net_profit > 0 else "debit_pnl_credit_equity" if net_profit < 0 else "none",
                "amount": _decimal_str(abs(net_profit)),
                "narration": (
                    "Move current year profit to retained earnings."
                    if net_profit > 0
                    else "Move current year loss to retained earnings."
                    if net_profit < 0
                    else "No profit transfer required."
                ),
            },
        ],
        "opening_balance_preview": {
            "assets": _flatten_rows((snapshot["bs"] or {}).get("assets") or [], section="assets"),
            "liabilities_and_equity": _flatten_rows((snapshot["bs"] or {}).get("liabilities_and_equity") or [], section="liabilities_and_equity"),
        },
        "book_boundary": {
            "from_date": snapshot["from_date"].isoformat() if snapshot["from_date"] else None,
            "to_date": snapshot["to_date"].isoformat() if snapshot["to_date"] else None,
            "first_posting_date": snapshot["first_posting_date"].isoformat() if snapshot["first_posting_date"] else None,
            "last_posting_date": snapshot["last_posting_date"].isoformat() if snapshot["last_posting_date"] else None,
        },
        "snapshot": {
            "profit_loss": {
                "income": _decimal_str(summary["income_total"]),
                "expense": _decimal_str(summary["expense_total"]),
                "net_profit": _decimal_str(net_profit),
                "rows": len((snapshot["pnl"] or {}).get("income") or []) + len((snapshot["pnl"] or {}).get("expenses") or []),
            },
            "balance_sheet": {
                "assets": _decimal_str(summary["assets_total"]),
                "liabilities_and_equity": _decimal_str(summary["liabilities_total"]),
                "difference": _decimal_str(balance_difference),
                "rows": len((snapshot["bs"] or {}).get("assets") or []) + len((snapshot["bs"] or {}).get("liabilities_and_equity") or []),
            },
        },
        "warnings": [item for item in [snapshot.get("pnl_error"), snapshot.get("bs_error")] if item],
        "next_steps": [
            "Review draft postings",
            "Validate balance sheet difference",
            "Preview opening balance carry-forward",
            "Lock the year after approval",
        ],
        "actions": {
            "can_preview": True,
            "can_print": True,
            "can_close": bool(snapshot["close_state"]["readiness_state"] == "ready" and not snapshot["close_state"]["is_year_closed"]),
            "can_generate_plan": True,
        },
    }


def build_year_end_close_execution(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    executed_by=None,
    reporting_policy: dict | None = None,
) -> dict:
    preview = build_year_end_close_preview(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        reporting_policy=reporting_policy,
    )
    if preview["close_state"]["is_year_closed"]:
        raise ValidationError({"detail": "This financial year is already closed."})
    if preview["close_state"]["readiness_state"] == "blocked":
        raise ValidationError({"detail": "Year-end close is blocked until the readiness checks pass."})

    snapshot = _compute_snapshot(entity_id, entityfin_id, subentity_id, reporting_policy)
    fy = snapshot["financial_year"]
    if fy is None:
        raise ValidationError({"detail": "Financial year could not be resolved for close execution."})

    with transaction.atomic():
        locked_fy = EntityFinancialYear.objects.select_for_update().filter(pk=fy.pk, entity_id=entity_id).first()
        if locked_fy is None:
            raise ValidationError({"detail": "Financial year could not be locked for close execution."})
        if locked_fy.is_year_closed or locked_fy.period_status == EntityFinancialYear.PeriodStatus.CLOSED:
            raise ValidationError({"detail": "This financial year is already closed."})

        close_metadata = _build_close_metadata(
            entity_id=entity_id,
            fy=locked_fy,
            subentity_id=subentity_id,
            snapshot=snapshot,
            preview=preview,
            executed_by=executed_by,
        )
        _apply_close_stamp(locked_fy, close_metadata)

    return {
        "status": "success",
        "message": "Financial year closed successfully.",
        "report_code": "year_end_close_execution",
        "entity_id": entity_id,
        "entityfin_id": fy.id,
        "subentity_id": subentity_id,
        "close_state": {
            **preview["close_state"],
            "period_status": EntityFinancialYear.PeriodStatus.CLOSED,
            "is_year_closed": True,
            "readiness_state": "blocked",
        },
        "execution": {
            "closed_at": close_metadata["closed_at"],
            "closed_by": close_metadata["closed_by"],
            "summary": close_metadata["summary"],
            "book_boundary": close_metadata["book_boundary"],
        },
    }
