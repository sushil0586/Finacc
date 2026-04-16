from __future__ import annotations

from copy import deepcopy
from typing import Any

from financial.models import FinancialSettings
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS, _deep_merge, _sanitize


def _opening_defaults() -> dict[str, Any]:
    return deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS.get("opening", {}))


def _sanitize_opening_policy(policy: dict[str, Any]) -> dict[str, Any]:
    data = {"opening": policy or {}}
    return _sanitize(_deep_merge({"opening": _opening_defaults()}, data))["opening"]


def resolve_opening_policy(entity_id: int) -> dict[str, Any]:
    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy", "opening_balance_edit_mode").first()
    merged = _deep_merge(
        FINANCIAL_REPORTING_POLICY_DEFAULTS,
        getattr(settings, "reporting_policy", None) or {},
    )
    return _sanitize(merged).get("opening", {})


def summarize_opening_policy(opening_policy: dict[str, Any]) -> list[dict[str, Any]]:
    carry_forward = opening_policy.get("carry_forward") or {}
    reset = opening_policy.get("reset") or {}
    return [
        {
            "label": "Opening mode",
            "value": opening_policy.get("opening_mode") or "hybrid",
            "note": "Controls how the next FY opening is materialized.",
        },
        {
            "label": "Batch style",
            "value": opening_policy.get("batch_materialization") or "single_batch",
            "note": "Physical batch layout for generated opening entries.",
        },
        {
            "label": "Posting date",
            "value": opening_policy.get("opening_posting_date_strategy") or "first_day_of_new_year",
            "note": "Default posting date strategy for the carry-forward batch.",
        },
        {
            "label": "Equity mapping",
            "value": opening_policy.get("opening_equity_static_account_code") or "auto",
            "note": "Static account role resolved to the destination equity ledger.",
        },
        {
            "label": "Inventory mapping",
            "value": opening_policy.get("opening_inventory_static_account_code") or "auto",
            "note": "Static account role resolved to the destination inventory ledger.",
        },
        {
            "label": "Carry forward",
            "value": sum(1 for value in carry_forward.values() if value),
            "note": "Enabled carry-forward buckets.",
        },
        {
            "label": "Reset groups",
            "value": sum(1 for value in reset.values() if value),
            "note": "Temporary statement groups reset at close.",
        },
        {
            "label": "Grouped sections",
            "value": len(opening_policy.get("grouped_sections") or []),
            "note": "Reporting sections available in grouped opening mode.",
        },
    ]


def update_opening_policy(*, entity_id: int, updates: dict[str, Any], created_by=None) -> dict[str, Any]:
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={
            "createdby": created_by,
            "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS),
        },
    )

    policy = deepcopy(settings.reporting_policy or {})
    opening = dict(policy.get("opening") or {})

    if "opening_mode" in updates:
        opening["opening_mode"] = str(updates.get("opening_mode") or "hybrid").strip().lower()
    if "batch_materialization" in updates:
        opening["batch_materialization"] = str(updates.get("batch_materialization") or "single_batch").strip().lower()
    if "opening_posting_date_strategy" in updates:
        opening["opening_posting_date_strategy"] = str(updates.get("opening_posting_date_strategy") or "first_day_of_new_year").strip().lower()
    if "require_closed_source_year" in updates:
        opening["require_closed_source_year"] = bool(updates.get("require_closed_source_year"))
    if "allow_partial_opening" in updates:
        opening["allow_partial_opening"] = bool(updates.get("allow_partial_opening"))
    if "opening_equity_static_account_code" in updates:
        raw_value = updates.get("opening_equity_static_account_code")
        opening["opening_equity_static_account_code"] = str(raw_value).strip().upper() if raw_value not in (None, "", "null", "None") else None
    if "opening_inventory_static_account_code" in updates:
        raw_value = updates.get("opening_inventory_static_account_code")
        opening["opening_inventory_static_account_code"] = str(raw_value).strip().upper() if raw_value not in (None, "", "null", "None") else None

    if "carry_forward" in updates:
        carry_forward = dict(opening.get("carry_forward") or {})
        incoming = updates.get("carry_forward") or {}
        if isinstance(incoming, dict):
            carry_forward.update({str(k): bool(v) for k, v in incoming.items()})
        opening["carry_forward"] = carry_forward

    if "reset" in updates:
        reset = dict(opening.get("reset") or {})
        incoming = updates.get("reset") or {}
        if isinstance(incoming, dict):
            reset.update({str(k): bool(v) for k, v in incoming.items()})
        opening["reset"] = reset

    if "grouped_sections" in updates:
        incoming = updates.get("grouped_sections") or []
        if isinstance(incoming, (list, tuple, set)):
            opening["grouped_sections"] = [str(item).strip().lower() for item in incoming if str(item).strip()]

    policy["opening"] = opening
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])

    return resolve_opening_policy(entity_id)
