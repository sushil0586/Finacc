from __future__ import annotations

from copy import deepcopy
from typing import Any

from financial.models import FinancialSettings


FINANCIAL_REPORTING_POLICY_DEFAULTS: dict[str, Any] = {
    "financial_hub": {
        "default_report_code": "trial_balance",
        "featured_reports": [
            "trial_balance",
            "ledger_book",
            "ledger_summary",
            "profit_loss",
            "balance_sheet",
            "trading_account",
            "daybook",
            "cashbook",
        ],
        "enabled_reports": [
            "trial_balance",
            "ledger_book",
            "ledger_summary",
            "profit_loss",
            "balance_sheet",
            "trading_account",
            "daybook",
            "cashbook",
        ],
    },
    "opening": {
        "opening_mode": "hybrid",
        "batch_materialization": "single_batch",
        "opening_posting_date_strategy": "first_day_of_new_year",
        "require_closed_source_year": True,
        "allow_partial_opening": False,
        "opening_equity_static_account_code": "OPENING_EQUITY_TRANSFER",
        "opening_inventory_static_account_code": "OPENING_INVENTORY_CARRY_FORWARD",
        "carry_forward": {
            "cash_bank": True,
            "receivables": True,
            "payables": True,
            "loans": True,
            "fixed_assets": True,
            "accumulated_depreciation": True,
            "inventory": True,
            "advances": True,
            "prepayments": True,
            "accruals": True,
            "statutory": True,
            "retained_earnings": True,
        },
        "reset": {
            "trading": True,
            "profit_loss": True,
            "temporary_accounts": True,
        },
        "grouped_sections": [
            "assets",
            "liabilities",
            "stock",
            "equity",
        ],
    },
    "recurring_journals": {
        "enabled": True,
        "run_mode": "manual_review",
        "auto_post_after_approval": False,
        "require_attachment": False,
        "default_frequency": "monthly",
        "templates": [],
    },
    "approval_workflow": {
        "enabled": True,
        "mode": "maker_checker",
        "default_approver_role": "finance_manager",
        "require_comment_on_reject": True,
        "document_types": {
            "journal": True,
            "payment": True,
            "receipt": True,
            "bank": True,
            "cash": True,
        },
        "thresholds": [],
    },
    "audit_trail": {
        "enabled": True,
        "retention_days": 365,
        "capture_read_actions": False,
        "capture_write_actions": True,
        "export_enabled": True,
        "modules": {
            "vouchers": True,
            "bank_reconciliation": True,
            "year_end_close": True,
            "opening_generation": True,
            "settings": True,
        },
    },
    "attachment_vault": {
        "enabled": True,
        "require_for_posting": False,
        "allow_delete_after_posting": False,
        "max_file_mb": 10,
        "required_documents": {
            "vouchers": False,
            "bank_reconciliation": True,
            "year_end_close": True,
            "statutory": True,
        },
    },
    "close_checklist": {
        "items": {},
    },
    "profit_loss": {
        "accounting_only_notes_disclosure": "summary",   # off | summary
        "accounting_only_notes_split": "purchase_sales", # combined | purchase_sales
    },
    "balance_sheet": {
        "include_accounting_only_notes_disclosure": True,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _sanitize(policy: dict[str, Any]) -> dict[str, Any]:
    hub = policy.setdefault("financial_hub", {})
    opening = policy.setdefault("opening", {})
    recurring = policy.setdefault("recurring_journals", {})
    approval = policy.setdefault("approval_workflow", {})
    audit = policy.setdefault("audit_trail", {})
    attachments = policy.setdefault("attachment_vault", {})
    close_checklist = policy.setdefault("close_checklist", {})
    pl = policy.setdefault("profit_loss", {})
    bs = policy.setdefault("balance_sheet", {})

    hub["default_report_code"] = str(hub.get("default_report_code", "trial_balance") or "trial_balance").strip().lower()
    enabled_reports = hub.get("enabled_reports") or []
    if not isinstance(enabled_reports, list):
        enabled_reports = list(enabled_reports) if enabled_reports else []
    hub["enabled_reports"] = [str(code).strip().lower() for code in enabled_reports if str(code).strip()]
    featured_reports = hub.get("featured_reports") or []
    if not isinstance(featured_reports, list):
        featured_reports = list(featured_reports) if featured_reports else []
    hub["featured_reports"] = [str(code).strip().lower() for code in featured_reports if str(code).strip()]

    disclosure_mode = str(pl.get("accounting_only_notes_disclosure", "summary")).strip().lower()
    if disclosure_mode not in {"off", "summary"}:
        disclosure_mode = "summary"
    pl["accounting_only_notes_disclosure"] = disclosure_mode

    split_mode = str(pl.get("accounting_only_notes_split", "purchase_sales")).strip().lower()
    if split_mode not in {"combined", "purchase_sales"}:
        split_mode = "purchase_sales"
    pl["accounting_only_notes_split"] = split_mode

    bs["include_accounting_only_notes_disclosure"] = bool(
        bs.get("include_accounting_only_notes_disclosure", True)
    )

    opening_mode = str(opening.get("opening_mode", "hybrid")).strip().lower()
    if opening_mode not in {"single_batch", "grouped_batches", "hybrid"}:
        opening_mode = "hybrid"
    opening["opening_mode"] = opening_mode

    batch_materialization = str(opening.get("batch_materialization", "single_batch")).strip().lower()
    if batch_materialization not in {"single_batch", "grouped_batches", "hybrid"}:
        batch_materialization = "single_batch"
    opening["batch_materialization"] = batch_materialization

    posting_strategy = str(opening.get("opening_posting_date_strategy", "first_day_of_new_year")).strip().lower()
    if posting_strategy not in {"first_day_of_new_year", "manual"}:
        posting_strategy = "first_day_of_new_year"
    opening["opening_posting_date_strategy"] = posting_strategy

    opening["require_closed_source_year"] = bool(opening.get("require_closed_source_year", True))
    opening["allow_partial_opening"] = bool(opening.get("allow_partial_opening", False))
    for key, default in (
        ("opening_equity_static_account_code", "OPENING_EQUITY_TRANSFER"),
        ("opening_inventory_static_account_code", "OPENING_INVENTORY_CARRY_FORWARD"),
    ):
        value = opening.get(key, default)
        opening[key] = str(value).strip().upper() if value not in (None, "", "null", "None") else default

    carry_forward = opening.get("carry_forward") or {}
    if not isinstance(carry_forward, dict):
        carry_forward = {}
    opening["carry_forward"] = {
        "cash_bank": bool(carry_forward.get("cash_bank", True)),
        "receivables": bool(carry_forward.get("receivables", True)),
        "payables": bool(carry_forward.get("payables", True)),
        "loans": bool(carry_forward.get("loans", True)),
        "fixed_assets": bool(carry_forward.get("fixed_assets", True)),
        "accumulated_depreciation": bool(carry_forward.get("accumulated_depreciation", True)),
        "inventory": bool(carry_forward.get("inventory", True)),
        "advances": bool(carry_forward.get("advances", True)),
        "prepayments": bool(carry_forward.get("prepayments", True)),
        "accruals": bool(carry_forward.get("accruals", True)),
        "statutory": bool(carry_forward.get("statutory", True)),
        "retained_earnings": bool(carry_forward.get("retained_earnings", True)),
    }

    reset = opening.get("reset") or {}
    if not isinstance(reset, dict):
        reset = {}
    opening["reset"] = {
        "trading": bool(reset.get("trading", True)),
        "profit_loss": bool(reset.get("profit_loss", True)),
        "temporary_accounts": bool(reset.get("temporary_accounts", True)),
    }

    grouped_sections = opening.get("grouped_sections") or []
    if not isinstance(grouped_sections, list):
        grouped_sections = list(grouped_sections) if grouped_sections else []
    allowed_groups = {"assets", "liabilities", "stock", "equity"}
    opening["grouped_sections"] = [
        str(section).strip().lower()
        for section in grouped_sections
        if str(section).strip().lower() in allowed_groups
    ] or ["assets", "liabilities", "stock", "equity"]

    recurring["enabled"] = bool(recurring.get("enabled", True))
    run_mode = str(recurring.get("run_mode", "manual_review")).strip().lower()
    if run_mode not in {"manual_review", "auto_draft", "auto_post"}:
        run_mode = "manual_review"
    recurring["run_mode"] = run_mode
    recurring["auto_post_after_approval"] = bool(recurring.get("auto_post_after_approval", False))
    recurring["require_attachment"] = bool(recurring.get("require_attachment", False))
    default_frequency = str(recurring.get("default_frequency", "monthly")).strip().lower()
    if default_frequency not in {"weekly", "monthly", "quarterly", "yearly"}:
        default_frequency = "monthly"
    recurring["default_frequency"] = default_frequency
    templates = recurring.get("templates") or []
    if not isinstance(templates, list):
        templates = []
    sanitized_templates = []
    for index, item in enumerate(templates[:50], start=1):
        if not isinstance(item, dict):
            continue
        frequency = str(item.get("frequency") or default_frequency).strip().lower()
        if frequency not in {"weekly", "monthly", "quarterly", "yearly"}:
            frequency = default_frequency
        status = str(item.get("status") or "active").strip().lower()
        if status not in {"active", "paused", "failed"}:
            status = "active"
        sanitized_templates.append(
            {
                "code": str(item.get("code") or f"RJ-{index:03d}").strip()[:40],
                "name": str(item.get("name") or f"Recurring Journal {index}").strip()[:120],
                "frequency": frequency,
                "status": status,
                "next_run_date": str(item.get("next_run_date") or "").strip()[:20] or None,
                "last_run_date": str(item.get("last_run_date") or "").strip()[:20] or None,
                "amount": str(item.get("amount") or "0.00").strip()[:32],
                "description": str(item.get("description") or "").strip()[:255],
                "debit_account": item.get("debit_account") or item.get("debit_account_id") or None,
                "credit_account": item.get("credit_account") or item.get("credit_account_id") or None,
                "failure_reason": str(item.get("failure_reason") or "").strip()[:255] or None,
            }
        )
    recurring["templates"] = sanitized_templates
    run_history = recurring.get("run_history") or []
    if not isinstance(run_history, list):
        run_history = []
    sanitized_runs = []
    for item in run_history[:20]:
        if not isinstance(item, dict):
            continue
        created_vouchers = item.get("created_vouchers") or []
        if not isinstance(created_vouchers, list):
            created_vouchers = []
        failed_templates = item.get("failed_templates") or []
        if not isinstance(failed_templates, list):
            failed_templates = []
        skipped_templates = item.get("skipped_templates") or []
        if not isinstance(skipped_templates, list):
            skipped_templates = []
        sanitized_runs.append(
            {
                "run_date": str(item.get("run_date") or "").strip()[:20] or None,
                "status": str(item.get("status") or "success").strip()[:40],
                "templates_reviewed": int(item.get("templates_reviewed") or 0),
                "vouchers_created": int(item.get("vouchers_created") or 0),
                "created_vouchers": [
                    {
                        "id": row.get("id"),
                        "voucher_code": str(row.get("voucher_code") or "").strip()[:60] or None,
                        "template_code": str(row.get("template_code") or "").strip()[:40] or None,
                        "status": str(row.get("status") or "").strip()[:40] or None,
                    }
                    for row in created_vouchers[:20]
                    if isinstance(row, dict)
                ],
                "failed_templates": [
                    {
                        "code": str(row.get("code") or "").strip()[:40] or None,
                        "name": str(row.get("name") or "").strip()[:120] or None,
                        "failure_reason": str(row.get("failure_reason") or "").strip()[:255] or None,
                    }
                    for row in failed_templates[:20]
                    if isinstance(row, dict)
                ],
                "skipped_templates": [
                    {
                        "code": str(row.get("code") or "").strip()[:40] or None,
                        "name": str(row.get("name") or "").strip()[:120] or None,
                        "voucher_id": row.get("voucher_id"),
                    }
                    for row in skipped_templates[:20]
                    if isinstance(row, dict)
                ],
                "retry_available": bool(item.get("retry_available", False)),
            }
        )
    recurring["run_history"] = sanitized_runs

    approval["enabled"] = bool(approval.get("enabled", True))
    approval_mode = str(approval.get("mode", "maker_checker")).strip().lower()
    if approval_mode not in {"none", "maker_checker", "threshold"}:
        approval_mode = "maker_checker"
    approval["mode"] = approval_mode
    approval["default_approver_role"] = str(approval.get("default_approver_role") or "finance_manager").strip().lower()[:80]
    approval["require_comment_on_reject"] = bool(approval.get("require_comment_on_reject", True))
    document_types = approval.get("document_types") or {}
    if not isinstance(document_types, dict):
        document_types = {}
    approval["document_types"] = {
        "journal": bool(document_types.get("journal", True)),
        "payment": bool(document_types.get("payment", True)),
        "receipt": bool(document_types.get("receipt", True)),
        "bank": bool(document_types.get("bank", True)),
        "cash": bool(document_types.get("cash", True)),
    }
    thresholds = approval.get("thresholds") or []
    if not isinstance(thresholds, list):
        thresholds = []
    sanitized_thresholds = []
    for index, item in enumerate(thresholds[:20], start=1):
        if not isinstance(item, dict):
            continue
        sanitized_thresholds.append(
            {
                "name": str(item.get("name") or f"Threshold {index}").strip()[:120],
                "amount_from": str(item.get("amount_from") or "0.00").strip()[:32],
                "amount_to": str(item.get("amount_to") or "").strip()[:32] or None,
                "approver_role": str(item.get("approver_role") or approval["default_approver_role"]).strip().lower()[:80],
                "required_approvals": max(1, int(item.get("required_approvals") or 1)),
            }
        )
    approval["thresholds"] = sanitized_thresholds

    audit["enabled"] = bool(audit.get("enabled", True))
    try:
        retention_days = int(audit.get("retention_days") or 365)
    except (TypeError, ValueError):
        retention_days = 365
    audit["retention_days"] = max(30, min(retention_days, 3650))
    audit["capture_read_actions"] = bool(audit.get("capture_read_actions", False))
    audit["capture_write_actions"] = bool(audit.get("capture_write_actions", True))
    audit["export_enabled"] = bool(audit.get("export_enabled", True))
    modules = audit.get("modules") or {}
    if not isinstance(modules, dict):
        modules = {}
    audit["modules"] = {
        "vouchers": bool(modules.get("vouchers", True)),
        "bank_reconciliation": bool(modules.get("bank_reconciliation", True)),
        "year_end_close": bool(modules.get("year_end_close", True)),
        "opening_generation": bool(modules.get("opening_generation", True)),
        "settings": bool(modules.get("settings", True)),
    }

    attachments["enabled"] = bool(attachments.get("enabled", True))
    attachments["require_for_posting"] = bool(attachments.get("require_for_posting", False))
    attachments["allow_delete_after_posting"] = bool(attachments.get("allow_delete_after_posting", False))
    try:
        max_file_mb = int(attachments.get("max_file_mb") or 10)
    except (TypeError, ValueError):
        max_file_mb = 10
    attachments["max_file_mb"] = max(1, min(max_file_mb, 100))
    required_documents = attachments.get("required_documents") or {}
    if not isinstance(required_documents, dict):
        required_documents = {}
    attachments["required_documents"] = {
        "vouchers": bool(required_documents.get("vouchers", False)),
        "bank_reconciliation": bool(required_documents.get("bank_reconciliation", True)),
        "year_end_close": bool(required_documents.get("year_end_close", True)),
        "statutory": bool(required_documents.get("statutory", True)),
    }

    items = close_checklist.get("items") or {}
    if not isinstance(items, dict):
        items = {}
    sanitized_items = {}
    for raw_scope, raw_items in items.items():
        if not isinstance(raw_items, dict):
            continue
        scope_key = str(raw_scope or "").strip()[:80]
        if not scope_key:
            continue
        sanitized_scope_items = {}
        for raw_key, raw_item in raw_items.items():
            if not isinstance(raw_item, dict):
                continue
            item_key = str(raw_key or "").strip()[:120]
            if not item_key:
                continue
            status = str(raw_item.get("status") or "review").strip().lower()
            if status not in {"review", "done"}:
                status = "review"
            sanitized_scope_items[item_key] = {
                "status": status,
                "comment": str(raw_item.get("comment") or "").strip()[:500],
                "updated_at": str(raw_item.get("updated_at") or "").strip()[:40] or None,
                "updated_by": raw_item.get("updated_by") or None,
            }
        sanitized_items[scope_key] = sanitized_scope_items
    close_checklist["items"] = sanitized_items

    return policy


def resolve_financial_reporting_policy(entity_id: int) -> dict[str, Any]:
    """
    Resolve entity-level financial report policy for SaaS environments.
    Source priority:
      defaults -> FinancialSettings.reporting_policy
    """
    settings_obj = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    override = getattr(settings_obj, "reporting_policy", None) if settings_obj else None
    merged = _deep_merge(FINANCIAL_REPORTING_POLICY_DEFAULTS, override or {})
    return _sanitize(merged)
