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
            "profit_loss",
            "balance_sheet",
            "trading_account",
            "daybook",
            "cashbook",
        ],
        "enabled_reports": [
            "trial_balance",
            "ledger_book",
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
