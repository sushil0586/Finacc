from __future__ import annotations

from collections.abc import Iterable


FINANCIAL_HUB_VERSION = "2026-04"

FINANCIAL_HUB_SECTIONS = [
    {
        "title": "Core Statements",
        "tag": "Statements",
        "codes": ["trial_balance", "ledger_book"],
    },
    {
        "title": "Financial Statements",
        "tag": "Statements",
        "codes": ["profit_loss", "balance_sheet", "trading_account"],
    },
    {
        "title": "Books",
        "tag": "Books",
        "codes": ["daybook", "cashbook"],
    },
]

FINANCIAL_HUB_FEATURED_REPORTS = [
    "trial_balance",
    "ledger_book",
    "profit_loss",
    "balance_sheet",
    "trading_account",
    "daybook",
    "cashbook",
]


def build_financial_hub(report_registry: Iterable[dict] | None) -> dict:
    registry_by_code = {}
    for item in report_registry or []:
        code = str(item.get("code") or "").strip().lower()
        if not code:
            continue
        registry_by_code[code] = item
        for alias in item.get("aliases") or []:
            normalized_alias = str(alias or "").strip().lower()
            if normalized_alias:
                registry_by_code[normalized_alias] = item

    sections = []
    for section in FINANCIAL_HUB_SECTIONS:
        section_reports = []
        for code in section["codes"]:
            report = registry_by_code.get(code)
            if not report:
                continue
            section_reports.append(_build_report_card(report))
        if section_reports:
            sections.append(
                {
                    "title": section["title"],
                    "tag": section["tag"],
                    "reports": section_reports,
                }
            )

    return {
        "version": FINANCIAL_HUB_VERSION,
        "default_report_code": "trial_balance",
        "featured_reports": list(FINANCIAL_HUB_FEATURED_REPORTS),
        "sections": sections,
    }


def _build_report_card(report: dict) -> dict:
    return {
        "code": report.get("code"),
        "name": report.get("name"),
        "path": report.get("path"),
        "route_name": report.get("route_name"),
        "category": report.get("category"),
        "scope_modes": list(report.get("scope_modes") or []),
        "supports": dict(report.get("supports") or {}),
        "defaults": {
            key: report[key]
            for key in (
                "default_group_by",
                "default_period_by",
                "default_view_type",
                "default_include_zero_balance",
                "default_include_opening",
                "default_include_movement",
                "default_include_closing",
                "default_posted_only",
                "default_hide_zero_rows",
                "default_stock_valuation_mode",
                "default_stock_valuation_method",
                "requires_ledger",
            )
            if key in report
        },
    }
