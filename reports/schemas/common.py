from __future__ import annotations


def build_report_envelope(
    *,
    report_code: str,
    report_name: str,
    payload: dict,
    filters: dict,
    defaults: dict,
) -> dict:
    payload["report_code"] = report_code
    payload["report_name"] = report_name
    payload["filters"] = filters
    payload["applied_filters"] = filters
    payload["display"] = {
        "decimal_places": defaults["decimal_places"],
        "show_zero_balances_default": defaults["show_zero_balances_default"],
        "show_opening_balance_default": defaults["show_opening_balance_default"],
    }
    payload["actions"] = {
        "can_view": True,
        "can_export_excel": True,
        "can_export_pdf": True,
        "can_export_csv": True,
        "can_drilldown": defaults["enable_drilldown"],
    }
    meta = payload.get("_meta") or {}
    if meta.get("available_exports") and "available_exports" not in payload:
        payload["available_exports"] = list(meta["available_exports"])
    if meta.get("available_drilldowns") and "available_drilldowns" not in payload:
        payload["available_drilldowns"] = list(meta["available_drilldowns"])
    return payload
