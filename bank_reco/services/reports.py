from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum, Case, When, F, DecimalField, Value as V

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
    build_unmatched_bank_rows_from_queryset,
    build_unmatched_book_rows,
    build_unmatched_book_rows_from_queryset,
    filter_bank_lines_queryset,
    filter_unmatched_book_lines_queryset,
    unmatched_bank_lines_for_run,
    unmatched_book_lines_for_run,
    resolve_bank_book_binding,
)


def _book_line_signed_amount(line: JournalLine) -> Decimal:
    amount = Decimal(str(line.amount or ZERO))
    return amount if bool(line.drcr) else (amount * Decimal("-1"))


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    return value or ZERO


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
    return qs.aggregate(
        balance=Sum(
            Case(
                When(drcr=True, then=F("amount")),
                default=F("amount") * V(Decimal("-1.00")),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
            default=ZERO,
        )
    )["balance"] or ZERO


def build_unmatched_bank_report(*, run: BankReconciliationRun, limit: int = 400, offset: int = 0, filters: dict | None = None):
    bank_lines = filter_bank_lines_queryset(unmatched_bank_lines_for_run(run=run), filters)
    total_count = bank_lines.count()
    rows = build_unmatched_bank_rows_from_queryset(
        bank_lines=bank_lines,
        current_from=run.statement_import.statement_from,
        limit=limit,
        offset=offset,
    )
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
    return {"count": total_count, "rows": rows, "totals": totals, "export_rows": export_rows}


def build_unmatched_books_report(*, run: BankReconciliationRun, limit: int = 400, offset: int = 0, filters: dict | None = None):
    book_lines = filter_unmatched_book_lines_queryset(unmatched_book_lines_for_run(run=run), filters)
    total_count = book_lines.count()
    rows = build_unmatched_book_rows_from_queryset(
        qs=book_lines,
        current_from=run.statement_import.statement_from,
        limit=limit,
        offset=offset,
    )
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
    return {"count": total_count, "rows": rows, "totals": totals, "export_rows": export_rows}


def build_audit_trail_report(*, run: BankReconciliationRun, action: str | None = None):
    queryset = BankReconciliationAuditLog.objects.filter(run=run).order_by("-created_at", "-id")
    if action:
        queryset = queryset.filter(action=action)
    rows = []
    for log in queryset.values(
        "id",
        "created_at",
        "action",
        "object_type",
        "object_id",
        "payload",
        "actor__username",
        "actor__email",
    )[:500]:
        rows.append(
            {
                "id": log["id"],
                "created_at": log["created_at"],
                "action": log["action"],
                "object_type": log["object_type"],
                "object_id": log["object_id"],
                "actor": log["actor__username"] or log["actor__email"] or "",
                "payload": log["payload"] or {},
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


def _unmatched_book_cheque_totals(*, run: BankReconciliationRun) -> tuple[Decimal, Decimal, int]:
    queryset = unmatched_book_lines_for_run(run=run)
    cheque_filter = (
        Q(description__icontains="cheque")
        | Q(description__icontains="chq")
        | Q(description__icontains="chk")
        | Q(entry__narration__icontains="cheque")
        | Q(entry__narration__icontains="chq")
        | Q(entry__narration__icontains="chk")
        | Q(voucher_no__icontains="cheque")
        | Q(voucher_no__icontains="chq")
        | Q(voucher_no__icontains="chk")
    )
    cheque_totals = queryset.filter(cheque_filter).aggregate(
        cheques_issued_not_presented=Sum(
            Case(
                When(drcr=False, then=F("amount")),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
        cheques_deposited_not_cleared=Sum(
            Case(
                When(drcr=True, then=F("amount")),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
    )
    return (
        _decimal_or_zero(cheque_totals["cheques_issued_not_presented"]),
        _decimal_or_zero(cheque_totals["cheques_deposited_not_cleared"]),
        queryset.count(),
    )


def _unmatched_bank_brs_totals(*, run: BankReconciliationRun) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, int]:
    queryset = unmatched_bank_lines_for_run(run=run)
    direct_entry_filter = ~Q(
        exception_status__in=[
            BankStatementLine.ExceptionStatus.BANK_ERROR,
            BankStatementLine.ExceptionStatus.BOOK_ERROR,
            BankStatementLine.ExceptionStatus.PENDING_CLEARANCE,
        ]
    )
    totals = queryset.aggregate(
        add_direct_bank_entries=Sum(
            Case(
                When(direct_entry_filter, credit_amount__gt=ZERO, then=F("credit_amount")),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
        less_direct_bank_entries=Sum(
            Case(
                When(direct_entry_filter, then=F("debit_amount")),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
        add_errors=Sum(
            Case(
                When(
                    exception_status__in=[
                        BankStatementLine.ExceptionStatus.BANK_ERROR,
                        BankStatementLine.ExceptionStatus.BOOK_ERROR,
                    ],
                    credit_amount__gt=ZERO,
                    then=F("credit_amount"),
                ),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
        less_errors=Sum(
            Case(
                When(
                    exception_status__in=[
                        BankStatementLine.ExceptionStatus.BANK_ERROR,
                        BankStatementLine.ExceptionStatus.BOOK_ERROR,
                    ],
                    then=F("debit_amount"),
                ),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
        pending_clearance=Sum(
            Case(
                When(
                    exception_status=BankStatementLine.ExceptionStatus.PENDING_CLEARANCE,
                    credit_amount__gt=ZERO,
                    then=F("credit_amount"),
                ),
                When(
                    exception_status=BankStatementLine.ExceptionStatus.PENDING_CLEARANCE,
                    then=F("debit_amount"),
                ),
                default=V(ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ),
    )
    return (
        _decimal_or_zero(totals["add_direct_bank_entries"]),
        _decimal_or_zero(totals["less_direct_bank_entries"]),
        _decimal_or_zero(totals["add_errors"]),
        _decimal_or_zero(totals["less_errors"]),
        _decimal_or_zero(totals["pending_clearance"]),
        queryset.count(),
    )


def build_brs_report(*, run: BankReconciliationRun):
    book_balance = _book_balance_as_of(run)
    bank_balance = run.statement_import.closing_balance
    cheques_issued_not_presented, cheques_deposited_not_cleared, unmatched_book_count = _unmatched_book_cheque_totals(run=run)
    (
        add_direct_bank_entries,
        less_direct_bank_entries,
        add_errors,
        less_errors,
        pending_clearance,
        unmatched_bank_count,
    ) = _unmatched_bank_brs_totals(run=run)

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
            "unmatched_bank_count": unmatched_bank_count,
            "unmatched_book_count": unmatched_book_count,
        },
    }
