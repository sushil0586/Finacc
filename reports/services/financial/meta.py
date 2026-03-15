from __future__ import annotations

from financial.models import account
from entity.models import EntityFinancialYear, SubEntity
from posting.models import EntryStatus, EntityStaticAccountMap, TxnType


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


DAYBOOK_VOUCHER_TYPES = (
    TxnType.SALES,
    TxnType.SALES_CREDIT_NOTE,
    TxnType.SALES_DEBIT_NOTE,
    TxnType.PURCHASE,
    TxnType.JOURNAL,
    TxnType.SALES_RETURN,
    TxnType.PURCHASE_RETURN,
    TxnType.PURCHASE_CREDIT_NOTE,
    TxnType.PURCHASE_DEBIT_NOTE,
    TxnType.JOURNAL_CASH,
    TxnType.JOURNAL_BANK,
    TxnType.RECEIPT,
    TxnType.PAYMENT,
)

CASHBOOK_VOUCHER_TYPES = (
    TxnType.JOURNAL_CASH,
    TxnType.JOURNAL_BANK,
    TxnType.RECEIPT,
    TxnType.PAYMENT,
)


def _voucher_type_options(txn_types: tuple[str, ...]) -> list[dict]:
    label_by_code = dict(TxnType.choices)
    return [{"code": code, "name": label_by_code[code]} for code in txn_types]


def _daybook_status_options() -> list[dict]:
    return [
        {"value": "draft", "label": EntryStatus.DRAFT.label},
        {"value": "posted", "label": EntryStatus.POSTED.label},
        {"value": "reversed", "label": EntryStatus.REVERSED.label},
    ]


def _account_kind_map(entity_id: int) -> dict[int, str]:
    static_maps = (
        EntityStaticAccountMap.objects.filter(
            entity_id=entity_id,
            is_active=True,
            static_account__is_active=True,
            static_account__group="CASH_BANK",
        )
        .select_related("static_account")
        .values("account_id", "static_account__code")
    )
    static_kind_by_account = {}
    for row in static_maps:
        static_kind_by_account[row["account_id"]] = "cash" if row["static_account__code"] == "CASH" else "bank"
    return static_kind_by_account


def _infer_account_kind(row, *, static_kind_by_account: dict[int, str]) -> str:
    explicit_kind = static_kind_by_account.get(row.id)
    if explicit_kind:
        return explicit_kind
    if str(getattr(row, "partytype", "")).lower() == "bank":
        return "bank"
    label = f"{getattr(row, 'accountname', '')} {getattr(getattr(row, 'ledger', None), 'name', '')}".lower()
    if "cash" in label:
        return "cash"
    if "bank" in label:
        return "bank"
    return "ledger"


def _account_option_payload(entity_id: int) -> dict[str, list[dict]]:
    static_kind_by_account = _account_kind_map(entity_id)
    rows = list(
        account.objects.filter(entity_id=entity_id, isactive=True)
        .select_related("ledger")
        .order_by("accountname", "id")
    )
    options = []
    for row in rows:
        options.append(
            {
                "id": row.id,
                "name": getattr(row.ledger, "name", None) or row.accountname or f"Account {row.id}",
                "code": getattr(row.ledger, "ledger_code", None) or row.accountcode,
                "account_type": _infer_account_kind(row, static_kind_by_account=static_kind_by_account),
            }
        )

    return {
        "all_accounts": options,
        "cash_accounts": [row for row in options if row["account_type"] == "cash"],
        "bank_accounts": [row for row in options if row["account_type"] == "bank"],
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
    account_options = _account_option_payload(entity_id)
    return {
        "entity_id": entity_id,
        "defaults": REPORT_DEFAULTS,
        "daybook_voucher_types": _voucher_type_options(DAYBOOK_VOUCHER_TYPES),
        "cashbook_voucher_types": _voucher_type_options(CASHBOOK_VOUCHER_TYPES),
        "voucher_types": _voucher_type_options(DAYBOOK_VOUCHER_TYPES),
        "daybook_statuses": _daybook_status_options(),
        **account_options,
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
