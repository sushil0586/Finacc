from __future__ import annotations

"""Central configuration for payables reports.

This module is the single place to register payables-facing report metadata:
- visible/export columns
- optional summary blocks
- drilldown target definitions
- traceability support
- related report navigation
- feature flags supported by a report
- close-pack section ordering

To add a new payables report:
1. add any new drilldown target to ``PAYABLE_DRILLDOWN_TARGETS``
2. add the report entry to ``PAYABLE_REPORTS``
3. enable ``supports_traceability`` and ``include_trace`` if rows should emit ``_trace``
4. if it participates in the close pack, add/update ``PAYABLE_CLOSE_PACK_SECTIONS``
5. consume the config through the helpers below instead of hardcoding headers/meta
"""

from collections import OrderedDict
from copy import deepcopy


PAYABLE_REPORT_DEFAULTS = {
    "default_page_size": 100,
    "decimal_places": 2,
    "show_zero_balances_default": False,
    "show_opening_balance_default": True,
    "enable_drilldown": True,
}

PAYABLE_EXPORT_FORMATS = ["excel", "pdf", "csv", "print"]

PAYABLE_FILTER_DEFINITIONS = OrderedDict(
    {
        "entity": {"code": "entity", "label": "Entity", "type": "integer", "required": True},
        "entityfinid": {"code": "entityfinid", "label": "Financial Year", "type": "integer", "required": False},
        "subentity": {"code": "subentity", "label": "Subentity", "type": "integer", "required": False},
        "from_date": {"code": "from_date", "label": "From Date", "type": "date", "required": False, "aliases": ["date_from"]},
        "to_date": {"code": "to_date", "label": "To Date", "type": "date", "required": False, "aliases": ["date_to"]},
        "as_of_date": {"code": "as_of_date", "label": "As Of Date", "type": "date", "required": False},
        "vendor": {"code": "vendor", "label": "Vendor", "type": "integer", "required": False},
        "vendor_group": {"code": "vendor_group", "label": "Vendor Group", "type": "string", "required": False},
        "region": {"code": "region", "label": "Region", "type": "integer", "required": False},
        "currency": {"code": "currency", "label": "Currency", "type": "string", "required": False},
        "search": {"code": "search", "label": "Search", "type": "string", "required": False},
        "sort_by": {"code": "sort_by", "label": "Sort By", "type": "string", "required": False},
        "sort_order": {"code": "sort_order", "label": "Sort Order", "type": "choice", "required": False},
        "page": {"code": "page", "label": "Page", "type": "integer", "required": False},
        "page_size": {"code": "page_size", "label": "Page Size", "type": "integer", "required": False},
        "overdue_only": {"code": "overdue_only", "label": "Overdue Only", "type": "boolean", "required": False},
        "credit_limit_exceeded": {"code": "credit_limit_exceeded", "label": "Credit Limit Exceeded", "type": "boolean", "required": False},
        "outstanding_gt": {"code": "outstanding_gt", "label": "Outstanding Greater Than", "type": "decimal", "required": False},
        "reconcile_gl": {"code": "reconcile_gl", "label": "Reconcile GL", "type": "boolean", "required": False},
        "include_trace": {"code": "include_trace", "label": "Include Trace", "type": "boolean", "required": False},
        "view": {"code": "view", "label": "View Mode", "type": "choice", "required": False},
        "min_amount": {"code": "min_amount", "label": "Minimum Amount", "type": "decimal", "required": False},
        "overdue_days_gt": {"code": "overdue_days_gt", "label": "Overdue Days Greater Than", "type": "integer", "required": False},
        "stale_days_gt": {"code": "stale_days_gt", "label": "Stale Days Greater Than", "type": "integer", "required": False},
        "include_negative_balances": {"code": "include_negative_balances", "label": "Include Negative Balances", "type": "boolean", "required": False},
        "include_old_advances": {"code": "include_old_advances", "label": "Include Old Advances", "type": "boolean", "required": False},
        "include_stale_vendors": {"code": "include_stale_vendors", "label": "Include Stale Vendors", "type": "boolean", "required": False},
        "include_opening": {"code": "include_opening", "label": "Include Opening", "type": "boolean", "required": False},
        "include_running_balance": {"code": "include_running_balance", "label": "Include Running Balance", "type": "boolean", "required": False},
        "include_settlement_drilldowns": {"code": "include_settlement_drilldowns", "label": "Include Settlement Drilldowns", "type": "boolean", "required": False},
        "include_related_reports": {"code": "include_related_reports", "label": "Include Related Reports", "type": "boolean", "required": False},
        "include_overview": {"code": "include_overview", "label": "Include Overview", "type": "boolean", "required": False},
        "include_aging": {"code": "include_aging", "label": "Include Aging", "type": "boolean", "required": False},
        "include_reconciliation": {"code": "include_reconciliation", "label": "Include Reconciliation", "type": "boolean", "required": False},
        "include_validation": {"code": "include_validation", "label": "Include Validation", "type": "boolean", "required": False},
        "include_exceptions": {"code": "include_exceptions", "label": "Include Exceptions", "type": "boolean", "required": False},
        "include_top_vendors": {"code": "include_top_vendors", "label": "Include Top Vendors", "type": "boolean", "required": False},
        "expanded_validation": {"code": "expanded_validation", "label": "Expanded Validation", "type": "boolean", "required": False},
        "settlement_type": {"code": "settlement_type", "label": "Settlement Type", "type": "choice", "required": False},
        "include_unapplied": {"code": "include_unapplied", "label": "Include Unapplied", "type": "boolean", "required": False},
        "note_type": {"code": "note_type", "label": "Note Type", "type": "choice", "required": False},
        "status": {"code": "status", "label": "Status", "type": "integer", "required": False},
    }
)

PAYABLE_DRILLDOWN_TARGETS = OrderedDict(
    {
        "vendor_outstanding": {
            "code": "vendor_outstanding",
            "label": "Vendor Outstanding",
            "target": "vendor_outstanding",
            "report_code": "vendor_outstanding",
            "path": "/api/reports/payables/vendor-outstanding/",
            "kind": "report",
        },
        "ap_aging": {
            "code": "ap_aging",
            "label": "AP Aging",
            "target": "ap_aging",
            "report_code": "ap_aging",
            "path": "/api/reports/payables/aging/",
            "kind": "report",
        },
        "purchase_register": {
            "code": "purchase_register",
            "label": "Purchase Register",
            "target": "purchase_register",
            "report_code": "purchase_register",
            "path": "/api/reports/purchases/register/",
            "kind": "report",
        },
        "vendor_ledger_statement": {
            "code": "vendor_ledger_statement",
            "label": "Vendor Ledger Statement",
            "target": "vendor_ledger_statement",
            "report_code": "vendor_ledger_statement",
            "path": "/api/reports/payables/vendor-ledger/",
            "kind": "report",
        },
        "vendor_settlement_history": {
            "code": "vendor_settlement_history",
            "label": "Vendor Settlement History",
            "target": "vendor_settlement_history",
            "report_code": "vendor_settlement_history",
            "path": "/api/reports/payables/settlement-history/",
            "kind": "report",
        },
        "vendor_note_register": {
            "code": "vendor_note_register",
            "label": "Vendor Debit/Credit Notes",
            "target": "vendor_note_register",
            "report_code": "vendor_note_register",
            "path": "/api/reports/payables/note-register/",
            "kind": "report",
        },
        "ap_gl_reconciliation": {
            "code": "ap_gl_reconciliation",
            "label": "AP to GL Reconciliation",
            "target": "ap_gl_reconciliation",
            "report_code": "ap_gl_reconciliation",
            "path": "/api/reports/payables/reconciliation/",
            "kind": "report",
        },
        "vendor_balance_exceptions": {
            "code": "vendor_balance_exceptions",
            "label": "Vendor Balance Exceptions",
            "target": "vendor_balance_exceptions",
            "report_code": "vendor_balance_exceptions",
            "path": "/api/reports/payables/exceptions/",
            "kind": "report",
        },
        "payables_close_pack": {
            "code": "payables_close_pack",
            "label": "Payables Close Pack",
            "target": "payables_close_pack",
            "report_code": "payables_close_pack",
            "path": "/api/reports/payables/close-pack/",
            "kind": "report",
        },
        "purchase_ap_vendor_statement": {
            "code": "purchase_ap_vendor_statement",
            "label": "Vendor Statement",
            "target": "purchase_ap_vendor_statement",
            "kind": "report",
        },
        "purchase_ap_open_items": {
            "code": "purchase_ap_open_items",
            "label": "Open Bills",
            "target": "purchase_ap_open_items",
            "kind": "report",
        },
        "purchase_ap_settlements": {
            "code": "purchase_ap_settlements",
            "label": "Settlement History",
            "target": "purchase_ap_settlements",
            "kind": "detail",
        },
        "purchase_document_detail": {
            "code": "purchase_document_detail",
            "label": "Bill Detail",
            "target": "purchase_document_detail",
            "kind": "document",
        },
        "payment_allocation": {
            "code": "payment_allocation",
            "label": "Payment Allocation",
            "target": "payment_allocation",
            "kind": "detail",
        },
    }
)

PAYABLE_CLOSE_PACK_SECTIONS = OrderedDict(
    {
        "overview": {"code": "overview", "label": "Overview", "default": True, "export_flatten_order": 10},
        "aging": {"code": "aging", "label": "Aging", "default": True, "export_flatten_order": 20},
        "reconciliation": {"code": "reconciliation", "label": "Reconciliation", "default": True, "export_flatten_order": 30},
        "validation": {"code": "validation", "label": "Validation", "default": True, "export_flatten_order": 40},
        "exceptions": {"code": "exceptions", "label": "Exceptions", "default": True, "export_flatten_order": 50},
        "top_vendors": {"code": "top_vendors", "label": "Top Vendors", "default": True, "export_flatten_order": 60},
    }
)


def _ordered_columns(*columns):
    return OrderedDict((column["key"], column) for column in columns)


PAYABLE_REPORTS = OrderedDict()

PAYABLE_REPORTS.update(
    {
        "vendor_outstanding": {
            "code": "vendor_outstanding",
            "name": "Vendor Outstanding Report",
            "path": "/api/reports/payables/vendor-outstanding/",
            "menu_code": "reports.vendoroutstanding",
            "route_name": "vendoroutstanding",
            "required_permission": "reports.vendoroutstanding.view",
            "supports_traceability": True,
            "default_filters": {
                "view": "summary",
                "aging_basis": "due_date",
                "sort_by": "outstanding",
                "sort_order": "desc",
                "include_zero_balance": False,
                "include_credit_balances": False,
                "include_advances_separately": False,
                "show_settled": False,
                "show_overdue_only": False,
                "show_not_due": False,
            },
            "feature_flags": OrderedDict(
                {
                    "view": {
                        "label": "View Mode",
                        "type": "choice",
                        "default": "summary",
                        "choices": [
                            {"value": "summary", "label": "Summary"},
                            {"value": "detailed", "label": "Detailed"},
                        ],
                    },
                    "aging_basis": {
                        "label": "Aging Basis",
                        "type": "choice",
                        "default": "due_date",
                        "choices": [
                            {"value": "due_date", "label": "Due Date"},
                            {"value": "bill_date", "label": "Bill Date"},
                        ],
                    },
                    "reconcile_gl": {"label": "GL Reconciliation Warning", "type": "boolean", "default": False},
                    "include_trace": {"label": "Traceability", "type": "boolean", "default": True},
                    "show_zero_balance": {"label": "Include Zero Balances", "type": "boolean", "default": False},
                    "show_credit_balances": {"label": "Include Credit Balances", "type": "boolean", "default": False},
                    "show_advances_separately": {"label": "Include Advances Separately", "type": "boolean", "default": False},
                }
            ),
            "views": {
                "summary": {
                    "columns": _ordered_columns(
                        {"key": "vendor_code", "label": "Vendor Code", "default": True},
                        {"key": "vendor_name", "label": "Vendor Name", "default": True},
                        {"key": "outstanding", "label": "Outstanding", "default": True},
                        {"key": "not_due", "label": "Not Due", "default": True},
                        {"key": "bucket_0_30", "label": "0-30", "default": True},
                        {"key": "bucket_31_60", "label": "31-60", "default": True},
                        {"key": "bucket_61_90", "label": "61-90", "default": True},
                        {"key": "bucket_91_180", "label": "91-180", "default": True},
                        {"key": "bucket_181_plus", "label": "181+", "default": True},
                        {"key": "oldest_due_date", "label": "Oldest Due Date", "default": True},
                        {"key": "gstin", "label": "GSTIN", "default": True},
                        {"key": "opening_balance", "label": "Opening", "default": True},
                        {"key": "bill_amount", "label": "Invoiced", "default": True},
                        {"key": "payment_amount", "label": "Paid / Adjusted", "default": True},
                        {"key": "last_bill_date", "label": "Latest Bill Date", "default": True},
                    ),
                    "summary_blocks": OrderedDict(
                        {
                            "totals": {"code": "totals", "label": "Totals", "default": True},
                            "vendor_count": {"code": "vendor_count", "label": "Vendor Count", "default": True},
                        }
                    ),
                },
                "detailed": {
                    "columns": _ordered_columns(
                        {"key": "date", "label": "Date", "default": True},
                        {"key": "voucher_no", "label": "Voucher No", "default": True},
                        {"key": "voucher_type_name", "label": "Voucher Type", "default": True},
                        {"key": "bill_ref_no", "label": "Bill / Ref No", "default": True},
                        {"key": "bill_date", "label": "Bill Date", "default": True},
                        {"key": "due_date", "label": "Due Date", "default": True},
                        {"key": "days_overdue", "label": "Days Overdue", "default": True},
                        {"key": "original_amount", "label": "Original Amount", "default": True},
                        {"key": "settled_amount", "label": "Settled Amount", "default": True},
                        {"key": "outstanding_amount", "label": "Outstanding Amount", "default": True},
                        {"key": "aging_bucket", "label": "Aging Bucket", "default": True},
                        {"key": "subentity_name", "label": "Subentity", "default": True},
                    ),
                    "summary_blocks": OrderedDict(
                        {
                            "totals": {"code": "totals", "label": "Totals", "default": True},
                            "vendor_count": {"code": "vendor_count", "label": "Vendor Count", "default": True},
                        }
                    ),
                },
            },
            "drilldown_targets": ["ap_aging", "purchase_ap_vendor_statement", "purchase_ap_open_items", "purchase_ap_settlements"],
            "export_columns": [
                "vendor_code",
                "vendor_name",
                "outstanding",
                "not_due",
                "bucket_0_30",
                "bucket_31_60",
                "bucket_61_90",
                "bucket_91_180",
                "bucket_181_plus",
                "oldest_due_date",
                "gstin",
                "opening_balance",
                "bill_amount",
                "payment_amount",
                "last_bill_date",
                "last_payment_date",
            ],
            "related_reports": [
                "vendor_outstanding",
                "ap_aging_summary",
                "ap_aging_invoice",
                "payables_dashboard_summary",
                "purchase_register",
                "vendor_ledger_statement",
                "payables_close_pack",
            ],
            "print_sections": ["rows", "totals"],
        },
        "ap_aging": {
            "code": "ap_aging",
            "name": "AP Aging Report",
            "path": "/api/reports/payables/aging/",
            "menu_code": "reports.accountspayableaging",
            "route_name": "accountspayableaging",
            "required_permission": "reports.accountspayableaging.view",
            "supports_traceability": True,
            "default_filters": {"view": "summary", "sort_by": "outstanding", "sort_order": "desc"},
            "feature_flags": OrderedDict(
                {
                    "include_trace": {"label": "Traceability", "type": "boolean", "default": True},
                    "view": {
                        "label": "View Mode",
                        "type": "choice",
                        "default": "summary",
                        "choices": [
                            {"value": "summary", "label": "Summary"},
                            {"value": "invoice", "label": "Invoice Aging"},
                        ],
                    }
                }
            ),
            "views": {
                "summary": {
                    "columns": _ordered_columns(
                        {"key": "vendor_name", "label": "Vendor Name", "default": True, "width": "240px"},
                        {"key": "vendor_code", "label": "Vendor Code", "default": True, "width": "120px"},
                        {"key": "outstanding", "label": "Outstanding", "default": True, "width": "130px"},
                        {"key": "overdue_amount", "label": "Overdue", "default": True, "width": "120px"},
                        {"key": "current", "label": "Not Due", "default": True, "width": "110px"},
                        {"key": "bucket_1_30", "label": "1-30 Days", "default": True, "width": "110px"},
                        {"key": "bucket_31_60", "label": "31-60 Days", "default": True, "width": "110px"},
                        {"key": "bucket_61_90", "label": "61-90 Days", "default": True, "width": "110px"},
                        {"key": "bucket_90_plus", "label": "90+ Days", "default": True, "width": "110px"},
                        {"key": "unapplied_advance", "label": "Advances", "default": True, "width": "120px"},
                        {"key": "credit_limit", "label": "Credit Limit", "default": True, "width": "120px"},
                        {"key": "credit_days", "label": "Credit Days", "default": True, "width": "110px"},
                        {"key": "last_payment_date", "label": "Last Payment", "default": True, "width": "120px"},
                        {"key": "currency", "label": "Currency", "default": True, "width": "90px"},
                    ),
                    "summary_blocks": OrderedDict(
                        {
                            "totals": {"code": "totals", "label": "Totals", "default": True},
                            "vendor_count": {"code": "vendor_count", "label": "Vendor Count", "default": True},
                        }
                    ),
                    "drilldown_targets": ["vendor_ledger_statement", "ap_aging", "purchase_ap_open_items", "purchase_ap_settlements"],
                    "export_columns": [
                        "vendor_name",
                        "vendor_code",
                        "outstanding",
                        "overdue_amount",
                        "current",
                        "bucket_1_30",
                        "bucket_31_60",
                        "bucket_61_90",
                        "bucket_90_plus",
                        "unapplied_advance",
                        "credit_limit",
                        "credit_days",
                        "last_payment_date",
                        "currency",
                    ],
                    "related_reports": ["vendor_outstanding", "vendor_ledger_statement", "purchase_register"],
                },
                "invoice": {
                    "columns": _ordered_columns(
                        {"key": "vendor_name", "label": "Vendor Name", "default": True, "width": "240px"},
                        {"key": "vendor_code", "label": "Vendor Code", "default": True, "width": "120px"},
                        {"key": "bill_number", "label": "Bill / Ref No", "default": True, "width": "140px"},
                        {"key": "bill_date", "label": "Bill Date", "default": True, "width": "110px"},
                        {"key": "due_date", "label": "Due Date", "default": True, "width": "110px"},
                        {"key": "credit_days", "label": "Credit Days", "default": True, "width": "100px"},
                        {"key": "bill_amount", "label": "Bill Amount", "default": True, "width": "130px"},
                        {"key": "paid_amount", "label": "Settled Amount", "default": True, "width": "130px"},
                        {"key": "balance", "label": "Outstanding Amount", "default": True, "width": "140px"},
                        {"key": "current", "label": "Not Due", "default": True, "width": "100px"},
                        {"key": "bucket_1_30", "label": "1-30 Days", "default": True, "width": "110px"},
                        {"key": "bucket_31_60", "label": "31-60 Days", "default": True, "width": "110px"},
                        {"key": "bucket_61_90", "label": "61-90 Days", "default": True, "width": "110px"},
                        {"key": "bucket_90_plus", "label": "90+ Days", "default": True, "width": "110px"},
                        {"key": "currency", "label": "Currency", "default": True, "width": "90px"},
                    ),
                    "summary_blocks": OrderedDict(
                        {
                            "totals": {"code": "totals", "label": "Totals", "default": True},
                            "invoice_count": {"code": "invoice_count", "label": "Invoice Count", "default": True},
                        }
                    ),
                    "drilldown_targets": ["purchase_document_detail", "payment_allocation", "vendor_ledger_statement"],
                    "export_columns": [
                        "vendor_name",
                        "vendor_code",
                        "bill_number",
                        "bill_date",
                        "due_date",
                        "credit_days",
                        "bill_amount",
                        "paid_amount",
                        "balance",
                        "current",
                        "bucket_1_30",
                        "bucket_31_60",
                        "bucket_61_90",
                        "bucket_90_plus",
                        "currency",
                    ],
                    "related_reports": ["vendor_outstanding", "vendor_ledger_statement", "purchase_register"],
                },
            },
            "print_sections": ["rows", "totals"],
        },
        "payables_dashboard_summary": {
            "code": "payables_dashboard_summary",
            "name": "Payables Dashboard Summary",
            "path": "/api/reports/payables/dashboard-summary/",
            "menu_code": "reports.payables.payables_dashboard_summary",
            "route_name": "reports-payables-payables-dashboard-summary",
            "required_permission": "reports.vendoroutstanding.view",
            "export_formats": [],
            "summary_blocks": OrderedDict(
                {
                    "totals": {"code": "totals", "label": "Totals", "default": True},
                    "top_vendors": {"code": "top_vendors", "label": "Top Vendors", "default": True},
                }
            ),
            "drilldown_targets": ["vendor_outstanding", "ap_aging"],
            "related_reports": ["vendor_outstanding", "ap_aging_summary", "payables_close_pack"],
        },
        "ap_gl_reconciliation": {
            "code": "ap_gl_reconciliation",
            "name": "AP to GL Reconciliation Report",
            "path": "/api/reports/payables/reconciliation/",
            "menu_code": "reports.apglreconciliation",
            "route_name": "apglreconciliation",
            "required_permission": "reports.apglreconciliation.view",
            "supports_traceability": True,
            "default_filters": {"sort_by": "difference_amount", "sort_order": "desc"},
            "feature_flags": OrderedDict(
                {
                    "include_trace": {"label": "Traceability", "type": "boolean", "default": True},
                }
            ),
            "columns": _ordered_columns(
                {"key": "vendor_name", "label": "Vendor Name", "default": True},
                {"key": "vendor_code", "label": "Vendor Code", "default": True},
                {"key": "open_invoice_balance", "label": "Open Invoice Balance", "default": True},
                {"key": "unapplied_advance", "label": "Unapplied Advance", "default": True},
                {"key": "subledger_balance", "label": "Subledger Balance", "default": True},
                {"key": "gl_balance", "label": "GL Balance", "default": True},
                {"key": "difference_amount", "label": "Difference Amount", "default": True},
                {"key": "reconciliation_status", "label": "Status", "default": True},
            ),
            "summary_blocks": OrderedDict(
                {
                    "component_breakdown": {"code": "component_breakdown", "label": "Component Breakdown", "default": True},
                    "status_summary": {"code": "status_summary", "label": "Status Summary", "default": True},
                }
            ),
            "drilldown_targets": ["vendor_outstanding", "ap_aging", "purchase_ap_vendor_statement"],
            "export_columns": [
                "vendor_name",
                "vendor_code",
                "open_invoice_balance",
                "unapplied_advance",
                "subledger_balance",
                "gl_balance",
                "difference_amount",
                "reconciliation_status",
            ],
            "related_reports": ["vendor_outstanding", "ap_aging_summary", "vendor_ledger_statement", "payables_close_pack"],
            "print_sections": ["rows", "summary"],
        },
        "vendor_balance_exceptions": {
            "code": "vendor_balance_exceptions",
            "name": "Vendor Balance Exception Report",
            "path": "/api/reports/payables/exceptions/",
            "menu_code": "reports.vendorbalanceexceptions",
            "route_name": "vendorbalanceexceptions",
            "required_permission": "reports.vendorbalanceexceptions.view",
            "feature_flags": OrderedDict(
                {
                    "include_negative_balances": {"label": "Negative Balances", "type": "boolean", "default": True},
                    "include_old_advances": {"label": "Old Advances", "type": "boolean", "default": True},
                    "include_stale_vendors": {"label": "Stale Vendors", "type": "boolean", "default": True},
                }
            ),
            "columns": _ordered_columns(
                {"key": "vendor_name", "label": "Vendor Name", "default": True},
                {"key": "vendor_code", "label": "Vendor Code", "default": True},
                {"key": "exception_type", "label": "Exception Type", "default": True},
                {"key": "severity", "label": "Severity", "default": True},
                {"key": "document_number", "label": "Document Number", "default": True},
                {"key": "amount", "label": "Amount", "default": True},
                {"key": "age_days", "label": "Age Days", "default": True},
                {"key": "message", "label": "Message", "default": True},
            ),
            "summary_blocks": OrderedDict(
                {
                    "by_type": {"code": "by_type", "label": "By Type", "default": True},
                    "total_exceptions": {"code": "total_exceptions", "label": "Total Exceptions", "default": True},
                }
            ),
            "drilldown_targets": ["vendor_outstanding", "ap_aging"],
            "export_columns": [
                "vendor_name",
                "vendor_code",
                "exception_type",
                "severity",
                "document_number",
                "amount",
                "age_days",
                "message",
            ],
            "related_reports": ["vendor_outstanding", "ap_aging_invoice", "payables_close_pack"],
            "print_sections": ["rows", "summary"],
        },
        "payables_close_validation": {
            "code": "payables_close_validation",
            "name": "Payables Close Validation",
            "path": "/api/reports/payables/close-validation/",
            "menu_code": "reports.payables.payables_close_validation",
            "route_name": "reports-payables-payables-close-validation",
            "required_permission": "reports.apglreconciliation.view",
            "export_formats": [],
            "summary_blocks": OrderedDict(
                {"validation_summary": {"code": "validation_summary", "label": "Validation Summary", "default": True}}
            ),
            "drilldown_targets": ["ap_gl_reconciliation"],
            "related_reports": ["ap_gl_reconciliation", "vendor_balance_exceptions", "payables_close_pack"],
        },
        "payables_close_readiness_summary": {
            "code": "payables_close_readiness_summary",
            "name": "Payables Close Readiness Summary",
            "path": "/api/reports/payables/close-readiness-summary/",
            "menu_code": "reports.payables.payables_close_readiness_summary",
            "route_name": "reports-payables-payables-close-readiness-summary",
            "required_permission": "reports.apglreconciliation.view",
            "export_formats": [],
            "summary_blocks": OrderedDict(
                {"top_critical_issues": {"code": "top_critical_issues", "label": "Top Critical Issues", "default": True}}
            ),
            "drilldown_targets": ["payables_close_pack", "ap_gl_reconciliation"],
            "related_reports": ["payables_close_pack", "ap_gl_reconciliation", "vendor_balance_exceptions"],
        },
        "purchase_register": {
            "code": "purchase_register",
            "name": "Purchase Register",
            "path": "/api/reports/purchases/register/",
            "menu_code": "reports.payables.purchase_register",
            "route_name": "reports-payables-purchase-register",
            "required_permission": "reports.purchasebook.view",
            "feature_flags": OrderedDict(
                {
                    "include_outstanding": {"label": "Outstanding Amount", "type": "boolean", "default": False},
                    "include_posting_summary": {"label": "Posting Summary", "type": "boolean", "default": False},
                    "include_payables_drilldowns": {"label": "Payables Drilldowns", "type": "boolean", "default": True},
                }
            ),
            "columns": _ordered_columns(
                {"key": "bill_date", "label": "Bill Date", "default": True},
                {"key": "posting_date", "label": "Posting Date", "default": True},
                {"key": "doc_type_name", "label": "Document Type", "default": True},
                {"key": "purchase_number", "label": "Document Number", "default": True},
                {"key": "supplier_name", "label": "Supplier", "default": True},
                {"key": "supplier_gstin", "label": "Supplier GSTIN", "default": True},
                {"key": "supplier_invoice_number", "label": "Supplier Invoice Number", "default": True},
                {"key": "supplier_invoice_date", "label": "Supplier Invoice Date", "default": True},
                {"key": "place_of_supply", "label": "Place of Supply", "default": True},
                {"key": "taxable_amount", "label": "Taxable Amount", "default": True},
                {"key": "cgst_amount", "label": "CGST", "default": True},
                {"key": "sgst_amount", "label": "SGST", "default": True},
                {"key": "igst_amount", "label": "IGST", "default": True},
                {"key": "cess_amount", "label": "CESS", "default": True},
                {"key": "discount_total", "label": "Discount", "default": True},
                {"key": "roundoff_amount", "label": "Round Off", "default": True},
                {"key": "grand_total", "label": "Grand Total", "default": True},
                {"key": "outstanding_amount", "label": "Outstanding Amount", "default": False, "feature_flag": "include_outstanding"},
                {"key": "status_name", "label": "Status", "default": True},
            ),
            "summary_blocks": OrderedDict(
                {
                    "totals": {"code": "totals", "label": "Totals", "default": True},
                    "posting_summary": {
                        "code": "posting_summary",
                        "label": "Posting Summary",
                        "default": False,
                        "feature_flag": "include_posting_summary",
                    },
                }
            ),
            "drilldown_targets": ["purchase_document_detail", "vendor_outstanding", "ap_aging", "vendor_ledger_statement"],
            "export_columns": [
                "bill_date",
                "posting_date",
                "doc_type_name",
                "purchase_number",
                "supplier_name",
                "supplier_gstin",
                "supplier_invoice_number",
                "supplier_invoice_date",
                "place_of_supply",
                "taxable_amount",
                "cgst_amount",
                "sgst_amount",
                "igst_amount",
                "cess_amount",
                "discount_total",
                "roundoff_amount",
                "grand_total",
                "outstanding_amount",
                "status_name",
            ],
            "related_reports": ["vendor_outstanding", "ap_aging_summary", "vendor_ledger_statement", "payables_close_pack"],
            "print_sections": ["rows", "totals", "posting_summary"],
        },
        "vendor_settlement_history": {
            "code": "vendor_settlement_history",
            "name": "Vendor Settlement History",
            "path": "/api/reports/payables/settlement-history/",
            "menu_code": "reports.vendorsettlementhistory",
            "route_name": "vendorsettlementhistory",
            "required_permission": "reports.vendorsettlementhistory.view",
            "supports_traceability": True,
            "feature_flags": OrderedDict(
                {
                    "include_unapplied": {"label": "Include Unapplied", "type": "boolean", "default": True},
                    "include_trace": {"label": "Traceability", "type": "boolean", "default": True},
                }
            ),
            "columns": _ordered_columns(
                {"key": "settlement_number", "label": "Settlement Number", "default": True},
                {"key": "settlement_date", "label": "Settlement Date", "default": True},
                {"key": "vendor_name", "label": "Vendor", "default": True},
                {"key": "vendor_code", "label": "Vendor Code", "default": True},
                {"key": "settlement_type_name", "label": "Settlement Type", "default": True},
                {"key": "bill_number", "label": "Bill Number", "default": True},
                {"key": "bill_date", "label": "Bill Date", "default": True},
                {"key": "applied_amount", "label": "Applied Amount", "default": True},
                {"key": "unapplied_amount", "label": "Unapplied Amount", "default": True, "feature_flag": "include_unapplied"},
                {"key": "status_name", "label": "Status", "default": True},
                {"key": "reference_number", "label": "Reference", "default": True},
                {"key": "remarks", "label": "Remarks", "default": True},
            ),
            "summary_blocks": OrderedDict(
                {
                    "totals": {"code": "totals", "label": "Totals", "default": True},
                    "settlement_count": {"code": "settlement_count", "label": "Settlement Count", "default": True},
                }
            ),
            "drilldown_targets": ["purchase_document_detail", "vendor_outstanding", "ap_aging", "vendor_ledger_statement", "purchase_ap_settlements"],
            "export_columns": [
                "settlement_number",
                "settlement_date",
                "vendor_name",
                "vendor_code",
                "settlement_type_name",
                "bill_number",
                "bill_date",
                "applied_amount",
                "unapplied_amount",
                "status_name",
                "reference_number",
                "remarks",
            ],
            "related_reports": ["vendor_outstanding", "ap_aging_invoice", "vendor_ledger_statement", "vendor_note_register", "purchase_register"],
            "print_sections": ["rows", "totals"],
        },
        "vendor_note_register": {
            "code": "vendor_note_register",
            "name": "Vendor Debit/Credit Note Register",
            "path": "/api/reports/payables/note-register/",
            "menu_code": "reports.vendornoteregister",
            "route_name": "vendornoteregister",
            "required_permission": "reports.vendornoteregister.view",
            "supports_traceability": True,
            "feature_flags": OrderedDict(
                {
                    "include_trace": {"label": "Traceability", "type": "boolean", "default": True},
                }
            ),
            "columns": _ordered_columns(
                {"key": "note_number", "label": "Note Number", "default": True},
                {"key": "note_date", "label": "Note Date", "default": True},
                {"key": "note_type_name", "label": "Note Type", "default": True},
                {"key": "vendor_name", "label": "Vendor", "default": True},
                {"key": "vendor_code", "label": "Vendor Code", "default": True},
                {"key": "linked_bill_number", "label": "Linked Bill", "default": True},
                {"key": "taxable_amount", "label": "Taxable Amount", "default": True},
                {"key": "tax_amount", "label": "Tax Amount", "default": True},
                {"key": "total_note_amount", "label": "Note Amount", "default": True},
                {"key": "outstanding_amount", "label": "Outstanding", "default": True},
                {"key": "status_name", "label": "Status", "default": True},
                {"key": "posting_status", "label": "Posting Status", "default": True},
            ),
            "summary_blocks": OrderedDict(
                {
                    "totals": {"code": "totals", "label": "Totals", "default": True},
                    "note_count": {"code": "note_count", "label": "Note Count", "default": True},
                }
            ),
            "drilldown_targets": ["purchase_document_detail", "vendor_outstanding", "ap_aging", "vendor_ledger_statement"],
            "export_columns": [
                "note_number",
                "note_date",
                "note_type_name",
                "vendor_name",
                "vendor_code",
                "linked_bill_number",
                "taxable_amount",
                "tax_amount",
                "total_note_amount",
                "outstanding_amount",
                "status_name",
                "posting_status",
            ],
            "related_reports": ["vendor_outstanding", "ap_aging_invoice", "vendor_ledger_statement", "vendor_settlement_history", "purchase_register"],
            "print_sections": ["rows", "totals"],
        },
        "vendor_ledger_statement": {
            "code": "vendor_ledger_statement",
            "name": "Vendor Ledger Statement",
            "path": "/api/reports/payables/vendor-ledger/",
            "menu_code": "reports.vendorledgerstatement",
            "route_name": "vendorledgerstatement",
            "required_permission": "reports.vendorledgerstatement.view",
            "supports_traceability": True,
            "feature_flags": OrderedDict(
                {
                    "include_trace": {"label": "Traceability", "type": "boolean", "default": True},
                    "include_opening": {"label": "Opening Balance", "type": "boolean", "default": True},
                    "include_running_balance": {"label": "Running Balance", "type": "boolean", "default": True},
                    "include_settlement_drilldowns": {"label": "Settlement Drilldowns", "type": "boolean", "default": True},
                    "include_related_reports": {"label": "Related Reports", "type": "boolean", "default": True},
                }
            ),
            "columns": _ordered_columns(
                {"key": "transaction_date", "label": "Transaction Date", "default": True},
                {"key": "document_number", "label": "Document Number", "default": True},
                {"key": "document_type_name", "label": "Document Type", "default": True},
                {"key": "reference", "label": "Reference", "default": True},
                {"key": "debit", "label": "Debit", "default": True},
                {"key": "credit", "label": "Credit", "default": True},
                {"key": "running_balance", "label": "Running Balance", "default": True, "feature_flag": "include_running_balance"},
            ),
            "summary_blocks": OrderedDict(
                {
                    "opening_balance": {
                        "code": "opening_balance",
                        "label": "Opening Balance",
                        "default": True,
                        "feature_flag": "include_opening",
                    },
                    "totals": {"code": "totals", "label": "Totals", "default": True},
                    "transaction_count": {"code": "transaction_count", "label": "Transaction Count", "default": True},
                }
            ),
            "drilldown_targets": ["purchase_document_detail", "purchase_ap_settlements", "vendor_outstanding", "ap_aging", "vendor_settlement_history", "vendor_note_register"],
            "export_columns": [
                "transaction_date",
                "document_number",
                "document_type_name",
                "reference",
                "debit",
                "credit",
                "running_balance",
            ],
            "related_reports": ["vendor_outstanding", "ap_aging_invoice", "purchase_register", "vendor_settlement_history", "vendor_note_register", "payables_close_pack"],
            "print_sections": ["opening_balance", "rows", "totals"],
        },
        "payables_close_pack": {
            "code": "payables_close_pack",
            "name": "Payables Close Pack",
            "path": "/api/reports/payables/close-pack/",
            "menu_code": "reports.payablesclosepack",
            "route_name": "payablesclosepack",
            "required_permission": "reports.payablesclosepack.view",
            "feature_flags": OrderedDict(
                {
                    "include_overview": {"label": "Overview Section", "type": "boolean", "default": True},
                    "include_aging": {"label": "Aging Section", "type": "boolean", "default": True},
                    "include_reconciliation": {"label": "Reconciliation Section", "type": "boolean", "default": True},
                    "include_validation": {"label": "Validation Section", "type": "boolean", "default": True},
                    "include_exceptions": {"label": "Exception Section", "type": "boolean", "default": True},
                    "include_top_vendors": {"label": "Top Vendors Section", "type": "boolean", "default": True},
                    "expanded_validation": {"label": "Expanded Validation", "type": "boolean", "default": False},
                }
            ),
            "columns": _ordered_columns(
                {"key": "section", "label": "Section", "default": True},
                {"key": "metric", "label": "Metric", "default": True},
                {"key": "value", "label": "Value", "default": True},
                {"key": "kind", "label": "Kind", "default": True},
            ),
            "summary_blocks": OrderedDict(
                {
                    "overview": {"code": "overview", "label": PAYABLE_CLOSE_PACK_SECTIONS["overview"]["label"], "default": True, "feature_flag": "include_overview"},
                    "aging": {"code": "aging", "label": PAYABLE_CLOSE_PACK_SECTIONS["aging"]["label"], "default": True, "feature_flag": "include_aging"},
                    "reconciliation": {"code": "reconciliation", "label": PAYABLE_CLOSE_PACK_SECTIONS["reconciliation"]["label"], "default": True, "feature_flag": "include_reconciliation"},
                    "validation": {"code": "validation", "label": PAYABLE_CLOSE_PACK_SECTIONS["validation"]["label"], "default": True, "feature_flag": "include_validation"},
                    "exceptions": {"code": "exceptions", "label": PAYABLE_CLOSE_PACK_SECTIONS["exceptions"]["label"], "default": True, "feature_flag": "include_exceptions"},
                    "top_vendors": {"code": "top_vendors", "label": PAYABLE_CLOSE_PACK_SECTIONS["top_vendors"]["label"], "default": True, "feature_flag": "include_top_vendors"},
                }
            ),
            "drilldown_targets": ["vendor_outstanding", "ap_aging", "ap_gl_reconciliation", "vendor_balance_exceptions"],
            "related_reports": [
                "vendor_outstanding",
                "ap_aging_summary",
                "ap_gl_reconciliation",
                "vendor_balance_exceptions",
                "payables_close_readiness_summary",
            ],
            "export_columns": ["section", "metric", "value", "kind"],
            "print_sections": list(PAYABLE_CLOSE_PACK_SECTIONS.keys()),
        },
    }
)


def _merge_report_variant(report_config, *, view=None):
    merged = deepcopy(report_config)
    if not view or "views" not in merged:
        return merged
    variant = deepcopy(merged["views"].get(view) or {})
    for key in ("columns", "summary_blocks", "feature_flags"):
        combined = OrderedDict()
        combined.update(merged.get(key, OrderedDict()))
        combined.update(variant.get(key, OrderedDict()))
        if combined:
            merged[key] = combined
    for key in ("drilldown_targets", "export_columns", "related_reports", "print_sections"):
        if key in variant:
            merged[key] = list(variant[key])
    if "default_filters" in variant:
        defaults = dict(merged.get("default_filters", {}))
        defaults.update(variant["default_filters"])
        merged["default_filters"] = defaults
    merged["active_view"] = view
    return merged


def get_payables_report_config(report_code, *, view=None):
    report = PAYABLE_REPORTS.get(report_code)
    if not report:
        return None
    return _merge_report_variant(report, view=view)


def _bool_enabled(value):
    return bool(value)


def _feature_state(report_config, enabled_features=None):
    feature_state = {}
    enabled_features = enabled_features or {}
    for key, meta in report_config.get("feature_flags", {}).items():
        feature_state[key] = enabled_features.get(key, meta.get("default"))
    return feature_state


def resolve_report_columns(report_code, *, view=None, enabled_features=None, export=False):
    report = get_payables_report_config(report_code, view=view)
    if not report:
        return []
    feature_state = _feature_state(report, enabled_features)
    columns = []
    for key, meta in report.get("columns", OrderedDict()).items():
        feature_flag = meta.get("feature_flag")
        included = meta.get("default", False)
        if feature_flag:
            included = _bool_enabled(feature_state.get(feature_flag))
        column = {
            "key": key,
            "label": meta["label"],
            "default": meta.get("default", False),
            "optional": not meta.get("default", False) or bool(feature_flag),
            "included": included,
        }
        if feature_flag:
            column["feature_flag"] = feature_flag
        columns.append(column)
    if export:
        export_keys = report.get("export_columns") or [column["key"] for column in columns if column["included"]]
        ordered = []
        for key in export_keys:
            match = next((column for column in columns if column["key"] == key), None)
            if match and match["included"]:
                ordered.append(match)
        return ordered
    return columns


def resolve_report_column_keys(report_code, *, view=None, enabled_features=None, export=False):
    return [column["key"] for column in resolve_report_columns(report_code, view=view, enabled_features=enabled_features, export=export)]


def resolve_report_summary_blocks(report_code, *, view=None, enabled_features=None):
    report = get_payables_report_config(report_code, view=view)
    if not report:
        return []
    feature_state = _feature_state(report, enabled_features)
    blocks = []
    for code, meta in report.get("summary_blocks", OrderedDict()).items():
        feature_flag = meta.get("feature_flag")
        enabled = meta.get("default", False)
        if feature_flag:
            enabled = _bool_enabled(feature_state.get(feature_flag))
        block = {
            "code": code,
            "label": meta["label"],
            "default": meta.get("default", False),
            "enabled": enabled,
        }
        if feature_flag:
            block["feature_flag"] = feature_flag
        blocks.append(block)
    return blocks


def get_payables_drilldown_target(target_code):
    return deepcopy(PAYABLE_DRILLDOWN_TARGETS.get(target_code))


def build_payables_drilldown(target_code, *, params, label=None, kind=None, path=None, report_code=None):
    target = get_payables_drilldown_target(target_code) or {
        "code": target_code,
        "label": label or target_code.replace("_", " ").title(),
        "target": target_code,
        "kind": kind or "navigate",
    }
    payload = {
        "label": label or target.get("label"),
        "target": target.get("target", target_code),
        "kind": kind or target.get("kind", "navigate"),
        "params": params,
    }
    resolved_path = path or target.get("path")
    resolved_report_code = report_code or target.get("report_code")
    if resolved_path:
        payload["path"] = resolved_path
    if resolved_report_code:
        payload["report_code"] = resolved_report_code
    return payload


def _permission_allowed(required_permission, permission_codes):
    if not required_permission or permission_codes is None:
        return True
    return required_permission in permission_codes


def get_payables_registry_payload(*, permission_codes=None):
    registry = []
    for report in PAYABLE_REPORTS.values():
        if not _permission_allowed(report.get("required_permission"), permission_codes):
            continue
        registry.append(
            {
                "code": report["code"],
                "label": report["name"],
                "name": report["name"],
                "path": report["path"],
                "endpoint": report["path"],
                "menu_code": report["menu_code"],
                "route_name": report["route_name"],
                "required_permission": report["required_permission"],
                "export_formats": list(report.get("export_formats", PAYABLE_EXPORT_FORMATS)),
            }
        )
    return registry


def _related_report_defaults(report_code, *, entity_id, entityfin_id, subentity_id, as_of_date=None, from_date=None, to_date=None, vendor_id=None):
    params = {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id}
    if report_code == "vendor_outstanding":
        params.update({"from_date": from_date, "to_date": to_date or as_of_date})
    elif report_code == "ap_aging_summary":
        params.update({"as_of_date": as_of_date or to_date, "view": "summary"})
    elif report_code == "ap_aging_invoice":
        params.update({"as_of_date": as_of_date or to_date, "view": "invoice"})
    elif report_code == "payables_dashboard_summary":
        params.update({"as_of_date": as_of_date or to_date})
    elif report_code == "purchase_register":
        params.update({"from_date": from_date, "to_date": to_date or as_of_date, "include_outstanding": True})
    elif report_code == "vendor_ledger_statement":
        params.update({"from_date": from_date, "to_date": to_date or as_of_date})
        if vendor_id is not None:
            params["vendor"] = vendor_id
    elif report_code in {"vendor_settlement_history", "vendor_note_register"}:
        params.update({"from_date": from_date, "to_date": to_date or as_of_date})
        if vendor_id is not None:
            params["vendor"] = vendor_id
    elif report_code in {"payables_close_pack", "payables_close_readiness_summary", "ap_gl_reconciliation", "vendor_balance_exceptions"}:
        params.update({"as_of_date": as_of_date or to_date})
    if vendor_id is not None and report_code in {"vendor_outstanding", "ap_aging_summary", "ap_aging_invoice"}:
        params["vendor"] = vendor_id
    return params


def build_related_report_links(report_codes, *, entity_id, entityfin_id, subentity_id, as_of_date=None, from_date=None, to_date=None, vendor_id=None, view=None, permission_codes=None):
    links = []
    for code in report_codes:
        if code == "ap_aging_summary":
            base = get_payables_report_config("ap_aging", view="summary")
            name = "AP Aging Summary"
        elif code == "ap_aging_invoice":
            base = get_payables_report_config("ap_aging", view="invoice")
            name = "AP Aging Invoice"
        else:
            base = get_payables_report_config(code)
            name = base["name"] if base else None
        if not base:
            continue
        if not _permission_allowed(base.get("required_permission"), permission_codes):
            continue
        links.append(
            {
                "code": code,
                "name": name,
                "path": base["path"],
                "route_name": base["route_name"],
                "menu_code": base["menu_code"],
                "required_permission": base["required_permission"],
                "default_params": _related_report_defaults(
                    code,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                    as_of_date=as_of_date,
                    from_date=from_date,
                    to_date=to_date,
                    vendor_id=vendor_id,
                ),
            }
        )
    return links


def _report_filter_codes(report_code, *, view=None):
    mapping = {
        "vendor_outstanding": [
            "entity",
            "entityfinid",
            "subentity",
            "from_date",
            "to_date",
            "as_of_date",
            "vendor",
            "vendor_ids",
            "vendor_group",
            "region",
            "currency",
            "gst_registered",
            "msme",
            "voucher_type",
            "aging_basis",
            "view",
            "overdue_only",
            "show_overdue_only",
            "show_not_due",
            "include_zero_balance",
            "include_credit_balances",
            "include_advances_separately",
            "show_settled",
            "credit_limit_exceeded",
            "outstanding_gt",
            "reconcile_gl",
            "include_trace",
            "search",
            "sort_by",
            "sort_order",
            "page",
            "page_size",
        ],
        "ap_aging": ["entity", "entityfinid", "subentity", "as_of_date", "vendor", "vendor_group", "region", "currency", "overdue_only", "credit_limit_exceeded", "include_trace", "search", "sort_by", "sort_order", "page", "page_size", "view"],
        "payables_dashboard_summary": ["entity", "entityfinid", "subentity", "as_of_date", "vendor", "vendor_group", "region", "currency", "search"],
        "ap_gl_reconciliation": ["entity", "entityfinid", "subentity", "as_of_date", "vendor", "vendor_group", "region", "currency", "include_trace", "search", "sort_by", "sort_order", "page", "page_size"],
        "vendor_balance_exceptions": ["entity", "entityfinid", "subentity", "as_of_date", "vendor", "vendor_group", "region", "currency", "search", "min_amount", "overdue_days_gt", "stale_days_gt", "include_negative_balances", "include_old_advances", "include_stale_vendors", "sort_by", "sort_order", "page", "page_size"],
        "payables_close_validation": ["entity", "entityfinid", "subentity", "as_of_date"],
        "payables_close_readiness_summary": ["entity", "entityfinid", "subentity", "as_of_date"],
        "purchase_register": ["entity", "entityfinid", "subentity", "from_date", "to_date", "vendor", "search", "page", "page_size"],
        "vendor_ledger_statement": ["entity", "entityfinid", "subentity", "vendor", "from_date", "to_date", "include_opening", "include_running_balance", "include_settlement_drilldowns", "include_related_reports", "include_trace"],
        "payables_close_pack": ["entity", "entityfinid", "subentity", "as_of_date", "include_overview", "include_aging", "include_reconciliation", "include_validation", "include_exceptions", "include_top_vendors", "expanded_validation"],
        "vendor_settlement_history": ["entity", "entityfinid", "subentity", "vendor", "from_date", "to_date", "settlement_type", "include_unapplied", "include_trace", "sort_by", "sort_order", "page", "page_size"],
        "vendor_note_register": ["entity", "entityfinid", "subentity", "vendor", "from_date", "to_date", "note_type", "status", "include_trace", "sort_by", "sort_order", "page", "page_size"],
    }
    codes = list(mapping.get(report_code, []))
    if report_code == "ap_aging" and view == "summary":
        return codes
    return codes


def resolve_supported_filters(report_code, *, view=None):
    return [
        deepcopy(PAYABLE_FILTER_DEFINITIONS[code])
        for code in _report_filter_codes(report_code, view=view)
        if code in PAYABLE_FILTER_DEFINITIONS
    ]


def resolve_pagination_mode(report_code, *, view=None):
    if report_code == "ap_aging":
        return "paged" if view == "invoice" else "none"
    if report_code in {"payables_dashboard_summary", "payables_close_validation", "payables_close_readiness_summary", "payables_close_pack"}:
        return "none"
    return "paged"


def resolve_view_modes(report_code):
    report = get_payables_report_config(report_code)
    if not report:
        return []
    view_flag = report.get("feature_flags", {}).get("view")
    if not view_flag:
        return []
    return list(view_flag.get("choices", []))


def get_payables_meta_entry(report_code, *, view=None, enabled_features=None, permission_codes=None):
    report = get_payables_report_config(report_code, view=view)
    if not report:
        return None
    if not _permission_allowed(report.get("required_permission"), permission_codes):
        return None
    columns = resolve_report_columns(report_code, view=view, enabled_features=enabled_features)
    summary_blocks = resolve_report_summary_blocks(report_code, view=view, enabled_features=enabled_features)
    drilldown_targets = []
    for code in report.get("drilldown_targets", []):
        target = get_payables_drilldown_target(code) or {"code": code, "target": code, "label": code.replace("_", " ").title()}
        target_permission = None
        target_report = get_payables_report_config(target.get("report_code") or code, view=target.get("view"))
        if target_report:
            target_permission = target_report.get("required_permission")
        if _permission_allowed(target_permission, permission_codes):
            drilldown_targets.append(target)
    related_reports = []
    for code in report.get("related_reports", []):
        related_report = get_payables_report_config(code, view=view)
        if code in {"ap_aging_summary", "ap_aging_invoice"}:
            related_report = get_payables_report_config("ap_aging")
        if related_report and _permission_allowed(related_report.get("required_permission"), permission_codes):
            related_reports.append(code)
    return {
        "code": report["code"],
        "label": report["name"],
        "name": report["name"],
        "path": report["path"],
        "endpoint": report["path"],
        "menu_code": report["menu_code"],
        "route_name": report["route_name"],
        "required_permission": report["required_permission"],
        "supports_traceability": bool(report.get("supports_traceability")),
        "pagination_mode": resolve_pagination_mode(report_code, view=view),
        "default_filters": report.get("default_filters", {}),
        "supported_filters": resolve_supported_filters(report_code, view=view),
        "feature_flags": [
            {"code": key, **value}
            for key, value in report.get("feature_flags", {}).items()
        ],
        "view_modes": resolve_view_modes(report_code),
        "available_columns": columns,
        "enabled_columns": [column["key"] for column in columns if column["included"]],
        "available_summary_blocks": summary_blocks,
        "enabled_summary_blocks": [block["code"] for block in summary_blocks if block["enabled"]],
        "drilldown_targets": drilldown_targets,
        "export_formats": list(report.get("export_formats", PAYABLE_EXPORT_FORMATS)),
        "export_columns": resolve_report_columns(report_code, view=view, enabled_features=enabled_features, export=True),
        "related_reports": related_reports,
        "print_sections": list(report.get("print_sections", [])),
        "view": view,
    }


def get_payables_registry_meta(*, permission_codes=None):
    registry = []
    for code, report in PAYABLE_REPORTS.items():
        if "views" in report:
            entry = get_payables_meta_entry(code, view="summary", permission_codes=permission_codes)
        else:
            entry = get_payables_meta_entry(code, permission_codes=permission_codes)
        if entry:
            registry.append(entry)
    return registry


def resolve_close_pack_sections(section_codes=None):
    if section_codes is None:
        section_codes = [code for code, section in PAYABLE_CLOSE_PACK_SECTIONS.items() if section.get("default")]
    sections = []
    for code in section_codes:
        section = PAYABLE_CLOSE_PACK_SECTIONS.get(code)
        if section:
            sections.append(deepcopy(section))
    sections.sort(key=lambda row: row.get("export_flatten_order", 999))
    return sections


def get_close_pack_section_codes(section_codes=None):
    return [section["code"] for section in resolve_close_pack_sections(section_codes)]




