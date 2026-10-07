from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from financial.models import FinancialSettings
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS, _deep_merge, _sanitize
from vouchers.models import VoucherHeader
from vouchers.services.voucher_service import VoucherService

Q2 = Decimal("0.01")


def resolve_recurring_journal_policy(entity_id: int) -> dict[str, Any]:
    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    merged = _deep_merge(
        FINANCIAL_REPORTING_POLICY_DEFAULTS,
        getattr(settings, "reporting_policy", None) or {},
    )
    return _sanitize(merged).get("recurring_journals", {})


def summarize_recurring_journal_policy(policy: dict[str, Any]) -> list[dict[str, Any]]:
    templates = policy.get("templates") or []
    active_count = sum(1 for item in templates if item.get("status") == "active")
    paused_count = sum(1 for item in templates if item.get("status") == "paused")
    failed_count = sum(1 for item in templates if item.get("status") == "failed")
    due_count = recurring_journal_due_count(policy)
    return [
        {"label": "Templates", "value": len(templates), "note": "Configured recurring journal templates.", "tone": "neutral"},
        {"label": "Active", "value": active_count, "note": "Templates eligible for the next scheduler run.", "tone": "accent"},
        {"label": "Due", "value": due_count, "note": "Templates due on or before today.", "tone": "warning" if due_count else "neutral"},
        {"label": "Paused", "value": paused_count, "note": "Templates intentionally excluded from generation.", "tone": "neutral"},
        {"label": "Failed", "value": failed_count, "note": "Templates requiring finance review.", "tone": "warning" if failed_count else "neutral"},
        {"label": "Run mode", "value": policy.get("run_mode") or "manual_review", "note": "Scheduler posting control mode.", "tone": "neutral"},
    ]


def recurring_journal_due_count(policy: dict[str, Any], *, today: date | None = None) -> int:
    today = today or date.today()
    due = 0
    for template in policy.get("templates") or []:
        if template.get("status") != "active":
            continue
        raw_date = template.get("next_run_date")
        if not raw_date:
            continue
        try:
            next_run = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            continue
        if next_run <= today:
            due += 1
    return due


def recurring_journal_failed_count(policy: dict[str, Any]) -> int:
    return sum(1 for item in policy.get("templates") or [] if item.get("status") == "failed")


def _parse_run_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _advance_run_date(current: date, frequency: str) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "yearly":
        year = current.year + 1
        day = min(current.day, calendar.monthrange(year, current.month)[1])
        return current.replace(year=year, day=day)
    months = 3 if frequency == "quarterly" else 1
    month_index = current.month - 1 + months
    year = current.year + month_index // 12
    month = month_index % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return current.replace(year=year, month=month, day=day)


def _existing_recurring_voucher(
    *,
    entity_id: int,
    entityfin_id: int,
    subentity_id: int | None,
    template_code: str | None,
    run_date: date,
):
    queryset = VoucherHeader.objects.filter(
        entity_id=entity_id,
        entityfinid_id=entityfin_id,
        voucher_type=VoucherHeader.VoucherType.JOURNAL,
        workflow_payload___recurring_journal__run_date=run_date.isoformat(),
    )
    if subentity_id:
        queryset = queryset.filter(subentity_id=subentity_id)
    else:
        queryset = queryset.filter(subentity_id__isnull=True)
    if template_code:
        queryset = queryset.filter(workflow_payload___recurring_journal__code=template_code)
    return queryset.exclude(status=VoucherHeader.Status.CANCELLED).order_by("-id").first()


def build_recurring_journal_readiness(entity_id: int) -> dict[str, Any]:
    policy = resolve_recurring_journal_policy(entity_id)
    templates = policy.get("templates") or []
    active_count = sum(1 for item in templates if item.get("status") == "active")
    failed_count = sum(1 for item in templates if item.get("status") == "failed")
    due_count = recurring_journal_due_count(policy)
    total_amount = Decimal("0.00")
    for item in templates:
        try:
            total_amount += Decimal(str(item.get("amount") or "0"))
        except Exception:
            continue

    if not policy.get("enabled", True):
        status = "review"
        status_label = "Disabled"
    elif failed_count:
        status = "blocked"
        status_label = "Failed Runs"
    elif due_count:
        status = "review"
        status_label = "Due for Review"
    elif active_count:
        status = "ready"
        status_label = "Scheduled"
    else:
        status = "review"
        status_label = "Not Configured"

    return {
        "status": status,
        "status_label": status_label,
        "summary_cards": summarize_recurring_journal_policy(policy),
        "policy": policy,
        "templates": templates,
        "run_history": policy.get("run_history") or [],
        "actions": [
            {
                "label": "Review Recurring Journals",
                "route": "/reports/controls/phase-one",
                "params": {},
            }
        ],
        "total_template_amount": str(total_amount.quantize(Decimal("0.01"))),
    }


def update_recurring_journal_policy(*, entity_id: int, updates: dict[str, Any], created_by=None) -> dict[str, Any]:
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={
            "createdby": created_by,
            "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS),
        },
    )
    policy = deepcopy(settings.reporting_policy or {})
    recurring = dict(policy.get("recurring_journals") or {})
    for key in ("enabled", "auto_post_after_approval", "require_attachment"):
        if key in updates:
            recurring[key] = bool(updates.get(key))
    for key in ("run_mode", "default_frequency"):
        if key in updates:
            recurring[key] = str(updates.get(key) or "").strip().lower()
    if "templates" in updates and isinstance(updates.get("templates"), list):
        recurring["templates"] = updates.get("templates")
    policy["recurring_journals"] = recurring
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])
    return resolve_recurring_journal_policy(entity_id)


def mark_recurring_journal_run(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    run_date: date | None = None,
    created_by=None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    run_date = run_date or date.today()
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={
            "createdby": created_by,
            "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS),
        },
    )
    policy = deepcopy(settings.reporting_policy or {})
    recurring = dict(policy.get("recurring_journals") or {})
    templates = []
    run_rows = []
    created_vouchers = []
    failed_templates = []
    skipped_templates = []
    run_mode = str(recurring.get("run_mode") or "manual_review").lower()
    for template in recurring.get("templates") or []:
        row = dict(template or {})
        next_run = _parse_run_date(row.get("next_run_date"))
        is_retry = retry_failed and row.get("status") == "failed"
        is_due = (row.get("status") == "active" and next_run is not None and next_run <= run_date) or is_retry
        if is_due:
            frequency = str(row.get("frequency") or recurring.get("default_frequency") or "monthly").lower()
            run_row = {
                "code": row.get("code"),
                "name": row.get("name"),
                "frequency": frequency,
                "amount": row.get("amount"),
                "previous_next_run_date": next_run.isoformat() if next_run else None,
                "next_run_date": None,
                "status": "marked_reviewed",
            }
            failure_reason = None
            try:
                amount = Decimal(str(row.get("amount") or "0")).quantize(Q2)
            except Exception:
                amount = Decimal("0.00")
                failure_reason = "Invalid recurring journal amount."
            debit_account = row.get("debit_account")
            credit_account = row.get("credit_account")
            if run_mode in {"auto_draft", "auto_post"}:
                if not entityfin_id:
                    failure_reason = "Financial year scope is required to create a voucher."
                elif not debit_account or not credit_account:
                    failure_reason = "Debit and credit posting accounts are required."
                elif amount <= Decimal("0.00"):
                    failure_reason = "Amount must be greater than zero."
                if failure_reason:
                    row["status"] = "failed"
                    row["failure_reason"] = failure_reason
                    run_row["status"] = "failed"
                    run_row["failure_reason"] = failure_reason
                    failed_templates.append({"code": row.get("code"), "name": row.get("name"), "failure_reason": failure_reason})
                else:
                    try:
                        existing_voucher = _existing_recurring_voucher(
                            entity_id=entity_id,
                            entityfin_id=entityfin_id,
                            subentity_id=subentity_id,
                            template_code=row.get("code"),
                            run_date=run_date,
                        )
                        if existing_voucher:
                            voucher_entry = {
                                "id": existing_voucher.id,
                                "voucher_code": existing_voucher.voucher_code,
                                "template_code": row.get("code"),
                                "status": "already_exists",
                            }
                            created_vouchers.append(voucher_entry)
                            row["status"] = "active"
                            row.pop("failure_reason", None)
                            row["last_run_date"] = run_date.isoformat()
                            row["next_run_date"] = _advance_run_date(run_date, frequency).isoformat()
                            run_row["status"] = "already_exists"
                            run_row["voucher_id"] = existing_voucher.id
                            run_row["next_run_date"] = row["next_run_date"]
                            skipped_templates.append({"code": row.get("code"), "name": row.get("name"), "voucher_id": existing_voucher.id})
                            run_rows.append(run_row)
                            templates.append(row)
                            continue
                        result = VoucherService.create_voucher(
                            data={
                                "entity_id": entity_id,
                                "entityfinid_id": entityfin_id,
                                "subentity_id": subentity_id,
                                "voucher_date": run_date,
                                "voucher_type": VoucherHeader.VoucherType.JOURNAL,
                                "reference_number": f"RJ-{row.get('code') or row.get('name') or run_date.isoformat()}",
                                "narration": row.get("description") or f"Recurring journal: {row.get('name') or row.get('code')}",
                                "workflow_payload": {
                                    "_recurring_journal": {
                                        "code": row.get("code"),
                                        "name": row.get("name"),
                                        "run_date": run_date.isoformat(),
                                    }
                                },
                                "lines": [
                                    {"line_no": 1, "account": debit_account, "dr_amount": amount, "cr_amount": Decimal("0.00"), "narration": row.get("description")},
                                    {"line_no": 2, "account": credit_account, "dr_amount": Decimal("0.00"), "cr_amount": amount, "narration": row.get("description")},
                                ],
                            },
                            created_by_id=getattr(created_by, "id", None),
                        )
                        voucher_entry = {"id": result.header.id, "voucher_code": result.header.voucher_code, "template_code": row.get("code")}
                        created_vouchers.append(voucher_entry)
                        if run_mode == "auto_post":
                            try:
                                confirmed = VoucherService.confirm_voucher(result.header.id, confirmed_by_id=getattr(created_by, "id", None))
                                posted = VoucherService.post_voucher(confirmed.header.id, posted_by_id=getattr(created_by, "id", None))
                                voucher_entry["status"] = "posted"
                                row["status"] = "active"
                                row.pop("failure_reason", None)
                                row["last_run_date"] = run_date.isoformat()
                                row["next_run_date"] = _advance_run_date(run_date, frequency).isoformat()
                                run_row["status"] = "posted"
                                run_row["voucher_id"] = posted.header.id
                                run_row["next_run_date"] = row["next_run_date"]
                            except Exception as exc:
                                failure_reason = str(exc)[:255] or "Draft voucher could not be posted."
                                voucher_entry["status"] = "posting_blocked"
                                row["status"] = "failed"
                                row["failure_reason"] = failure_reason
                                run_row["status"] = "posting_blocked"
                                run_row["voucher_id"] = result.header.id
                                run_row["failure_reason"] = failure_reason
                                failed_templates.append({"code": row.get("code"), "name": row.get("name"), "failure_reason": failure_reason})
                        else:
                            voucher_entry["status"] = "draft_created"
                            row["status"] = "active"
                            row.pop("failure_reason", None)
                            row["last_run_date"] = run_date.isoformat()
                            row["next_run_date"] = _advance_run_date(run_date, frequency).isoformat()
                            run_row["status"] = "draft_created"
                            run_row["voucher_id"] = result.header.id
                            run_row["next_run_date"] = row["next_run_date"]
                    except Exception as exc:
                        failure_reason = str(exc)[:255] or "Draft voucher creation failed."
                        row["status"] = "failed"
                        row["failure_reason"] = failure_reason
                        run_row["status"] = "failed"
                        run_row["failure_reason"] = failure_reason
                        failed_templates.append({"code": row.get("code"), "name": row.get("name"), "failure_reason": failure_reason})
            else:
                row["status"] = "active"
                row.pop("failure_reason", None)
                row["last_run_date"] = run_date.isoformat()
                row["next_run_date"] = _advance_run_date(run_date, frequency).isoformat()
                run_row["next_run_date"] = row["next_run_date"]
            run_rows.append(run_row)
        templates.append(row)
    recurring["templates"] = templates
    run_history = list(recurring.get("run_history") or [])
    run_history.insert(
        0,
        {
            "run_date": run_date.isoformat(),
            "status": "failed" if failed_templates else "success",
            "templates_reviewed": len(run_rows),
            "vouchers_created": len(created_vouchers),
            "created_vouchers": created_vouchers,
            "failed_templates": failed_templates,
            "skipped_templates": skipped_templates,
            "retry_available": bool(failed_templates),
        },
    )
    recurring["run_history"] = run_history[:20]
    policy["recurring_journals"] = recurring
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])
    updated_policy = resolve_recurring_journal_policy(entity_id)
    return {
        "entity": entity_id,
        "run_date": run_date.isoformat(),
        "status": "failed" if failed_templates else "success",
        "templates_reviewed": len(run_rows),
        "vouchers_created": len(created_vouchers),
        "created_vouchers": created_vouchers,
        "failed_templates": failed_templates,
        "skipped_templates": skipped_templates,
        "retry_available": bool(failed_templates),
        "templates": run_rows,
        "recurring_journal_policy": updated_policy,
        "summary": summarize_recurring_journal_policy(updated_policy),
        "readiness": build_recurring_journal_readiness(entity_id),
    }
