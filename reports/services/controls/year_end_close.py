from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import FinancialSettings
from posting.models import Entry, EntryStatus
from posting.adapters.year_opening import YearOpeningPostingAdapter
from posting.models import TxnType
from posting.services.posting_service import JLInput, PostingService
from posting.services.static_accounts import StaticAccountService
from reports.services.controls.drilldowns import build_posting_detail_drilldown
from reports.services.controls.posting_rollback import purge_posting_locator
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
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
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


def _leaf_rows(rows: list[dict], *, section: str) -> list[dict]:
    out: list[dict] = []
    for row in rows or []:
        children = row.get("children") or []
        if children:
            out.extend(_leaf_rows(children, section=section))
            continue
        payload = dict(row)
        payload["section"] = section
        out.append(payload)
    return out


def _count_roll_forward_rows(rows: list[dict]) -> int:
    return sum(1 for row in rows or [] if Decimal(str(row.get("amount") or 0)) != 0)


def _build_carry_forward_buckets(*, assets_rows: list[dict], liabilities_rows: list[dict], pnl_rows: int) -> list[dict[str, object]]:
    permanent_accounts = _count_roll_forward_rows(assets_rows) + _count_roll_forward_rows(liabilities_rows)
    opening_batch_count = 1 if permanent_accounts else 0
    return [
        {
            "key": "permanent_accounts",
            "title": "Permanent accounts",
            "value": permanent_accounts,
            "note": "Assets, liabilities, and equity rows expected to roll into the next year.",
        },
        {
            "key": "temporary_accounts",
            "title": "Temporary accounts",
            "value": pnl_rows,
            "note": "Income and expense rows expected to reset through the close transfer.",
        },
        {
            "key": "opening_balance_batch",
            "title": "Opening balance batch",
            "value": opening_batch_count,
            "note": "Expected opening batch footprint based on the current carry-forward scope.",
        },
    ]


def _build_close_journal_lines(*, snapshot: dict, entity_id: int, opening_policy: dict | None) -> tuple[list[JLInput], list[dict[str, object]], dict[str, object]]:
    pnl = snapshot.get("pnl") or {}
    summary = snapshot.get("summary") or {}
    net_profit = Decimal(str(summary.get("net_profit") or 0))
    income_rows = _leaf_rows(pnl.get("income") or [], section="income")
    expense_rows = _leaf_rows(pnl.get("expenses") or [], section="expense")

    opening_adapter = YearOpeningPostingAdapter(entity_id=entity_id, opening_policy=opening_policy or {})

    journal_lines: list[JLInput] = []
    line_meta: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")

    def _append_row(*, row: dict, section: str, source: str) -> None:
        debit_amount = Decimal(str(row.get("debit") or 0))
        credit_amount = Decimal(str(row.get("credit") or 0))
        net_amount = debit_amount - credit_amount
        amount = abs(net_amount)
        if amount <= Decimal("0.00"):
            return
        accounthead_id = row.get("accounthead_id")
        if not accounthead_id:
            skipped_rows.append(
                {
                    "section": section,
                    "label": row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or section.title(),
                    "amount": f"{amount:.2f}",
                    "reason": "non_postable_summary_row",
                }
            )
            return
        # Close by posting the opposite of the row's net balance direction.
        drcr = net_amount < 0
        journal_lines.append(
            JLInput(
                accounthead_id=int(accounthead_id),
                drcr=drcr,
                amount=amount,
                description=f"Year-end close transfer - {row.get('label') or row.get('ledger_name') or section.title()}",
            )
        )
        line_meta.append(
            {
                "section": section,
                "label": row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or section.title(),
                "amount": f"{amount:.2f}",
                "drcr": "debit" if drcr else "credit",
                "source": source,
            }
        )

    for row in income_rows:
        amount = Decimal(str(row.get("amount_decimal") or row.get("amount") or 0))
        income_total += amount
        _append_row(row=row, section="income", source="pnl_income")

    for row in expense_rows:
        amount = Decimal(str(row.get("amount_decimal") or row.get("amount") or 0))
        expense_total += amount
        _append_row(row=row, section="expense", source="pnl_expense")

    close_debit_total = sum((line.amount for line in journal_lines if line.drcr), Decimal("0.00"))
    close_credit_total = sum((line.amount for line in journal_lines if not line.drcr), Decimal("0.00"))
    effective_net_profit = close_debit_total - close_credit_total

    context = opening_adapter.build_context(net_profit=effective_net_profit)
    validation_issues = context.get("validation_issues") or []
    if any(issue.get("severity") == "error" for issue in validation_issues):
        raise ValidationError(
            {
                "detail": "Year-end close cannot proceed until constitution validation passes.",
                "validation_issues": validation_issues,
            }
        )

    equity_targets = context.get("equity_targets") or []
    missing_equity_codes = context.get("missing_equity_codes") or []
    if missing_equity_codes:
        raise ValidationError(
            {
                "detail": (
                    "Year-end close cannot resolve the configured equity destination ledgers. "
                    f"Please configure: {', '.join(sorted(set(missing_equity_codes)))}."
                )
            }
        )

    if effective_net_profit != Decimal("0.00"):
        if equity_targets:
            for target in equity_targets:
                amount = Decimal(str(target.get("amount") or 0))
                if amount <= Decimal("0.00"):
                    continue
                code = str(target.get("static_account_code") or "").upper()
                ledger_id = target.get("ledger_id")
                account_id = StaticAccountService.get_account_id(entity_id, code, required=False) if code else None
                if not account_id and not ledger_id:
                    raise ValidationError({"detail": f"Year-end close could not resolve mapped account for {code or 'equity target'}."})
                journal_lines.append(
                    JLInput(
                        account_id=int(account_id) if account_id else None,
                        ledger_id=int(ledger_id) if ledger_id else None,
                        drcr=(target.get("drcr") or ("credit" if effective_net_profit > 0 else "debit")) == "debit",
                        amount=amount,
                        description=(
                            "Year-end close transfer - "
                            f"{target.get('static_account_name') or 'Retained Earnings'}"
                        ),
                    )
                )
                line_meta.append(
                    {
                        "section": "equity",
                        "label": target.get("static_account_name") or "Retained Earnings",
                        "amount": f"{amount:.2f}",
                        "drcr": "debit" if ((target.get("drcr") or ("credit" if effective_net_profit > 0 else "debit")) == "debit") else "credit",
                        "source": "equity_target",
                    }
                )
        else:
            code = str((opening_policy or {}).get("opening_equity_static_account_code") or "OPENING_EQUITY_TRANSFER").upper()
            account_id = StaticAccountService.get_account_id(entity_id, code, required=False)
            ledger_id = StaticAccountService.get_ledger_id(entity_id, code, required=False)
            if not account_id and not ledger_id:
                raise ValidationError({"detail": f"Year-end close could not resolve mapped account for {code}."})
            journal_lines.append(
                JLInput(
                    account_id=int(account_id) if account_id else None,
                    ledger_id=int(ledger_id) if ledger_id else None,
                    drcr=effective_net_profit < 0,
                    amount=abs(effective_net_profit),
                    description="Year-end close transfer - Retained Earnings",
                )
            )
            line_meta.append(
                {
                    "section": "equity",
                    "label": "Retained Earnings",
                    "amount": f"{abs(effective_net_profit):.2f}",
                    "drcr": "debit" if effective_net_profit < 0 else "credit",
                    "source": "retained_earnings",
                }
            )

    diagnostics = {
        "income_total": f"{income_total:.2f}",
        "expense_total": f"{expense_total:.2f}",
        "net_profit": f"{net_profit:.2f}",
        "postable_net_profit": f"{effective_net_profit:.2f}",
        "equity_allocation_mode": context.get("equity_allocation_mode"),
        "constitution": context.get("constitution") or {},
        "allocation_plan": context.get("allocation_plan") or [],
        "validation_issues": validation_issues,
        "skipped_non_postable_rows": skipped_rows,
    }

    return journal_lines, line_meta, diagnostics


def _build_next_steps(*, close_state: dict[str, object], summary: dict[str, object], close_history: dict[str, object] | None) -> list[str]:
    if close_history:
        return [
            "Year-end close has already been executed for this scope.",
            "Review close history and locked dates before making follow-up operational changes.",
            "Use opening carry-forward preview to validate the next-year seed data.",
        ]

    steps: list[str] = []
    if int(summary.get("draft_entries") or 0) > 0:
        steps.append("Resolve draft postings before executing year-end close.")
    if Decimal(str(summary.get("balance_difference") or 0)) != 0:
        steps.append("Investigate and resolve the balance sheet difference before closing the books.")
    if Decimal(str(summary.get("net_profit") or 0)) != 0:
        steps.append("Review the retained earnings transfer amount and narration before final close.")
    if close_state.get("readiness_state") == "ready":
        steps.append("Execute the close to stamp the financial year and lock operational periods.")
        steps.append("Open the carry-forward preview next to validate the new-year opening seed.")
    elif close_state.get("readiness_state") == "review":
        steps.append("Clear review items and warnings so the year can move into a fully ready state.")
    else:
        steps.append("Resolve blockers in the checklist before year-end close can be executed.")
    return steps


def _build_carry_forward_notes(*, summary: dict[str, object], carry_forward_buckets: list[dict[str, object]]) -> list[str]:
    notes: list[str] = []
    permanent_count = next((int(item.get("value") or 0) for item in carry_forward_buckets if item.get("key") == "permanent_accounts"), 0)
    temporary_count = next((int(item.get("value") or 0) for item in carry_forward_buckets if item.get("key") == "temporary_accounts"), 0)
    balance_difference = Decimal(str(summary.get("balance_difference") or 0))
    net_profit = Decimal(str(summary.get("net_profit") or 0))

    notes.append(f"{permanent_count} permanent balance rows are currently expected to roll into the next financial year.")
    notes.append(f"{temporary_count} temporary statement rows are expected to reset through the close transfer.")

    if net_profit > 0:
        notes.append("Current-year profit is expected to move into retained earnings / capital continuity.")
    elif net_profit < 0:
        notes.append("Current-year loss is expected to reduce retained earnings / capital continuity.")
    else:
        notes.append("The current year is at break-even, so no profit transfer amount is expected.")

    if balance_difference == 0:
        notes.append("Balance sheet difference is currently zero, so the carry-forward base is aligned.")
    else:
        notes.append(f"Balance sheet difference is {_decimal_str(balance_difference)}, so carry-forward should be reviewed before final close.")

    return notes


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
        "previous_state": {
            "period_status": getattr(fy, "period_status", EntityFinancialYear.PeriodStatus.OPEN),
            "is_year_closed": bool(getattr(fy, "is_year_closed", False)),
            "books_locked_until": getattr(fy, "books_locked_until", None).isoformat() if getattr(fy, "books_locked_until", None) else None,
            "gst_locked_until": getattr(fy, "gst_locked_until", None).isoformat() if getattr(fy, "gst_locked_until", None) else None,
            "inventory_locked_until": getattr(fy, "inventory_locked_until", None).isoformat() if getattr(fy, "inventory_locked_until", None) else None,
            "ap_ar_locked_until": getattr(fy, "ap_ar_locked_until", None).isoformat() if getattr(fy, "ap_ar_locked_until", None) else None,
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
        "warnings": preview.get("warnings") or [],
        "next_steps": preview.get("next_steps") or [],
        "snapshot": preview.get("snapshot") or {},
        "journal_entry": preview.get("journal_entry"),
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


def _build_close_history(
    fy: EntityFinancialYear | None,
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
) -> dict[str, object] | None:
    if fy is None:
        return None
    metadata = getattr(fy, "metadata", None) or {}
    history = metadata.get("year_end_close")
    if not isinstance(history, dict):
        return None
    journal_entry = history.get("journal_entry")
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
        "warnings": history.get("warnings") or [],
        "next_steps": history.get("next_steps") or [],
        "snapshot": history.get("snapshot") or {},
        "journal_entry": (
            {
                **journal_entry,
                "drilldown": build_posting_detail_drilldown(
                    entry_id=journal_entry.get("entry_id"),
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                    label="Open close journal",
                ),
            }
            if isinstance(journal_entry, dict)
            else journal_entry
        ),
    }


def build_year_end_close_rollback(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    executed_by=None,
) -> dict:
    scope = _resolve_scope(entity_id, entityfin_id, subentity_id)
    fy = scope.get("entityfin_object")
    if fy is None:
        raise ValidationError({"detail": "Financial year could not be resolved for rollback."})

    with transaction.atomic():
        locked_fy = EntityFinancialYear.objects.select_for_update().filter(pk=fy.pk, entity_id=entity_id).first()
        if locked_fy is None:
            raise ValidationError({"detail": "Financial year could not be locked for rollback."})

        metadata = dict(getattr(locked_fy, "metadata", None) or {})
        close_history = metadata.get("year_end_close")
        if not isinstance(close_history, dict):
            raise ValidationError({"detail": "No year-end close history was found to roll back."})

        from reports.services.controls.opening_preview import _resolve_destination_year

        destination_info = _resolve_destination_year(entity_id, locked_fy)
        destination_id = destination_info.get("id")
        if destination_id:
            destination_fy = EntityFinancialYear.objects.select_for_update().filter(pk=destination_id, entity_id=entity_id).first()
            destination_history = ((getattr(destination_fy, "metadata", None) or {}).get("opening_carry_forward") if destination_fy else None)
            source_year = destination_history.get("source_year") if isinstance(destination_history, dict) else {}
            if isinstance(destination_history, dict) and source_year.get("id") == locked_fy.id:
                raise ValidationError(
                    {"detail": "Opening carry-forward already exists for the next financial year. Roll back opening generation first."}
                )

        rollback_counts = purge_posting_locator(
            entity_id=entity_id,
            entityfin_id=locked_fy.id,
            subentity_id=subentity_id,
            txn_type=TxnType.YEAR_END_CLOSE,
            txn_id=locked_fy.id,
        )

        previous_state = close_history.get("previous_state") or {}
        locked_fy.period_status = previous_state.get("period_status") or EntityFinancialYear.PeriodStatus.OPEN
        locked_fy.is_year_closed = bool(previous_state.get("is_year_closed", False))
        locked_fy.books_locked_until = _as_date(previous_state.get("books_locked_until"))
        locked_fy.gst_locked_until = _as_date(previous_state.get("gst_locked_until"))
        locked_fy.inventory_locked_until = _as_date(previous_state.get("inventory_locked_until"))
        locked_fy.ap_ar_locked_until = _as_date(previous_state.get("ap_ar_locked_until"))

        rollback_logs = list(metadata.get("year_end_close_rollbacks") or [])
        rollback_logs.append(
            {
                "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                "rolled_back_by": {
                    "id": getattr(executed_by, "id", None),
                    "username": getattr(executed_by, "get_username", lambda: None)(),
                    "name": " ".join(
                        part for part in [getattr(executed_by, "first_name", ""), getattr(executed_by, "last_name", "")]
                        if part
                    ).strip() or None,
                },
                "scope": close_history.get("scope") or {},
                "journal_entry": close_history.get("journal_entry"),
                "purge_result": rollback_counts,
            }
        )
        metadata["year_end_close_rollbacks"] = rollback_logs
        metadata.pop("year_end_close", None)
        locked_fy.metadata = metadata
        locked_fy.save(
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

    return {
        "status": "success",
        "message": "Year-end close rolled back successfully.",
        "report_code": "year_end_close_rollback",
        "entity_id": entity_id,
        "entityfin_id": locked_fy.id,
        "subentity_id": subentity_id,
        "rollback": {
            "rolled_back_close": True,
            "purge_result": rollback_counts,
        },
    }


def build_year_end_close_preview(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None, reporting_policy: dict | None = None) -> dict:
    scope = _resolve_scope(entity_id, entityfin_id, subentity_id)
    snapshot = _compute_snapshot(entity_id, entityfin_id, subentity_id, reporting_policy)
    fy = snapshot["financial_year"]
    summary = snapshot["summary"]
    balance_difference = summary["balance_difference"]
    net_profit = summary["net_profit"]

    assets_rows = _flatten_rows((snapshot["bs"] or {}).get("assets") or [], section="assets")
    liabilities_rows = _flatten_rows((snapshot["bs"] or {}).get("liabilities_and_equity") or [], section="liabilities_and_equity")
    pnl_rows = len((snapshot["pnl"] or {}).get("income") or []) + len((snapshot["pnl"] or {}).get("expenses") or [])
    carry_forward_buckets = _build_carry_forward_buckets(
        assets_rows=assets_rows,
        liabilities_rows=liabilities_rows,
        pnl_rows=pnl_rows,
    )
    carry_forward_notes = _build_carry_forward_notes(
        summary=summary,
        carry_forward_buckets=carry_forward_buckets,
    )

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

    close_history = _build_close_history(
        fy,
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    )
    next_steps = _build_next_steps(
        close_state=snapshot["close_state"],
        summary=summary,
        close_history=close_history,
    )

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
        "close_history": close_history,
        "summary_cards": [
            {"label": "Entries", "value": summary["total_entries"], "note": "Scope posting headers", "tone": "neutral"},
            {"label": "Drafts", "value": summary["draft_entries"], "note": "Pending vouchers to review", "tone": "warning" if summary["draft_entries"] else "accent"},
            {"label": "Posted", "value": summary["posted_entries"], "note": "Finalized accounting postings", "tone": "accent"},
            {"label": "Readiness", "value": snapshot["close_state"]["readiness_state"].title(), "note": "Blockers and warnings distilled", "tone": "neutral"},
        ],
        "checks": snapshot["checks"],
        "source_summary": source_summary,
        "carry_forward_buckets": carry_forward_buckets,
        "carry_forward_notes": carry_forward_notes,
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
            "assets": assets_rows,
            "liabilities_and_equity": liabilities_rows,
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
                "rows": pnl_rows,
            },
            "balance_sheet": {
                "assets": _decimal_str(summary["assets_total"]),
                "liabilities_and_equity": _decimal_str(summary["liabilities_total"]),
                "difference": _decimal_str(balance_difference),
                "rows": len(assets_rows) + len(liabilities_rows),
            },
        },
        "warnings": [item for item in [snapshot.get("pnl_error"), snapshot.get("bs_error")] if item],
        "next_steps": next_steps,
        "journal_entry": close_history.get("journal_entry") if close_history else None,
        "actions": {
            "can_preview": True,
            "can_print": True,
            "can_close": bool(snapshot["close_state"]["readiness_state"] == "ready" and not snapshot["close_state"]["is_year_closed"]),
            "can_rollback": bool(close_history),
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
    if preview["close_state"]["readiness_state"] != "ready":
        raise ValidationError({"detail": "Year-end close can only be executed when the readiness state is ready."})

    snapshot = _compute_snapshot(entity_id, entityfin_id, subentity_id, reporting_policy)
    fy = snapshot["financial_year"]
    if fy is None:
        raise ValidationError({"detail": "Financial year could not be resolved for close execution."})
    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    opening_policy = (settings.reporting_policy if settings else {}) or {}
    journal_lines, line_meta, diagnostics = _build_close_journal_lines(
        snapshot=snapshot,
        entity_id=entity_id,
        opening_policy=opening_policy,
    )

    with transaction.atomic():
        locked_fy = EntityFinancialYear.objects.select_for_update().filter(pk=fy.pk, entity_id=entity_id).first()
        if locked_fy is None:
            raise ValidationError({"detail": "Financial year could not be locked for close execution."})
        if locked_fy.is_year_closed or locked_fy.period_status == EntityFinancialYear.PeriodStatus.CLOSED:
            raise ValidationError({"detail": "This financial year is already closed."})

        entry = None
        if journal_lines:
            posting_date = _as_date(locked_fy.finendyear)
            if posting_date is None:
                raise ValidationError({"detail": "Financial year does not have a closing date for journal posting."})
            posting_service = PostingService(
                entity_id=entity_id,
                entityfin_id=locked_fy.id,
                subentity_id=subentity_id,
                user_id=getattr(executed_by, "id", None),
            )
            entry = posting_service.post(
                txn_type=TxnType.YEAR_END_CLOSE,
                txn_id=locked_fy.id,
                voucher_no=f"YEC-{locked_fy.year_code or locked_fy.id}",
                voucher_date=posting_date,
                posting_date=posting_date,
                narration=f"Year-end close transfer for {locked_fy.desc or locked_fy.year_code or locked_fy.id}",
                jl_inputs=journal_lines,
                use_advisory_lock=False,
            )

        preview["journal_entry"] = (
            {
                "entry_id": entry.id,
                "posting_batch_id": str(getattr(getattr(entry, "posting_batch", None), "id", None))
                if getattr(getattr(entry, "posting_batch", None), "id", None) is not None
                else None,
                "voucher_no": getattr(entry, "voucher_no", None),
                "posting_date": entry.posting_date.isoformat() if getattr(entry, "posting_date", None) else None,
                "line_count": len(line_meta),
                "lines": line_meta,
                "diagnostics": diagnostics,
                "drilldown": build_posting_detail_drilldown(
                    entry_id=getattr(entry, "id", None),
                    entity_id=entity_id,
                    entityfin_id=locked_fy.id,
                    subentity_id=subentity_id,
                    label="Open close journal",
                ),
            }
            if entry or line_meta
            else None
        )

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
            "journal_entry": close_metadata.get("journal_entry"),
        },
    }
