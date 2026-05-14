from __future__ import annotations

from copy import deepcopy

from entity.models import Entity
from reports.services.report_preferences import get_user_report_preference, upsert_user_report_preference


PAYABLES_SETTINGS_REPORT_CODE = "payables_settings"

PAYABLES_SETTINGS_DEFAULTS = {
    "global_defaults": {
        "default_aging_basis": "due_date",
        "default_view_mode": "summary",
        "default_page_size": 50,
        "posted_only": True,
        "include_traceability": False,
        "currency_code": "INR",
    },
    "display_preferences": {
        "amount_unit": "actual",
        "decimal_places": 2,
        "rounding_mode": "half_up",
        "negative_number_style": "minus",
        "show_zero_as_dash": False,
        "date_format": "dd-mm-yyyy",
    },
    "export_defaults": {
        "default_format": "excel",
        "include_filters": True,
        "freeze_header": True,
        "show_generated_on": True,
        "include_company_header": True,
        "include_report_summary": True,
        "include_applied_settings": True,
    },
    "filter_defaults": {
        "exclude_cancelled": True,
        "exclude_drafts": True,
        "include_adjustment_entries": True,
    },
    "thresholds": {
        "overdue_days_warning": 30,
        "credit_limit_breach_warning": True,
        "negative_balance_warning": True,
    },
    "report_overrides": {
        "vendor_outstanding": {
            "default_sort_by": "outstanding",
            "default_sort_order": "desc",
            "columns": [
                "vendor_name",
                "vendor_code",
                "opening",
                "bill_amount",
                "payment_amount",
                "outstanding",
                "bucket_0_30",
                "bucket_31_60",
                "bucket_61_90",
                "bucket_91_180",
                "bucket_181_plus",
                "drilldown",
            ],
        },
        "ap_aging": {
            "default_sort_by": "overdue_amount",
            "default_sort_order": "desc",
            "columns": [
                "vendor_name",
                "total_amount",
                "amount_paid",
                "total_balance",
                "current",
                "bucket_1_30",
                "bucket_31_60",
                "bucket_61_90",
                "bucket_90_plus",
                "drilldown",
            ],
        },
        "vendor_ledger_statement": {
            "include_opening": True,
            "include_running_balance": True,
            "columns": [
                "transaction_date",
                "document_number",
                "document_type",
                "reference",
                "debit",
                "credit",
                "running_balance",
                "drilldown",
            ],
        },
        "upcoming_payments_calendar": {
            "overdue_only": False,
            "default_window_days": 30,
            "columns": [
                "vendor_name",
                "vendor_code",
                "bill_number",
                "bill_date",
                "due_date",
                "days_to_due",
                "payment_status",
                "balance",
                "reference",
                "drilldown",
            ],
        },
    },
}

PAYABLES_MANDATORY_COLUMNS = {
    "vendor_outstanding": ("vendor_name", "outstanding", "drilldown"),
    "ap_aging": ("vendor_name", "total_balance", "drilldown"),
    "vendor_ledger_statement": ("transaction_date", "running_balance", "drilldown"),
    "upcoming_payments_calendar": ("vendor_name", "balance", "drilldown"),
}


def _as_bool(value, *, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_int(value, *, default, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_choice(value, *, default, allowed):
    parsed = str(value or "").strip().lower()
    return parsed if parsed in allowed else default


def _as_string(value, *, default):
    parsed = str(value or "").strip()
    return parsed or default


def _as_column_list(value, *, default):
    if not isinstance(value, list):
        return list(default)
    cleaned = []
    for item in value:
        item_value = str(item or "").strip()
        if item_value and item_value not in cleaned:
            cleaned.append(item_value)
    return cleaned or list(default)


def normalize_payables_settings_payload(payload) -> dict:
    defaults = deepcopy(PAYABLES_SETTINGS_DEFAULTS)
    source = payload if isinstance(payload, dict) else {}

    global_defaults = source.get("global_defaults") if isinstance(source.get("global_defaults"), dict) else {}
    display_preferences = source.get("display_preferences") if isinstance(source.get("display_preferences"), dict) else {}
    export_defaults = source.get("export_defaults") if isinstance(source.get("export_defaults"), dict) else {}
    filter_defaults = source.get("filter_defaults") if isinstance(source.get("filter_defaults"), dict) else {}
    thresholds = source.get("thresholds") if isinstance(source.get("thresholds"), dict) else {}
    report_overrides = source.get("report_overrides") if isinstance(source.get("report_overrides"), dict) else {}

    defaults["global_defaults"]["default_aging_basis"] = _as_choice(
        global_defaults.get("default_aging_basis"),
        default=defaults["global_defaults"]["default_aging_basis"],
        allowed={"bill_date", "due_date"},
    )
    defaults["global_defaults"]["default_view_mode"] = _as_choice(
        global_defaults.get("default_view_mode"),
        default=defaults["global_defaults"]["default_view_mode"],
        allowed={"summary", "detailed"},
    )
    defaults["global_defaults"]["default_page_size"] = _as_int(
        global_defaults.get("default_page_size"),
        default=defaults["global_defaults"]["default_page_size"],
        minimum=10,
        maximum=500,
    )
    defaults["global_defaults"]["posted_only"] = _as_bool(
        global_defaults.get("posted_only"), default=defaults["global_defaults"]["posted_only"]
    )
    defaults["global_defaults"]["include_traceability"] = _as_bool(
        global_defaults.get("include_traceability"), default=defaults["global_defaults"]["include_traceability"]
    )
    defaults["global_defaults"]["currency_code"] = _as_string(
        global_defaults.get("currency_code"), default=defaults["global_defaults"]["currency_code"]
    )[:8].upper()

    defaults["display_preferences"]["amount_unit"] = _as_choice(
        display_preferences.get("amount_unit"),
        default=defaults["display_preferences"]["amount_unit"],
        allowed={"actual", "thousand", "lakh", "million", "crore"},
    )
    defaults["display_preferences"]["decimal_places"] = _as_int(
        display_preferences.get("decimal_places"),
        default=defaults["display_preferences"]["decimal_places"],
        minimum=0,
        maximum=6,
    )
    defaults["display_preferences"]["rounding_mode"] = _as_choice(
        display_preferences.get("rounding_mode"),
        default=defaults["display_preferences"]["rounding_mode"],
        allowed={"half_up", "half_even", "floor", "ceil"},
    )
    defaults["display_preferences"]["negative_number_style"] = _as_choice(
        display_preferences.get("negative_number_style"),
        default=defaults["display_preferences"]["negative_number_style"],
        allowed={"minus", "parentheses"},
    )
    defaults["display_preferences"]["show_zero_as_dash"] = _as_bool(
        display_preferences.get("show_zero_as_dash"), default=defaults["display_preferences"]["show_zero_as_dash"]
    )
    defaults["display_preferences"]["date_format"] = _as_choice(
        display_preferences.get("date_format"),
        default=defaults["display_preferences"]["date_format"],
        allowed={"dd-mm-yyyy", "mm-dd-yyyy", "yyyy-mm-dd"},
    )

    format_value = str(export_defaults.get("default_format", "")).strip().lower()
    defaults["export_defaults"]["default_format"] = format_value if format_value in {"excel", "csv", "pdf", "print"} else "excel"
    defaults["export_defaults"]["include_filters"] = _as_bool(
        export_defaults.get("include_filters"), default=defaults["export_defaults"]["include_filters"]
    )
    defaults["export_defaults"]["freeze_header"] = _as_bool(
        export_defaults.get("freeze_header"), default=defaults["export_defaults"]["freeze_header"]
    )
    defaults["export_defaults"]["show_generated_on"] = _as_bool(
        export_defaults.get("show_generated_on"), default=defaults["export_defaults"]["show_generated_on"]
    )
    defaults["export_defaults"]["include_company_header"] = _as_bool(
        export_defaults.get("include_company_header"), default=defaults["export_defaults"]["include_company_header"]
    )
    defaults["export_defaults"]["include_report_summary"] = _as_bool(
        export_defaults.get("include_report_summary"), default=defaults["export_defaults"]["include_report_summary"]
    )
    defaults["export_defaults"]["include_applied_settings"] = _as_bool(
        export_defaults.get("include_applied_settings"), default=defaults["export_defaults"]["include_applied_settings"]
    )

    defaults["filter_defaults"]["exclude_cancelled"] = _as_bool(
        filter_defaults.get("exclude_cancelled"), default=defaults["filter_defaults"]["exclude_cancelled"]
    )
    defaults["filter_defaults"]["exclude_drafts"] = _as_bool(
        filter_defaults.get("exclude_drafts"), default=defaults["filter_defaults"]["exclude_drafts"]
    )
    defaults["filter_defaults"]["include_adjustment_entries"] = _as_bool(
        filter_defaults.get("include_adjustment_entries"), default=defaults["filter_defaults"]["include_adjustment_entries"]
    )

    defaults["thresholds"]["overdue_days_warning"] = _as_int(
        thresholds.get("overdue_days_warning"),
        default=defaults["thresholds"]["overdue_days_warning"],
        minimum=0,
        maximum=365,
    )
    defaults["thresholds"]["credit_limit_breach_warning"] = _as_bool(
        thresholds.get("credit_limit_breach_warning"), default=defaults["thresholds"]["credit_limit_breach_warning"]
    )
    defaults["thresholds"]["negative_balance_warning"] = _as_bool(
        thresholds.get("negative_balance_warning"), default=defaults["thresholds"]["negative_balance_warning"]
    )

    for code, code_defaults in defaults["report_overrides"].items():
        candidate = report_overrides.get(code) if isinstance(report_overrides.get(code), dict) else {}
        for key, default_value in code_defaults.items():
            if isinstance(default_value, bool):
                code_defaults[key] = _as_bool(candidate.get(key), default=default_value)
            elif isinstance(default_value, int):
                code_defaults[key] = _as_int(candidate.get(key), default=default_value, minimum=0, maximum=1000)
            elif isinstance(default_value, list):
                code_defaults[key] = _as_column_list(candidate.get(key), default=default_value)
            else:
                code_defaults[key] = str(candidate.get(key, default_value)).strip() or default_value

        # Protect required report columns even for direct API patches.
        columns = code_defaults.get("columns")
        if isinstance(columns, list):
            mandatory = PAYABLES_MANDATORY_COLUMNS.get(code, set())
            if mandatory:
                seen = set(columns)
                for key in mandatory:
                    if key not in seen:
                        columns.append(key)
                        seen.add(key)

    return defaults


def get_payables_settings_response(*, user, entity_id) -> dict:
    defaults = normalize_payables_settings_payload(PAYABLES_SETTINGS_DEFAULTS)
    preference = get_user_report_preference(user=user, entity_id=entity_id, report_code=PAYABLES_SETTINGS_REPORT_CODE)
    payload = normalize_payables_settings_payload(preference.payload if preference else {})
    return {
        "entity": int(entity_id),
        "report_code": PAYABLES_SETTINGS_REPORT_CODE,
        "defaults": defaults,
        "payload": payload,
        "updated_at": preference.updated_at if preference else None,
    }


def save_payables_settings(*, user, entity: Entity, payload: dict) -> dict:
    normalized = normalize_payables_settings_payload(payload or {})
    preference = upsert_user_report_preference(
        user=user,
        entity=entity,
        report_code=PAYABLES_SETTINGS_REPORT_CODE,
        payload=normalized,
    )
    return {
        "entity": entity.id,
        "report_code": PAYABLES_SETTINGS_REPORT_CODE,
        "defaults": normalize_payables_settings_payload(PAYABLES_SETTINGS_DEFAULTS),
        "payload": normalized,
        "updated_at": preference.updated_at,
    }
