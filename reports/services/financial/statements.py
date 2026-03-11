from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum

from financial.models import Ledger
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)


PNL_INCOME_TYPE_CODES = {"1014", "1015"}
PNL_EXPENSE_TYPE_CODES = {"1016"}
BS_ASSET_TYPE_CODES = {"1002", "1003", "1009", "1010"}
BS_LIABILITY_TYPE_CODES = {"1008", "1012"}


def _closing_map(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)
    lines = journal_lines_for_scope(entity_id, entityfin_id, subentity_id, from_date, to_date)
    movement_rows = (
        lines.values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=Decimal("0.00")),
            credit=Sum("amount", filter=Q(drcr=False), default=Decimal("0.00")),
        )
    )
    movement_map = {row["resolved_ledger_id"]: row for row in movement_rows}
    ledgers = (
        Ledger.objects.filter(id__in=movement_map.keys())
        .select_related("accounthead", "accounthead__accounttype")
        .order_by("accounthead__code", "ledger_code", "name")
    )
    closing = {}
    for ledger in ledgers:
        move = movement_map.get(ledger.id, {})
        opening = (ledger.openingbdr or Decimal("0.00")) - (ledger.openingbcr or Decimal("0.00"))
        closing[ledger.id] = {
            "ledger": ledger,
            "amount": opening + (move.get("debit") or Decimal("0.00")) - (move.get("credit") or Decimal("0.00")),
        }
    return entity_id, entityfin_id, subentity_id, from_date, to_date, closing


def build_profit_and_loss(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id, from_date, to_date, closing = _closing_map(
        entity_id, entityfin_id, subentity_id, from_date, to_date
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)
    income_rows = []
    expense_rows = []
    total_income = Decimal("0.00")
    total_expense = Decimal("0.00")

    for item in closing.values():
        ledger = item["ledger"]
        head = ledger.accounthead
        acc_type = getattr(head, "accounttype", None) if head else None
        type_code = str(getattr(acc_type, "accounttypecode", "")) if acc_type else ""
        amount = item["amount"]
        if type_code in PNL_INCOME_TYPE_CODES:
            display_amount = abs(amount)
            income_rows.append(
                {
                    "ledger_id": ledger.id,
                    "ledger_code": ledger.ledger_code,
                    "ledger_name": ledger.name,
                    "accounthead_id": head.id if head else None,
                    "accounthead_name": head.name if head else None,
                    "accounttype_id": acc_type.id if acc_type else None,
                    "accounttype_name": acc_type.accounttypename if acc_type else None,
                    "amount": f"{display_amount:.2f}",
                }
            )
            total_income += display_amount
        elif type_code in PNL_EXPENSE_TYPE_CODES:
            display_amount = abs(amount)
            expense_rows.append(
                {
                    "ledger_id": ledger.id,
                    "ledger_code": ledger.ledger_code,
                    "ledger_name": ledger.name,
                    "accounthead_id": head.id if head else None,
                    "accounthead_name": head.name if head else None,
                    "accounttype_id": acc_type.id if acc_type else None,
                    "accounttype_name": acc_type.accounttypename if acc_type else None,
                    "amount": f"{display_amount:.2f}",
                }
            )
            total_expense += display_amount

    net_profit = total_income - total_expense
    return {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "income": income_rows,
        "expenses": expense_rows,
        "totals": {
            "income": f"{total_income:.2f}",
            "expense": f"{total_expense:.2f}",
            "net_profit": f"{net_profit:.2f}",
        },
    }


def build_balance_sheet(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id, from_date, to_date, closing = _closing_map(
        entity_id, entityfin_id, subentity_id, from_date, to_date
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    assets = []
    liabilities = []
    asset_total = Decimal("0.00")
    liability_total = Decimal("0.00")
    for item in closing.values():
        ledger = item["ledger"]
        head = ledger.accounthead
        acc_type = getattr(head, "accounttype", None) if head else None
        type_code = str(getattr(acc_type, "accounttypecode", "")) if acc_type else ""
        amount = item["amount"]
        if type_code in BS_ASSET_TYPE_CODES:
            display_amount = abs(amount)
            assets.append(
                {
                    "ledger_id": ledger.id,
                    "ledger_code": ledger.ledger_code,
                    "ledger_name": ledger.name,
                    "accounthead_id": head.id if head else None,
                    "accounthead_name": head.name if head else None,
                    "accounttype_id": acc_type.id if acc_type else None,
                    "accounttype_name": acc_type.accounttypename if acc_type else None,
                    "amount": f"{display_amount:.2f}",
                }
            )
            asset_total += display_amount
        elif type_code in BS_LIABILITY_TYPE_CODES:
            display_amount = abs(amount)
            liabilities.append(
                {
                    "ledger_id": ledger.id,
                    "ledger_code": ledger.ledger_code,
                    "ledger_name": ledger.name,
                    "accounthead_id": head.id if head else None,
                    "accounthead_name": head.name if head else None,
                    "accounttype_id": acc_type.id if acc_type else None,
                    "accounttype_name": acc_type.accounttypename if acc_type else None,
                    "amount": f"{display_amount:.2f}",
                }
            )
            liability_total += display_amount

    return {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "assets": assets,
        "liabilities_and_equity": liabilities,
        "totals": {
            "assets": f"{asset_total:.2f}",
            "liabilities_and_equity": f"{liability_total:.2f}",
        },
    }
