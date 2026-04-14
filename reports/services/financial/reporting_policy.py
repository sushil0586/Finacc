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
