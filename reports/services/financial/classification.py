from __future__ import annotations

from dataclasses import dataclass


# detailsingroup values used in financial masters today.
TRADING_GROUP = 1
PROFIT_LOSS_GROUP = 2
BALANCE_SHEET_GROUP = 3


def _norm_text(value) -> str:
    return str(value or "").strip().lower()


def _norm_code(value) -> str:
    return str(value or "").strip()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _detailsingroup_value(head) -> int | None:
    value = getattr(head, "detailsingroup", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _head_name(head) -> str:
    return _norm_text(getattr(head, "name", None))


def _head_code(head) -> str:
    return _norm_code(getattr(head, "code", None))


def _type_name(acc_type) -> str:
    return _norm_text(getattr(acc_type, "accounttypename", None))


def _type_code(acc_type) -> str:
    return _norm_code(getattr(acc_type, "accounttypecode", None) or getattr(acc_type, "code", None))


def _is_opening_stock_head(head, acc_type) -> bool:
    text = " ".join((_head_name(head), _type_name(acc_type))).strip()
    return "opening stock" in text


def _is_closing_stock_head(head, acc_type) -> bool:
    text = " ".join((_head_name(head), _type_name(acc_type))).strip()
    return _contains_any(text, ("closing stock", "stock in hand"))


def _is_inventory_asset_head(head, acc_type) -> bool:
    text = " ".join((_head_name(head), _type_name(acc_type))).strip()
    return _contains_any(text, ("inventory", "stock")) and not _is_opening_stock_head(head, acc_type)


def _is_direct_type(acc_type) -> bool:
    type_name = _type_name(acc_type)
    type_code = _type_code(acc_type)
    return type_code in {"4100", "5100"} or type_name in {"direct income", "direct expenses"}


def _is_indirect_type(acc_type) -> bool:
    type_name = _type_name(acc_type)
    type_code = _type_code(acc_type)
    return type_code in {"4200", "5200"} or type_name in {"indirect income", "indirect expenses"}


def _is_balance_sheet_type(acc_type) -> bool:
    type_name = _type_name(acc_type)
    type_code = _type_code(acc_type)
    return type_code in {
        "1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010", "1012",
    } or type_name in {
        "receivable",
        "current assets",
        "non current assets",
        "bank and cash",
        "fixed assets",
        "current liabilities",
        "non current liabilities",
        "borrowings",
        "loans and advances",
        "payable",
        "party",
        "tax",
        "equity",
        "capital and equity",
    }


def _is_purchase_or_sales_head(head, acc_type) -> bool:
    text = " ".join((_head_name(head), _type_name(acc_type))).strip()
    code = _head_code(head)
    return code in {"1000", "3000"} or _contains_any(
        text,
        ("purchase", "sales", "sale", "sales revenue", "turnover"),
    )


@dataclass(frozen=True)
class FinancialClassification:
    include_in_trading: bool = False
    include_in_profit_loss: bool = False
    include_in_balance_sheet: bool = False
    profit_loss_side: str | None = None
    reason: str = ""


def classify_financial_head(head, acc_type) -> FinancialClassification:
    """
    Central accounting rules shared by Trading, P&L, and Balance Sheet.
    Rule 1: Opening stock belongs only to Trading.
    Rule 2: Closing stock/inventory belongs to Trading and Balance Sheet.
    Rule 3: Statement group / detailsingroup is the primary routing rule.
    Rule 4: Purchases, Sales, and direct income/expense heads fall back to Trading
            only when statement-group metadata is incomplete.
    Rule 5: Indirect income/expense heads belong to Profit & Loss.
    Rule 6: Structural asset/liability/equity heads belong to Balance Sheet.
    """
    if _is_opening_stock_head(head, acc_type):
        return FinancialClassification(include_in_trading=True, reason="opening_stock")

    if _is_closing_stock_head(head, acc_type) or _is_inventory_asset_head(head, acc_type):
        return FinancialClassification(
            include_in_trading=True,
            include_in_balance_sheet=True,
            reason="closing_stock_or_inventory",
        )

    detailsingroup = _detailsingroup_value(head)
    if detailsingroup == TRADING_GROUP:
        return FinancialClassification(include_in_trading=True, reason="fallback_detailsingroup_trading")
    if detailsingroup == PROFIT_LOSS_GROUP:
        return FinancialClassification(
            include_in_profit_loss=True,
            profit_loss_side=(
                "income"
                if _type_code(acc_type) == "4200" or _type_name(acc_type) == "indirect income"
                else "expense"
            ),
            reason="fallback_detailsingroup_profit_loss",
        )
    if detailsingroup == BALANCE_SHEET_GROUP:
        return FinancialClassification(include_in_balance_sheet=True, reason="fallback_detailsingroup_balance_sheet")

    if _is_purchase_or_sales_head(head, acc_type) or _is_direct_type(acc_type):
        return FinancialClassification(include_in_trading=True, reason="direct_trading")

    if _is_indirect_type(acc_type):
        return FinancialClassification(
            include_in_profit_loss=True,
            profit_loss_side="income" if _type_code(acc_type) == "4200" or _type_name(acc_type) == "indirect income" else "expense",
            reason="indirect_profit_loss",
        )

    if _is_balance_sheet_type(acc_type):
        return FinancialClassification(include_in_balance_sheet=True, reason="structural_balance_sheet")

    return FinancialClassification(reason="unclassified")
