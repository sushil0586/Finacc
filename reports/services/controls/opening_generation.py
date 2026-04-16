from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from entity.models import EntityFinancialYear
from posting.models import TxnType
from posting.adapters.year_opening import YearOpeningPostingAdapter
from posting.services.posting_service import JLInput, PostingService
from posting.services.static_accounts import StaticAccountService  # compatibility for existing tests/patches
from reports.services.controls.opening_policy import resolve_opening_policy
from reports.services.controls.opening_preview import _build_opening_history, _resolve_destination_year, build_opening_preview
from reports.services.controls.year_end_close import _compute_snapshot


ZERO = Decimal("0.00")
INVENTORY_SYNTHETIC_LABEL = "Inventory (Closing Stock)"
CURRENT_PROFIT_LABEL = "Current Period Profit"
CURRENT_LOSS_LABEL = "Current Period Loss"


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return ZERO


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return None


def _year_code(start_date: date | None, end_date: date | None) -> str:
    if not start_date or not end_date:
        return "OPENING"
    return f"FY{start_date.year}-{str(end_date.year)[-2:]}"


def _fy_label(start_date: date | None, end_date: date | None) -> str:
    if not start_date or not end_date:
        return "Opening Year"
    return f"FY {start_date.year}-{str(end_date.year)[-2:]}"


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


def _opening_adapter(entity_id: int, opening_policy: dict) -> YearOpeningPostingAdapter:
    return YearOpeningPostingAdapter(entity_id=entity_id, opening_policy=opening_policy)


def _resolve_destination_fy(entity_id: int, source_fy: EntityFinancialYear | None, executed_by=None) -> EntityFinancialYear:
    if source_fy is None:
        raise ValidationError({"detail": "Source financial year could not be resolved."})

    source_end = _as_date(source_fy.finendyear)
    if source_end is None:
        raise ValidationError({"detail": "Source financial year does not have a closing date."})

    dest_info = _resolve_destination_year(entity_id, source_fy)
    if dest_info.get("id"):
        destination_fy = EntityFinancialYear.objects.select_for_update().filter(pk=dest_info["id"], entity_id=entity_id).first()
        if destination_fy is None:
            raise ValidationError({"detail": "Destination financial year could not be locked."})
        return destination_fy

    start_date = _as_date(dest_info.get("start_date"))
    end_date = _as_date(dest_info.get("end_date"))
    if start_date is None:
        start_date = source_end + timedelta(days=1)
    if end_date is None:
        try:
            end_date = date(start_date.year + 1, start_date.month, start_date.day) - timedelta(days=1)
        except ValueError:
            end_date = start_date + timedelta(days=364)

    return EntityFinancialYear.objects.create(
        entity_id=entity_id,
        desc=dest_info.get("name") or _fy_label(start_date, end_date),
        year_code=_year_code(start_date, end_date),
        finstartyear=timezone.make_aware(datetime.combine(start_date, time.min)),
        finendyear=timezone.make_aware(datetime.combine(end_date, time.max.replace(microsecond=0))),
        period_status=EntityFinancialYear.PeriodStatus.OPEN,
        is_year_closed=False,
        is_audit_closed=False,
        createdby=executed_by,
    )


def _build_opening_lines(snapshot: dict, *, opening_policy: dict, entity_id: int) -> tuple[list[JLInput], list[dict], dict[str, object]]:
    bs = snapshot.get("bs") or {}
    summary = bs.get("summary") or {}
    stock_valuation = bs.get("stock_valuation") or {}
    adapter = _opening_adapter(entity_id, opening_policy)
    context = adapter.build_context(net_profit=_decimal(summary.get("net_profit_brought_to_equity") or 0))
    validation_issues = context.get("validation_issues") or []
    if any(issue.get("severity") == "error" for issue in validation_issues):
        raise ValidationError(
            {
                "detail": "Opening generation cannot proceed until constitution validation passes.",
                "validation_issues": validation_issues,
            }
        )
    opening_ledgers = context["destination_ledgers"]
    equity_targets = context.get("equity_targets") or []
    missing_equity_codes = context.get("missing_equity_codes") or []
    if missing_equity_codes:
        raise ValidationError(
            {
                "detail": (
                    "Opening generation cannot resolve the configured partner equity ledgers. "
                    f"Please configure: {', '.join(sorted(set(missing_equity_codes)))}."
                )
            }
        )

    asset_rows = _leaf_rows(bs.get("assets") or [], section="assets")
    liability_rows = _leaf_rows(bs.get("liabilities_and_equity") or [], section="liabilities_and_equity")

    inventory_rows = [
        row for row in asset_rows
        if row.get("ledger_id") is None and str(row.get("ledger_name") or "").strip().lower() == INVENTORY_SYNTHETIC_LABEL.lower()
    ]
    actual_asset_rows = [
        row for row in asset_rows
        if row.get("ledger_id") is not None
    ]
    actual_liability_rows = [
        row for row in liability_rows
        if row.get("ledger_id") is not None
    ]

    journal_lines: list[JLInput] = []
    line_meta: list[dict[str, object]] = []
    sections = {
        "assets": 0,
        "liabilities": 0,
        "inventory": 0,
        "equity": 0,
    }

    def _append_line(*, ledger_id: int, accounthead_id: int | None, drcr: bool, amount: Decimal, description: str, section: str, label: str, source: str):
        if amount <= ZERO:
            return
        journal_lines.append(
            JLInput(
                accounthead_id=accounthead_id,
                ledger_id=ledger_id,
                drcr=drcr,
                amount=amount,
                description=description,
            )
        )
        line_meta.append(
            {
                "section": section,
                "label": label,
                "source": source,
                "amount": f"{amount:.2f}",
                "drcr": "debit" if drcr else "credit",
            }
        )
        sections[section] += 1

    for row in actual_asset_rows:
        amount = _decimal(row.get("amount_decimal") or row.get("amount"))
        ledger_id = row.get("ledger_id")
        if ledger_id is None:
            continue
        _append_line(
            ledger_id=int(ledger_id),
            accounthead_id=row.get("accounthead_id"),
            drcr=True,
            amount=amount,
            description=f"Opening balance carry forward - {row.get('ledger_name') or row.get('label') or 'Asset'}",
            section="assets",
            label=row.get("ledger_name") or row.get("label") or "Asset",
            source="asset_row",
        )

    for row in actual_liability_rows:
        amount = _decimal(row.get("amount_decimal") or row.get("amount"))
        ledger_id = row.get("ledger_id")
        if ledger_id is None:
            continue
        _append_line(
            ledger_id=int(ledger_id),
            accounthead_id=row.get("accounthead_id"),
            drcr=False,
            amount=amount,
            description=f"Opening balance carry forward - {row.get('ledger_name') or row.get('label') or 'Liability'}",
            section="liabilities",
            label=row.get("ledger_name") or row.get("label") or "Liability",
            source="liability_row",
        )

    if inventory_rows:
        inventory_amount = sum((_decimal(row.get("amount_decimal") or row.get("amount")) for row in inventory_rows), ZERO)
        _append_line(
        ledger_id=opening_ledgers["inventory"]["ledger_id"],
        accounthead_id=None,
        drcr=True,
        amount=inventory_amount,
            description="Opening balance carry forward - Closing stock",
            section="inventory",
            label=INVENTORY_SYNTHETIC_LABEL,
            source="synthetic_inventory",
        )

    net_profit = _decimal(summary.get("net_profit_brought_to_equity") or 0)
    if equity_targets:
        for target in equity_targets:
            amount = _decimal(target.get("amount"))
            ledger_id = target.get("ledger_id")
            if ledger_id is None:
                continue
            if amount <= ZERO:
                continue
            _append_line(
                ledger_id=int(ledger_id),
                accounthead_id=None,
                drcr=(target.get("drcr") or ("credit" if net_profit > ZERO else "debit")) == "debit",
                amount=amount,
                description=(
                    "Opening balance carry forward - "
                    f"{CURRENT_PROFIT_LABEL if net_profit > ZERO else CURRENT_LOSS_LABEL}"
                    + (f" - {target.get('ownership_name')}" if target.get("ownership_name") else "")
                ),
                section="equity",
                label=target.get("static_account_name") or CURRENT_PROFIT_LABEL,
                source="synthetic_profit_allocation" if net_profit > ZERO else "synthetic_loss_allocation",
            )
    elif net_profit > ZERO:
        _append_line(
            ledger_id=opening_ledgers["equity"]["ledger_id"],
            accounthead_id=None,
            drcr=False,
            amount=net_profit,
            description="Opening balance carry forward - Current period profit",
            section="equity",
            label=CURRENT_PROFIT_LABEL,
            source="synthetic_profit",
        )
    elif net_profit < ZERO:
        _append_line(
            ledger_id=opening_ledgers["equity"]["ledger_id"],
            accounthead_id=None,
            drcr=True,
            amount=abs(net_profit),
            description="Opening balance carry forward - Current period loss",
            section="equity",
            label=CURRENT_LOSS_LABEL,
            source="synthetic_loss",
        )

    diagnostics = {
        "source_assets": f"{sum((_decimal(row.get('amount_decimal') or row.get('amount')) for row in actual_asset_rows), ZERO):.2f}",
        "source_liabilities": f"{sum((_decimal(row.get('amount_decimal') or row.get('amount')) for row in actual_liability_rows), ZERO):.2f}",
        "inventory_carry_forward": f"{sum((_decimal(row.get('amount_decimal') or row.get('amount')) for row in inventory_rows), ZERO):.2f}",
        "net_profit_transfer": f"{net_profit:.2f}",
        "stock_effective_mode": stock_valuation.get("effective_mode"),
        "valuation_method": stock_valuation.get("valuation_method"),
        "constitution": context["constitution"],
        "allocation_plan": context["allocation_plan"],
        "equity_targets": equity_targets,
        "missing_equity_codes": missing_equity_codes,
        "equity_allocation_mode": context.get("equity_allocation_mode"),
    }

    return journal_lines, line_meta, {
        "sections": sections,
        "diagnostics": diagnostics,
        "net_profit": net_profit,
    }


def _build_opening_history_payload(*, source_fy: EntityFinancialYear, destination_fy: EntityFinancialYear, entry, posting_batch, line_meta: list[dict[str, object]], summary: dict[str, object], opening_policy: dict, executed_by) -> dict[str, object]:
    now = timezone.now()
    user_id = getattr(executed_by, "id", None)
    username = getattr(executed_by, "get_username", lambda: None)()
    full_name = " ".join(part for part in [getattr(executed_by, "first_name", ""), getattr(executed_by, "last_name", "")] if part).strip() or None
    source_start = _as_date(source_fy.finstartyear)
    source_end = _as_date(source_fy.finendyear)
    dest_start = _as_date(destination_fy.finstartyear)
    dest_end = _as_date(destination_fy.finendyear)

    return {
        "status": "generated",
        "generated_at": now.isoformat(),
        "generated_by": {
            "id": user_id,
            "username": username,
            "name": full_name,
        },
        "source_year": {
            "id": source_fy.id,
            "name": source_fy.desc or source_fy.year_code or _fy_label(source_start, source_end),
            "start_date": source_start.isoformat() if source_start else None,
            "end_date": source_end.isoformat() if source_end else None,
            "status": source_fy.period_status,
        },
        "destination_year": {
            "id": destination_fy.id,
            "name": destination_fy.desc or destination_fy.year_code or _fy_label(dest_start, dest_end),
            "start_date": dest_start.isoformat() if dest_start else None,
            "end_date": dest_end.isoformat() if dest_end else None,
            "status": destination_fy.period_status,
        },
        "summary": summary,
        "sections": [
            {"key": key, "title": key.replace("_", " ").title(), "count": value}
            for key, value in summary.get("sections", {}).items()
        ],
        "batch": {
            "posting_batch_id": str(posting_batch.id),
            "entry_id": entry.id,
            "txn_type": posting_batch.txn_type,
            "txn_id": posting_batch.txn_id,
            "voucher_no": posting_batch.voucher_no,
        },
        "opening_lines": line_meta,
        "policy_snapshot": deepcopy(opening_policy),
        "constitution_source": summary.get("constitution", {}).get("constitution_source"),
        "constitution_notes": summary.get("constitution", {}).get("constitution_notes") or [],
        "validation_issues": summary.get("validation_issues") or [],
        "equity_allocation_mode": summary.get("constitution", {}).get("allocation_mode") or summary.get("equity_allocation_mode"),
    }


def build_opening_generation(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    executed_by=None,
    reporting_policy: dict | None = None,
) -> dict:
    preview = build_opening_preview(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        reporting_policy=reporting_policy,
    )
    if not preview["actions"]["can_generate"]:
        if preview["opening_history"]:
            raise ValidationError({"detail": "Opening carry-forward has already been generated for the destination year."})
        if preview["source_year"].get("is_closed") is not True and preview["opening_policy"].get("require_closed_source_year", True):
            raise ValidationError({"detail": "Opening generation requires the source year to be closed."})
        raise ValidationError({"detail": "Opening generation is not ready yet."})

    snapshot = _compute_snapshot(entity_id, entityfin_id, subentity_id, reporting_policy)
    source_fy = snapshot["financial_year"]
    if source_fy is None:
        raise ValidationError({"detail": "Source financial year could not be resolved."})
    if not bool(getattr(source_fy, "is_year_closed", False)):
        raise ValidationError({"detail": "Opening generation requires the source year to be closed."})

    opening_policy = resolve_opening_policy(entity_id)
    with transaction.atomic():
        locked_source = EntityFinancialYear.objects.select_for_update().filter(pk=source_fy.pk, entity_id=entity_id).first()
        if locked_source is None:
            raise ValidationError({"detail": "Source financial year could not be locked."})
        if not bool(getattr(locked_source, "is_year_closed", False)):
            raise ValidationError({"detail": "Opening generation requires the source year to be closed."})

        destination_fy = _resolve_destination_fy(entity_id, locked_source, executed_by=executed_by)
        destination_fy = EntityFinancialYear.objects.select_for_update().filter(pk=destination_fy.pk, entity_id=entity_id).first() or destination_fy
        destination_metadata = dict(getattr(destination_fy, "metadata", None) or {})
        if isinstance(destination_metadata.get("opening_carry_forward"), dict):
            raise ValidationError({"detail": "Opening carry-forward already exists for the destination year."})

        journal_lines, line_meta, summary_payload = _build_opening_lines(
            snapshot,
            opening_policy=opening_policy,
            entity_id=entity_id,
        )
        if not journal_lines:
            raise ValidationError({"detail": "No opening balance lines were found to generate."})

        posting_date = _as_date(destination_fy.finstartyear)
        if posting_date is None:
            posting_date = _as_date(locked_source.finendyear)
            if posting_date is None:
                raise ValidationError({"detail": "Unable to determine the opening posting date."})

        voucher_no = f"OB-{destination_fy.year_code or destination_fy.id}"
        opening_txn_id = destination_fy.id
        posting_service = PostingService(
            entity_id=entity_id,
            entityfin_id=destination_fy.id,
            subentity_id=subentity_id,
            user_id=getattr(executed_by, "id", None),
        )
        entry = posting_service.post(
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=opening_txn_id,
            voucher_no=voucher_no,
            voucher_date=posting_date,
            posting_date=posting_date,
            narration=f"Opening balance carry forward for {destination_fy.desc or destination_fy.year_code or destination_fy.id}",
            jl_inputs=journal_lines,
            use_advisory_lock=False,
        )

        opening_history = _build_opening_history_payload(
            source_fy=locked_source,
            destination_fy=destination_fy,
            entry=entry,
            posting_batch=entry.posting_batch,
            line_meta=line_meta,
            summary={
                "entries": len(line_meta),
                "asset_lines": summary_payload["sections"]["assets"],
                "liability_lines": summary_payload["sections"]["liabilities"],
                "inventory_lines": summary_payload["sections"]["inventory"],
                "equity_lines": summary_payload["sections"]["equity"],
                "net_profit_transfer": f"{summary_payload['net_profit']:.2f}",
                "diagnostics": summary_payload["diagnostics"],
                "constitution": summary_payload.get("constitution") or {},
                "allocation_plan": summary_payload.get("allocation_plan") or [],
                "validation_issues": summary_payload.get("validation_issues") or [],
                "equity_allocation_mode": summary_payload.get("equity_allocation_mode"),
            },
            opening_policy=opening_policy,
            executed_by=executed_by,
        )

        metadata = dict(getattr(destination_fy, "metadata", None) or {})
        metadata["opening_carry_forward"] = opening_history
        destination_fy.metadata = metadata
        destination_fy.save(update_fields=["metadata"])

    return {
        "status": "success",
        "message": "Opening carry-forward generated successfully.",
        "report_code": "opening_generation",
        "entity_id": entity_id,
        "entityfin_id": destination_fy.id,
        "subentity_id": subentity_id,
        "opening_history": opening_history,
        "destination_year": {
            "id": destination_fy.id,
            "name": destination_fy.desc or destination_fy.year_code or _fy_label(_as_date(destination_fy.finstartyear), _as_date(destination_fy.finendyear)),
            "status": destination_fy.period_status,
            "start_date": _as_date(destination_fy.finstartyear).isoformat() if _as_date(destination_fy.finstartyear) else None,
            "end_date": _as_date(destination_fy.finendyear).isoformat() if _as_date(destination_fy.finendyear) else None,
        },
    }
