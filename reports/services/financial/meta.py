from __future__ import annotations

from entity.models import EntityFinancialYear, SubEntity


REPORT_DEFAULTS = {
    "default_page_size": 100,
    "decimal_places": 2,
    "show_zero_balances_default": False,
    "show_opening_balance_default": True,
    "allow_custom_date_range": True,
    "default_export_format": "excel",
    "group_trial_balance_by": "ledger",
    "trial_balance_period_by": None,
    "group_profit_loss_by": "accounthead",
    "profit_loss_period_by": None,
    "group_balance_sheet_by": "accounthead",
    "balance_sheet_period_by": None,
    "balance_sheet_stock_valuation_mode": "auto",
    "balance_sheet_stock_valuation_method": "fifo",
    "enable_drilldown": True,
    "require_subentity_filter": False,
}


def build_financial_report_meta(entity_id: int) -> dict:
    financial_years = list(
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=1)
        .order_by("-finstartyear")
        .values("id", "desc", "finstartyear", "finendyear")
    )
    subentities = list(
        SubEntity.objects.filter(entity_id=entity_id, isactive=1)
        .order_by("subentityname")
        .values("id", "subentityname", "ismainentity")
    )
    return {
        "entity_id": entity_id,
        "defaults": REPORT_DEFAULTS,
        "choices": {
            "group_by": [
                {"value": "ledger", "label": "Ledger"},
                {"value": "accounthead", "label": "Account Head"},
                {"value": "accounttype", "label": "Account Type"},
            ],
            "period_by": [
                {"value": "month", "label": "Monthly"},
                {"value": "quarter", "label": "Quarterly"},
                {"value": "year", "label": "Yearly"},
            ],
            "stock_valuation_mode": [
                {"value": "auto", "label": "Auto"},
                {"value": "gl", "label": "Use GL Stock"},
                {"value": "valuation", "label": "Use Stock Valuation"},
                {"value": "none", "label": "Ignore Stock"},
            ],
            "stock_valuation_method": [
                {"value": "fifo", "label": "FIFO"},
                {"value": "lifo", "label": "LIFO"},
                {"value": "mwa", "label": "Moving Average"},
                {"value": "wac", "label": "Weighted Average"},
                {"value": "latest", "label": "Latest Cost"},
            ],
            "sort_order": [
                {"value": "asc", "label": "Ascending"},
                {"value": "desc", "label": "Descending"},
            ],
            "export": [
                {"value": "excel", "label": "Excel"},
                {"value": "pdf", "label": "PDF"},
                {"value": "csv", "label": "CSV"},
            ],
        },
        "reports": [
            {
                "code": "trial_balance",
                "name": "Trial Balance",
                "path": "/api/reports/financial/trial-balance/",
                "default_group_by": REPORT_DEFAULTS["group_trial_balance_by"],
                "default_period_by": REPORT_DEFAULTS["trial_balance_period_by"],
            },
            {
                "code": "ledger_book",
                "name": "Ledger Book",
                "path": "/api/reports/financial/ledger-book/",
                "requires_ledger": True,
            },
            {
                "code": "profit_loss",
                "name": "Profit and Loss",
                "path": "/api/reports/financial/profit-loss/",
                "default_group_by": REPORT_DEFAULTS["group_profit_loss_by"],
                "default_period_by": REPORT_DEFAULTS["profit_loss_period_by"],
            },
            {
                "code": "balance_sheet",
                "name": "Balance Sheet",
                "path": "/api/reports/financial/balance-sheet/",
                "default_group_by": REPORT_DEFAULTS["group_balance_sheet_by"],
                "default_period_by": REPORT_DEFAULTS["balance_sheet_period_by"],
                "default_stock_valuation_mode": REPORT_DEFAULTS["balance_sheet_stock_valuation_mode"],
                "default_stock_valuation_method": REPORT_DEFAULTS["balance_sheet_stock_valuation_method"],
            },
        ],
        "financial_years": financial_years,
        "subentities": subentities,
        "actions": {
            "can_view": True,
            "can_export_excel": True,
            "can_export_pdf": True,
            "can_export_csv": True,
            "can_drilldown": True,
        },
    }
