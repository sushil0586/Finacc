from __future__ import annotations

from decimal import Decimal

from financial.services_opening_balance import ACCOUNT_OPENING_TXN_ID_BASE
from purchase.models.purchase_core import PurchaseInvoiceLine
from sales.models.sales_core import SalesInvoiceLine
from financial.models import Ledger
from posting.models import TxnType
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)
from reports.services.financial.opening_balance_source import effective_opening_map_for_ledgers

SORTABLE_FIELDS = {
    "posting_date": lambda row: (row.get("posting_date") or "", row.get("journal_line_id") or 0),
    "voucher_number": lambda row: (row.get("voucher_number") or "", row.get("journal_line_id") or 0),
    "voucher_type": lambda row: (row.get("voucher_type_name") or row.get("voucher_type") or "", row.get("journal_line_id") or 0),
    "description": lambda row: (row.get("description") or "", row.get("journal_line_id") or 0),
    "debit": lambda row: Decimal(row.get("debit") or "0.00"),
    "credit": lambda row: Decimal(row.get("credit") or "0.00"),
    "running_balance": lambda row: Decimal(row.get("running_balance") or "0.00"),
}


def _invoice_drilldown_route(txn_type: str | None, txn_id: int | None) -> str | None:
    if not txn_id:
        return None
    if txn_type in {
        TxnType.PURCHASE,
        TxnType.PURCHASE_CREDIT_NOTE,
        TxnType.PURCHASE_DEBIT_NOTE,
        TxnType.PURCHASE_RETURN,
    }:
        if PurchaseInvoiceLine.objects.filter(header_id=txn_id, is_service=True).exists():
            return "/purchaseserviceinvoice"
        return "/purchaseinvoice"
    if txn_type in {
        TxnType.SALES,
        TxnType.SALES_CREDIT_NOTE,
        TxnType.SALES_DEBIT_NOTE,
        TxnType.SALES_RETURN,
    }:
        if SalesInvoiceLine.objects.filter(header_id=txn_id, is_service=True).exists():
            return "/saleserviceinvoice"
        return "/saleinvoice"
    return None


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
        TxnType.FIXED_ASSET_CAPITALIZATION: ("assets", "fixed_asset", "asset_history_detail"),
        TxnType.FIXED_ASSET_IMPAIRMENT: ("assets", "fixed_asset", "asset_history_detail"),
        TxnType.FIXED_ASSET_DISPOSAL: ("assets", "fixed_asset", "asset_history_detail"),
        TxnType.FIXED_ASSET_DEPRECIATION: ("assets", "depreciation_run", "posting_entry_detail"),
        TxnType.OPENING_BALANCE: ("posting", "journal_entry", "posting_entry_detail"),
        TxnType.JOURNAL: ("vouchers", "voucher", "voucher_detail"),
        TxnType.YEAR_END_CLOSE: ("controls", "year_end_close", "posting_entry_detail"),
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
    account_opening_account_id = None
    if txn_type == TxnType.OPENING_BALANCE and int(source_id or 0) >= ACCOUNT_OPENING_TXN_ID_BASE:
        account_opening_account_id = int(source_id) - ACCOUNT_OPENING_TXN_ID_BASE
        source_app, source_model, drilldown_target = ("financial", "account_opening", "account_opening_detail")

    drilldown_params = {
        "id": source_id,
        "entry_id": line.entry_id,
        "entity": entity_id,
        "entityfinid": entityfin_id,
        "subentity": subentity_id,
    }
    if drilldown_target == "asset_history_detail":
        drilldown_params["asset_id"] = source_id
    if account_opening_account_id:
        drilldown_params["account_id"] = account_opening_account_id

    return {
        "txn_type": txn_type,
        "txn_type_name": txn_type_name,
        "txn_id": line.txn_id,
        "detail_id": line.detail_id,
        "source_app": source_app,
        "source_model": source_model,
        "source_id": source_id,
        "drilldown_target": drilldown_target,
        "drilldown_route": _invoice_drilldown_route(txn_type, source_id),
        "drilldown_params": drilldown_params,
    }


def build_ledger_book(
    entity_id,
    ledger_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    *,
    scope_mode=None,
    search=None,
    voucher_types=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    ledger = Ledger.objects.select_related("accounthead").get(id=ledger_id, entity_id=entity_id)
    normalized_scope_mode = str(scope_mode or "").strip().lower()
    separate_opening = normalized_scope_mode == "custom" or bool(from_date and to_date and not normalized_scope_mode)
    opening = (
        effective_opening_map_for_ledgers(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            ledgers=[ledger],
            from_date=from_date,
        ).get(ledger.id, Decimal("0.00"))
        if separate_opening
        else Decimal("0.00")
    )

    lines = journal_lines_for_scope(entity_id, entityfin_id, subentity_id, from_date, to_date)
    if separate_opening:
        lines = lines.exclude(txn_type=TxnType.OPENING_BALANCE)
    lines = lines.filter(resolved_ledger_id=ledger_id).order_by("posting_date", "entry_id", "id")

    running = opening
    row_data = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    voucher_type_set = {str(value).strip().lower() for value in (voucher_types or []) if str(value).strip()}
    search_term = str(search or "").strip().lower()
    for line in lines:
        debit = line.amount if line.drcr else Decimal("0.00")
        credit = line.amount if not line.drcr else Decimal("0.00")
        running += debit - credit
        total_debit += debit
        total_credit += credit
        row = {
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

        if voucher_type_set:
            voucher_matches = {
                str(row["voucher_type"] or "").strip().lower(),
                str(row["voucher_type_name"] or "").strip().lower(),
            }
            if not voucher_matches.intersection(voucher_type_set):
                continue

        if search_term:
            search_blob = " ".join(
                str(value or "").strip().lower()
                for value in (
                    row["voucher_number"],
                    row["voucher_type_name"],
                    row["voucher_type"],
                    row["description"],
                )
            )
            if search_term not in search_blob:
                continue

        row_data.append(row)

    sort_key = SORTABLE_FIELDS.get(sort_by or "posting_date", SORTABLE_FIELDS["posting_date"])
    reverse = str(sort_order or "asc").lower() == "desc"
    row_data = sorted(row_data, key=sort_key, reverse=reverse)

    total_records = len(row_data)
    safe_page_size = max(int(page_size or 100), 1)
    total_pages = max((total_records + safe_page_size - 1) // safe_page_size, 1)
    safe_page = min(max(int(page or 1), 1), total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    paged_rows = row_data[start:end]

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
        "running_balance_scope": "account",
        "balance_basis": "ledger_running_balance",
        "balance_integrity": True,
        "balance_note": (
            "Ledger Book running balance is derived from posted journal lines for the selected ledger "
            "and is ordered deterministically by posting date, entry id, and journal line id."
        ),
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
            "total_records": total_records,
        },
        "reporting": {
            "basis": "ledger_running_balance",
            "scope_mode": scope_mode or "financial_year",
            "separate_opening": separate_opening,
            "sort_by": sort_by or "posting_date",
            "sort_order": "desc" if reverse else "asc",
        },
        "rows": paged_rows,
    }
