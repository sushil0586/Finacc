from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

from entity.models import Entity
from reports.services.report_preferences import get_user_report_preference, upsert_user_report_preference


FINANCIAL_HUB_SETTINGS_REPORT_CODE = "financial_hub_settings"

FINANCIAL_HUB_SETTINGS_DEFAULTS = {
    "general_display": {
        "amount_display_unit": "actual",
        "decimal_places": 2,
        "negative_number_style": "minus",
        "balance_style": "dr_cr",
        "zero_value_display": "zero",
        "date_format": "dd-mmm-yyyy",
        "numbering_style": "indian",
        "density": "compact",
        "highlight_abnormal_balance": True,
    },
    "export_layout": {
        "export_action_mode": "separate_buttons",
        "default_export_format": "pdf",
        "default_orientation": "landscape",
        "header_density": "compact",
        "metadata_visibility": "compact",
        "show_pdf_export": True,
        "show_excel_export": True,
        "show_csv_export": True,
        "show_print_export": True,
        "show_entity_name": True,
        "show_financial_year": True,
        "show_subentity": True,
        "show_filters": True,
        "show_generated_on": True,
        "show_page_number": True,
        "excel_raw_data_sheet": True,
        "freeze_excel_header": True,
        "auto_fit_excel_columns": True,
    },
    "report_defaults": {
        "default_group_by": "ledger",
        "default_view_type": "summary",
        "include_zero_balances": False,
        "include_opening": True,
        "include_movement": True,
        "include_closing": True,
        "posted_only": True,
        "default_sort_order": "asc",
    },
    "report_overrides": {
        "trial_balance": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {},
            "columns": {
                "code": {"export_visible": True, "display_order": 1, "mandatory": False},
                "name": {"export_visible": True, "display_order": 2, "mandatory": True},
                "account_head": {"export_visible": True, "display_order": 3, "mandatory": False},
                "account_type": {"export_visible": True, "display_order": 4, "mandatory": False},
                "opening": {"export_visible": True, "display_order": 5, "mandatory": True},
                "debit": {"export_visible": True, "display_order": 6, "mandatory": True},
                "credit": {"export_visible": True, "display_order": 7, "mandatory": True},
                "closing": {"export_visible": True, "display_order": 8, "mandatory": True},
                "abnormal": {"export_visible": True, "display_order": 9, "mandatory": False},
            },
        }
        ,
        "ledger_book": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_sort_order": "asc",
            },
            "columns": {
                "date": {"export_visible": True, "display_order": 1, "mandatory": True},
                "voucher_no": {"export_visible": True, "display_order": 2, "mandatory": False},
                "voucher_type": {"export_visible": True, "display_order": 3, "mandatory": False},
                "description": {"export_visible": True, "display_order": 4, "mandatory": True},
                "debit": {"export_visible": True, "display_order": 5, "mandatory": True},
                "credit": {"export_visible": True, "display_order": 6, "mandatory": True},
                "running_balance": {"export_visible": True, "display_order": 7, "mandatory": True},
            },
        },
        "ledger_summary": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_group_by": "ledger",
                "default_view_type": "summary",
                "include_zero_balances": False,
                "posted_only": True,
                "default_sort_order": "asc",
            },
            "columns": {
                "account_head": {"export_visible": True, "display_order": 1, "mandatory": False},
                "account_name": {"export_visible": True, "display_order": 2, "mandatory": True},
                "account_type": {"export_visible": True, "display_order": 3, "mandatory": False},
                "opening": {"export_visible": True, "display_order": 4, "mandatory": True},
                "ob_dc": {"export_visible": True, "display_order": 5, "mandatory": False},
                "debit": {"export_visible": True, "display_order": 6, "mandatory": True},
                "credit": {"export_visible": True, "display_order": 7, "mandatory": True},
                "balance": {"export_visible": True, "display_order": 8, "mandatory": True},
                "dc": {"export_visible": True, "display_order": 9, "mandatory": False},
            },
        },
        "profit_loss": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_view_type": "summary",
                "default_group_by": "ledger",
                "default_sort_order": "asc",
                "posted_only": True,
                "hide_zero_rows": True,
                "stock_valuation_mode": "auto",
                "stock_valuation_method": "fifo",
            },
            "columns": {
                "section": {"export_visible": True, "display_order": 1, "mandatory": True},
                "particulars": {"export_visible": True, "display_order": 2, "mandatory": True},
                "account_head": {"export_visible": True, "display_order": 3, "mandatory": False},
                "account_type": {"export_visible": True, "display_order": 4, "mandatory": False},
                "amount": {"export_visible": True, "display_order": 5, "mandatory": True},
            },
        },
        "balance_sheet": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_view_type": "summary",
                "default_group_by": "ledger",
                "default_sort_order": "asc",
                "posted_only": True,
                "hide_zero_rows": True,
                "stock_valuation_mode": "auto",
                "stock_valuation_method": "fifo",
            },
            "columns": {
                "section": {"export_visible": True, "display_order": 1, "mandatory": True},
                "particulars": {"export_visible": True, "display_order": 2, "mandatory": True},
                "account_head": {"export_visible": True, "display_order": 3, "mandatory": False},
                "account_type": {"export_visible": True, "display_order": 4, "mandatory": False},
                "amount": {"export_visible": True, "display_order": 5, "mandatory": True},
            },
        },
        "trading_account": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_view_type": "summary",
                "default_group_by": "accounthead",
                "default_sort_order": "asc",
                "posted_only": True,
                "hide_zero_rows": True,
                "stock_valuation_method": "fifo",
            },
            "columns": {
                "side": {"export_visible": True, "display_order": 1, "mandatory": True},
                "particulars": {"export_visible": True, "display_order": 2, "mandatory": True},
                "qty": {"export_visible": True, "display_order": 3, "mandatory": False},
                "amount": {"export_visible": True, "display_order": 4, "mandatory": True},
            },
        },
        "daybook": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_sort_order": "asc",
            },
            "columns": {
                "transaction_date": {"export_visible": True, "display_order": 1, "mandatory": True},
                "voucher_date": {"export_visible": True, "display_order": 2, "mandatory": False},
                "voucher_no": {"export_visible": True, "display_order": 3, "mandatory": False},
                "voucher_type": {"export_visible": True, "display_order": 4, "mandatory": False},
                "narration": {"export_visible": True, "display_order": 5, "mandatory": True},
                "reference": {"export_visible": True, "display_order": 6, "mandatory": False},
                "debit": {"export_visible": True, "display_order": 7, "mandatory": True},
                "credit": {"export_visible": True, "display_order": 8, "mandatory": True},
                "status": {"export_visible": True, "display_order": 9, "mandatory": False},
                "posted": {"export_visible": True, "display_order": 10, "mandatory": False},
                "source": {"export_visible": True, "display_order": 11, "mandatory": False},
            },
        },
        "cashbook": {
            "enabled": False,
            "general_display": {},
            "export_layout": {},
            "report_defaults": {
                "default_sort_order": "asc",
            },
            "columns": {
                "date": {"export_visible": True, "display_order": 1, "mandatory": True},
                "voucher_no": {"export_visible": True, "display_order": 2, "mandatory": False},
                "voucher_type": {"export_visible": True, "display_order": 3, "mandatory": False},
                "account_impacted": {"export_visible": True, "display_order": 4, "mandatory": False},
                "counter_account": {"export_visible": True, "display_order": 5, "mandatory": False},
                "particulars": {"export_visible": True, "display_order": 6, "mandatory": True},
                "receipt": {"export_visible": True, "display_order": 7, "mandatory": True},
                "payment": {"export_visible": True, "display_order": 8, "mandatory": True},
                "running_balance": {"export_visible": True, "display_order": 9, "mandatory": False},
                "source": {"export_visible": True, "display_order": 10, "mandatory": False},
            },
        },
    },
}

AMOUNT_UNIT_FACTORS = {
    "actual": Decimal("1"),
    "hundreds": Decimal("100"),
    "thousands": Decimal("1000"),
    "lakhs": Decimal("100000"),
    "crores": Decimal("10000000"),
    "millions": Decimal("1000000"),
}

AMOUNT_UNIT_LABELS = {
    "actual": "Actual",
    "hundreds": "Hundreds",
    "thousands": "Thousands",
    "lakhs": "Lakhs",
    "crores": "Crores",
    "millions": "Millions",
}

TRIAL_BALANCE_COLUMN_KEYS = (
    "code",
    "name",
    "account_head",
    "account_type",
    "opening",
    "debit",
    "credit",
    "closing",
    "abnormal",
)

LEDGER_BOOK_COLUMN_KEYS = (
    "date",
    "voucher_no",
    "voucher_type",
    "description",
    "debit",
    "credit",
    "running_balance",
)

LEDGER_SUMMARY_COLUMN_KEYS = (
    "account_head",
    "account_name",
    "account_type",
    "opening",
    "ob_dc",
    "debit",
    "credit",
    "balance",
    "dc",
)

PROFIT_LOSS_COLUMN_KEYS = (
    "section",
    "particulars",
    "account_head",
    "account_type",
    "amount",
)

BALANCE_SHEET_COLUMN_KEYS = (
    "section",
    "particulars",
    "account_head",
    "account_type",
    "amount",
)

TRADING_ACCOUNT_COLUMN_KEYS = (
    "side",
    "particulars",
    "qty",
    "amount",
)

DAYBOOK_COLUMN_KEYS = (
    "transaction_date",
    "voucher_date",
    "voucher_no",
    "voucher_type",
    "narration",
    "reference",
    "debit",
    "credit",
    "status",
    "posted",
    "source",
)

CASHBOOK_COLUMN_KEYS = (
    "date",
    "voucher_no",
    "voucher_type",
    "account_impacted",
    "counter_account",
    "particulars",
    "receipt",
    "payment",
    "running_balance",
    "source",
)


def _merge_dict(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_bool(value, fallback):
    if isinstance(value, bool):
        return value
    if value in {"true", "True", "1", 1}:
        return True
    if value in {"false", "False", "0", 0}:
        return False
    return fallback


def _normalize_general_display_settings(general: dict, defaults: dict) -> dict:
    amount_unit = str(general.get("amount_display_unit") or defaults["amount_display_unit"]).strip().lower()
    if amount_unit not in AMOUNT_UNIT_FACTORS:
        amount_unit = defaults["amount_display_unit"]

    decimal_places = general.get("decimal_places", defaults["decimal_places"])
    try:
        decimal_places = max(0, min(4, int(decimal_places)))
    except (TypeError, ValueError):
        decimal_places = defaults["decimal_places"]

    negative_style = str(general.get("negative_number_style") or defaults["negative_number_style"]).strip().lower()
    if negative_style not in {"minus", "brackets"}:
        negative_style = defaults["negative_number_style"]

    balance_style = str(general.get("balance_style") or defaults["balance_style"]).strip().lower()
    if balance_style not in {"dr_cr", "signed"}:
        balance_style = defaults["balance_style"]

    zero_display = str(general.get("zero_value_display") or defaults["zero_value_display"]).strip().lower()
    if zero_display not in {"zero", "dash", "blank"}:
        zero_display = defaults["zero_value_display"]

    numbering_style = str(general.get("numbering_style") or defaults["numbering_style"]).strip().lower()
    if numbering_style not in {"indian", "international"}:
        numbering_style = defaults["numbering_style"]

    density = str(general.get("density") or defaults["density"]).strip().lower()
    if density not in {"compact", "normal"}:
        density = defaults["density"]

    date_format = str(general.get("date_format") or defaults["date_format"]).strip().lower()
    if date_format not in {"dd-mm-yyyy", "dd-mmm-yyyy", "yyyy-mm-dd"}:
        date_format = defaults["date_format"]

    return {
        "amount_display_unit": amount_unit,
        "decimal_places": decimal_places,
        "negative_number_style": negative_style,
        "balance_style": balance_style,
        "zero_value_display": zero_display,
        "date_format": date_format,
        "numbering_style": numbering_style,
        "density": density,
        "highlight_abnormal_balance": _normalize_bool(
            general.get("highlight_abnormal_balance"),
            defaults["highlight_abnormal_balance"],
        ),
    }


def _normalize_export_layout_settings(export: dict, defaults: dict) -> dict:
    normalized = {
        "export_action_mode": str(export.get("export_action_mode") or defaults["export_action_mode"]).strip().lower(),
        "default_export_format": str(export.get("default_export_format") or defaults["default_export_format"]).strip().lower(),
        "default_orientation": str(export.get("default_orientation") or defaults["default_orientation"]).strip().lower(),
        "header_density": str(export.get("header_density") or defaults["header_density"]).strip().lower(),
        "metadata_visibility": str(export.get("metadata_visibility") or defaults["metadata_visibility"]).strip().lower(),
        "show_pdf_export": _normalize_bool(export.get("show_pdf_export"), defaults["show_pdf_export"]),
        "show_excel_export": _normalize_bool(export.get("show_excel_export"), defaults["show_excel_export"]),
        "show_csv_export": _normalize_bool(export.get("show_csv_export"), defaults["show_csv_export"]),
        "show_print_export": _normalize_bool(export.get("show_print_export"), defaults["show_print_export"]),
        "show_entity_name": _normalize_bool(export.get("show_entity_name"), defaults["show_entity_name"]),
        "show_financial_year": _normalize_bool(export.get("show_financial_year"), defaults["show_financial_year"]),
        "show_subentity": _normalize_bool(export.get("show_subentity"), defaults["show_subentity"]),
        "show_filters": _normalize_bool(export.get("show_filters"), defaults["show_filters"]),
        "show_generated_on": _normalize_bool(export.get("show_generated_on"), defaults["show_generated_on"]),
        "show_page_number": _normalize_bool(export.get("show_page_number"), defaults["show_page_number"]),
        "excel_raw_data_sheet": _normalize_bool(export.get("excel_raw_data_sheet"), defaults["excel_raw_data_sheet"]),
        "freeze_excel_header": _normalize_bool(export.get("freeze_excel_header"), defaults["freeze_excel_header"]),
        "auto_fit_excel_columns": _normalize_bool(export.get("auto_fit_excel_columns"), defaults["auto_fit_excel_columns"]),
    }
    if normalized["export_action_mode"] not in {"separate_buttons", "single_button", "button_with_dropdown"}:
        normalized["export_action_mode"] = defaults["export_action_mode"]
    if normalized["default_export_format"] not in {"pdf", "excel", "csv", "print"}:
        normalized["default_export_format"] = defaults["default_export_format"]
    if normalized["default_orientation"] not in {"portrait", "landscape"}:
        normalized["default_orientation"] = defaults["default_orientation"]
    if normalized["header_density"] not in {"full", "compact", "minimal"}:
        normalized["header_density"] = defaults["header_density"]
    if normalized["metadata_visibility"] not in {"full", "compact", "hide"}:
        normalized["metadata_visibility"] = defaults["metadata_visibility"]
    return normalized


def _normalize_report_defaults_settings(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_group_by": str(report.get("default_group_by") or defaults["default_group_by"]).strip().lower(),
        "default_view_type": str(report.get("default_view_type") or defaults["default_view_type"]).strip().lower(),
        "include_zero_balances": _normalize_bool(report.get("include_zero_balances"), defaults["include_zero_balances"]),
        "include_opening": _normalize_bool(report.get("include_opening"), defaults["include_opening"]),
        "include_movement": _normalize_bool(report.get("include_movement"), defaults["include_movement"]),
        "include_closing": _normalize_bool(report.get("include_closing"), defaults["include_closing"]),
        "posted_only": _normalize_bool(report.get("posted_only"), defaults["posted_only"]),
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
    }
    if normalized["default_group_by"] not in {"ledger", "accounthead", "accounttype"}:
        normalized["default_group_by"] = defaults["default_group_by"]
    if normalized["default_view_type"] not in {"summary", "detailed"}:
        normalized["default_view_type"] = defaults["default_view_type"]
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    return normalized


def _normalize_trial_balance_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in TRIAL_BALANCE_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_trial_balance_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_report_defaults_settings(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["report_defaults"],
        ),
        "columns": _normalize_trial_balance_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_ledger_book_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in LEDGER_BOOK_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_ledger_book_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
    }
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    return normalized


def _normalize_ledger_book_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_ledger_book_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_ledger_book_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_ledger_summary_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in LEDGER_SUMMARY_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_ledger_summary_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_group_by": str(report.get("default_group_by") or defaults["default_group_by"]).strip().lower(),
        "default_view_type": str(report.get("default_view_type") or defaults["default_view_type"]).strip().lower(),
        "include_zero_balances": _normalize_bool(report.get("include_zero_balances"), defaults["include_zero_balances"]),
        "posted_only": _normalize_bool(report.get("posted_only"), defaults["posted_only"]),
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
    }
    if normalized["default_group_by"] not in {"ledger", "accounthead", "accounttype"}:
        normalized["default_group_by"] = defaults["default_group_by"]
    if normalized["default_view_type"] not in {"summary", "detailed"}:
        normalized["default_view_type"] = defaults["default_view_type"]
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    return normalized


def _normalize_ledger_summary_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_ledger_summary_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_ledger_summary_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_profit_loss_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in PROFIT_LOSS_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_profit_loss_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_view_type": str(report.get("default_view_type") or defaults["default_view_type"]).strip().lower(),
        "default_group_by": str(report.get("default_group_by") or defaults["default_group_by"]).strip().lower(),
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
        "posted_only": _normalize_bool(report.get("posted_only"), defaults["posted_only"]),
        "hide_zero_rows": _normalize_bool(report.get("hide_zero_rows"), defaults["hide_zero_rows"]),
        "stock_valuation_mode": str(report.get("stock_valuation_mode") or defaults["stock_valuation_mode"]).strip().lower(),
        "stock_valuation_method": str(report.get("stock_valuation_method") or defaults["stock_valuation_method"]).strip().lower(),
    }
    if normalized["default_view_type"] not in {"summary", "detailed"}:
        normalized["default_view_type"] = defaults["default_view_type"]
    if normalized["default_group_by"] not in {"ledger", "accounthead", "accounttype"}:
        normalized["default_group_by"] = defaults["default_group_by"]
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    if normalized["stock_valuation_mode"] not in {"auto", "gl", "valuation", "none"}:
        normalized["stock_valuation_mode"] = defaults["stock_valuation_mode"]
    if normalized["stock_valuation_method"] not in {"fifo", "lifo", "mwa", "wac", "latest"}:
        normalized["stock_valuation_method"] = defaults["stock_valuation_method"]
    return normalized


def _normalize_profit_loss_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_profit_loss_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_profit_loss_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_balance_sheet_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in BALANCE_SHEET_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_balance_sheet_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_view_type": str(report.get("default_view_type") or defaults["default_view_type"]).strip().lower(),
        "default_group_by": str(report.get("default_group_by") or defaults["default_group_by"]).strip().lower(),
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
        "posted_only": _normalize_bool(report.get("posted_only"), defaults["posted_only"]),
        "hide_zero_rows": _normalize_bool(report.get("hide_zero_rows"), defaults["hide_zero_rows"]),
        "stock_valuation_mode": str(report.get("stock_valuation_mode") or defaults["stock_valuation_mode"]).strip().lower(),
        "stock_valuation_method": str(report.get("stock_valuation_method") or defaults["stock_valuation_method"]).strip().lower(),
    }
    if normalized["default_view_type"] not in {"summary", "detailed"}:
        normalized["default_view_type"] = defaults["default_view_type"]
    if normalized["default_group_by"] not in {"ledger", "accounthead", "accounttype"}:
        normalized["default_group_by"] = defaults["default_group_by"]
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    if normalized["stock_valuation_mode"] not in {"auto", "gl", "valuation", "none"}:
        normalized["stock_valuation_mode"] = defaults["stock_valuation_mode"]
    if normalized["stock_valuation_method"] not in {"fifo", "lifo", "mwa", "wac", "latest"}:
        normalized["stock_valuation_method"] = defaults["stock_valuation_method"]
    return normalized


def _normalize_balance_sheet_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_balance_sheet_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_balance_sheet_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_trading_account_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in TRADING_ACCOUNT_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_trading_account_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_view_type": str(report.get("default_view_type") or defaults["default_view_type"]).strip().lower(),
        "default_group_by": str(report.get("default_group_by") or defaults["default_group_by"]).strip().lower(),
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
        "posted_only": _normalize_bool(report.get("posted_only"), defaults["posted_only"]),
        "hide_zero_rows": _normalize_bool(report.get("hide_zero_rows"), defaults["hide_zero_rows"]),
        "stock_valuation_method": str(report.get("stock_valuation_method") or defaults["stock_valuation_method"]).strip().lower(),
    }
    if normalized["default_view_type"] not in {"summary", "detailed"}:
        normalized["default_view_type"] = defaults["default_view_type"]
    if normalized["default_group_by"] not in {"ledger", "accounthead", "accounttype"}:
        normalized["default_group_by"] = defaults["default_group_by"]
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    if normalized["stock_valuation_method"] not in {"fifo", "lifo", "mwa", "wac", "latest"}:
        normalized["stock_valuation_method"] = defaults["stock_valuation_method"]
    return normalized


def _normalize_trading_account_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_trading_account_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_trading_account_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_daybook_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in DAYBOOK_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_daybook_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
    }
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    return normalized


def _normalize_daybook_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_daybook_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_daybook_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def _normalize_cashbook_columns(columns: dict, defaults: dict) -> dict:
    normalized: dict[str, dict] = {}
    used_orders = set()
    next_order = 1

    for key in CASHBOOK_COLUMN_KEYS:
        column_input = columns.get(key) if isinstance(columns, dict) else {}
        if not isinstance(column_input, dict):
            column_input = {}
        column_default = defaults[key]
        mandatory = _normalize_bool(column_input.get("mandatory"), column_default["mandatory"])
        export_visible = _normalize_bool(column_input.get("export_visible"), column_default["export_visible"])
        if mandatory:
            export_visible = True
        display_order = column_input.get("display_order", column_default["display_order"])
        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            display_order = column_default["display_order"]
        if display_order in used_orders or display_order < 1:
            while next_order in used_orders:
                next_order += 1
            display_order = next_order
        used_orders.add(display_order)
        next_order = max(next_order, display_order + 1)
        normalized[key] = {
            "export_visible": export_visible,
            "display_order": display_order,
            "mandatory": mandatory,
        }
    return normalized


def _normalize_cashbook_report_defaults(report: dict, defaults: dict) -> dict:
    normalized = {
        "default_sort_order": str(report.get("default_sort_order") or defaults["default_sort_order"]).strip().lower(),
    }
    if normalized["default_sort_order"] not in {"asc", "desc"}:
        normalized["default_sort_order"] = defaults["default_sort_order"]
    return normalized


def _normalize_cashbook_override(override: dict, defaults: dict) -> dict:
    override = override if isinstance(override, dict) else {}
    return {
        "enabled": _normalize_bool(override.get("enabled"), defaults["enabled"]),
        "general_display": _normalize_general_display_settings(
            override.get("general_display") if isinstance(override.get("general_display"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["general_display"],
        ),
        "export_layout": _normalize_export_layout_settings(
            override.get("export_layout") if isinstance(override.get("export_layout"), dict) else {},
            FINANCIAL_HUB_SETTINGS_DEFAULTS["export_layout"],
        ),
        "report_defaults": _normalize_cashbook_report_defaults(
            override.get("report_defaults") if isinstance(override.get("report_defaults"), dict) else {},
            defaults["report_defaults"],
        ),
        "columns": _normalize_cashbook_columns(
            override.get("columns") if isinstance(override.get("columns"), dict) else {},
            defaults["columns"],
        ),
    }


def normalize_financial_hub_settings_payload(payload) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    defaults = deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS)
    general = payload.get("general_display") if isinstance(payload.get("general_display"), dict) else {}
    export = payload.get("export_layout") if isinstance(payload.get("export_layout"), dict) else {}
    report = payload.get("report_defaults") if isinstance(payload.get("report_defaults"), dict) else {}
    report_overrides = payload.get("report_overrides") if isinstance(payload.get("report_overrides"), dict) else {}

    return {
        "general_display": _normalize_general_display_settings(general, defaults["general_display"]),
        "export_layout": _normalize_export_layout_settings(export, defaults["export_layout"]),
        "report_defaults": _normalize_report_defaults_settings(report, defaults["report_defaults"]),
        "report_overrides": {
            "trial_balance": _normalize_trial_balance_override(
                report_overrides.get("trial_balance"),
                defaults["report_overrides"]["trial_balance"],
            ),
            "ledger_book": _normalize_ledger_book_override(
                report_overrides.get("ledger_book"),
                defaults["report_overrides"]["ledger_book"],
            ),
            "ledger_summary": _normalize_ledger_summary_override(
                report_overrides.get("ledger_summary"),
                defaults["report_overrides"]["ledger_summary"],
            ),
            "profit_loss": _normalize_profit_loss_override(
                report_overrides.get("profit_loss"),
                defaults["report_overrides"]["profit_loss"],
            ),
            "balance_sheet": _normalize_balance_sheet_override(
                report_overrides.get("balance_sheet"),
                defaults["report_overrides"]["balance_sheet"],
            ),
            "trading_account": _normalize_trading_account_override(
                report_overrides.get("trading_account"),
                defaults["report_overrides"]["trading_account"],
            ),
            "daybook": _normalize_daybook_override(
                report_overrides.get("daybook"),
                defaults["report_overrides"]["daybook"],
            ),
            "cashbook": _normalize_cashbook_override(
                report_overrides.get("cashbook"),
                defaults["report_overrides"]["cashbook"],
            ),
        },
    }


def get_financial_hub_settings_payload(*, user, entity_id) -> dict:
    preference = get_user_report_preference(
        user=user,
        entity_id=entity_id,
        report_code=FINANCIAL_HUB_SETTINGS_REPORT_CODE,
    )
    return normalize_financial_hub_settings_payload(preference.payload if preference else {})


def get_effective_trial_balance_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": deepcopy(normalized["report_defaults"]),
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["trial_balance"]["columns"]),
    }
    trial_balance = (
        normalized.get("report_overrides", {}).get("trial_balance")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if trial_balance.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], trial_balance.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], trial_balance.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], trial_balance.get("report_defaults") or {})
        effective["columns"] = _normalize_trial_balance_columns(
            trial_balance.get("columns") or {},
            effective["columns"],
        )
    return effective


def get_visible_trial_balance_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_trial_balance_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["trial_balance"]["columns"],
            )
        }
    else:
        effective = get_effective_trial_balance_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_ledger_book_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": {"default_sort_order": normalized["report_defaults"]["default_sort_order"]},
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["ledger_book"]["columns"]),
    }
    ledger_book = (
        normalized.get("report_overrides", {}).get("ledger_book")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if ledger_book.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], ledger_book.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], ledger_book.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], ledger_book.get("report_defaults") or {})
        effective["columns"] = _normalize_ledger_book_columns(
            ledger_book.get("columns") or {},
            effective["columns"],
        )
    return effective


def get_visible_ledger_book_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_ledger_book_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["ledger_book"]["columns"],
            )
        }
    else:
        effective = get_effective_ledger_book_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_profit_loss_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["profit_loss"]["report_defaults"]),
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["profit_loss"]["columns"]),
    }
    profit_loss = (
        normalized.get("report_overrides", {}).get("profit_loss")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if profit_loss.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], profit_loss.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], profit_loss.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], profit_loss.get("report_defaults") or {})
        effective["columns"] = _normalize_profit_loss_columns(
            profit_loss.get("columns") or {},
            effective["columns"],
        )
    return effective


def get_visible_profit_loss_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_profit_loss_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["profit_loss"]["columns"],
            )
        }
    else:
        effective = get_effective_profit_loss_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_ledger_summary_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["ledger_summary"]["report_defaults"]),
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["ledger_summary"]["columns"]),
    }
    ledger_summary = (
        normalized.get("report_overrides", {}).get("ledger_summary")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if ledger_summary.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], ledger_summary.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], ledger_summary.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], ledger_summary.get("report_defaults") or {})
        effective["columns"] = _normalize_ledger_summary_columns(
            ledger_summary.get("columns") or {},
            effective["columns"],
        )
    return effective


def get_visible_ledger_summary_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_ledger_summary_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["ledger_summary"]["columns"],
            )
        }
    else:
        effective = get_effective_ledger_summary_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_balance_sheet_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["balance_sheet"]["report_defaults"]),
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["balance_sheet"]["columns"]),
    }
    balance_sheet = (
        normalized.get("report_overrides", {}).get("balance_sheet")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if balance_sheet.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], balance_sheet.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], balance_sheet.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], balance_sheet.get("report_defaults") or {})
        effective["columns"] = _normalize_balance_sheet_columns(
            balance_sheet.get("columns") or {},
            effective["columns"],
        )
    return effective


def get_visible_balance_sheet_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_balance_sheet_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["balance_sheet"]["columns"],
            )
        }
    else:
        effective = get_effective_balance_sheet_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_trading_account_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["trading_account"]["report_defaults"]),
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["trading_account"]["columns"]),
    }
    trading_account = (
        normalized.get("report_overrides", {}).get("trading_account")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if trading_account.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], trading_account.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], trading_account.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], trading_account.get("report_defaults") or {})
        effective["columns"] = _normalize_trading_account_columns(
            trading_account.get("columns") or {},
            effective["columns"],
        )
    return effective


def get_visible_trading_account_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_trading_account_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["trading_account"]["columns"],
            )
        }
    else:
        effective = get_effective_trading_account_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_daybook_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": {"default_sort_order": normalized["report_defaults"]["default_sort_order"]},
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["daybook"]["columns"]),
    }
    daybook = (
        normalized.get("report_overrides", {}).get("daybook")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if daybook.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], daybook.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], daybook.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], daybook.get("report_defaults") or {})
        effective["columns"] = _normalize_daybook_columns(daybook.get("columns") or {}, effective["columns"])
    return effective


def get_visible_daybook_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_daybook_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["daybook"]["columns"],
            )
        }
    else:
        effective = get_effective_daybook_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_effective_cashbook_settings(settings: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(settings or {})
    effective = {
        "general_display": deepcopy(normalized["general_display"]),
        "export_layout": deepcopy(normalized["export_layout"]),
        "report_defaults": {"default_sort_order": normalized["report_defaults"]["default_sort_order"]},
        "columns": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["cashbook"]["columns"]),
    }
    cashbook = (
        normalized.get("report_overrides", {}).get("cashbook")
        if isinstance(normalized.get("report_overrides"), dict)
        else None
    ) or {}
    if cashbook.get("enabled"):
        effective["general_display"] = _merge_dict(effective["general_display"], cashbook.get("general_display") or {})
        effective["export_layout"] = _merge_dict(effective["export_layout"], cashbook.get("export_layout") or {})
        effective["report_defaults"] = _merge_dict(effective["report_defaults"], cashbook.get("report_defaults") or {})
        effective["columns"] = _normalize_cashbook_columns(cashbook.get("columns") or {}, effective["columns"])
    return effective


def get_visible_cashbook_columns(settings: dict) -> list[str]:
    if isinstance(settings, dict) and isinstance(settings.get("columns"), dict) and "general_display" in settings:
        effective = {
            "columns": _normalize_cashbook_columns(
                settings.get("columns") or {},
                FINANCIAL_HUB_SETTINGS_DEFAULTS["report_overrides"]["cashbook"]["columns"],
            )
        }
    else:
        effective = get_effective_cashbook_settings(settings)
    columns = effective.get("columns") or {}
    ordered = sorted(
        (
            (key, config if isinstance(config, dict) else {})
            for key, config in columns.items()
            if isinstance(config, dict) and config.get("export_visible")
        ),
        key=lambda item: (int(item[1].get("display_order", 999)), item[0]),
    )
    return [key for key, _config in ordered]


def get_financial_hub_settings_response(*, user, entity_id) -> dict:
    preference = get_user_report_preference(
        user=user,
        entity_id=entity_id,
        report_code=FINANCIAL_HUB_SETTINGS_REPORT_CODE,
    )
    payload = normalize_financial_hub_settings_payload(preference.payload if preference else {})
    effective = _merge_dict(FINANCIAL_HUB_SETTINGS_DEFAULTS, payload)
    effective["trial_balance"] = get_effective_trial_balance_settings(payload)
    effective["ledger_book"] = get_effective_ledger_book_settings(payload)
    effective["ledger_summary"] = get_effective_ledger_summary_settings(payload)
    effective["profit_loss"] = get_effective_profit_loss_settings(payload)
    effective["balance_sheet"] = get_effective_balance_sheet_settings(payload)
    effective["trading_account"] = get_effective_trading_account_settings(payload)
    effective["daybook"] = get_effective_daybook_settings(payload)
    effective["cashbook"] = get_effective_cashbook_settings(payload)
    return {
        "entity": int(entity_id),
        "report_code": FINANCIAL_HUB_SETTINGS_REPORT_CODE,
        "defaults": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS),
        "payload": payload,
        "effective": effective,
        "updated_at": getattr(preference, "updated_at", None),
    }


def save_financial_hub_settings(*, user, entity: Entity, payload: dict) -> dict:
    normalized = normalize_financial_hub_settings_payload(payload)
    preference = upsert_user_report_preference(
        user=user,
        entity=entity,
        report_code=FINANCIAL_HUB_SETTINGS_REPORT_CODE,
        payload=normalized,
    )
    effective = _merge_dict(FINANCIAL_HUB_SETTINGS_DEFAULTS, normalized)
    effective["trial_balance"] = get_effective_trial_balance_settings(normalized)
    effective["ledger_book"] = get_effective_ledger_book_settings(normalized)
    effective["ledger_summary"] = get_effective_ledger_summary_settings(normalized)
    effective["profit_loss"] = get_effective_profit_loss_settings(normalized)
    effective["balance_sheet"] = get_effective_balance_sheet_settings(normalized)
    effective["trading_account"] = get_effective_trading_account_settings(normalized)
    effective["daybook"] = get_effective_daybook_settings(normalized)
    effective["cashbook"] = get_effective_cashbook_settings(normalized)
    return {
        "entity": entity.id,
        "report_code": FINANCIAL_HUB_SETTINGS_REPORT_CODE,
        "defaults": deepcopy(FINANCIAL_HUB_SETTINGS_DEFAULTS),
        "payload": normalized,
        "effective": effective,
        "updated_at": preference.updated_at,
    }


def _format_fixed(amount: Decimal, decimals: int) -> str:
    quant = Decimal("1") if decimals == 0 else Decimal(f"1.{'0' * decimals}")
    return f"{amount.quantize(quant, rounding=ROUND_HALF_UP):,.{decimals}f}"


def format_financial_hub_amount(value, *, settings: dict) -> str:
    general = (settings or {}).get("general_display") or {}
    decimals = int(general.get("decimal_places", 2))
    unit = general.get("amount_display_unit", "actual")
    zero_display = general.get("zero_value_display", "zero")
    negative_style = general.get("negative_number_style", "minus")
    factor = AMOUNT_UNIT_FACTORS.get(unit, Decimal("1"))
    amount = Decimal(str(value or 0))
    scaled = amount / factor if factor else amount
    if scaled == 0:
        if zero_display == "blank":
            return ""
        if zero_display == "dash":
            return "-"
        return _format_fixed(Decimal("0"), decimals)
    formatted = _format_fixed(abs(scaled), decimals)
    if scaled < 0:
        return f"({formatted})" if negative_style == "brackets" else f"-{formatted}"
    return formatted


def format_financial_hub_balance(value, *, settings: dict) -> str:
    general = (settings or {}).get("general_display") or {}
    balance_style = general.get("balance_style", "dr_cr")
    zero_display = general.get("zero_value_display", "zero")
    amount = Decimal(str(value or 0))
    formatted = format_financial_hub_amount(amount, settings=settings)
    if amount == 0:
        return formatted if formatted else ("" if zero_display == "blank" else "-" if zero_display == "dash" else "0.00")
    if balance_style == "signed":
        return formatted
    side = "Dr" if amount >= 0 else "Cr"
    clean = formatted.lstrip("-")
    if clean.startswith("(") and clean.endswith(")"):
        clean = clean[1:-1]
    return f"{clean} {side}"


def financial_hub_amount_unit_label(settings: dict) -> str:
    unit = ((settings or {}).get("general_display") or {}).get("amount_display_unit", "actual")
    return AMOUNT_UNIT_LABELS.get(unit, "Actual")


def apply_amount_display_unit_override(settings: dict, amount_display_unit: str | None) -> dict:
    overridden = deepcopy(settings or {})
    if not amount_display_unit:
        return overridden

    unit = str(amount_display_unit).strip().lower()
    if unit not in AMOUNT_UNIT_FACTORS:
        return overridden

    general = overridden.setdefault("general_display", {})
    general["amount_display_unit"] = unit
    return overridden
