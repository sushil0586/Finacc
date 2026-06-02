from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from posting.models import EntryStatus, JournalLine

from ..models import (
    ZERO,
    BankReconciliationAuditLog,
    BankReconciliationRun,
    BankStatementLine,
)
from .matching import (
    _statement_amount,
    bank_line_signed_amount,
    bank_lines_for_run,
    build_unmatched_bank_rows,
    build_unmatched_book_rows,
    resolve_bank_book_binding,
)


def _book_line_signed_amount(line: JournalLine) -> Decimal:
    amount = Decimal(str(line.amount or ZERO))
    return amount if bool(line.drcr) else (amount * Decimal("-1"))


def _book_balance_as_of(run: BankReconciliationRun) -> Decimal:
    binding = resolve_bank_book_binding(entity=run.entity, bank_account=run.bank_account, metadata=run.metadata)
    qs = JournalLine.objects.select_related("entry").filter(
        entity=run.entity,
        entry__status=EntryStatus.POSTED,
    )
    if run.entityfin_id:
        qs = qs.filter(entityfin_id=run.entityfin_id)
    if run.subentity_id:
        qs = qs.filter(subentity_id=run.subentity_id)
    if run.as_of_date:
        qs = qs.filter(posting_date__lte=run.as_of_date)
    if binding.account_ids and binding.ledger_ids:
        qs = qs.filter(Q(account_id__in=binding.account_ids) | Q(ledger_id__in=binding.ledger_ids))
    elif binding.account_ids:
        qs = qs.filter(account_id__in=binding.account_ids)
    else:
        qs = qs.filter(ledger_id__in=binding.ledger_ids)
    return sum((_book_line_signed_amount(line) for line in qs.iterator()), ZERO)


def build_unmatched_bank_report(*, run: BankReconciliationRun):
    rows = build_unmatched_bank_rows(run=run)
    if run.statement_import.statement_from:
        for row in rows:
            row["is_opening_item"] = bool(row["is_opening_item"])
    totals = {
        "count": len(rows),
        "debit_amount": sum((Decimal(str(row.get("debit_amount") or ZERO)) for row in rows), ZERO),
        "credit_amount": sum((Decimal(str(row.get("credit_amount") or ZERO)) for row in rows), ZERO),
    }
    export_rows = [
        {
            "Txn Date": row.get("txn_date") or row.get("value_date") or "",
            "Reference": row.get("reference_no") or row.get("cheque_no") or "",
            "Narration": row.get("narration") or "",
            "Debit": row.get("debit_amount") or ZERO,
            "Credit": row.get("credit_amount") or ZERO,
            "Status": row.get("status") or "",
            "Exception Status": row.get("exception_status") or "",
        }
        for row in rows
    ]
    return {"rows": rows, "totals": totals, "export_rows": export_rows}


def build_unmatched_books_report(*, run: BankReconciliationRun):
    rows = build_unmatched_book_rows(run=run)
    totals = {
        "count": len(rows),
        "amount": sum((Decimal(str(row.get("amount") or ZERO)) for row in rows), ZERO),
    }
    export_rows = [
        {
            "Posting Date": row.get("posting_date") or "",
            "Voucher": row.get("voucher_no") or "",
            "Direction": row.get("drcr") or "",
            "Amount": row.get("amount") or ZERO,
            "Description": row.get("description") or row.get("reference") or "",
        }
        for row in rows
    ]
    return {"rows": rows, "totals": totals, "export_rows": export_rows}


def build_audit_trail_report(*, run: BankReconciliationRun, action: str | None = None):
    queryset = BankReconciliationAuditLog.objects.filter(run=run).select_related("actor", "match").order_by("-created_at", "-id")
    if action:
        queryset = queryset.filter(action=action)
    rows = []
    for log in queryset[:500]:
        rows.append(
            {
                "id": log.id,
                "created_at": log.created_at,
                "action": log.action,
                "object_type": log.object_type,
                "object_id": log.object_id,
                "actor": getattr(log.actor, "username", "") or getattr(log.actor, "email", "") or "",
                "payload": log.payload or {},
            }
        )
    return {
        "rows": rows,
        "export_rows": [
            {
                "When": row["created_at"],
                "Action": row["action"],
                "Object Type": row["object_type"],
                "Object Id": row["object_id"],
                "Actor": row["actor"],
                "Payload": row["payload"],
            }
            for row in rows
        ],
    }


def _descriptor_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "").lower()
        for key in ("description", "reference", "voucher_no")
    )


def _is_cheque_row(row: dict) -> bool:
    text = _descriptor_text(row)
    return any(token in text for token in ("cheque", "chq", "chk"))


def build_brs_report(*, run: BankReconciliationRun):
    book_balance = _book_balance_as_of(run)
    bank_balance = run.statement_import.closing_balance
    unmatched_bank = build_unmatched_bank_rows(run=run)
    unmatched_books = build_unmatched_book_rows(run=run)

    cheques_issued_not_presented = ZERO
    cheques_deposited_not_cleared = ZERO
    for row in unmatched_books:
        if not _is_cheque_row(row):
            continue
        amount = Decimal(str(row["amount"] or ZERO))
        if row["drcr"] == "cr":
            cheques_issued_not_presented += amount
        else:
            cheques_deposited_not_cleared += amount

    add_direct_bank_entries = ZERO
    less_direct_bank_entries = ZERO
    add_errors = ZERO
    less_errors = ZERO
    pending_clearance = ZERO
    for row in unmatched_bank:
        amount = Decimal(str(row["credit_amount"] or ZERO)) if Decimal(str(row["credit_amount"] or ZERO)) > ZERO else Decimal(str(row["debit_amount"] or ZERO))
        is_credit = Decimal(str(row["credit_amount"] or ZERO)) > ZERO
        exception_status = row.get("exception_status") or BankStatementLine.ExceptionStatus.NONE
        if exception_status in {
            BankStatementLine.ExceptionStatus.BANK_ERROR,
            BankStatementLine.ExceptionStatus.BOOK_ERROR,
        }:
            if is_credit:
                add_errors += amount
            else:
                less_errors += amount
        elif exception_status == BankStatementLine.ExceptionStatus.PENDING_CLEARANCE:
            pending_clearance += amount
        else:
            if is_credit:
                add_direct_bank_entries += amount
            else:
                less_direct_bank_entries += amount

    reconciled_balance = (
        book_balance
        + cheques_issued_not_presented
        - cheques_deposited_not_cleared
        + add_direct_bank_entries
        - less_direct_bank_entries
        + add_errors
        - less_errors
    )
    difference_amount = bank_balance - reconciled_balance
    sections = [
        {"label": "Balance as per books", "amount": book_balance, "direction": "base"},
        {"label": "Add cheques issued but not presented", "amount": cheques_issued_not_presented, "direction": "add"},
        {"label": "Less cheques deposited but not cleared", "amount": cheques_deposited_not_cleared, "direction": "less"},
        {"label": "Add direct bank entries", "amount": add_direct_bank_entries, "direction": "add"},
        {"label": "Less direct bank entries", "amount": less_direct_bank_entries, "direction": "less"},
        {"label": "Add errors", "amount": add_errors, "direction": "add"},
        {"label": "Less errors", "amount": less_errors, "direction": "less"},
        {"label": "Pending clearance", "amount": pending_clearance, "direction": "memo"},
        {"label": "Balance as per bank statement", "amount": bank_balance, "direction": "target"},
        {"label": "Difference amount", "amount": difference_amount, "direction": "difference"},
    ]
    return {
        "balance_as_per_books": book_balance,
        "add_cheques_issued_not_presented": cheques_issued_not_presented,
        "less_cheques_deposited_not_cleared": cheques_deposited_not_cleared,
        "add_direct_bank_entries": add_direct_bank_entries,
        "less_direct_bank_entries": less_direct_bank_entries,
        "add_errors": add_errors,
        "less_errors": less_errors,
        "pending_clearance_amount": pending_clearance,
        "balance_as_per_bank_statement": bank_balance,
        "difference_amount": difference_amount,
        "sections": sections,
        "export_rows": [{"Section": section["label"], "Amount": section["amount"], "Direction": section["direction"]} for section in sections],
        "supporting_rows": {
            "unmatched_bank_count": len(unmatched_bank),
            "unmatched_book_count": len(unmatched_books),
        },
    }
