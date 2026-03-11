from __future__ import annotations

from decimal import Decimal

from financial.models import Ledger
from posting.models import TxnType
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)


def _drilldown_meta(line, *, entity_id, entityfin_id, subentity_id):
    txn_type = line.txn_type
    txn_type_name = line.get_txn_type_display() if hasattr(line, "get_txn_type_display") else None

    mapping = {
        TxnType.SALES: ("sales", "sales_invoice", "sales_invoice_detail"),
        TxnType.SALES_CREDIT_NOTE: ("sales", "sales_invoice", "sales_invoice_detail"),
        TxnType.SALES_DEBIT_NOTE: ("sales", "sales_invoice", "sales_invoice_detail"),
        TxnType.SALES_RETURN: ("sales", "sales_invoice", "sales_invoice_detail"),
        TxnType.PURCHASE: ("purchase", "purchase_invoice", "purchase_invoice_detail"),
        TxnType.PURCHASE_CREDIT_NOTE: ("purchase", "purchase_invoice", "purchase_invoice_detail"),
        TxnType.PURCHASE_DEBIT_NOTE: ("purchase", "purchase_invoice", "purchase_invoice_detail"),
        TxnType.PURCHASE_RETURN: ("purchase", "purchase_invoice", "purchase_invoice_detail"),
        TxnType.JOURNAL: ("vouchers", "voucher", "voucher_detail"),
        TxnType.JOURNAL_CASH: ("vouchers", "voucher", "voucher_detail"),
        TxnType.JOURNAL_BANK: ("vouchers", "voucher", "voucher_detail"),
        TxnType.RECEIPT: ("receipts", "receipt_voucher", "receipt_voucher_detail"),
        TxnType.PAYMENT: ("payments", "payment_voucher", "payment_voucher_detail"),
    }
    source_app, source_model, drilldown_target = mapping.get(
        txn_type,
        ("posting", "journal_entry", "journal_entry_detail"),
    )
    source_id = line.txn_id

    return {
        "txn_type": txn_type,
        "txn_type_name": txn_type_name,
        "txn_id": line.txn_id,
        "detail_id": line.detail_id,
        "source_app": source_app,
        "source_model": source_model,
        "source_id": source_id,
        "drilldown_target": drilldown_target,
        "drilldown_params": {
            "id": source_id,
            "entity": entity_id,
            "entityfinid": entityfin_id,
            "subentity": subentity_id,
        },
    }


def build_ledger_book(entity_id, ledger_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    ledger = Ledger.objects.select_related("accounthead").get(id=ledger_id, entity_id=entity_id)
    opening = (ledger.openingbdr or Decimal("0.00")) - (ledger.openingbcr or Decimal("0.00"))

    lines = (
        journal_lines_for_scope(entity_id, entityfin_id, subentity_id, from_date, to_date)
        .filter(resolved_ledger_id=ledger_id)
        .order_by("posting_date", "entry_id", "id")
    )

    running = opening
    row_data = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for line in lines:
        debit = line.amount if line.drcr else Decimal("0.00")
        credit = line.amount if not line.drcr else Decimal("0.00")
        running += debit - credit
        total_debit += debit
        total_credit += credit
        row_data.append(
            {
                "journal_line_id": line.id,
                "entry_id": line.entry_id,
                "posting_date": line.posting_date,
                "voucher_number": line.voucher_no or getattr(line.entry, "voucher_no", None),
                "voucher_type": line.txn_type,
                "voucher_type_name": line.get_txn_type_display() if hasattr(line, "get_txn_type_display") else None,
                "description": line.description,
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
                "running_balance": f"{running:.2f}",
                **_drilldown_meta(
                    line,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                ),
            }
        )

    return {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "ledger": {
            "id": ledger.id,
            "ledger_code": ledger.ledger_code,
            "name": ledger.name,
            "accounthead_id": ledger.accounthead_id,
            "accounthead_name": ledger.accounthead.name if ledger.accounthead_id else None,
            "accounttype_id": ledger.accounttype_id,
            "accounttype_name": ledger.accounttype.accounttypename if ledger.accounttype_id else None,
        },
        "opening_balance": f"{opening:.2f}",
        "totals": {
            "debit": f"{total_debit:.2f}",
            "credit": f"{total_credit:.2f}",
            "closing_balance": f"{running:.2f}",
        },
        "rows": row_data,
    }
