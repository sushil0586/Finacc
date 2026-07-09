from __future__ import annotations

from decimal import Decimal

from django.http import HttpResponse
from reportlab.lib.pagesizes import A3, A4, landscape
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.financial.export_utils import (
    ExportSection,
    attach_export_actions as _attach_financial_actions,
    build_report_filename,
    filtered_querydict as _filtered_querydict,
    safe_filename as _safe_filename,
    truncate_text as _truncate_text,
    write_csv as _write_csv,
    write_excel as _write_excel,
    write_pdf as _write_pdf,
    write_balance_sheet_statement_pdf,
    write_sectioned_csv,
    write_sectioned_excel,
    write_sectioned_pdf,
)
from reports.api.report_permissions import assert_any_report_permission
from reports.services.financial_hub_settings import (
    financial_hub_amount_unit_label,
    get_effective_balance_sheet_settings,
    get_effective_ledger_summary_settings,
    get_effective_profit_loss_settings,
    get_effective_trading_account_settings,
    format_financial_hub_amount,
    format_financial_hub_balance,
    get_effective_ledger_book_settings,
    get_effective_trial_balance_settings,
    get_financial_hub_settings_payload,
    get_visible_balance_sheet_columns,
    get_visible_ledger_book_columns,
    get_visible_ledger_summary_columns,
    get_visible_profit_loss_columns,
    get_visible_trading_account_columns,
    get_visible_trial_balance_columns,
    apply_amount_display_unit_override,
)
from reports.schemas.common import build_report_envelope
from reports.schemas.financial_reports import FinancialReportScopeSerializer, LedgerBookScopeSerializer
from reports.services.financial.meta import REPORT_DEFAULTS, build_financial_report_meta
from reports.services.financial.ledger_book import build_ledger_book
from reports.services.financial.ledger_summary import build_ledger_summary
from reports.services.financial.reporting_policy import resolve_financial_reporting_policy
from reports.services.financial.statements import build_balance_sheet, build_profit_and_loss
from reports.services.financial.trial_balance import build_trial_balance
from reports.services.trading_account import build_trading_account_dynamic
from reports.selectors.financial import resolve_date_window, resolve_scope_names
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class FinancialReportPermissionMixin:
    required_permission_codes: tuple[str, ...] = ()
    permission_denied_message = "You do not have permission to access this financial report."

    def enforce_report_permission(self, request, *, entity_id: int):
        assert_any_report_permission(
            user=request.user,
            entity_id=entity_id,
            required_permissions=self.required_permission_codes,
            message=self.permission_denied_message,
        )


class _BaseFinancialReportAPIView(FinancialReportPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FinancialReportScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        return scope

    def build_filters(self, scope):
        return {
            "entity": scope["entity"],
            "entityfinid": scope.get("entityfinid"),
            "subentity": scope.get("subentity"),
            "scope_mode": scope.get("scope_mode"),
            "as_on_date": scope.get("as_on_date"),
            "from_date": scope.get("from_date"),
            "to_date": scope.get("to_date"),
            "as_of_date": scope.get("as_of_date"),
            "view_type": scope.get("view_type"),
            "presentation": scope.get("presentation"),
            "account_group": scope.get("account_group"),
            "ledger_ids": scope.get("ledger_ids"),
            "include_zero_balance": scope.get("include_zero_balance", REPORT_DEFAULTS["show_zero_balances_default"]),
            "hide_zero_rows": scope.get("hide_zero_rows", not REPORT_DEFAULTS["show_zero_balances_default"]),
            "group_by": scope.get("group_by"),
            "period_by": scope.get("period_by"),
            "include_opening": scope.get("include_opening"),
            "include_movement": scope.get("include_movement"),
            "include_closing": scope.get("include_closing"),
            "posted_only": scope.get("posted_only", True),
            "stock_valuation_mode": scope.get(
                "stock_valuation_mode",
                REPORT_DEFAULTS["balance_sheet_stock_valuation_mode"],
            ),
            "stock_valuation_method": scope.get(
                "stock_valuation_method",
                REPORT_DEFAULTS["balance_sheet_stock_valuation_method"],
            ),
            "include_zero_balances": scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            "include_inactive_ledgers": scope.get("include_inactive_ledgers", False),
            "search": scope.get("search"),
            "amount_display_unit": scope.get("amount_display_unit"),
            "sort_by": scope.get("sort_by"),
            "sort_order": scope.get("sort_order", "asc"),
            "page": scope.get("page", 1),
            "page_size": scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            "export": scope.get("export"),
        }


def _format_scope_date(value):
    if not value:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _presentation_mode(scope):
    return "statement" if (scope.get("presentation") or "standard").strip().lower() == "statement" else "standard"


def _presentation_label(scope, view_label, group_label=None):
    if _presentation_mode(scope) == "statement":
        base = "Statement view"
    else:
        base = f"{view_label} view"
    if group_label:
        return f"{base} • Grouped by {group_label}"
    return base


def _effective_period_by(scope):
    period_by = scope.get("period_by")
    if period_by:
        return period_by
    if _presentation_mode(scope) == "statement":
        return "year"
    return None




def _format_balance_amount(value, *, decimals=2):
    amount = _parse_decimal(value)
    if amount == 0:
        return f"{amount:.{decimals}f}"
    display = f"{abs(amount):.{decimals}f}"
    return f"{display} {'Dr' if amount >= 0 else 'Cr'}"


def _parse_decimal(value):
    if value is None:
        return Decimal("0")
    text = str(value).strip()
    if not text:
        return Decimal("0")
    text = text.replace(",", "")
    for suffix in (" Dr", " Cr", " DR", " CR", "dr", "cr"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    try:
        return Decimal(text)
    except Exception:
        return Decimal("0")


def _trial_balance_subtitle(scope_names, scope):
    subentity_label = scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")
    scope_label = _humanize_trial_balance_scope(scope.get("scope_mode") or "financial_year")
    group_label = _humanize_trial_balance_group(scope.get("account_group") or scope.get("group_by") or "ledger")
    view_label = _humanize_trial_balance_view(scope.get("view_type") or "summary")
    return (
        f"Entity: {scope_names['entity_name'] or 'Selected entity'} | "
        f"FY: {scope_names['entityfin_name'] or 'Current FY'} | "
        f"Subentity: {subentity_label} | "
        f"Scope: {scope_label} | "
        f"Group: {group_label} | "
        f"View: {view_label}"
    )


def _ledger_book_subtitle(scope_names, scope, ledger):
    subentity_label = scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")
    return (
        f"Entity: {scope_names['entity_name'] or 'Selected entity'} | "
        f"FY: {scope_names['entityfin_name'] or 'Current FY'} | "
        f"Subentity: {subentity_label} | "
        f"Ledger: {ledger.get('name') or 'Selected ledger'} ({ledger.get('ledger_code') or '-'}) | "
        f"Account head: {ledger.get('accounthead_name') or '-'} | "
        f"Account type: {ledger.get('accounttype_name') or '-'} | "
        f"Scope: {scope.get('scope_mode') or 'financial_year'} | "
        f"Sort: {scope.get('sort_by') or 'posting_date'} {scope.get('sort_order') or 'asc'}"
    )


def _trial_balance_flatten_rows(rows, *, depth=0):
    flattened = []
    for row in rows:
        flattened.append((row, depth))
        children = row.get("children") or []
        if children:
            flattened.extend(_trial_balance_flatten_rows(children, depth=depth + 1))
    return flattened


def _trial_balance_row_key(row, *, parent_key="", index=0):
    explicit_key = (
        row.get("group_id")
        or row.get("label")
        or row.get("ledger_id")
        or row.get("accounthead_id")
        or row.get("accounttype_id")
        or row.get("ledger_name")
        or "-"
    )
    return f"{parent_key}|{explicit_key}-{index}"


def _trial_balance_visible_rows(rows, expanded_keys, *, parent_key="", depth=0):
    visible = []
    for index, row in enumerate(rows or []):
        key = _trial_balance_row_key(row, parent_key=parent_key, index=index)
        visible.append((row, depth, key))
        children = row.get("children") or []
        if children and key in expanded_keys:
            visible.extend(
                _trial_balance_visible_rows(
                    children,
                    expanded_keys,
                    parent_key=key,
                    depth=depth + 1,
                )
            )
    return visible


def _parse_expanded_row_keys(request):
    raw_value = request.query_params.get("expanded_keys")
    if raw_value is None:
        return None
    return {item for item in raw_value.split(",") if item}


def _parse_collapsed_sections(request):
    raw_value = request.query_params.get("collapsed_sections")
    if raw_value is None:
        return None
    return {item.strip().lower() for item in raw_value.split(",") if item.strip()}


def _scope_includes_separate_opening(scope) -> bool:
    scope_mode = str(scope.get("scope_mode") or "").strip().lower()
    if scope_mode == "custom":
        return bool(scope.get("include_opening", True))
    if scope_mode in {"financial_year", "month", "quarter", "year", "as_of"}:
        return False
    return bool(scope.get("from_date") and scope.get("to_date") and not scope.get("as_of_date") and scope.get("include_opening", True))


def _trial_balance_scope_includes_opening(scope) -> bool:
    scope_mode = str(scope.get("scope_mode") or "").strip().lower()
    if scope_mode == "custom":
        return True
    if scope_mode in {"financial_year", "month", "quarter", "year", "as_of"}:
        return False
    return bool(scope.get("from_date") and scope.get("to_date") and not scope.get("as_of_date"))


def _trial_balance_export_table(report):
    rows = report.get("rows") or []
    periods = report.get("periods") or []
    flattened = _trial_balance_flatten_rows(rows)
    include_opening = bool(((report.get("reporting") or {}).get("include_opening")))

    headers = [
        "Level",
        "Type",
        "Code",
        "Name",
        "Account Head",
        "Account Type",
        "Debit",
        "Credit",
        "Closing",
        "Abnormal",
    ]
    if include_opening:
        headers.insert(6, "Opening")
    for period in periods:
        label = period.get("period_label") or period.get("label") or period.get("name") or period.get("title") or period.get("key")
        if include_opening:
            headers.extend([
                f"{label} Opening",
                f"{label} Debit",
                f"{label} Credit",
                f"{label} Closing",
            ])
        else:
            headers.extend([
                f"{label} Debit",
                f"{label} Credit",
                f"{label} Closing",
            ])

    table_rows = []
    for row, depth in flattened:
        label = row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name") or "-"
        prefix = ("  " * depth) + label
        row_periods = {str(item.get("key") or item.get("code") or item.get("label") or item.get("name") or ""): item for item in row.get("periods") or []}
        values = [
            depth,
            "Group" if row.get("children") else "Row",
            row.get("ledger_code") or row.get("code") or "",
            prefix,
            row.get("accounthead_name") or "",
            row.get("accounttype_name") or "",
            row.get("debit", "0.00"),
            row.get("credit", "0.00"),
            _format_balance_amount(row.get("closing", "0.00")),
            "Yes" if row.get("is_abnormal_balance") else "No",
        ]
        if include_opening:
            values.insert(6, _format_balance_amount(row.get("opening", "0.00")))
        for period in periods:
            key = str(period.get("period_key") or period.get("key") or period.get("code") or period.get("label") or period.get("name") or "")
            period_row = row_periods.get(key) or {}
            if include_opening:
                values.extend([
                    _format_balance_amount(period_row.get("opening", "0.00")),
                    period_row.get("debit", "0.00"),
                    period_row.get("credit", "0.00"),
                    _format_balance_amount(period_row.get("closing", "0.00")),
                ])
            else:
                values.extend([
                    period_row.get("debit", "0.00"),
                    period_row.get("credit", "0.00"),
                    _format_balance_amount(period_row.get("closing", "0.00")),
                ])
        table_rows.append(values)

    totals = report.get("totals") or {}
    total_row = [
        "",
        "",
        "",
        "Totals",
        "",
        "",
        totals.get("debit", "0.00"),
        totals.get("credit", "0.00"),
        totals.get("closing", "0.00"),
        "",
    ]
    if include_opening:
        total_row.insert(6, totals.get("opening", "0.00"))
    for _period in periods:
        total_row.extend(["", "", "", ""] if include_opening else ["", "", ""])
    table_rows.append(total_row)

    return headers, table_rows


def _trial_balance_presentation_table(report, *, view_type="summary", group_by="ledger", settings=None, expanded_keys=None):
    rows = report.get("rows") or []
    periods = report.get("periods") or []
    normalized_view = (view_type or "summary").strip().lower()
    normalized_group = (group_by or "ledger").strip().lower()
    if expanded_keys is not None:
        base_rows = [(row, depth) for row, depth, _key in _trial_balance_visible_rows(rows, expanded_keys)]
    else:
        base_rows = _trial_balance_flatten_rows(rows) if normalized_view == "detailed" else [(row, 0) for row in rows]

    visible_columns = get_visible_trial_balance_columns(settings or {})
    column_labels = {
        "code": "Code",
        "name": "Name",
        "account_head": "Account Head",
        "account_type": "Account Type",
        "opening": "Opening",
        "debit": "Debit",
        "credit": "Credit",
        "closing": "Closing",
        "abnormal": "Abnormal",
    }
    numeric_column_keys = {"opening", "debit", "credit", "closing"}
    center_column_keys = {"abnormal"}

    headers = [column_labels[key] for key in visible_columns]
    numeric_columns = {index for index, key in enumerate(visible_columns) if key in numeric_column_keys}
    center_columns = {index for index, key in enumerate(visible_columns) if key in center_column_keys}

    for period_index, period in enumerate(periods):
        label = period.get("period_label") or period.get("label") or period.get("name") or period.get("title") or period.get("key")
        start = len(headers)
        headers.extend([
            f"{label} Opening",
            f"{label} Debit",
            f"{label} Credit",
            f"{label} Closing",
        ])
        numeric_columns.update({start, start + 1, start + 2, start + 3})

    table_rows = []
    for row, depth in base_rows:
        label = row.get("label") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name") or "-"
        prefixed_label = f"{'  ' * depth}{label}"
        row_periods = {
            str(item.get("key") or item.get("code") or item.get("label") or item.get("name") or ""): item
            for item in row.get("periods") or []
        }
        code = row.get("ledger_code") or row.get("code") or ""
        account_head_name = row.get("accounthead_name") or ""
        account_type_name = row.get("accounttype_name") or ""
        if normalized_view != "detailed":
            if normalized_group == "accounthead":
                code = ""
                account_head_name = ""
                account_type_name = ""
            elif normalized_group == "accounttype":
                code = ""
                account_head_name = ""
                account_type_name = ""
        base_values = {
            "code": code,
            "name": prefixed_label,
            "account_head": account_head_name,
            "account_type": account_type_name,
            "opening": format_financial_hub_balance(row.get("opening", "0.00"), settings=settings or {}),
            "debit": format_financial_hub_amount(row.get("debit", "0.00"), settings=settings or {}),
            "credit": format_financial_hub_amount(row.get("credit", "0.00"), settings=settings or {}),
            "closing": format_financial_hub_balance(row.get("closing", "0.00"), settings=settings or {}),
            "abnormal": "Yes" if row.get("is_abnormal_balance") else "",
        }
        values = [base_values[key] for key in visible_columns]
        for period in periods:
            key = str(period.get("period_key") or period.get("key") or period.get("code") or period.get("label") or period.get("name") or "")
            period_row = row_periods.get(key) or {}
            values.extend([
                format_financial_hub_balance(period_row.get("opening", "0.00"), settings=settings or {}),
                format_financial_hub_amount(period_row.get("debit", "0.00"), settings=settings or {}),
                format_financial_hub_amount(period_row.get("credit", "0.00"), settings=settings or {}),
                format_financial_hub_balance(period_row.get("closing", "0.00"), settings=settings or {}),
            ])
        table_rows.append(values)

    totals = report.get("totals") or {}
    total_base_values = {
        "code": "",
        "name": "Totals",
        "account_head": "",
        "account_type": "",
        "opening": format_financial_hub_balance(totals.get("opening", "0.00"), settings=settings or {}),
        "debit": format_financial_hub_amount(totals.get("debit", "0.00"), settings=settings or {}),
        "credit": format_financial_hub_amount(totals.get("credit", "0.00"), settings=settings or {}),
        "closing": format_financial_hub_balance(totals.get("closing", "0.00"), settings=settings or {}),
        "abnormal": "",
    }
    total_row = [total_base_values[key] for key in visible_columns]
    for _period in periods:
        total_row.extend(["", "", "", ""])
    table_rows.append(total_row)

    return headers, table_rows, numeric_columns, center_columns


def _trial_balance_statement_pdf_sections(report, *, view_type="summary", group_by="ledger", settings=None, expanded_keys=None):
    periods = report.get("periods") or []
    amount_headers = ["Opening", "Debit", "Credit", "Closing"]

    def _fmt_amount(value):
        return format_financial_hub_amount(value or "0.00", settings=settings or {}) if settings else (value or "0.00")

    def _fmt_balance(value):
        return format_financial_hub_balance(value or "0.00", settings=settings or {}) if settings else (value or "0.00")

    def _amounts_for_row(row):
        values = [
            _fmt_balance(row.get("opening")),
            _fmt_amount(row.get("debit")),
            _fmt_amount(row.get("credit")),
            _fmt_balance(row.get("closing")),
        ]
        for period in periods:
            period_key = str(
                period.get("period_key")
                or period.get("key")
                or period.get("code")
                or period.get("label")
                or period.get("name")
                or ""
            )
            period_row = {}
            for item in row.get("periods") or []:
                item_key = str(
                    item.get("key")
                    or item.get("period_key")
                    or item.get("code")
                    or item.get("label")
                    or item.get("name")
                    or ""
                )
                if item_key == period_key:
                    period_row = item
                    break
            values.extend([
                _fmt_balance(period_row.get("opening")),
                _fmt_amount(period_row.get("debit")),
                _fmt_amount(period_row.get("credit")),
                _fmt_balance(period_row.get("closing")),
            ])
        return values

    for period in periods:
        label = (
            period.get("period_label")
            or period.get("label")
            or period.get("name")
            or period.get("title")
            or period.get("period_key")
            or period.get("key")
            or "Period"
        )
        amount_headers.extend([
            f"{label} Opening",
            f"{label} Debit",
            f"{label} Credit",
            f"{label} Closing",
        ])

    def _row_label(row, depth=0):
        return _statement_indent(
            str(
                row.get("label")
                or row.get("ledger_name")
                or row.get("accounthead_name")
                or row.get("accounttype_name")
                or "-"
            ),
            depth,
        )

    def _flatten_children(rows, depth=0):
        lines = []
        for row in rows or []:
            lines.append({
                "label": _row_label(row, depth),
                "amounts": _amounts_for_row(row),
            })
            if row.get("children"):
                lines.extend(_flatten_children(row.get("children") or [], depth + 1))
        return lines

    normalized_group = (group_by or "ledger").strip().lower()
    leaf_bucket_title = {
        "ledger": "Ledgers",
        "accounthead": "Account Heads",
        "accounttype": "Account Types",
    }.get(normalized_group, "Accounts")

    groups = []
    leaf_lines = []
    if expanded_keys is not None:
        visible_rows = _trial_balance_visible_rows(report.get("rows") or [], expanded_keys)
        index = 0
        while index < len(visible_rows):
            row, depth, key = visible_rows[index]
            if depth > 0:
                index += 1
                continue
            title = (
                row.get("label")
                or row.get("ledger_name")
                or row.get("accounthead_name")
                or row.get("accounttype_name")
                or "-"
            )
            if (row.get("children") or []) and key in expanded_keys:
                lines = []
                index += 1
                while index < len(visible_rows) and visible_rows[index][1] > 0:
                    child_row, child_depth, _child_key = visible_rows[index]
                    lines.append({
                        "label": _row_label(child_row, child_depth - 1),
                        "amounts": _amounts_for_row(child_row),
                    })
                    index += 1
                groups.append({
                    "title": str(title),
                    "lines": lines,
                    "total_label": f"Total {title}",
                    "total_amounts": _amounts_for_row(row),
                })
            else:
                leaf_lines.append({
                    "label": _row_label(row, 0),
                    "amounts": _amounts_for_row(row),
                })
                index += 1
    else:
        for row in report.get("rows") or []:
            children = row.get("children") or []
            if children:
                title = (
                    row.get("label")
                    or row.get("ledger_name")
                    or row.get("accounthead_name")
                    or row.get("accounttype_name")
                    or "-"
                )
                groups.append({
                    "title": str(title),
                    "lines": _flatten_children(children, 0),
                    "total_label": f"Total {title}",
                    "total_amounts": _amounts_for_row(row),
                })
            else:
                leaf_lines.append({
                    "label": _row_label(row, 0),
                    "amounts": _amounts_for_row(row),
                })

    if leaf_lines:
        groups.insert(0, {
            "title": leaf_bucket_title,
            "lines": leaf_lines,
            "total_label": "",
            "total_amounts": [],
        })

    totals = report.get("totals") or {}
    total_amounts = [
        _fmt_balance(totals.get("opening")),
        _fmt_amount(totals.get("debit")),
        _fmt_amount(totals.get("credit")),
        _fmt_balance(totals.get("closing")),
    ]
    for period in periods:
        period_totals = period.get("totals") or {}
        total_amounts.extend([
            _fmt_balance(period_totals.get("opening")),
            _fmt_amount(period_totals.get("debit")),
            _fmt_amount(period_totals.get("credit")),
            _fmt_balance(period_totals.get("closing")),
        ])

    return amount_headers, [
        {
            "title": "Trial Balance",
            "groups": groups,
            "total_label": "Grand Totals",
            "total_amounts": total_amounts,
        }
    ]


def _humanize_trial_balance_scope(value):
    labels = {
        "financial_year": "Financial year",
        "month": "This month",
        "quarter": "This quarter",
        "year": "This year",
        "custom": "Custom range",
        "as_of": "As of date",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "Financial year").replace("_", " ").title())


def _humanize_trial_balance_group(value):
    labels = {
        "ledger": "Ledger",
        "accounthead": "Account head",
        "accounttype": "Account type",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "ledger").replace("_", " ").title())


def _humanize_trial_balance_view(value):
    labels = {
        "summary": "Summary",
        "detailed": "Detailed",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "summary").replace("_", " ").title())


def _trial_balance_export_meta(scope_names, scope, report, settings=None):
    subentity_label = scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")
    total_rows = len(_trial_balance_flatten_rows(report.get("rows") or []))
    scope_label = _humanize_trial_balance_scope(scope.get("scope_mode") or "financial_year")
    group_label = _humanize_trial_balance_group(scope.get("account_group") or scope.get("group_by") or "ledger")
    view_label = _humanize_trial_balance_view(scope.get("view_type") or "summary")
    presentation_label = "Posted only" if scope.get("posted_only", True) else "Posted and draft"
    zero_balance_label = "Zero balances included" if scope.get("include_zero_balances", REPORT_DEFAULTS["show_zero_balances_default"]) else "Zero balances hidden"
    meta_items = [
        ("Entity", scope_names["entity_name"] or "Selected entity"),
        ("Financial Year", scope_names["entityfin_name"] or "Current FY"),
        ("Subentity", subentity_label),
        ("Scope", scope_label),
        ("Presentation", _presentation_label(scope, view_label, group_label)),
        ("Filters", f"{presentation_label} • {zero_balance_label}"),
        ("Amount Unit", financial_hub_amount_unit_label(settings or {})),
        ("Rows", total_rows),
    ]
    if scope.get("search"):
        meta_items.append(("Search", scope.get("search")))
    return meta_items


def _ledger_summary_subtitle(scope_names, scope, report):
    reporting = report.get("reporting") or {}
    parts = [
        scope_names.get("entity_name") or "Selected entity",
        scope_names.get("entityfin_name") or "Current FY",
    ]
    if scope_names.get("subentity_name"):
        parts.append(scope_names["subentity_name"])
    if report.get("from_date") and report.get("to_date"):
        parts.append(f"{_format_scope_date(report.get('from_date'))} to {_format_scope_date(report.get('to_date'))}")
    parts.append(f"Group by {str(reporting.get('group_by') or 'ledger').replace('account', 'account ').title()}")
    parts.append(f"{str(reporting.get('view_type') or 'summary').replace('_', ' ').title()} view")
    return " | ".join(str(part) for part in parts if part)


def _ledger_summary_scope_filename(scope_names, scope):
    date_bits = []
    if scope.get("from_date"):
        date_bits.append(str(scope.get("from_date")))
    if scope.get("to_date"):
        date_bits.append(str(scope.get("to_date")))
    period_label = "_to_".join(date_bits) if date_bits else (scope_names.get("entityfin_name") or "scope")
    return f"{(scope.get('group_by') or scope.get('account_group') or 'ledger')}_{period_label}"


def _ledger_summary_export_meta(scope_names, scope, report, settings=None):
    reporting = report.get("reporting") or {}
    pagination = report.get("pagination") or {}
    return [
        ("Entity", scope_names.get("entity_name") or "Selected entity"),
        ("Financial Year", scope_names.get("entityfin_name") or "Current FY"),
        ("Subentity", scope_names.get("subentity_name") or "All subentities"),
        ("Period", f"{_format_scope_date(report.get('from_date'))} to {_format_scope_date(report.get('to_date'))}"),
        ("Presentation", f"{str(reporting.get('view_type') or 'summary').replace('_', ' ').title()} view"),
        ("Group by", str(reporting.get("group_by") or "ledger").replace("account", "account ").title()),
        ("Posted", "Posted only" if reporting.get("posted_only", True) else "All entries"),
        ("Zero balances", "Included" if reporting.get("include_zero_balances") else "Hidden"),
        ("Rows", str(pagination.get("total_records") or len(report.get("rows") or []))),
        ("Amount Unit", financial_hub_amount_unit_label(settings or {})),
    ]


def _ledger_summary_row_key(row, *, parent_key="", index=0):
    identity = row.get("group_id") or row.get("ledger_id") or row.get("ledger_name") or row.get("label") or index
    return f"{parent_key}/{identity}" if parent_key else str(identity)


def _ledger_summary_visible_rows(rows, expanded_keys, *, parent_key="", depth=0):
    visible = []
    for index, row in enumerate(rows or []):
        key = _ledger_summary_row_key(row, parent_key=parent_key, index=index)
        visible.append((row, depth, key))
        children = row.get("children") or []
        if children and key in expanded_keys:
            visible.extend(_ledger_summary_visible_rows(children, expanded_keys, parent_key=key, depth=depth + 1))
    return visible


def _ledger_summary_flatten_rows(rows, *, parent_key="", depth=0):
    flattened = []
    for index, row in enumerate(rows or []):
        key = _ledger_summary_row_key(row, parent_key=parent_key, index=index)
        flattened.append((row, depth, key))
        children = row.get("children") or []
        if children:
            flattened.extend(_ledger_summary_flatten_rows(children, parent_key=key, depth=depth + 1))
    return flattened


def _ledger_summary_export_table(report, *, settings=None, expanded_keys=None):
    visible_columns = get_visible_ledger_summary_columns(settings or {})
    if not visible_columns:
        visible_columns = ["account_name", "opening", "debit", "credit", "balance"]
    include_opening = bool(((report.get("reporting") or {}).get("include_opening")))
    if not include_opening:
        visible_columns = [key for key in visible_columns if key not in {"opening", "ob_dc"}]
    labels = {
        "account_head": "Account Head",
        "account_name": "Account Name",
        "account_type": "Account Type",
        "opening": "Opening",
        "ob_dc": "OB DC",
        "debit": "Debit",
        "credit": "Credit",
        "balance": "Balance",
        "dc": "DC",
    }
    numeric_keys = {"opening", "debit", "credit", "balance"}
    center_keys = {"ob_dc", "dc"}
    group_by = ((report.get("reporting") or {}).get("group_by") or "ledger").strip().lower()
    view_type = ((report.get("reporting") or {}).get("view_type") or "summary").strip().lower()
    rows = report.get("rows") or []
    if view_type == "detailed":
        flattened = _ledger_summary_visible_rows(rows, expanded_keys) if expanded_keys is not None else _ledger_summary_flatten_rows(rows)
    else:
        flattened = [(row, 0, _ledger_summary_row_key(row, index=index)) for index, row in enumerate(rows)]

    headers = [labels[key] for key in visible_columns]
    table_rows = []
    row_kinds = []
    for row, depth, _row_key in flattened:
        is_group = bool(row.get("children")) or row.get("group_id") is not None
        label = row.get("label") or row.get("ledger_name") or "-"
        name_value = f"{'  ' * depth}{label}"
        account_head_value = row.get("accounthead_name") or row.get("label") if group_by == "accounthead" else row.get("accounthead_name") or "-"
        account_type_value = row.get("accounttype_name") or row.get("label") if group_by == "accounttype" else row.get("accounttype_name") or "-"
        balance_value = {
            "account_head": account_head_value or "-",
            "account_name": name_value,
            "account_type": account_type_value or "-",
            "opening": format_financial_hub_amount(row.get("opening"), settings=settings or {}) if settings else (row.get("opening") or "0.00"),
            "ob_dc": row.get("ob_drcr") or "-",
            "debit": format_financial_hub_amount(row.get("debit"), settings=settings or {}) if settings else (row.get("debit") or "0.00"),
            "credit": format_financial_hub_amount(row.get("credit"), settings=settings or {}) if settings else (row.get("credit") or "0.00"),
            "balance": format_financial_hub_balance(row.get("balance"), settings=settings or {}) if settings else (row.get("balance") or "0.00"),
            "dc": row.get("drcr") or "-",
        }
        table_rows.append([balance_value[key] for key in visible_columns])
        row_kinds.append("group" if is_group and depth == 0 else "detail" if depth > 0 else "group")

    totals = report.get("totals") or {}
    total_values = {
        "account_head": "",
        "account_name": "Totals",
        "account_type": "",
        "opening": format_financial_hub_amount(totals.get("opening", "0.00"), settings=settings or {}) if settings else totals.get("opening", "0.00"),
        "ob_dc": "",
        "debit": format_financial_hub_amount(totals.get("debit", "0.00"), settings=settings or {}) if settings else totals.get("debit", "0.00"),
        "credit": format_financial_hub_amount(totals.get("credit", "0.00"), settings=settings or {}) if settings else totals.get("credit", "0.00"),
        "balance": format_financial_hub_balance(totals.get("balance", "0.00"), settings=settings or {}) if settings else totals.get("balance", "0.00"),
        "dc": "",
    }
    table_rows.append([total_values[key] for key in visible_columns])
    row_kinds.append("subtotal")
    numeric_columns = {index for index, key in enumerate(visible_columns) if key in numeric_keys}
    center_columns = {index for index, key in enumerate(visible_columns) if key in center_keys}
    return headers, table_rows, row_kinds, numeric_columns, center_columns


def _trial_balance_scope_filename(scope_names, scope):
    if scope.get("as_of_date"):
        return f"AsOf_{scope.get('as_of_date')}"
    if scope.get("from_date") and scope.get("to_date"):
        return f"{scope.get('from_date')}_to_{scope.get('to_date')}"
    if scope_names.get("entityfin_name"):
        return scope_names["entityfin_name"]
    return scope.get("scope_mode") or "trial_balance"


def _profit_loss_subtitle(scope_names, scope, report):
    return _financial_export_subtitle(scope_names, scope)


def _profit_loss_period_lookup(row):
    lookup = {}
    for item in row.get("periods") or []:
        key = str(item.get("key") or item.get("code") or item.get("label") or item.get("name") or item.get("title") or "")
        if key:
            lookup[key] = item
    return lookup


def _humanize_profit_loss_group(value):
    labels = {
        "ledger": "Ledger",
        "accounthead": "Account head",
        "accounttype": "Account type",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "ledger").replace("_", " ").title())


def _humanize_profit_loss_view(value):
    labels = {
        "summary": "Summary",
        "detailed": "Detailed",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "summary").replace("_", " ").title())


def _profit_loss_export_meta(scope_names, scope, report, settings=None):
    subentity_label = scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")
    view_label = _humanize_profit_loss_view(scope.get("view_type") or report.get("reporting", {}).get("view_type") or "summary")
    group_label = _humanize_profit_loss_group(scope.get("account_group") or scope.get("group_by") or report.get("reporting", {}).get("group_by") or "ledger")
    presentation_label = "Posted only" if scope.get("posted_only", True) else "Posted and draft"
    zero_balance_label = "Zero rows hidden" if scope.get("hide_zero_rows", True) else "Zero rows shown"
    stock = report.get("stock_valuation") or {}
    summary = report.get("summary") or {}
    meta_items = [
        ("Entity", scope_names["entity_name"] or "Selected entity"),
        ("Financial Year", scope_names["entityfin_name"] or "Current FY"),
        ("Subentity", subentity_label),
        ("Scope", _humanize_trial_balance_scope(scope.get("scope_mode") or "financial_year")),
        ("Presentation", _presentation_label(scope, view_label, group_label)),
        ("Filters", f"{presentation_label} • {zero_balance_label}"),
        ("Amount Unit", financial_hub_amount_unit_label(settings or {})),
        ("Stock", f"{stock.get('effective_mode') or 'auto'} / {stock.get('valuation_method') or 'fifo'}"),
        ("Gross Result", format_financial_hub_amount(summary.get("gross_result") or "0.00", settings=settings or {})),
        ("Net Margin", f"{summary.get('net_margin_percent') or '0.00'}%"),
    ]
    if scope.get("search"):
        meta_items.append(("Search", scope.get("search")))
    return meta_items


def _profit_loss_scope_filename(scope_names, scope):
    if scope.get("as_of_date"):
        return f"As_Of_{scope.get('as_of_date')}"
    if scope.get("from_date") and scope.get("to_date"):
        return f"{scope.get('from_date')}_to_{scope.get('to_date')}"
    if scope_names.get("entityfin_name"):
        return scope_names["entityfin_name"]
    return scope.get("scope_mode") or "profit_loss"


def _profit_loss_export_table(report, *, include_periods=True, settings=None, expanded_keys=None):
    visible_columns = set(get_visible_profit_loss_columns(settings)) if settings else {
        "section", "particulars", "account_head", "account_type", "amount"
    }
    headers = []
    if "section" in visible_columns:
        headers.append("Section")
    if "particulars" in visible_columns:
        headers.append("Particulars")
    if "account_head" in visible_columns:
        headers.append("Account Head")
    if "account_type" in visible_columns:
        headers.append("Account Type")
    periods = _exportable_financial_periods(report.get("periods") or [])
    empty_period_cells = [""] * len(periods) if include_periods else []
    if include_periods:
        for period in periods:
            label = period.get("period_label") or period.get("label") or period.get("name") or period.get("title") or period.get("key")
            headers.extend([f"{label} Amount"])
    if "amount" in visible_columns:
        headers.append("Amount")

    def flatten_rows(items, *, depth=0):
        flattened = []
        for row in items or []:
            label = row.get("label") or row.get("name") or row.get("title") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name") or "-"
            children = row.get("children") or []
            flattened.append({
                "label": f"{'  ' * depth}{label}",
                "account_head": row.get("accounthead_name") or "",
                "account_type": row.get("accounttype_name") or "",
                "amount": row.get("amount", "0.00"),
                "period_lookup": _profit_loss_period_lookup(row),
                "row_kind": "group" if children else "detail",
            })
            if include_children and children:
                flattened.extend(flatten_rows(children, depth=depth + 1))
        return flattened

    def visible_flatten(items):
        flattened = []
        for row, depth, _key in _profit_loss_visible_rows(items, expanded_keys or set()):
            flattened.append({
                "label": f"{'  ' * depth}{row.get('label') or row.get('name') or row.get('title') or row.get('ledger_name') or row.get('accounthead_name') or row.get('accounttype_name') or '-'}",
                "account_head": row.get("accounthead_name") or "",
                "account_type": row.get("accounttype_name") or "",
                "amount": row.get("amount", "0.00"),
                "period_lookup": _profit_loss_period_lookup(row),
                "row_kind": "group" if (row.get("children") or []) else "detail",
            })
        return flattened

    def build_rows(section_name, items, subtotal):
        section_rows = []
        row_kinds = []
        header_row = []
        if "section" in visible_columns:
            header_row.append(section_name)
        if "particulars" in visible_columns:
            header_row.append(section_name)
        if "account_head" in visible_columns:
            header_row.append("")
        if "account_type" in visible_columns:
            header_row.append("")
        header_row.extend(empty_period_cells)
        if "amount" in visible_columns:
            header_row.append("")
        section_rows.append(header_row)
        row_kinds.append("group")

        source_rows = visible_flatten(items) if expanded_keys is not None else flatten_rows(items)
        for row in source_rows:
            value_row = []
            if "section" in visible_columns:
                value_row.append("")
            if "particulars" in visible_columns:
                value_row.append(row["label"])
            if "account_head" in visible_columns:
                value_row.append(row["account_head"])
            if "account_type" in visible_columns:
                value_row.append(row["account_type"])
            period_lookup = row["period_lookup"]
            if include_periods:
                for period in periods:
                    key = str(period.get("period_key") or period.get("key") or period.get("code") or period.get("label") or period.get("name") or period.get("title") or "")
                    period_item = period_lookup.get(key) or {}
                    amount = period_item.get("amount", period_item.get("value", "0.00"))
                    value_row.append(format_financial_hub_amount(amount, settings=settings) if settings else amount)
            if "amount" in visible_columns:
                value_row.append(format_financial_hub_amount(row["amount"], settings=settings) if settings else row["amount"])
            section_rows.append(value_row)
            row_kinds.append(row["row_kind"])

        subtotal_row = []
        if "section" in visible_columns:
            subtotal_row.append("")
        if "particulars" in visible_columns:
            subtotal_row.append(f"{section_name} subtotal")
        if "account_head" in visible_columns:
            subtotal_row.append("")
        if "account_type" in visible_columns:
            subtotal_row.append("")
        subtotal_row.extend(empty_period_cells)
        if "amount" in visible_columns:
            subtotal_row.append(format_financial_hub_amount(subtotal, settings=settings) if settings else subtotal)
        section_rows.append(subtotal_row)
        row_kinds.append("subtotal")
        return section_rows, row_kinds

    rows = []
    row_kinds = []
    income_rows, income_kinds = build_rows("Income", report.get("income") or [], report.get("totals", {}).get("income", "0.00"))
    rows.extend(income_rows)
    row_kinds.extend(income_kinds)
    expense_rows, expense_kinds = build_rows("Expense", report.get("expenses") or [], report.get("totals", {}).get("expense", "0.00"))
    rows.extend(expense_rows)
    row_kinds.extend(expense_kinds)
    summary_row = []
    if "section" in visible_columns:
        summary_row.append("Summary")
    if "particulars" in visible_columns:
        summary_row.append("Net Profit")
    if "account_head" in visible_columns:
        summary_row.append("")
    if "account_type" in visible_columns:
        summary_row.append("")
    summary_row.extend(empty_period_cells)
    if "amount" in visible_columns:
        summary_row.append(format_financial_hub_amount(report.get("totals", {}).get("net_profit", "0.00"), settings=settings) if settings else report.get("totals", {}).get("net_profit", "0.00"))
    rows.append(summary_row)
    row_kinds.append("final_total")

    return headers, rows, row_kinds


def _profit_loss_row_key(row, *, parent_key="", index=0):
    explicit_key = row.get("group_id") or row.get("key") or row.get("id") or row.get("ledger_id") or (
        row.get("label") or row.get("name") or row.get("title") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name") or "-"
    )
    return f"{parent_key}|{explicit_key}-{index}"


def _profit_loss_visible_rows(rows, expanded_keys, *, parent_key="", depth=0):
    visible = []
    for index, row in enumerate(rows or []):
        key = _profit_loss_row_key(row, parent_key=parent_key, index=index)
        visible.append((row, depth, key))
        if row.get("children") and key in expanded_keys:
            visible.extend(_profit_loss_visible_rows(row.get("children") or [], expanded_keys, parent_key=key, depth=depth + 1))
    return visible


def _normalize_trading_label(value):
    return str(value or "").strip().lower()


def _trading_account_subtitle(scope_names, scope, report):
    return _financial_export_subtitle(scope_names, scope)


def _humanize_trading_group(value):
    labels = {
        "ledger": "Ledger",
        "accounthead": "Account head",
        "accounttype": "Account type",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "accounthead").replace("_", " ").title())


def _humanize_trading_view(value):
    labels = {
        "summary": "Summary",
        "detailed": "Detailed",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "summary").replace("_", " ").title())


def _trading_account_export_meta(scope_names, scope, report, settings=None):
    subentity_label = scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")
    reporting = report.get("params") or {}
    meta_items = [
        ("Entity", scope_names["entity_name"] or "Selected entity"),
        ("Financial Year", scope_names["entityfin_name"] or "Current FY"),
        ("Subentity", subentity_label),
        ("Scope", _humanize_trial_balance_scope(scope.get("scope_mode") or "financial_year")),
        ("Presentation", _presentation_label(
            scope,
            _humanize_trading_view(scope.get('view_type') or reporting.get('view_type') or 'summary'),
            _humanize_trading_group(scope.get('account_group') or scope.get('group_by') or reporting.get('account_group') or 'accounthead'),
        )),
        ("Filters", f"{'Posted only' if scope.get('posted_only', True) else 'Posted and draft'} • {'Zero rows hidden' if scope.get('hide_zero_rows', True) else 'Zero rows shown'}"),
        ("Amount Unit", financial_hub_amount_unit_label(settings or {})),
        ("Valuation", str(scope.get("valuation_method") or report.get("params", {}).get("valuation_method") or "fifo").upper()),
        ("Gross Profit", format_financial_hub_amount(report.get("gross_profit", "0.00") or "0.00", settings=settings or {})),
        ("Gross Loss", format_financial_hub_amount(report.get("gross_loss", "0.00") or "0.00", settings=settings or {})),
    ]
    return meta_items


def _trading_account_scope_filename(scope_names, scope):
    if scope.get("as_of_date"):
        return f"As_Of_{scope.get('as_of_date')}"
    if scope.get("from_date") and scope.get("to_date"):
        return f"{scope.get('from_date')}_to_{scope.get('to_date')}"
    if scope_names.get("entityfin_name"):
        return scope_names["entityfin_name"]
    return scope.get("scope_mode") or "trading_account"


def _trading_account_row_label(row):
    return row.get("label") or row.get("name") or row.get("title") or "-"


def _trading_account_row_identity(side, path):
    return f"{side}|{' / '.join(path)}"


def _trading_account_flatten_rows(rows, side, out, depth=0, path=None, include_children=True):
    path = list(path or [])
    for row in rows or []:
        label = _trading_account_row_label(row)
        current_path = [*path, label]
        children = row.get("children") or []
        out.append(
            {
                "identity": _trading_account_row_identity(side, current_path),
                "side": side,
                "particulars": "  " * depth + str(label),
                "qty": row.get("qty", ""),
                "amount": row.get("amount", "0.00"),
                "row_kind": "group" if children else "detail",
            }
        )
        if include_children and children:
            _trading_account_flatten_rows(row["children"], side, out, depth + 1, current_path, include_children=include_children)


def _trading_account_row_lookup(rows, side, lookup=None, path=None):
    lookup = lookup or {}
    path = list(path or [])
    for row in rows or []:
        label = _trading_account_row_label(row)
        current_path = [*path, label]
        lookup[_trading_account_row_identity(side, current_path)] = row.get("amount", "0.00")
        if row.get("children"):
            _trading_account_row_lookup(row["children"], side, lookup, current_path)
    return lookup


def _trading_account_export_table(report, *, include_periods=True, settings=None, expanded_keys=None):
    periods = _exportable_financial_periods(report.get("periods") or [])
    visible_columns = set(get_visible_trading_account_columns(settings)) if settings else {
        "side", "particulars", "qty", "amount"
    }
    headers = []
    if "side" in visible_columns:
        headers.append("Side")
    if "particulars" in visible_columns:
        headers.append("Particulars")
    if "qty" in visible_columns:
        headers.append("Qty")
    if include_periods:
        for period in periods:
            label = period.get("period_label") or period.get("label") or period.get("name") or period.get("title") or period.get("key")
            headers.append(str(label or "Period"))
    if "amount" in visible_columns:
        headers.append("Amount")

    rows = []
    row_kinds = []
    debit_rows = []
    credit_rows = []
    if expanded_keys is not None:
        for row, side, depth, _key, _path, _label_path in _trading_visible_rows(report.get("debit_rows") or [], "debit", expanded_keys):
            debit_rows.append({
                "side": "Debit",
                "particulars": f"{'  ' * depth}{_trading_account_row_label(row)}",
                "qty": row.get("quantity", ""),
                "amount": row.get("amount", "0.00"),
                "identity": ("Debit", tuple(_label_path)),
                "row_kind": "group" if (row.get("children") or []) else "detail",
            })
        for row, side, depth, _key, _path, _label_path in _trading_visible_rows(report.get("credit_rows") or [], "credit", expanded_keys):
            credit_rows.append({
                "side": "Credit",
                "particulars": f"{'  ' * depth}{_trading_account_row_label(row)}",
                "qty": row.get("quantity", ""),
                "amount": row.get("amount", "0.00"),
                "identity": ("Credit", tuple(_label_path)),
                "row_kind": "group" if (row.get("children") or []) else "detail",
            })
    else:
        params = report.get("params") or {}
        normalized_view = str(params.get("view_type") or "summary").strip().lower()
        include_children = normalized_view == "detailed"
        _trading_account_flatten_rows(report.get("debit_rows") or [], "Debit", debit_rows, include_children=include_children)
        _trading_account_flatten_rows(report.get("credit_rows") or [], "Credit", credit_rows, include_children=include_children)

    period_lookups = []
    if include_periods:
        for period in periods:
            period_lookups.append(
                {
                    "debit": _trading_account_row_lookup(period.get("debit_rows") or [], "Debit"),
                    "credit": _trading_account_row_lookup(period.get("credit_rows") or [], "Credit"),
                    "debit_total": period.get("debit_total", "0.00"),
                    "credit_total": period.get("credit_total", "0.00"),
                    "gross_profit": period.get("gross_profit", "0.00") or "0.00",
                    "gross_loss": period.get("gross_loss", "0.00") or "0.00",
                }
            )

    def append_row(row, amount=None):
        value_row = []
        if "side" in visible_columns:
            value_row.append(row["side"])
        if "particulars" in visible_columns:
            value_row.append(row["particulars"])
        if "qty" in visible_columns:
            value_row.append(row["qty"])
        if include_periods:
            for period in period_lookups:
                side_lookup = period["debit"] if row["side"] == "Debit" else period["credit"]
                period_amount = side_lookup.get(row["identity"], "")
                value_row.append(format_financial_hub_amount(period_amount, settings=settings) if settings and period_amount not in {"", None} else period_amount)
        if "amount" in visible_columns:
            final_amount = amount if amount is not None else row["amount"]
            value_row.append(format_financial_hub_amount(final_amount, settings=settings) if settings else final_amount)
        rows.append(value_row)
        row_kinds.append(row.get("row_kind", "detail"))

    section_row = []
    if "side" in visible_columns:
        section_row.append("Debit")
    if "particulars" in visible_columns:
        section_row.append("Debit Side")
    if "qty" in visible_columns:
        section_row.append("")
    if include_periods:
        section_row.extend(["" for _ in period_lookups])
    if "amount" in visible_columns:
        section_row.append("")
    rows.append(section_row)
    row_kinds.append("group")
    for row in debit_rows:
        append_row(row)
    debit_total_row = []
    if "side" in visible_columns:
        debit_total_row.append("Debit Total")
    if "particulars" in visible_columns:
        debit_total_row.append("")
    if "qty" in visible_columns:
        debit_total_row.append("")
    if include_periods:
        debit_total_row.extend([
            format_financial_hub_amount(period["debit_total"], settings=settings) if settings else period["debit_total"]
            for period in period_lookups
        ])
    if "amount" in visible_columns:
        debit_total_row.append(format_financial_hub_amount(report.get("debit_total", "0.00"), settings=settings) if settings else report.get("debit_total", "0.00"))
    rows.append(debit_total_row)
    row_kinds.append("subtotal")

    section_row = []
    if "side" in visible_columns:
        section_row.append("Credit")
    if "particulars" in visible_columns:
        section_row.append("Credit Side")
    if "qty" in visible_columns:
        section_row.append("")
    if include_periods:
        section_row.extend(["" for _ in period_lookups])
    if "amount" in visible_columns:
        section_row.append("")
    rows.append(section_row)
    row_kinds.append("group")
    for row in credit_rows:
        append_row(row)
    credit_total_row = []
    if "side" in visible_columns:
        credit_total_row.append("Credit Total")
    if "particulars" in visible_columns:
        credit_total_row.append("")
    if "qty" in visible_columns:
        credit_total_row.append("")
    if include_periods:
        credit_total_row.extend([
            format_financial_hub_amount(period["credit_total"], settings=settings) if settings else period["credit_total"]
            for period in period_lookups
        ])
    if "amount" in visible_columns:
        credit_total_row.append(format_financial_hub_amount(report.get("credit_total", "0.00"), settings=settings) if settings else report.get("credit_total", "0.00"))
    rows.append(credit_total_row)
    row_kinds.append("subtotal")
    gross_profit_row = []
    if "side" in visible_columns:
        gross_profit_row.append("Gross Profit")
    if "particulars" in visible_columns:
        gross_profit_row.append("")
    if "qty" in visible_columns:
        gross_profit_row.append("")
    if include_periods:
        gross_profit_row.extend([
            format_financial_hub_amount(period["gross_profit"], settings=settings) if settings else period["gross_profit"]
            for period in period_lookups
        ])
    if "amount" in visible_columns:
        gross_profit_row.append(format_financial_hub_amount(report.get("gross_profit", "0.00") or "0.00", settings=settings) if settings else (report.get("gross_profit", "0.00") or "0.00"))
    rows.append(gross_profit_row)
    row_kinds.append("final_total")
    gross_loss_row = []
    if "side" in visible_columns:
        gross_loss_row.append("Gross Loss")
    if "particulars" in visible_columns:
        gross_loss_row.append("")
    if "qty" in visible_columns:
        gross_loss_row.append("")
    if include_periods:
        gross_loss_row.extend([
            format_financial_hub_amount(period["gross_loss"], settings=settings) if settings else period["gross_loss"]
            for period in period_lookups
        ])
    if "amount" in visible_columns:
        gross_loss_row.append(format_financial_hub_amount(report.get("gross_loss", "0.00") or "0.00", settings=settings) if settings else (report.get("gross_loss", "0.00") or "0.00"))
    rows.append(gross_loss_row)
    row_kinds.append("final_total")
    return headers, rows, row_kinds


def _trading_row_key(side, path, row, index):
    return f"{side}:{'.'.join(str(part) for part in path)}:{row.get('label')}-{index}"


def _trading_visible_rows(rows, side, expanded_keys, *, depth=0, parent_path=None, parent_labels=None):
    visible = []
    parent_path = parent_path or []
    parent_labels = parent_labels or []
    for index, row in enumerate(rows or []):
        path = [*parent_path, index]
        label_path = [*parent_labels, _normalize_trading_label(row.get("label"))]
        key = _trading_row_key(side, path, row, index)
        visible.append((row, side, depth, key, path, label_path))
        if row.get("children") and key in expanded_keys:
            visible.extend(
                _trading_visible_rows(
                    row.get("children") or [],
                    side,
                    expanded_keys,
                    depth=depth + 1,
                    parent_path=path,
                    parent_labels=label_path,
                )
            )
    return visible


def _balance_sheet_row_label(row, depth=0):
    label = (
        row.get("label")
        or row.get("name")
        or row.get("title")
        or row.get("ledger_name")
        or row.get("accounthead_name")
        or row.get("accounttype_name")
        or "-"
    )
    return f"{'  ' * depth}{label}"


def _balance_sheet_row_period_value(row, period):
    if period.get("unavailable"):
        return "N/A"

    period_key = str(period.get("period_key") or period.get("key") or period.get("code") or period.get("label") or period.get("name") or "")
    period_values = row.get("period_values") or {}
    if period_key in period_values:
        return period_values.get(period_key)

    amounts_by_period = row.get("amounts_by_period") or {}
    if period_key in amounts_by_period:
        return amounts_by_period.get(period_key)

    for item in row.get("periods") or []:
        item_key = str(item.get("key") or item.get("code") or item.get("label") or item.get("name") or "")
        if item_key == period_key:
            return item.get("amount") or item.get("value") or item.get("closing")

    return None


def _balance_sheet_flatten_rows(rows, *, section_label, periods, include_children=True, depth=0):
    flattened = []
    for row in rows or []:
        children = row.get("children") or []
        flattened.append(
            {
                "section": section_label if depth == 0 else "",
                "particulars": _balance_sheet_row_label(row, depth=depth),
                "account_head": row.get("accounthead_name") or "-",
                "account_type": row.get("accounttype_name") or "-",
                "period_values": [_balance_sheet_row_period_value(row, period) for period in periods],
                "amount": row.get("amount"),
                "row_kind": "group" if children else "detail",
            }
        )
        if include_children and children:
            flattened.extend(
                _balance_sheet_flatten_rows(
                    children,
                    section_label=section_label,
                    periods=periods,
                    include_children=include_children,
                    depth=depth + 1,
                )
            )
    return flattened


def _balance_sheet_row_key(row, *, parent_key="", index=0):
    explicit_key = (
        row.get("key")
        or row.get("id")
        or row.get("ledger_id")
        or row.get("accounthead_id")
        or row.get("accounttype_id")
        or _balance_sheet_row_label(row)
    )
    return f"{parent_key}|{explicit_key}-{index}"


def _balance_sheet_visible_rows(rows, *, section_label, periods, expanded_keys, parent_key="", depth=0):
    visible = []
    for index, row in enumerate(rows or []):
        key = _balance_sheet_row_key(row, parent_key=parent_key, index=index)
        visible.append({
            "section": section_label if depth == 0 else "",
            "particulars": _balance_sheet_row_label(row, depth=depth),
            "account_head": row.get("accounthead_name") or "-",
            "account_type": row.get("accounttype_name") or "-",
            "period_values": [_balance_sheet_row_period_value(row, period) for period in periods],
            "amount": row.get("amount"),
            "row_kind": "group" if (row.get("children") or []) else "detail",
            "key": key,
            "depth": depth,
            "row": row,
        })
        if row.get("children") and key in expanded_keys:
            visible.extend(
                _balance_sheet_visible_rows(
                    row.get("children") or [],
                    section_label=section_label,
                    periods=periods,
                    expanded_keys=expanded_keys,
                    parent_key=key,
                    depth=depth + 1,
                )
            )
    return visible


def _balance_sheet_export_table(report, *, settings=None, expanded_keys=None):
    periods = _exportable_financial_periods(report.get("periods") or [])
    period_labels = [
        str(
            period.get("period_label")
            or period.get("label")
            or period.get("name")
            or period.get("code")
            or period.get("period_key")
            or f"Period {index}"
        )
        for index, period in enumerate(periods, start=1)
    ]
    visible_columns = set(get_visible_balance_sheet_columns(settings)) if settings else {
        "section", "particulars", "account_head", "account_type", "amount"
    }
    headers = []
    if "section" in visible_columns:
        headers.append("Section")
    if "particulars" in visible_columns:
        headers.append("Particulars")
    if "account_head" in visible_columns:
        headers.append("Account Head")
    if "account_type" in visible_columns:
        headers.append("Account Type")
    headers.extend(period_labels)
    if "amount" in visible_columns:
        headers.append("Amount")
    rows = []
    row_kinds = []
    for section_label, section_rows in (
        ("Assets", report.get("assets") or []),
        ("Liabilities & Equity", report.get("liabilities_and_equity") or []),
    ):
        section_items = _balance_sheet_visible_rows(
            section_rows,
            section_label=section_label,
            periods=periods,
            expanded_keys=expanded_keys,
        ) if expanded_keys is not None else _balance_sheet_flatten_rows(
            section_rows,
            section_label=section_label,
            periods=periods,
            include_children=str((report.get("reporting") or {}).get("view_type") or "summary").strip().lower() == "detailed",
        )
        for item in section_items:
            row_values = []
            if "section" in visible_columns:
                row_values.append(item["section"])
            if "particulars" in visible_columns:
                row_values.append(item["particulars"])
            if "account_head" in visible_columns:
                row_values.append(item["account_head"])
            if "account_type" in visible_columns:
                row_values.append(item["account_type"])
            row_values.extend([
                format_financial_hub_amount(period_value, settings=settings) if settings and period_value not in {None, "", "N/A"} else (period_value or "")
                for period_value in item["period_values"]
            ])
            if "amount" in visible_columns:
                row_values.append(format_financial_hub_amount(item["amount"], settings=settings) if settings else item["amount"])
            rows.append(row_values)
            row_kinds.append(item["row_kind"])
        total_row = []
        if "section" in visible_columns:
            total_row.append(section_label)
        if "particulars" in visible_columns:
            total_row.append(f"{section_label} Total")
        if "account_head" in visible_columns:
            total_row.append("")
        if "account_type" in visible_columns:
            total_row.append("")
        total_row.extend(["" for _ in periods])
        if "amount" in visible_columns:
            total_row.append(
                format_financial_hub_amount(
                    report.get("totals", {}).get("assets" if section_label == "Assets" else "liabilities_and_equity") or "0.00",
                    settings=settings,
                ) if settings else report.get("totals", {}).get("assets" if section_label == "Assets" else "liabilities_and_equity") or "0.00"
            )
        rows.append(total_row)
        row_kinds.append("subtotal")

    assets_total = _parse_decimal(report.get("totals", {}).get("assets"))
    liabilities_total = _parse_decimal(report.get("totals", {}).get("liabilities_and_equity"))
    balance_diff = assets_total - liabilities_total
    diff_row = []
    if "section" in visible_columns:
        diff_row.append("")
    if "particulars" in visible_columns:
        diff_row.append("Balance Difference")
    if "account_head" in visible_columns:
        diff_row.append("")
    if "account_type" in visible_columns:
        diff_row.append("")
    diff_row.extend(["" for _ in periods])
    if "amount" in visible_columns:
        diff_row.append(format_financial_hub_amount(f"{balance_diff:.2f}", settings=settings) if settings else f"{balance_diff:.2f}")
    rows.append(diff_row)
    row_kinds.append("difference")

    return headers, rows, row_kinds


def _statement_period_columns(report):
    periods = report.get("periods") or []
    period_defs = []
    for period in periods:
        label = (
            period.get("period_label")
            or period.get("label")
            or period.get("name")
            or period.get("title")
            or period.get("period_key")
            or period.get("key")
        )
        period_defs.append({"label": str(label or "Period"), "period": period})
    if not period_defs:
        period_defs.append({"label": "N/A", "period": None})
    return "Current Year", period_defs


def _period_export_label(period):
    if not period:
        return ""
    label = (
        period.get("period_label")
        or period.get("label")
        or period.get("name")
        or period.get("title")
        or period.get("key")
        or period.get("period_key")
        or period.get("code")
    )
    return str(label or "").strip()


def _exportable_financial_periods(periods):
    exportable = []
    for period in periods or []:
        if not period or period.get("unavailable"):
            continue
        label = _period_export_label(period)
        if not label or label.upper() == "N/A":
            continue
        exportable.append(period)
    return exportable


def _financial_export_scope_text(scope_names, scope):
    if scope.get("from_date") and scope.get("to_date"):
        return f"{_format_scope_date(scope.get('from_date'))} to {_format_scope_date(scope.get('to_date'))}"
    if scope.get("as_of_date"):
        return f"As of {_format_scope_date(scope.get('as_of_date'))}"
    if scope_names.get("entityfin_name"):
        return scope_names["entityfin_name"]
    return _humanize_trial_balance_scope(scope.get("scope_mode") or "financial_year")


def _financial_export_subtitle(scope_names, scope):
    entity_name = scope_names.get("entity_name") or "Selected entity"
    return f"{entity_name} • {_financial_export_scope_text(scope_names, scope)}"


def _statement_period_amount(row, period):
    if not period:
        return "N/A"
    if period.get("unavailable"):
        return "N/A"
    key = str(period.get("period_key") or period.get("key") or period.get("code") or period.get("label") or period.get("name") or "")
    if not key:
        return ""
    period_values = row.get("period_values") or {}
    if key in period_values:
        return period_values.get(key) or "0.00"
    amounts_by_period = row.get("amounts_by_period") or {}
    if key in amounts_by_period:
        return amounts_by_period.get(key) or "0.00"
    for item in row.get("periods") or []:
        item_key = str(item.get("key") or item.get("period_key") or item.get("code") or item.get("label") or item.get("name") or "")
        if item_key == key:
            return item.get("amount") or item.get("value") or item.get("closing") or "0.00"
    return ""


def _statement_indent(label, depth):
    return f"{'  ' * depth}{label}"


def _statement_pdf_layout(headers):
    total_columns = len(headers)
    comparison_count = max(0, total_columns - 4)

    if total_columns <= 10:
        pagesize = landscape(A4)
        base_widths = [180, 44, 74, 74] + [74] * comparison_count
        min_widths = [120, 32, 52, 52] + [52] * comparison_count
    elif total_columns <= 16:
        pagesize = landscape(A3)
        base_widths = [160, 40, 64, 64] + [64] * comparison_count
        min_widths = [110, 28, 44, 44] + [44] * comparison_count
    else:
        pagesize = landscape(A3)
        base_widths = [140, 34, 56, 56] + [56] * comparison_count
        min_widths = [82, 24, 34, 34] + [34] * comparison_count

    available_width = pagesize[0] - 36  # matches left/right margins used by write_sectioned_pdf
    current_total = sum(base_widths)
    if current_total <= available_width:
        return pagesize, base_widths

    shrink_capacity = [max(0, base - minimum) for base, minimum in zip(base_widths, min_widths)]
    total_capacity = sum(shrink_capacity)
    if total_capacity <= 0:
        return pagesize, min_widths

    reduction_ratio = min(1, (current_total - available_width) / total_capacity)
    fitted_widths = [
        round(base - (capacity * reduction_ratio), 2)
        for base, capacity in zip(base_widths, shrink_capacity)
    ]
    return pagesize, fitted_widths


def _statement_balance_sheet_rows(report, *, settings=None, expanded_keys=None):
    _current_label, period_defs = _statement_period_columns(report)
    headers = ["Particulars", "Note", "Current Detail", "Current Total"]
    for item in period_defs:
        headers.extend([f"{item['label']} Detail", f"{item['label']} Total"])
    rows = []
    note_number = 1

    def _fmt(value):
        if value in {None, ""}:
            return ""
        if value == "N/A":
            return "N/A"
        return format_financial_hub_amount(value, settings=settings or {}) if settings else value

    def append_tree(items, section_title, total_value, *, total_key):
        nonlocal note_number
        rows.append([section_title, "", *["" for _ in range(2 + (len(period_defs) * 2))]])

        def walk(tree_rows, depth=0, parent_key=""):
            nonlocal note_number
            for index, row in enumerate(tree_rows or []):
                key = _balance_sheet_row_key(row, parent_key=parent_key, index=index)
                label = (
                    row.get("label")
                    or row.get("name")
                    or row.get("title")
                    or row.get("ledger_name")
                    or row.get("accounthead_name")
                    or row.get("accounttype_name")
                    or "-"
                )
                note = str(note_number) if depth == 0 else ""
                if depth == 0:
                    note_number += 1
                is_major = bool(row.get("children")) or depth == 0
                current_value = row.get("amount") or "0.00"
                row_values = ["" if is_major else _fmt(current_value), _fmt(current_value) if is_major else ""]
                for item in period_defs:
                    period_value = _statement_period_amount(row, item["period"])
                    row_values.extend(["" if is_major else _fmt(period_value), _fmt(period_value) if is_major else ""])
                rows.append([
                    _statement_indent(str(label), depth),
                    note,
                    *row_values,
                ])
                children = row.get("children") or []
                if children and (expanded_keys is None or key in expanded_keys):
                    walk(children, depth + 1, key)

        walk(items)
        total_row = [f"Total {section_title}", "", "-", _fmt(total_value or "0.00")]
        for item in period_defs:
            period = item["period"]
            if period and not period.get("unavailable"):
                period_total = ((period.get("totals") or {}).get(total_key)) or "0.00"
            else:
                period_total = "N/A"
            total_row.extend(["-", _fmt(period_total)])
        rows.append(total_row)
        rows.append(["", "", *["" for _ in range(2 + (len(period_defs) * 2))]])

    append_tree(report.get("liabilities_and_equity") or [], "Equity and Liabilities", (report.get("totals") or {}).get("liabilities_and_equity"), total_key="liabilities_and_equity")
    append_tree(report.get("assets") or [], "Assets", (report.get("totals") or {}).get("assets"), total_key="assets")
    return headers, rows


def _balance_sheet_statement_pdf_sections(report, *, settings=None, expanded_keys=None):
    current_label, raw_period_defs = _statement_period_columns(report)
    period_defs = [item for item in raw_period_defs if item.get("period") and not item["period"].get("unavailable")]
    amount_headers = [current_label, *[str(item["label"]) for item in period_defs]]

    def _fmt(value):
        if value in {None, ""}:
            return ""
        if value == "N/A":
            return "N/A"
        return format_financial_hub_amount(value, settings=settings or {}) if settings else value

    def _amounts_for_row(row):
        amounts = [_fmt(row.get("amount") or "0.00")]
        for item in period_defs:
            amounts.append(_fmt(_statement_period_amount(row, item["period"])))
        return amounts

    def _flatten_children(rows, depth=0, parent_key=""):
        lines = []
        for index, row in enumerate(rows or []):
            key = _balance_sheet_row_key(row, parent_key=parent_key, index=index)
            label = (
                row.get("label")
                or row.get("name")
                or row.get("title")
                or row.get("ledger_name")
                or row.get("accounthead_name")
                or row.get("accounttype_name")
                or "-"
            )
            lines.append({
                "label": _statement_indent(str(label), depth),
                "amounts": _amounts_for_row(row),
            })
            if row.get("children") and (expanded_keys is None or key in expanded_keys):
                lines.extend(_flatten_children(row.get("children") or [], depth + 1, key))
        return lines

    def _build_groups(rows, parent_key=""):
        groups = []
        for index, row in enumerate(rows or []):
            key = _balance_sheet_row_key(row, parent_key=parent_key, index=index)
            label = (
                row.get("label")
                or row.get("name")
                or row.get("title")
                or row.get("ledger_name")
                or row.get("accounthead_name")
                or row.get("accounttype_name")
                or "-"
            )
            children = row.get("children") or []
            is_expanded = expanded_keys is None or key in expanded_keys
            if children and is_expanded:
                lines = _flatten_children(children, 0, key)
            else:
                lines = []
            compact_row = None
            if not children or not lines:
                compact_row = {
                    "label": str(label),
                    "amounts": _amounts_for_row(row),
                }
            groups.append({
                "title": str(label),
                "lines": lines,
                "compact_row": compact_row,
                "total_label": f"Total {label}" if lines else "",
                "total_amounts": _amounts_for_row(row),
            })
        return groups

    def _section_total(total_key):
        total_amounts = [_fmt((report.get("totals") or {}).get(total_key) or "0.00")]
        for item in period_defs:
            period = item["period"]
            total_amounts.append(_fmt(((period.get("totals") or {}).get(total_key)) or "0.00"))
        return total_amounts

    sections = [
        {
            "title": "Assets",
            "groups": _build_groups(report.get("assets") or []),
            "total_label": "Total Assets",
            "total_amounts": _section_total("assets"),
        },
        {
            "title": "Liabilities and Equity",
            "groups": _build_groups(report.get("liabilities_and_equity") or []),
            "total_label": "Total Liabilities and Equity",
            "total_amounts": _section_total("liabilities_and_equity"),
        },
    ]
    return amount_headers, sections


def _profit_loss_statement_pdf_sections(report, *, settings=None, expanded_keys=None, collapsed_sections=None):
    current_label, raw_period_defs = _statement_period_columns(report)
    period_defs = [item for item in raw_period_defs if item.get("period") and not item["period"].get("unavailable")]
    amount_headers = [current_label, *[str(item["label"]) for item in period_defs]]

    def _fmt(value):
        if value in {None, ""}:
            return ""
        if value == "N/A":
            return "N/A"
        return format_financial_hub_amount(value, settings=settings or {}) if settings else value

    def _amounts_for_row(row):
        amounts = [_fmt(row.get("amount") or "0.00")]
        for item in period_defs:
            amounts.append(_fmt(_statement_period_amount(row, item["period"])))
        return amounts

    def _flatten_children(rows, depth=0, parent_key=""):
        lines = []
        for index, row in enumerate(rows or []):
            key = _profit_loss_row_key(row, parent_key=parent_key, index=index)
            label = (
                row.get("label")
                or row.get("name")
                or row.get("title")
                or row.get("ledger_name")
                or row.get("accounthead_name")
                or row.get("accounttype_name")
                or "-"
            )
            lines.append({
                "label": _statement_indent(str(label), depth),
                "amounts": _amounts_for_row(row),
            })
            if row.get("children") and (expanded_keys is None or key in expanded_keys):
                lines.extend(_flatten_children(row.get("children") or [], depth + 1, key))
        return lines

    def _build_groups(rows, parent_key=""):
        groups = []
        for index, row in enumerate(rows or []):
            key = _profit_loss_row_key(row, parent_key=parent_key, index=index)
            label = (
                row.get("label")
                or row.get("name")
                or row.get("title")
                or row.get("ledger_name")
                or row.get("accounthead_name")
                or row.get("accounttype_name")
                or "-"
            )
            children = row.get("children") or []
            is_expanded = expanded_keys is None or key in expanded_keys
            if children and is_expanded:
                lines = _flatten_children(children, 0, key)
            else:
                lines = []
            compact_row = None
            if not children or not lines:
                compact_row = {
                    "label": str(label),
                    "amounts": _amounts_for_row(row),
                }
            groups.append({
                "title": str(label),
                "lines": lines,
                "compact_row": compact_row,
                "total_label": f"Total {label}" if lines else "",
                "total_amounts": _amounts_for_row(row),
            })
        return groups

    def _section_total(total_key):
        total_amounts = [_fmt((report.get("totals") or {}).get(total_key) or "0.00")]
        for item in period_defs:
            period = item["period"]
            total_amounts.append(_fmt(((period.get("totals") or {}).get(total_key)) or "0.00"))
        return total_amounts

    current_net_profit = report.get("totals", {}).get("net_profit") or "0.00"
    result_label = "Net Profit" if Decimal(str(current_net_profit or "0")) >= 0 else "Net Loss"
    result_amounts = [_fmt(current_net_profit)]
    for item in period_defs:
        period = item["period"]
        result_amounts.append(_fmt((period.get("totals") or {}).get("net_profit") or "0.00"))

    collapsed_sections = collapsed_sections or set()
    sections = []
    if "income" not in collapsed_sections:
        sections.append({
            "title": "Income",
            "groups": _build_groups(report.get("income") or []),
            "total_label": "Total Income",
            "total_amounts": _section_total("income"),
        })
    if "expense" not in collapsed_sections:
        sections.append({
            "title": "Expenses",
            "groups": _build_groups(report.get("expenses") or []),
            "total_label": "Total Expenses",
            "total_amounts": _section_total("expense"),
        })
    if "net" not in collapsed_sections:
        sections.append({
            "title": "Result",
            "groups": [
                {
                    "title": result_label,
                    "lines": [],
                    "compact_row": {
                        "label": result_label,
                        "amounts": result_amounts,
                    },
                    "total_label": "",
                    "total_amounts": result_amounts,
                }
            ],
            "total_label": "",
            "total_amounts": [],
        })
    return amount_headers, sections


def _trading_account_statement_pdf_sections(report, *, settings=None, expanded_keys=None):
    current_label, raw_period_defs = _statement_period_columns(report)
    period_defs = [item for item in raw_period_defs if item.get("period") and not item["period"].get("unavailable")]
    amount_headers = [current_label, *[str(item["label"]) for item in period_defs]]

    def _normalize_label(value):
        return str(value or "").strip().lower()

    def _find_period_row(rows_list, label_path):
        if not label_path:
            return None
        head, *rest = label_path
        for row in rows_list or []:
            if _normalize_label(row.get("label")) != head:
                continue
            if not rest:
                return row
            nested = _find_period_row(row.get("children") or [], rest)
            if nested:
                return nested
        return None

    def _period_trading_amount(period, side_key, label_path):
        if not period or period.get("unavailable"):
            return "N/A" if period and period.get("unavailable") else ""
        rows_list = period.get(side_key) or []
        matched = _find_period_row(rows_list, label_path)
        if not matched:
            return ""
        return matched.get("amount") or "0.00"

    def _fmt(value):
        if value in {None, ""}:
            return ""
        if value == "N/A":
            return "N/A"
        return format_financial_hub_amount(value, settings=settings or {}) if settings else value

    def _flatten_children(rows, side_key, parent_labels=None, depth=0, parent_path=None):
        parent_labels = parent_labels or []
        parent_path = parent_path or []
        lines = []
        for index, row in enumerate(rows or []):
            path = [*parent_path, index]
            label = _trading_account_row_label(row)
            label_path = [*parent_labels, _normalize_label(label)]
            key = _trading_row_key("debit" if side_key == "debit_rows" else "credit", path, row, index)
            amounts = [_fmt(row.get("amount") or "0.00")]
            for item in period_defs:
                amounts.append(_fmt(_period_trading_amount(item["period"], side_key, label_path)))
            lines.append({
                "label": _statement_indent(str(label), depth),
                "amounts": amounts,
            })
            if row.get("children") and (expanded_keys is None or key in expanded_keys):
                lines.extend(_flatten_children(row.get("children") or [], side_key, label_path, depth + 1, path))
        return lines

    def _build_groups(rows, side_key):
        groups = []
        for index, row in enumerate(rows or []):
            path = [index]
            label = _trading_account_row_label(row)
            label_path = [_normalize_label(label)]
            key = _trading_row_key("debit" if side_key == "debit_rows" else "credit", path, row, index)
            amounts = [_fmt(row.get("amount") or "0.00")]
            for item in period_defs:
                amounts.append(_fmt(_period_trading_amount(item["period"], side_key, label_path)))
            children = row.get("children") or []
            is_expanded = expanded_keys is None or key in expanded_keys
            lines = _flatten_children(children, side_key, label_path, 0, path) if children and is_expanded else []
            groups.append({
                "title": str(label),
                "lines": lines,
                "compact_row": {
                    "label": str(label),
                    "amounts": amounts,
                } if not children or not lines else None,
                "total_label": f"Total {label}" if lines else "",
                "total_amounts": amounts,
            })
        return groups

    def _report_total(current_key):
        amounts = [_fmt(report.get(current_key) or "0.00")]
        for item in period_defs:
            period = item["period"]
            amounts.append(_fmt(period.get(current_key, "0.00") if period else "0.00"))
        return amounts

    result_groups = []
    gross_profit = Decimal(str(report.get("gross_profit") or "0.00"))
    gross_loss = Decimal(str(report.get("gross_loss") or "0.00"))
    if gross_profit != 0:
        result_groups.append({
            "title": "Gross Profit",
            "lines": [],
            "compact_row": {
                "label": "Gross Profit",
                "amounts": _report_total("gross_profit"),
            },
            "total_label": "",
            "total_amounts": _report_total("gross_profit"),
        })
    if gross_loss != 0 or not result_groups:
        result_groups.append({
            "title": "Gross Loss",
            "lines": [],
            "compact_row": {
                "label": "Gross Loss",
                "amounts": _report_total("gross_loss"),
            },
            "total_label": "",
            "total_amounts": _report_total("gross_loss"),
        })

    sections = [
        {
            "title": "Debit Side",
            "groups": _build_groups(report.get("debit_rows") or [], "debit_rows"),
            "total_label": "Total Debit",
            "total_amounts": _report_total("debit_total"),
        },
        {
            "title": "Credit Side",
            "groups": _build_groups(report.get("credit_rows") or [], "credit_rows"),
            "total_label": "Total Credit",
            "total_amounts": _report_total("credit_total"),
        },
        {
            "title": "Result",
            "groups": result_groups,
            "total_label": "",
            "total_amounts": [],
        },
    ]
    return amount_headers, sections


def _statement_profit_loss_rows(report, *, settings=None, expanded_keys=None, collapsed_sections=None):
    _current_label, period_defs = _statement_period_columns(report)
    headers = ["Particulars", "Note", "Current Detail", "Current Total"]
    for item in period_defs:
        headers.extend([f"{item['label']} Detail", f"{item['label']} Total"])
    rows = []
    note_number = 1

    def _fmt(value):
        if value in {None, ""}:
            return ""
        if value == "N/A":
            return "N/A"
        return format_financial_hub_amount(value, settings=settings or {}) if settings else value

    def append_tree(items, section_title, total_value, total_key):
        nonlocal note_number
        rows.append([section_title, "", *["" for _ in range(2 + (len(period_defs) * 2))]])

        def walk(tree_rows, depth=0, parent_key=""):
            nonlocal note_number
            for index, row in enumerate(tree_rows or []):
                key = _profit_loss_row_key(row, parent_key=parent_key, index=index)
                label = row.get("label") or row.get("name") or row.get("title") or row.get("ledger_name") or row.get("accounthead_name") or row.get("accounttype_name") or "-"
                note = str(note_number) if depth == 0 else ""
                if depth == 0:
                    note_number += 1
                is_major = bool(row.get("children")) or depth == 0
                current_value = row.get("amount") or "0.00"
                row_values = ["" if is_major else _fmt(current_value), _fmt(current_value) if is_major else ""]
                for item in period_defs:
                    period_value = _statement_period_amount(row, item["period"])
                    row_values.extend(["" if is_major else _fmt(period_value), _fmt(period_value) if is_major else ""])
                rows.append([
                    _statement_indent(str(label), depth),
                    note,
                    *row_values,
                ])
                if row.get("children") and (expanded_keys is None or key in expanded_keys):
                    walk(row.get("children") or [], depth + 1, key)

        walk(items)
        total_row = [f"Total {section_title}", "", "-", _fmt(total_value or "0.00")]
        for item in period_defs:
            period = item["period"]
            if period and not period.get("unavailable"):
                period_total = ((period.get("totals") or {}).get(total_key)) or "0.00"
            else:
                period_total = "N/A"
            total_row.extend(["-", _fmt(period_total)])
        rows.append(total_row)
        rows.append(["", "", *["" for _ in range(2 + (len(period_defs) * 2))]])

    collapsed_sections = collapsed_sections or set()
    if "income" not in collapsed_sections:
        append_tree(report.get("income") or [], "Income", (report.get("totals") or {}).get("income"), "income")
    if "expense" not in collapsed_sections:
        append_tree(report.get("expenses") or [], "Expenses", (report.get("totals") or {}).get("expense"), "expense")
    period_net = []
    for item in period_defs:
        period = item["period"]
        if period and not period.get("unavailable"):
            period_net.append(period.get("net_profit") or ((period.get("totals") or {}).get("net_profit")) or "0.00")
        else:
            period_net.append("N/A")
    net_row = ["Net Profit / Loss", "", "-", _fmt((report.get("totals") or {}).get("net_profit") or "0.00")]
    for period_value in period_net:
        net_row.extend(["-", _fmt(period_value)])
    if "net" not in collapsed_sections:
        rows.append(net_row)
    return headers, rows


def _statement_trading_rows(report, *, settings=None, expanded_keys=None):
    _current_label, period_defs = _statement_period_columns(report)
    headers = ["Particulars", "Note", "Current Detail", "Current Total"]
    for item in period_defs:
        headers.extend([f"{item['label']} Detail", f"{item['label']} Total"])
    rows = []
    note_number = 1

    def _normalize_label(value):
        return str(value or "").strip().lower()

    def _find_period_row(rows_list, label_path):
        if not label_path:
            return None
        head, *rest = label_path
        for row in rows_list or []:
            if _normalize_label(row.get("label")) != head:
                continue
            if not rest:
                return row
            nested = _find_period_row(row.get("children") or [], rest)
            if nested:
                return nested
        return None

    def _period_trading_amount(period, side_key, label_path):
        if not period:
            return "N/A"
        if period.get("unavailable"):
            return "N/A"
        rows_list = period.get(side_key) or []
        matched = _find_period_row(rows_list, label_path)
        if not matched:
            return ""
        return matched.get("amount") or "0.00"

    def _fmt(value):
        if value in {None, ""}:
            return ""
        if value == "N/A":
            return "N/A"
        return format_financial_hub_amount(value, settings=settings or {}) if settings else value

    def walk(tree_rows, side_key, depth=0, parent_labels=None, parent_path=None):
        nonlocal note_number
        parent_labels = parent_labels or []
        parent_path = parent_path or []
        for index, row in enumerate(tree_rows or []):
            path = [*parent_path, index]
            label = _trading_account_row_label(row)
            label_path = [*parent_labels, _normalize_label(label)]
            key = _trading_row_key("debit" if side_key == "debit_rows" else "credit", path, row, index)
            note = str(note_number) if depth == 0 else ""
            if depth == 0:
                note_number += 1
            is_major = bool(row.get("children")) or depth == 0
            current_value = row.get("amount") or "0.00"
            row_values = ["" if is_major else _fmt(current_value), _fmt(current_value) if is_major else ""]
            for item in period_defs:
                period_value = _period_trading_amount(item["period"], side_key, label_path)
                row_values.extend(["" if is_major else _fmt(period_value), _fmt(period_value) if is_major else ""])
            rows.append([
                _statement_indent(str(label), depth),
                note,
                *row_values,
            ])
            if row.get("children") and (expanded_keys is None or key in expanded_keys):
                walk(row.get("children") or [], side_key, depth + 1, label_path, path)

    blank_cells = ["" for _ in range(2 + (len(period_defs) * 2))]
    rows.append(["Debit Side", "", *blank_cells])
    walk(report.get("debit_rows") or [], "debit_rows")
    debit_row = ["Total Debit", "", "-", _fmt(report.get("debit_total") or "0.00")]
    for item in period_defs:
        period_value = item["period"].get("debit_total", "0.00") if item["period"] and not item["period"].get("unavailable") else "N/A"
        debit_row.extend(["-", _fmt(period_value)])
    rows.append(debit_row)
    rows.append(["", "", *blank_cells])
    rows.append(["Credit Side", "", *blank_cells])
    walk(report.get("credit_rows") or [], "credit_rows")
    credit_row = ["Total Credit", "", "-", _fmt(report.get("credit_total") or "0.00")]
    for item in period_defs:
        period_value = item["period"].get("credit_total", "0.00") if item["period"] and not item["period"].get("unavailable") else "N/A"
        credit_row.extend(["-", _fmt(period_value)])
    rows.append(credit_row)
    gross_profit_row = ["Gross Profit", "", "-", _fmt(report.get("gross_profit") or "0.00")]
    for item in period_defs:
        period_value = item["period"].get("gross_profit", "0.00") if item["period"] and not item["period"].get("unavailable") else "N/A"
        gross_profit_row.extend(["-", _fmt(period_value)])
    rows.append(gross_profit_row)
    gross_loss_row = ["Gross Loss", "", "-", _fmt(report.get("gross_loss") or "0.00")]
    for item in period_defs:
        period_value = item["period"].get("gross_loss", "0.00") if item["period"] and not item["period"].get("unavailable") else "N/A"
        gross_loss_row.extend(["-", _fmt(period_value)])
    rows.append(gross_loss_row)
    return headers, rows


class FinancialReportsMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        entity_id = int(entity_id)
        self.enforce_scope(request, entity_id=entity_id)
        payload = build_financial_report_meta(entity_id)
        payload["reporting_policy"] = resolve_financial_reporting_policy(entity_id)
        return Response(payload)


class TrialBalanceAPIView(_BaseFinancialReportAPIView):
    required_permission_codes = (
        "reports.financial_hub.trial_balance.view",
        "reports.trial_balance.view",
    )

    def get(self, request):
        scope = self.get_scope(request)
        data = build_trial_balance(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            ledger_ids=scope.get("ledger_ids"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            account_group=scope.get("account_group") or scope.get("group_by"),
            include_zero_balances=scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            posted_only=scope.get("posted_only", True),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=scope.get("period_by"),
            view_type=scope.get("view_type"),
            include_opening=_trial_balance_scope_includes_opening(scope),
            include_movement=scope.get("include_movement", True),
            include_closing=scope.get("include_closing", True),
        )
        response = build_report_envelope(
            report_code="trial_balance",
            report_name="Trial Balance",
            payload=data,
            filters=self.build_filters(scope),
            defaults=REPORT_DEFAULTS,
        )
        return Response(_attach_financial_actions(response, request, export_base_path="/api/reports/financial/trial-balance/"))


class _BaseTrialBalanceExportAPIView(_BaseFinancialReportAPIView):
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content=content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def report_data(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_trial_balance_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        data = build_trial_balance(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            ledger_ids=scope.get("ledger_ids"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            account_group=scope.get("account_group") or scope.get("group_by"),
            include_zero_balances=scope.get("include_zero_balances", REPORT_DEFAULTS["show_zero_balances_default"]),
            posted_only=scope.get("posted_only", True),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=1,
            page_size=100000,
            period_by=scope.get("period_by"),
            view_type=scope.get("view_type"),
            include_opening=_trial_balance_scope_includes_opening(scope),
            include_movement=scope.get("include_movement", True),
            include_closing=scope.get("include_closing", True),
        )
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        headers, rows = _trial_balance_export_table(data)
        subtitle = _trial_balance_subtitle(scope_names, scope)
        return scope, data, headers, rows, subtitle, settings


class TrialBalanceExcelAPIView(_BaseTrialBalanceExportAPIView):
    def get(self, request):
        scope, data, raw_headers, raw_rows, subtitle, settings = self.report_data(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        expanded_keys = _parse_expanded_row_keys(request)
        presentation_headers, presentation_rows, presentation_numeric, presentation_center = _trial_balance_presentation_table(
            data,
            view_type=scope.get("view_type") or data.get("reporting", {}).get("view_type") or "summary",
            group_by=scope.get("account_group") or scope.get("group_by") or data.get("reporting", {}).get("group_by") or "ledger",
            settings=settings,
            expanded_keys=expanded_keys,
        )
        content = write_sectioned_excel(
            title="Trial Balance",
            subtitle=subtitle,
            summary_items=_trial_balance_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Trial Balance",
                    headers=presentation_headers,
                    rows=presentation_rows,
                    numeric_columns=presentation_numeric,
                    center_columns=presentation_center,
                ),
                ExportSection(
                    title="Raw Data",
                    headers=raw_headers,
                    rows=raw_rows,
                    numeric_columns={0, 6, 7, 8, 9},
                    center_columns={1, 10},
                ),
            ] if settings.get("export_layout", {}).get("excel_raw_data_sheet", True) else [
                ExportSection(
                    title="Trial Balance",
                    headers=presentation_headers,
                    rows=presentation_rows,
                    numeric_columns=presentation_numeric,
                    center_columns=presentation_center,
                )
            ],
            freeze_header=settings.get("export_layout", {}).get("freeze_excel_header", True),
        )
        filename = build_report_filename(
            "Trial_Balance",
            entity_name=scope_names.get("entity_name"),
            scope_label=_trial_balance_scope_filename(scope_names, scope),
            extension="xlsx",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class TrialBalanceCSVAPIView(_BaseTrialBalanceExportAPIView):
    def get(self, request):
        scope, data, _headers, _rows, subtitle, settings = self.report_data(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        expanded_keys = _parse_expanded_row_keys(request)
        presentation_headers, presentation_rows, presentation_numeric, presentation_center = _trial_balance_presentation_table(
            data,
            view_type=scope.get("view_type") or data.get("reporting", {}).get("view_type") or "summary",
            group_by=scope.get("account_group") or scope.get("group_by") or data.get("reporting", {}).get("group_by") or "ledger",
            settings=settings,
            expanded_keys=expanded_keys,
        )
        content = write_sectioned_csv(
            title="Trial Balance",
            meta_items=_trial_balance_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Trial Balance",
                    headers=presentation_headers,
                    rows=presentation_rows,
                    numeric_columns=presentation_numeric,
                    center_columns=presentation_center,
                )
            ],
        )
        filename = build_report_filename(
            "Trial_Balance",
            entity_name=scope_names.get("entity_name"),
            scope_label=_trial_balance_scope_filename(scope_names, scope),
            extension="csv",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="text/csv",
        )


class TrialBalancePDFAPIView(_BaseTrialBalanceExportAPIView):
    def get(self, request):
        scope, data, _headers, _rows, subtitle, settings = self.report_data(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        expanded_keys = _parse_expanded_row_keys(request)
        amount_headers, sections = _trial_balance_statement_pdf_sections(
            data,
            view_type=scope.get("view_type") or data.get("reporting", {}).get("view_type") or "summary",
            group_by=scope.get("account_group") or scope.get("group_by") or data.get("reporting", {}).get("group_by") or "ledger",
            settings=settings,
            expanded_keys=expanded_keys,
        )
        content = write_balance_sheet_statement_pdf(
            title="Trial Balance",
            subtitle=subtitle,
            meta_items=_trial_balance_export_meta(scope_names, scope, data, settings),
            amount_headers=amount_headers,
            sections=sections,
            header_density=settings.get("export_layout", {}).get("header_density", "compact"),
            metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
            amount_col_widths=[90, 84, 84, 90] if len(amount_headers) == 4 else None,
            particulars_min_width=410 if len(amount_headers) == 4 else None,
        )
        filename = build_report_filename(
            "Trial_Balance",
            entity_name=scope_names.get("entity_name"),
            scope_label=_trial_balance_scope_filename(scope_names, scope),
            extension="pdf",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/pdf",
        )


class TrialBalancePrintAPIView(TrialBalancePDFAPIView):
    export_mode = "inline"


class LedgerBookAPIView(_BaseFinancialReportAPIView):
    serializer_class = LedgerBookScopeSerializer
    required_permission_codes = (
        "reports.financial_hub.ledger_book.view",
        "reports.ledger_book.view",
    )

    def get(self, request):
        scope = self.get_scope(request)
        data = build_ledger_book(
            entity_id=scope["entity"],
            ledger_id=scope["ledger"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            scope_mode=scope.get("scope_mode"),
            search=scope.get("search"),
            voucher_types=[scope.get("voucher_type")] if scope.get("voucher_type") else None,
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
        )
        return Response(
            _attach_financial_actions(
                build_report_envelope(
                report_code="ledger_book",
                report_name="Ledger Book",
                payload=data,
                filters={**self.build_filters(scope), "ledger": scope["ledger"], "voucher_type": scope.get("voucher_type")},
                defaults=REPORT_DEFAULTS,
                ),
                request,
                export_base_path="/api/reports/financial/ledger-book/",
            )
        )


class _BaseLedgerBookExportAPIView(_BaseFinancialReportAPIView):
    serializer_class = LedgerBookScopeSerializer
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content=content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def report_data(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_ledger_book_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        data = build_ledger_book(
            entity_id=scope["entity"],
            ledger_id=scope["ledger"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            scope_mode=scope.get("scope_mode"),
            search=scope.get("search"),
            voucher_types=[scope.get("voucher_type")] if scope.get("voucher_type") else None,
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=1,
            page_size=100000,
        )
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        ledger = data.get("ledger") or {}
        subtitle = _ledger_book_subtitle(scope_names, scope, ledger)
        return scope, data, subtitle, settings

    def build_table(self, data, settings):
        visible_columns = get_visible_ledger_book_columns(settings)
        column_labels = {
            "date": "Date",
            "voucher_no": "Voucher No",
            "voucher_type": "Voucher Type",
            "description": "Description",
            "debit": "Debit",
            "credit": "Credit",
            "running_balance": "Running Balance",
        }
        numeric_keys = {"debit", "credit", "running_balance"}
        headers = [column_labels[key] for key in visible_columns]
        rows = []
        for row in data.get("rows", []):
            base_values = {
                "date": _format_scope_date(row.get("posting_date")),
                "voucher_no": row.get("voucher_number") or "-",
                "voucher_type": row.get("voucher_type_name") or row.get("voucher_type") or "-",
                "description": row.get("description") or "-",
                "debit": format_financial_hub_amount(row.get("debit", "0.00"), settings=settings),
                "credit": format_financial_hub_amount(row.get("credit", "0.00"), settings=settings),
                "running_balance": format_financial_hub_balance(row.get("running_balance", "0.00"), settings=settings),
            }
            rows.append([base_values[key] for key in visible_columns])
        totals = data.get("totals") or {}
        total_base_values = {
            "date": "",
            "voucher_no": "",
            "voucher_type": "",
            "description": "Totals",
            "debit": format_financial_hub_amount(totals.get("debit", "0.00"), settings=settings),
            "credit": format_financial_hub_amount(totals.get("credit", "0.00"), settings=settings),
            "running_balance": format_financial_hub_balance(totals.get("closing_balance", "0.00"), settings=settings),
        }
        rows.append([total_base_values[key] for key in visible_columns])
        numeric_columns = {index for index, key in enumerate(visible_columns) if key in numeric_keys}
        return headers, rows, numeric_columns, visible_columns


def _ledger_book_export_meta(scope_names, scope, data, settings):
    ledger = data.get("ledger") or {}
    reporting = data.get("reporting") or {}
    return [
        ("Entity", scope_names["entity_name"] or "Selected entity"),
        ("Financial Year", scope_names["entityfin_name"] or "Current FY"),
        ("Subentity", scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")),
        ("Period", f"{_format_scope_date(scope.get('from_date')) or '-'} to {_format_scope_date(scope.get('to_date')) or '-'}"),
        ("Scope Mode", reporting.get("scope_mode") or scope.get("scope_mode") or "financial_year"),
        ("Ledger", ledger.get("name") or "Selected ledger"),
        ("Ledger Code", ledger.get("ledger_code") or "-"),
        ("Account Head", ledger.get("accounthead_name") or "-"),
        ("Account Type", ledger.get("accounttype_name") or "-"),
        ("Display Unit", financial_hub_amount_unit_label(settings)),
        ("Running Balance Scope", ledger.get("running_balance_scope") or reporting.get("basis") or "-"),
        ("Balance Basis", ledger.get("balance_basis") or reporting.get("basis") or "-"),
        ("Balance Integrity", "Verified" if ledger.get("balance_integrity", True) else "Review required"),
    ]


def _ledger_book_export_section(data, *, settings):
    visible_columns = get_visible_ledger_book_columns(settings)
    headers = {
        "date": "Date",
        "voucher_no": "Voucher No",
        "voucher_type": "Voucher Type",
        "description": "Description",
        "debit": "Debit",
        "credit": "Credit",
        "running_balance": "Running Balance",
    }
    numeric_keys = {"debit", "credit", "running_balance"}
    width_map = {
        "date": 64,
        "voucher_no": 96,
        "voucher_type": 90,
        "description": 250,
        "debit": 76,
        "credit": 76,
        "running_balance": 88,
    }
    rows = []
    row_kinds = []
    for row in data.get("rows", []):
        base_values = {
            "date": _format_scope_date(row.get("posting_date")),
            "voucher_no": row.get("voucher_number") or "-",
            "voucher_type": row.get("voucher_type_name") or row.get("voucher_type") or "-",
            "description": row.get("description") or "-",
            "debit": format_financial_hub_amount(row.get("debit", "0.00"), settings=settings),
            "credit": format_financial_hub_amount(row.get("credit", "0.00"), settings=settings),
            "running_balance": format_financial_hub_balance(row.get("running_balance", "0.00"), settings=settings),
        }
        rows.append([base_values[key] for key in visible_columns])
        row_kinds.append("detail")
    totals = data.get("totals") or {}
    total_base_values = {
        "date": "",
        "voucher_no": "",
        "voucher_type": "",
        "description": "Report Total",
        "debit": format_financial_hub_amount(totals.get("debit", "0.00"), settings=settings),
        "credit": format_financial_hub_amount(totals.get("credit", "0.00"), settings=settings),
        "running_balance": format_financial_hub_balance(totals.get("closing_balance", "0.00"), settings=settings),
    }
    rows.append([total_base_values[key] for key in visible_columns])
    row_kinds.append("final_total")
    return ExportSection(
        title="Ledger Entries",
        headers=[headers[key] for key in visible_columns],
        rows=rows,
        row_kinds=row_kinds,
        numeric_columns={index for index, key in enumerate(visible_columns) if key in numeric_keys},
        col_widths=[width_map.get(key, 84) for key in visible_columns],
        empty_message="No ledger rows found for the selected scope.",
    )


class LedgerBookExcelAPIView(_BaseLedgerBookExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        ledger = data.get("ledger") or {}
        section = _ledger_book_export_section(data, settings=settings)
        summary_items = [
            ("Entity", scope_names["entity_name"] or "Selected entity"),
            ("Financial Year", scope_names["entityfin_name"] or "Current FY"),
            ("Subentity", scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")),
            ("Scope Mode", (data.get("reporting") or {}).get("scope_mode") or scope.get("scope_mode") or "financial_year"),
            ("Ledger", ledger.get("name") or "Selected ledger"),
            ("Opening Balance", format_financial_hub_balance(data.get("opening_balance", "0.00"), settings=settings)),
            ("Debit Total", format_financial_hub_amount((data.get("totals") or {}).get("debit", "0.00"), settings=settings)),
            ("Credit Total", format_financial_hub_amount((data.get("totals") or {}).get("credit", "0.00"), settings=settings)),
            ("Closing Balance", format_financial_hub_balance((data.get("totals") or {}).get("closing_balance", "0.00"), settings=settings)),
            ("Running Balance Scope", data.get("running_balance_scope") or (data.get("reporting") or {}).get("basis") or "-"),
            ("Balance Basis", data.get("balance_basis") or (data.get("reporting") or {}).get("basis") or "-"),
            ("Balance Integrity", "Verified" if data.get("balance_integrity", True) else "Review required"),
            ("Display Unit", financial_hub_amount_unit_label(settings)),
        ]
        export_subtitle = f"{subtitle} | Display Unit: {financial_hub_amount_unit_label(settings)}"
        content = write_sectioned_excel(
            title="Ledger Book",
            subtitle=export_subtitle,
            summary_items=summary_items,
            sections=[section],
            orientation="landscape",
            freeze_header=settings.get("export_layout", {}).get("freeze_excel_header", True),
        )
        return self.export_response(
            filename=f"LedgerBook_{_safe_filename(subtitle)}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class LedgerBookCSVAPIView(_BaseLedgerBookExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        ledger = data.get("ledger") or {}
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        section = _ledger_book_export_section(data, settings=settings)
        meta_items = _ledger_book_export_meta(scope_names, scope, data, settings)
        content = write_sectioned_csv(
            title="Ledger Book",
            meta_items=meta_items,
            sections=[section],
        )
        return self.export_response(
            filename=f"LedgerBook_{_safe_filename(subtitle)}.csv",
            content=content,
            content_type="text/csv",
        )


class LedgerBookPDFAPIView(_BaseLedgerBookExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        ledger = data.get("ledger") or {}
        meta_items = _ledger_book_export_meta(scope_names, scope, data, settings)
        meta_items.extend([
            ("Opening Balance", format_financial_hub_balance(data.get("opening_balance", "0.00"), settings=settings)),
            ("Closing Balance", format_financial_hub_balance((data.get("totals") or {}).get("closing_balance", "0.00"), settings=settings)),
            ("Transactions", (data.get("pagination") or {}).get("total_records", 0)),
            ("Display Unit", financial_hub_amount_unit_label(settings)),
        ])
        export_subtitle = f"{subtitle} | Display Unit: {financial_hub_amount_unit_label(settings)}"
        content = write_sectioned_pdf(
            title="Ledger Book",
            meta_items=meta_items,
            subtitle=export_subtitle,
            sections=[_ledger_book_export_section(data, settings=settings)],
            pagesize=landscape(A4),
            header_density=settings.get("export_layout", {}).get("header_density", "compact"),
            metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
        )
        return self.export_response(
            filename=f"LedgerBook_{_safe_filename(subtitle)}.pdf",
            content=content,
            content_type="application/pdf",
        )


class LedgerBookPrintAPIView(LedgerBookPDFAPIView):
    export_mode = "inline"


class LedgerSummaryAPIView(_BaseFinancialReportAPIView):
    required_permission_codes = (
        "reports.financial_hub.ledger_summary.view",
        "reports.ledgersummary.view",
        "reports.ledger_summary.view",
    )

    def get(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_ledger_summary_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        report_defaults = settings.get("report_defaults") or {}
        data = build_ledger_summary(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by"),
            include_zero_balance=scope.get("include_zero_balances", report_defaults.get("include_zero_balances", False)),
            include_opening=_scope_includes_separate_opening(scope),
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", True)),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order") or report_defaults.get("default_sort_order") or "asc",
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            view_type=scope.get("view_type") or report_defaults.get("default_view_type") or "summary",
        )
        response = build_report_envelope(
            report_code="ledger_summary",
            report_name="Ledger Summary",
            payload=data,
            filters=self.build_filters(scope),
            defaults=REPORT_DEFAULTS,
        )
        return Response(_attach_financial_actions(response, request, export_base_path="/api/reports/financial/ledger-summary/"))


class _BaseLedgerSummaryExportAPIView(_BaseFinancialReportAPIView):
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content=content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def report_data(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_ledger_summary_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        report_defaults = settings.get("report_defaults") or {}
        data = build_ledger_summary(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by"),
            include_zero_balance=scope.get("include_zero_balances", report_defaults.get("include_zero_balances", False)),
            include_opening=_scope_includes_separate_opening(scope),
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", True)),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order") or report_defaults.get("default_sort_order") or "asc",
            page=1,
            page_size=100000,
            view_type=scope.get("view_type") or report_defaults.get("default_view_type") or "summary",
        )
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        subtitle = _ledger_summary_subtitle(scope_names, scope, data)
        return scope, data, subtitle, settings


class LedgerSummaryExcelAPIView(_BaseLedgerSummaryExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        headers, rows, row_kinds, numeric_columns, center_columns = _ledger_summary_export_table(
            data,
            settings=settings,
            expanded_keys=expanded_keys,
        )
        content = write_sectioned_excel(
            title="Ledger Summary",
            subtitle=subtitle,
            summary_items=_ledger_summary_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Ledger Summary",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
            freeze_header=settings.get("export_layout", {}).get("freeze_excel_header", True),
        )
        filename = build_report_filename(
            "Ledger_Summary",
            entity_name=scope_names.get("entity_name"),
            scope_label=_ledger_summary_scope_filename(scope_names, scope),
            extension="xlsx",
        )
        return self.export_response(filename=filename, content=content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class LedgerSummaryCSVAPIView(_BaseLedgerSummaryExportAPIView):
    def get(self, request):
        scope, data, _subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        headers, rows, row_kinds, numeric_columns, center_columns = _ledger_summary_export_table(
            data,
            settings=settings,
            expanded_keys=expanded_keys,
        )
        content = write_sectioned_csv(
            title="Ledger Summary",
            meta_items=_ledger_summary_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Ledger Summary",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
        )
        filename = build_report_filename(
            "Ledger_Summary",
            entity_name=scope_names.get("entity_name"),
            scope_label=_ledger_summary_scope_filename(scope_names, scope),
            extension="csv",
        )
        return self.export_response(filename=filename, content=content, content_type="text/csv")


class LedgerSummaryPDFAPIView(_BaseLedgerSummaryExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        headers, rows, row_kinds, numeric_columns, center_columns = _ledger_summary_export_table(
            data,
            settings=settings,
            expanded_keys=expanded_keys,
        )
        col_width_map = {
            "Account Head": 110,
            "Account Name": 170,
            "Account Type": 110,
            "Opening": 76,
            "OB DC": 40,
            "Debit": 76,
            "Credit": 76,
            "Balance": 84,
            "DC": 36,
        }
        col_widths = [col_width_map.get(header, 70) for header in headers]
        content = write_sectioned_pdf(
            title="Ledger Summary",
            subtitle=subtitle,
            meta_items=_ledger_summary_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Ledger Summary",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                    col_widths=col_widths,
                )
            ],
            pagesize=landscape(A4),
            header_density=settings.get("export_layout", {}).get("header_density", "compact"),
            metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
        )
        filename = build_report_filename(
            "Ledger_Summary",
            entity_name=scope_names.get("entity_name"),
            scope_label=_ledger_summary_scope_filename(scope_names, scope),
            extension="pdf",
        )
        return self.export_response(filename=filename, content=content, content_type="application/pdf")


class LedgerSummaryPrintAPIView(LedgerSummaryPDFAPIView):
    export_mode = "inline"


class ProfitAndLossAPIView(_BaseFinancialReportAPIView):
    required_permission_codes = (
        "reports.financial_hub.profit_loss.view",
        "reports.income_expenditure.view",
    )

    def get(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_profit_loss_settings(settings_payload)
        report_defaults = settings.get("report_defaults") or {}
        reporting_policy = resolve_financial_reporting_policy(scope["entity"])
        view_type = (scope.get("view_type") or report_defaults.get("default_view_type") or "summary").lower()
        account_group = scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by")
        if not account_group:
            account_group = "ledger" if view_type == "detailed" else "accounthead"
        stock_valuation_mode = scope.get(
            "stock_valuation_mode",
            report_defaults.get("stock_valuation_mode") or REPORT_DEFAULTS["profit_loss_stock_valuation_mode"],
        )
        stock_valuation_method = scope.get(
            "stock_valuation_method",
            report_defaults.get("stock_valuation_method") or REPORT_DEFAULTS["profit_loss_stock_valuation_method"],
        )
        period_by = _effective_period_by(scope)
        data = build_profit_and_loss(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=account_group,
            include_zero_balances=scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order") or report_defaults.get("default_sort_order") or "asc",
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=period_by,
            view_type=view_type,
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", True)),
            hide_zero_rows=scope.get("hide_zero_rows", report_defaults.get("hide_zero_rows", True)),
            account_group=account_group,
            ledger_ids=scope.get("ledger_ids") or None,
            stock_valuation_mode=stock_valuation_mode,
            stock_valuation_method=stock_valuation_method,
            reporting_policy=reporting_policy,
        )
        response = build_report_envelope(
            report_code="profit_loss",
            report_name="Profit and Loss",
            payload=data,
            filters=self.build_filters(scope),
            defaults=REPORT_DEFAULTS,
        )
        response = _attach_financial_actions(
            response,
            request,
            export_base_path="/api/reports/financial/profit-loss/",
        )
        query = _filtered_querydict(request, exclude=["page", "page_size", "orientation"])
        base_url = "/api/reports/financial/profit-loss/"
        query_suffix = f"?{query}" if query else ""
        response["actions"]["export_urls"]["pdf_landscape"] = f"{base_url}pdf/landscape/{query_suffix}"
        response["actions"]["export_urls"]["pdf_portrait"] = f"{base_url}pdf/portrait/{query_suffix}"
        response["actions"]["export_urls"]["excel_landscape"] = f"{base_url}excel/landscape/{query_suffix}"
        response["actions"]["export_urls"]["excel_portrait"] = f"{base_url}excel/portrait/{query_suffix}"
        response["available_exports"] = ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"]
        return Response(response)


class _BaseProfitAndLossExportAPIView(_BaseFinancialReportAPIView):
    export_mode = "attachment"
    export_orientation = "landscape"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content=content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def report_data(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_profit_loss_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        reporting_policy = resolve_financial_reporting_policy(scope["entity"])
        report_defaults = settings.get("report_defaults") or {}
        view_type = (scope.get("view_type") or report_defaults.get("default_view_type") or "summary").lower()
        account_group = scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by")
        if not account_group:
            account_group = "ledger" if view_type == "detailed" else "accounthead"
        stock_valuation_mode = scope.get(
            "stock_valuation_mode",
            report_defaults.get("stock_valuation_mode") or REPORT_DEFAULTS["profit_loss_stock_valuation_mode"],
        )
        stock_valuation_method = scope.get(
            "stock_valuation_method",
            report_defaults.get("stock_valuation_method") or REPORT_DEFAULTS["profit_loss_stock_valuation_method"],
        )
        period_by = _effective_period_by(scope)
        data = build_profit_and_loss(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=account_group,
            include_zero_balances=scope.get("include_zero_balances", REPORT_DEFAULTS["show_zero_balances_default"]),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order") or report_defaults.get("default_sort_order") or "asc",
            page=1,
            page_size=100000,
            period_by=period_by,
            view_type=view_type,
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", True)),
            hide_zero_rows=scope.get("hide_zero_rows", report_defaults.get("hide_zero_rows", True)),
            account_group=account_group,
            ledger_ids=scope.get("ledger_ids") or None,
            stock_valuation_mode=stock_valuation_mode,
            stock_valuation_method=stock_valuation_method,
            reporting_policy=reporting_policy,
        )
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        subtitle = _profit_loss_subtitle(scope_names, scope, data)
        return scope, data, subtitle, settings

    def build_orientation(self, request):
        orientation = str(
            getattr(self, "export_orientation", None)
            or request.query_params.get("orientation")
            or "landscape"
        ).strip().lower()
        return orientation if orientation in {"landscape", "portrait"} else "landscape"


class ProfitAndLossExcelAPIView(_BaseProfitAndLossExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        collapsed_sections = _parse_collapsed_sections(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if _presentation_mode(scope) == "statement":
            headers, rows = _statement_profit_loss_rows(data, settings=settings, expanded_keys=expanded_keys, collapsed_sections=collapsed_sections)
            numeric_columns = set(range(2, len(headers)))
            center_columns = {1}
            row_kinds = None
        else:
            headers, rows, row_kinds = _profit_loss_export_table(data, include_periods=True, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = {index for index, header in enumerate(headers) if header.endswith("Amount") or header == "Amount"}
            center_columns = set()
        content = write_sectioned_excel(
            title="Profit & Loss",
            subtitle=subtitle,
            summary_items=_profit_loss_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Profit & Loss",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
            orientation=self.build_orientation(request),
            freeze_header=settings.get("export_layout", {}).get("freeze_excel_header", True),
        )
        filename = build_report_filename(
            "Profit_Loss",
            entity_name=scope_names.get("entity_name"),
            scope_label=_profit_loss_scope_filename(scope_names, scope),
            extension="xlsx",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ProfitAndLossCSVAPIView(_BaseProfitAndLossExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        collapsed_sections = _parse_collapsed_sections(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if _presentation_mode(scope) == "statement":
            headers, rows = _statement_profit_loss_rows(data, settings=settings, expanded_keys=expanded_keys, collapsed_sections=collapsed_sections)
            numeric_columns = set(range(2, len(headers)))
            center_columns = {1}
            row_kinds = None
        else:
            headers, rows, row_kinds = _profit_loss_export_table(data, include_periods=True, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = {index for index, header in enumerate(headers) if header.endswith("Amount") or header == "Amount"}
            center_columns = set()
        content = write_sectioned_csv(
            title="Profit & Loss",
            meta_items=_profit_loss_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Profit & Loss",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
        )
        filename = build_report_filename(
            "Profit_Loss",
            entity_name=scope_names.get("entity_name"),
            scope_label=_profit_loss_scope_filename(scope_names, scope),
            extension="csv",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="text/csv",
        )


class ProfitAndLossPDFAPIView(_BaseProfitAndLossExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        collapsed_sections = _parse_collapsed_sections(request)
        orientation = self.build_orientation(request)
        portrait_mode = orientation == "portrait"
        statement_mode = _presentation_mode(scope) == "statement"
        periods = data.get("periods") or []
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if statement_mode:
            amount_headers, sections = _profit_loss_statement_pdf_sections(data, settings=settings, expanded_keys=expanded_keys, collapsed_sections=collapsed_sections)
            content = write_balance_sheet_statement_pdf(
                title="Profit & Loss",
                subtitle=subtitle,
                meta_items=_profit_loss_export_meta(scope_names, scope, data, settings),
                amount_headers=amount_headers,
                sections=sections,
                header_density=settings.get("export_layout", {}).get("header_density", "compact"),
                metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
            )
            filename = build_report_filename(
                "Profit_Loss",
                entity_name=scope_names.get("entity_name"),
                scope_label=_profit_loss_scope_filename(scope_names, scope),
                extension="pdf",
            )
            return self.export_response(
                filename=filename,
                content=content,
                content_type="application/pdf",
            )
        else:
            headers, rows, row_kinds = _profit_loss_export_table(data, include_periods=True, settings=settings, expanded_keys=expanded_keys)
            if portrait_mode:
                base_widths = {
                    "Section": 64,
                    "Particulars": 190,
                    "Account Head": 104,
                    "Account Type": 98,
                    "Amount": 76,
                }
                col_widths = [base_widths.get(header, 42) for header in headers[:max(0, len(headers) - len(periods))]]
                if periods:
                    insertion_at = len(col_widths) - (1 if "Amount" in headers else 0)
                    col_widths[insertion_at:insertion_at] = [60] * len(periods)
                pagesize = A4
            else:
                base_widths = {
                    "Section": 76,
                    "Particulars": 240,
                    "Account Head": 146,
                    "Account Type": 126,
                    "Amount": 110,
                }
                col_widths = [base_widths.get(header, 72) for header in headers[:max(0, len(headers) - len(periods))]]
                if periods:
                    insertion_at = len(col_widths) - (1 if "Amount" in headers else 0)
                    col_widths[insertion_at:insertion_at] = [94] * len(periods)
                pagesize = landscape(A4)
            numeric_columns = {index for index, header in enumerate(headers) if header.endswith("Amount") or header == "Amount"}
            center_columns = set()
        content = write_sectioned_pdf(
            title="Profit & Loss",
            subtitle=subtitle,
            meta_items=_profit_loss_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Profit & Loss",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                    col_widths=col_widths,
                )
            ],
            pagesize=pagesize,
            header_density=settings.get("export_layout", {}).get("header_density", "compact"),
            metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
        )
        filename = build_report_filename(
            "Profit_Loss",
            entity_name=scope_names.get("entity_name"),
            scope_label=_profit_loss_scope_filename(scope_names, scope),
            extension="pdf",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/pdf",
        )


class ProfitAndLossPrintAPIView(ProfitAndLossPDFAPIView):
    export_mode = "inline"


class ProfitAndLossExcelLandscapeAPIView(ProfitAndLossExcelAPIView):
    export_orientation = "landscape"


class ProfitAndLossExcelPortraitAPIView(ProfitAndLossExcelAPIView):
    export_orientation = "portrait"


class ProfitAndLossPDFLandscapeAPIView(ProfitAndLossPDFAPIView):
    export_orientation = "landscape"


class ProfitAndLossPDFPortraitAPIView(ProfitAndLossPDFAPIView):
    export_orientation = "portrait"


class BalanceSheetAPIView(_BaseFinancialReportAPIView):
    required_permission_codes = (
        "reports.financial_hub.balance_sheet.view",
        "reports.balance_sheet.view",
    )

    def get(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_balance_sheet_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        report_defaults = settings.get("report_defaults") or {}
        reporting_policy = resolve_financial_reporting_policy(scope["entity"])
        period_by = _effective_period_by(scope)
        data = build_balance_sheet(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by"),
            view_type=scope.get("view_type") or report_defaults.get("default_view_type"),
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", REPORT_DEFAULTS["balance_sheet_posted_only_default"])),
            hide_zero_rows=scope.get("hide_zero_rows", report_defaults.get("hide_zero_rows", REPORT_DEFAULTS["balance_sheet_hide_zero_rows_default"])),
            include_zero_balances=scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            account_group=scope.get("account_group") or report_defaults.get("default_group_by"),
            ledger_ids=scope.get("ledger_ids"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order") or report_defaults.get("default_sort_order") or "asc",
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=period_by,
            reporting_policy=reporting_policy,
            include_diagnostics=scope.get("include_diagnostics", False),
        )
        response = build_report_envelope(
            report_code="balance_sheet",
            report_name="Balance Sheet",
            payload=data,
            filters=self.build_filters(scope),
            defaults=REPORT_DEFAULTS,
        )
        response = _attach_financial_actions(
            response,
            request,
            export_base_path="/api/reports/financial/balance-sheet/",
        )
        query = _filtered_querydict(request, exclude=["page", "page_size", "orientation"])
        base_url = "/api/reports/financial/balance-sheet/"
        query_suffix = f"?{query}" if query else ""
        response["actions"]["export_urls"]["pdf_landscape"] = f"{base_url}pdf/landscape/{query_suffix}"
        response["actions"]["export_urls"]["pdf_portrait"] = f"{base_url}pdf/portrait/{query_suffix}"
        response["actions"]["export_urls"]["excel_landscape"] = f"{base_url}excel/landscape/{query_suffix}"
        response["actions"]["export_urls"]["excel_portrait"] = f"{base_url}excel/portrait/{query_suffix}"
        response["available_exports"] = ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"]
        return Response(response)


def _balance_sheet_subtitle(scope_names, scope, report):
    return _financial_export_subtitle(scope_names, scope)


def _humanize_balance_sheet_group(value):
    labels = {
        "ledger": "Ledger",
        "accounthead": "Account head",
        "accounttype": "Account type",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "ledger").replace("_", " ").title())


def _humanize_balance_sheet_view(value):
    labels = {
        "summary": "Summary",
        "detailed": "Detailed",
    }
    return labels.get(str(value or "").strip().lower(), str(value or "summary").replace("_", " ").title())


def _balance_sheet_export_meta(scope_names, scope, report, settings=None):
    subentity_label = scope_names["subentity_name"] or (f"Subentity {scope.get('subentity')}" if scope.get("subentity") else "All subentities")
    balance_diff = _parse_decimal(report.get("totals", {}).get("assets")) - _parse_decimal(report.get("totals", {}).get("liabilities_and_equity"))
    reporting = report.get("reporting") or {}
    meta_items = [
        ("Entity", scope_names["entity_name"] or "Selected entity"),
        ("Financial Year", scope_names["entityfin_name"] or "Current FY"),
        ("Subentity", subentity_label),
        ("Scope", _humanize_trial_balance_scope(scope.get("scope_mode") or "financial_year")),
        ("Presentation", _presentation_label(
            scope,
            _humanize_balance_sheet_view(scope.get('view_type') or reporting.get('view_type') or 'summary'),
            _humanize_balance_sheet_group(scope.get('account_group') or scope.get('group_by') or reporting.get('group_by') or 'ledger'),
        )),
        ("Filters", f"{'Posted only' if scope.get('posted_only', True) else 'Posted and draft'} • {'Zero rows hidden' if scope.get('hide_zero_rows', True) else 'Zero rows shown'}"),
        ("Amount Unit", financial_hub_amount_unit_label(settings or {})),
        ("Stock", f"{scope.get('stock_valuation_mode') or reporting.get('stock_valuation_mode') or 'auto'} / {scope.get('stock_valuation_method') or reporting.get('stock_valuation_method') or 'fifo'}"),
        ("Balance Status", "Balanced" if balance_diff == 0 else "Mismatch"),
        ("Difference", format_financial_hub_amount(f"{balance_diff:.2f}", settings=settings or {})),
    ]
    if scope.get("search"):
        meta_items.append(("Search", scope.get("search")))
    return meta_items


def _balance_sheet_scope_filename(scope_names, scope):
    if scope.get("as_of_date"):
        return f"As_Of_{scope.get('as_of_date')}"
    if scope.get("from_date") and scope.get("to_date"):
        return f"{scope.get('from_date')}_to_{scope.get('to_date')}"
    if scope_names.get("entityfin_name"):
        return scope_names["entityfin_name"]
    return scope.get("scope_mode") or "balance_sheet"


class _BaseBalanceSheetExportAPIView(_BaseFinancialReportAPIView):
    export_mode = "attachment"
    export_orientation = "landscape"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content=content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def build_orientation(self, request):
        orientation = str(
            getattr(self, "export_orientation", None)
            or request.query_params.get("orientation")
            or "landscape"
        ).strip().lower()
        return orientation if orientation in {"landscape", "portrait"} else "landscape"

    def report_data(self, request):
        scope = self.get_scope(request)
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_balance_sheet_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        report_defaults = settings.get("report_defaults") or {}
        reporting_policy = resolve_financial_reporting_policy(scope["entity"])
        period_by = _effective_period_by(scope)
        data = build_balance_sheet(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by"),
            view_type=scope.get("view_type") or report_defaults.get("default_view_type"),
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", REPORT_DEFAULTS["balance_sheet_posted_only_default"])),
            hide_zero_rows=scope.get("hide_zero_rows", report_defaults.get("hide_zero_rows", REPORT_DEFAULTS["balance_sheet_hide_zero_rows_default"])),
            include_zero_balances=scope.get("include_zero_balances", REPORT_DEFAULTS["show_zero_balances_default"]),
            account_group=scope.get("account_group") or report_defaults.get("default_group_by"),
            ledger_ids=scope.get("ledger_ids"),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order") or report_defaults.get("default_sort_order") or "asc",
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=period_by,
            reporting_policy=reporting_policy,
            include_diagnostics=True,
        )
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        subtitle = _balance_sheet_subtitle(scope_names, scope, data)
        return scope, data, subtitle, settings


class BalanceSheetExcelAPIView(_BaseBalanceSheetExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        orientation = self.build_orientation(request)
        statement_mode = _presentation_mode(scope) == "statement"
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if statement_mode:
            headers, rows = _statement_balance_sheet_rows(data, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = set(range(2, len(headers)))
            center_columns = {1}
            row_kinds = None
        else:
            headers, rows, row_kinds = _balance_sheet_export_table(data, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Section", "Particulars", "Account Head", "Account Type"})}
            center_columns = set()
        content = write_sectioned_excel(
            title="Balance Sheet",
            subtitle=subtitle,
            summary_items=_balance_sheet_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Balance Sheet",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
            orientation=orientation,
            freeze_header=settings.get("export_layout", {}).get("freeze_excel_header", True),
        )
        filename = build_report_filename(
            "Balance_Sheet",
            entity_name=scope_names.get("entity_name"),
            scope_label=_balance_sheet_scope_filename(scope_names, scope),
            extension="xlsx",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class BalanceSheetCSVAPIView(_BaseBalanceSheetExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if _presentation_mode(scope) == "statement":
            headers, rows = _statement_balance_sheet_rows(data, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = set(range(2, len(headers)))
            center_columns = {1}
            row_kinds = None
        else:
            headers, rows, row_kinds = _balance_sheet_export_table(data, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Section", "Particulars", "Account Head", "Account Type"})}
            center_columns = set()
        content = write_sectioned_csv(
            title="Balance Sheet",
            meta_items=_balance_sheet_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Balance Sheet",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
        )
        filename = build_report_filename(
            "Balance_Sheet",
            entity_name=scope_names.get("entity_name"),
            scope_label=_balance_sheet_scope_filename(scope_names, scope),
            extension="csv",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="text/csv",
        )


class BalanceSheetPDFAPIView(_BaseBalanceSheetExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        orientation = self.build_orientation(request)
        statement_mode = _presentation_mode(scope) == "statement"
        pagesize = landscape(A4) if orientation == "landscape" and not statement_mode else A4
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if statement_mode:
            amount_headers, sections = _balance_sheet_statement_pdf_sections(data, settings=settings, expanded_keys=expanded_keys)
            content = write_balance_sheet_statement_pdf(
                title="Balance Sheet",
                subtitle=subtitle,
                meta_items=_balance_sheet_export_meta(scope_names, scope, data, settings),
                amount_headers=amount_headers,
                sections=sections,
                header_density=settings.get("export_layout", {}).get("header_density", "compact"),
                metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
            )
            filename = build_report_filename(
                "Balance_Sheet",
                entity_name=scope_names.get("entity_name"),
                scope_label=_balance_sheet_scope_filename(scope_names, scope),
                extension="pdf",
            )
            return self.export_response(
                filename=filename,
                content=content,
                content_type="application/pdf",
            )
        elif orientation == "landscape":
            headers, rows, row_kinds = _balance_sheet_export_table(data, settings=settings, expanded_keys=expanded_keys)
            base_widths = {
                "Section": 76,
                "Particulars": 240,
                "Account Head": 146,
                "Account Type": 126,
                "Amount": 110,
            }
            col_widths = [base_widths.get(header, 72) for header in headers]
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Section", "Particulars", "Account Head", "Account Type"})}
            center_columns = set()
        else:
            headers, rows, row_kinds = _balance_sheet_export_table(data, settings=settings, expanded_keys=expanded_keys)
            base_widths = {
                "Section": 64,
                "Particulars": 190,
                "Account Head": 104,
                "Account Type": 98,
                "Amount": 76,
            }
            col_widths = [base_widths.get(header, 42) for header in headers]
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Section", "Particulars", "Account Head", "Account Type"})}
            center_columns = set()
        content = write_sectioned_pdf(
            title="Balance Sheet",
            subtitle=subtitle,
            meta_items=_balance_sheet_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Balance Sheet",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                    col_widths=col_widths,
                )
            ],
            pagesize=pagesize,
            header_density=settings.get("export_layout", {}).get("header_density", "compact"),
            metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
        )
        filename = build_report_filename(
            "Balance_Sheet",
            entity_name=scope_names.get("entity_name"),
            scope_label=_balance_sheet_scope_filename(scope_names, scope),
            extension="pdf",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/pdf",
        )


class BalanceSheetPrintAPIView(BalanceSheetPDFAPIView):
    export_mode = "inline"


class BalanceSheetExcelLandscapeAPIView(BalanceSheetExcelAPIView):
    export_orientation = "landscape"


class BalanceSheetExcelPortraitAPIView(BalanceSheetExcelAPIView):
    export_orientation = "portrait"


class BalanceSheetPDFLandscapeAPIView(BalanceSheetPDFAPIView):
    export_orientation = "landscape"


class BalanceSheetPDFPortraitAPIView(BalanceSheetPDFAPIView):
    export_orientation = "portrait"


class TradingAccountAPIView(FinancialReportPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = (
        "reports.financial_hub.trading_account.view",
        "reports.trading_account.view",
    )

    def get(self, request):
        serializer = FinancialReportScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_trading_account_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        report_defaults = settings.get("report_defaults") or {}
        effective_view_type = scope.get("view_type") or report_defaults.get("default_view_type") or "summary"
        valuation_method = (request.query_params.get("valuation_method") or report_defaults.get("stock_valuation_method") or "fifo").lower()
        level = (request.query_params.get("level") or ("account" if effective_view_type == "detailed" else "head")).lower()
        period_by = (_effective_period_by(scope) or request.query_params.get("period_by") or "").strip().lower() or None

        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])

        from_date = scope.get("from_date")
        to_date = scope.get("to_date")
        as_of_date = scope.get("as_of_date") or scope.get("as_on_date")
        if as_of_date and not to_date:
            to_date = as_of_date
        start, end = resolve_date_window(
            scope.get("entityfinid"),
            from_date,
            to_date,
        )
        data = build_trading_account_dynamic(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            startdate=start.isoformat(),
            enddate=end.isoformat(),
            period_by=period_by,
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", True)),
            hide_zero_rows=scope.get("hide_zero_rows", report_defaults.get("hide_zero_rows", not scope.get("include_zero_balance", False))),
            view_type=effective_view_type or ("detailed" if level == "account" else "summary"),
            account_group=scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by"),
            ledger_ids=scope.get("ledger_ids") or None,
            search=scope.get("search"),
            valuation_method=valuation_method,
            level=level,
        )
        response = build_report_envelope(
            report_code="trading_account",
            report_name="Trading Account",
            payload=data,
            filters=self.build_filters(scope, level=level, valuation_method=valuation_method, start=start, end=end, period_by=period_by),
            defaults=REPORT_DEFAULTS,
        )
        response = _attach_financial_actions(
            response,
            request,
            export_base_path="/api/reports/financial/trading-account/",
        )
        query = _filtered_querydict(request, exclude=["page", "page_size", "orientation"])
        base_url = "/api/reports/financial/trading-account/"
        query_suffix = f"?{query}" if query else ""
        response["actions"]["export_urls"]["pdf_landscape"] = f"{base_url}pdf/landscape/{query_suffix}"
        response["actions"]["export_urls"]["pdf_portrait"] = f"{base_url}pdf/portrait/{query_suffix}"
        response["actions"]["export_urls"]["excel_landscape"] = f"{base_url}excel/landscape/{query_suffix}"
        response["actions"]["export_urls"]["excel_portrait"] = f"{base_url}excel/portrait/{query_suffix}"
        response["available_exports"] = ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"]
        return Response(response)

    def build_filters(self, scope, *, level: str, valuation_method: str, start, end, period_by: str | None):
        return {
            "entity": scope["entity"],
            "entityfinid": scope.get("entityfinid"),
            "financial_year": scope.get("financial_year") or scope.get("entityfinid"),
            "subentity": scope.get("subentity"),
            "scope_mode": scope.get("scope_mode"),
            "as_on_date": scope.get("as_on_date"),
            "from_date": start.isoformat() if start else None,
            "to_date": end.isoformat() if end else None,
            "period_by": period_by,
            "view_type": scope.get("view_type") or ("detailed" if level == "account" else "summary"),
            "account_group": scope.get("account_group") or scope.get("group_by"),
            "ledger_ids": scope.get("ledger_ids"),
            "search": scope.get("search"),
            "posted_only": scope.get("posted_only", True),
            "include_zero_balance": scope.get("include_zero_balance", False),
            "hide_zero_rows": not scope.get("include_zero_balance", False),
            "valuation_method": valuation_method,
            "level": level,
        }


class _BaseTradingAccountExportAPIView(FinancialReportPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    export_mode = "attachment"
    export_orientation = "landscape"
    required_permission_codes = (
        "reports.financial_hub.trading_account.view",
        "reports.trading_account.view",
    )

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content=content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def build_orientation(self, request):
        orientation = str(
            getattr(self, "export_orientation", None)
            or request.query_params.get("orientation")
            or "landscape"
        ).strip().lower()
        return orientation if orientation in {"landscape", "portrait"} else "landscape"

    def report_data(self, request):
        serializer = FinancialReportScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        settings_payload = get_financial_hub_settings_payload(user=request.user, entity_id=scope["entity"])
        settings = get_effective_trading_account_settings(settings_payload)
        settings = apply_amount_display_unit_override(settings, scope.get("amount_display_unit"))
        report_defaults = settings.get("report_defaults") or {}
        effective_view_type = scope.get("view_type") or report_defaults.get("default_view_type") or "summary"
        valuation_method = (request.query_params.get("valuation_method") or report_defaults.get("stock_valuation_method") or "fifo").lower()
        level = (request.query_params.get("level") or ("account" if effective_view_type == "detailed" else "head")).lower()
        period_by = (_effective_period_by(scope) or request.query_params.get("period_by") or "").strip().lower() or None
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        from_date = scope.get("from_date")
        to_date = scope.get("to_date")
        as_of_date = scope.get("as_of_date") or scope.get("as_on_date")
        if as_of_date and not to_date:
            to_date = as_of_date
        start, end = resolve_date_window(
            scope.get("entityfinid"),
            from_date,
            to_date,
        )
        data = build_trading_account_dynamic(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            startdate=start.isoformat(),
            enddate=end.isoformat(),
            period_by=period_by,
            posted_only=scope.get("posted_only", report_defaults.get("posted_only", True)),
            hide_zero_rows=scope.get("hide_zero_rows", report_defaults.get("hide_zero_rows", not scope.get("include_zero_balance", False))),
            view_type=effective_view_type or ("detailed" if level == "account" else "summary"),
            account_group=scope.get("account_group") or scope.get("group_by") or report_defaults.get("default_group_by"),
            ledger_ids=scope.get("ledger_ids") or None,
            search=scope.get("search"),
            valuation_method=valuation_method,
            level=level,
        )
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        subtitle = _trading_account_subtitle(scope_names, scope, data)
        return scope, data, subtitle, settings


class TradingAccountExcelAPIView(_BaseTradingAccountExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        statement_mode = _presentation_mode(scope) == "statement"
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if statement_mode:
            headers, rows = _statement_trading_rows(data, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = set(range(2, len(headers)))
            center_columns = {1}
            row_kinds = None
        else:
            headers, rows, row_kinds = _trading_account_export_table(data, include_periods=True, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Side", "Particulars", "Qty"})}
            center_columns = set()
        content = write_sectioned_excel(
            title="Trading Account",
            subtitle=subtitle,
            summary_items=_trading_account_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Trading Account",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
            orientation=self.build_orientation(request),
            freeze_header=settings.get("export_layout", {}).get("freeze_excel_header", True),
        )
        filename = build_report_filename(
            "Trading_Account",
            entity_name=scope_names.get("entity_name"),
            scope_label=_trading_account_scope_filename(scope_names, scope),
            extension="xlsx",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class TradingAccountCSVAPIView(_BaseTradingAccountExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        if _presentation_mode(scope) == "statement":
            headers, rows = _statement_trading_rows(data, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = set(range(2, len(headers)))
            center_columns = {1}
            row_kinds = None
        else:
            headers, rows, row_kinds = _trading_account_export_table(data, include_periods=True, settings=settings, expanded_keys=expanded_keys)
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Side", "Particulars", "Qty"})}
            center_columns = set()
        content = write_sectioned_csv(
            title="Trading Account",
            meta_items=_trading_account_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Trading Account",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                )
            ],
        )
        filename = build_report_filename(
            "Trading_Account",
            entity_name=scope_names.get("entity_name"),
            scope_label=_trading_account_scope_filename(scope_names, scope),
            extension="csv",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="text/csv",
        )


class TradingAccountPDFAPIView(_BaseTradingAccountExportAPIView):
    def get(self, request):
        scope, data, subtitle, settings = self.report_data(request)
        expanded_keys = _parse_expanded_row_keys(request)
        orientation = self.build_orientation(request)
        statement_mode = _presentation_mode(scope) == "statement"
        scope_names = resolve_scope_names(scope["entity"], scope.get("entityfinid"), scope.get("subentity"))
        periods = data.get("periods") or []
        if statement_mode:
            amount_headers, sections = _trading_account_statement_pdf_sections(data, settings=settings, expanded_keys=expanded_keys)
            content = write_balance_sheet_statement_pdf(
                title="Trading Account",
                subtitle=subtitle,
                meta_items=_trading_account_export_meta(scope_names, scope, data, settings),
                amount_headers=amount_headers,
                sections=sections,
                header_density=settings.get("export_layout", {}).get("header_density", "compact"),
                metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
            )
            filename = build_report_filename(
                "Trading_Account",
                entity_name=scope_names.get("entity_name"),
                scope_label=_trading_account_scope_filename(scope_names, scope),
                extension="pdf",
            )
            return self.export_response(
                filename=filename,
                content=content,
                content_type="application/pdf",
            )
        elif orientation == "landscape":
            headers, rows, row_kinds = _trading_account_export_table(data, include_periods=True, settings=settings, expanded_keys=expanded_keys)
            base_widths = {
                "Side": 72,
                "Particulars": 260,
                "Qty": 72,
                "Amount": 104,
            }
            col_widths = [base_widths.get(header, 72) for header in headers[:max(0, len(headers) - len(periods))]]
            if periods:
                insertion_at = len(col_widths) - (1 if "Amount" in headers else 0)
                col_widths[insertion_at:insertion_at] = [88] * len(periods)
            pagesize = landscape(A4)
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Side", "Particulars", "Qty"})}
            center_columns = set()
        else:
            headers, rows, row_kinds = _trading_account_export_table(data, include_periods=True, settings=settings)
            base_widths = {
                "Side": 60,
                "Particulars": 205,
                "Qty": 56,
                "Amount": 74,
            }
            col_widths = [base_widths.get(header, 42) for header in headers[:max(0, len(headers) - len(periods))]]
            if periods:
                insertion_at = len(col_widths) - (1 if "Amount" in headers else 0)
                col_widths[insertion_at:insertion_at] = [58] * len(periods)
            pagesize = A4
            numeric_columns = {index for index, header in enumerate(headers) if header == "Amount" or (header not in {"Side", "Particulars", "Qty"})}
            center_columns = set()
        content = write_sectioned_pdf(
            title="Trading Account",
            subtitle=subtitle,
            meta_items=_trading_account_export_meta(scope_names, scope, data, settings),
            sections=[
                ExportSection(
                    title="Trading Account",
                    headers=headers,
                    rows=rows,
                    row_kinds=row_kinds,
                    numeric_columns=numeric_columns,
                    center_columns=center_columns,
                    col_widths=col_widths,
                )
            ],
            pagesize=pagesize,
            header_density=settings.get("export_layout", {}).get("header_density", "compact"),
            metadata_visibility=settings.get("export_layout", {}).get("metadata_visibility", "compact"),
        )
        filename = build_report_filename(
            "Trading_Account",
            entity_name=scope_names.get("entity_name"),
            scope_label=_trading_account_scope_filename(scope_names, scope),
            extension="pdf",
        )
        return self.export_response(
            filename=filename,
            content=content,
            content_type="application/pdf",
        )


class TradingAccountPrintAPIView(TradingAccountPDFAPIView):
    export_mode = "inline"


class TradingAccountExcelLandscapeAPIView(TradingAccountExcelAPIView):
    export_orientation = "landscape"


class TradingAccountExcelPortraitAPIView(TradingAccountExcelAPIView):
    export_orientation = "portrait"


class TradingAccountPDFLandscapeAPIView(TradingAccountPDFAPIView):
    export_orientation = "landscape"


class TradingAccountPDFPortraitAPIView(TradingAccountPDFAPIView):
    export_orientation = "portrait"
