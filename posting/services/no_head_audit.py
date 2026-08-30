from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.db.models import Count, Q, Sum

from posting.models import EntryStatus, JournalLine, TxnType


SALES_TXN_TYPES = {
    TxnType.SALES,
    TxnType.SALES_CREDIT_NOTE,
    TxnType.SALES_DEBIT_NOTE,
    TxnType.SALES_RETURN,
}
PURCHASE_TXN_TYPES = {
    TxnType.PURCHASE,
    TxnType.PURCHASE_CREDIT_NOTE,
    TxnType.PURCHASE_DEBIT_NOTE,
    TxnType.PURCHASE_RETURN,
}
VOUCHER_TXN_TYPES = {
    TxnType.JOURNAL,
    TxnType.JOURNAL_CASH,
    TxnType.JOURNAL_BANK,
    TxnType.RECEIPT,
    TxnType.PAYMENT,
}
PAYROLL_TXN_TYPES = {
    TxnType.PAYROLL,
    TxnType.PAYROLL_FNF,
}
MANUFACTURING_TXN_TYPES = {
    TxnType.MANUFACTURING_WORK_ORDER,
}
INVENTORY_TXN_TYPES = {
    TxnType.INVENTORY_TRANSFER,
    TxnType.INVENTORY_ADJUSTMENT,
}
ASSET_TXN_TYPES = {
    TxnType.FIXED_ASSET_CAPITALIZATION,
    TxnType.FIXED_ASSET_DEPRECIATION,
    TxnType.FIXED_ASSET_IMPAIRMENT,
    TxnType.FIXED_ASSET_DISPOSAL,
}
OPENING_TXN_TYPES = {
    TxnType.OPENING_BALANCE,
    TxnType.YEAR_END_CLOSE,
}

MODULE_TXN_TYPES: dict[str, set[str]] = {
    "sales": set(SALES_TXN_TYPES),
    "purchase": set(PURCHASE_TXN_TYPES),
    "vouchers": set(VOUCHER_TXN_TYPES),
    "payroll": set(PAYROLL_TXN_TYPES),
    "manufacturing": set(MANUFACTURING_TXN_TYPES),
    "inventory": set(INVENTORY_TXN_TYPES),
    "assets": set(ASSET_TXN_TYPES),
    "opening": set(OPENING_TXN_TYPES),
}


@dataclass(frozen=True)
class NoHeadPostingIssue:
    module: str
    txn_type: str
    ledger_id: int | None
    ledger_name: str
    account_id: int | None
    account_name: str
    row_count: int
    debit: Decimal
    credit: Decimal
    net: Decimal
    sample_txn_ids: list[int] = field(default_factory=list)
    sample_vouchers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "module": self.module,
            "txn_type": self.txn_type,
            "ledger_id": self.ledger_id,
            "ledger_name": self.ledger_name,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "row_count": self.row_count,
            "debit": str(self.debit),
            "credit": str(self.credit),
            "net": str(self.net),
            "sample_txn_ids": self.sample_txn_ids,
            "sample_vouchers": self.sample_vouchers,
        }


def module_for_txn_type(txn_type: str) -> str:
    for module, txn_types in MODULE_TXN_TYPES.items():
        if txn_type in txn_types:
            return module
    return "other"


def _decimal(value) -> Decimal:
    return Decimal(value or "0.00")


def _scoped_no_head_queryset(
    *,
    entity_id: int | None = None,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    txn_types: Iterable[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    posted_only: bool = True,
):
    qs = JournalLine.objects.select_related("entry", "ledger", "account").filter(account_id__isnull=False)
    qs = qs.filter(Q(ledger_id__isnull=True) | Q(ledger__accounthead_id__isnull=True, ledger__creditaccounthead_id__isnull=True))

    if posted_only:
        qs = qs.filter(entry__status=EntryStatus.POSTED)
    if entity_id:
        qs = qs.filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if txn_types:
        qs = qs.filter(txn_type__in=list(txn_types))
    if from_date:
        qs = qs.filter(posting_date__gte=from_date)
    if to_date:
        qs = qs.filter(posting_date__lte=to_date)

    return qs


def audit_no_head_postings(
    *,
    entity_id: int | None = None,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    txn_types: Iterable[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    posted_only: bool = True,
    sample_size: int = 5,
) -> list[NoHeadPostingIssue]:
    qs = _scoped_no_head_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        txn_types=txn_types,
        from_date=from_date,
        to_date=to_date,
        posted_only=posted_only,
    )

    rows = (
        qs.values(
            "txn_type",
            "ledger_id",
            "ledger__name",
            "account_id",
            "account__accountname",
        )
        .annotate(
            row_count=Count("id"),
            debit=Sum("amount", filter=Q(drcr=True)),
            credit=Sum("amount", filter=Q(drcr=False)),
        )
        .order_by("txn_type", "ledger__name", "account__accountname")
    )

    issues: list[NoHeadPostingIssue] = []
    for row in rows:
        group_qs = qs.filter(
            txn_type=row["txn_type"],
            ledger_id=row["ledger_id"],
            account_id=row["account_id"],
        ).order_by("posting_date", "id")
        sample_rows = list(group_qs.values("txn_id", "voucher_no")[:sample_size])
        debit = _decimal(row.get("debit"))
        credit = _decimal(row.get("credit"))
        issues.append(
            NoHeadPostingIssue(
                module=module_for_txn_type(row["txn_type"]),
                txn_type=row["txn_type"],
                ledger_id=row["ledger_id"],
                ledger_name=row.get("ledger__name") or "Missing Ledger",
                account_id=row["account_id"],
                account_name=row.get("account__accountname") or "Missing Account",
                row_count=int(row["row_count"] or 0),
                debit=debit,
                credit=credit,
                net=debit - credit,
                sample_txn_ids=[int(sample["txn_id"]) for sample in sample_rows if sample.get("txn_id") is not None],
                sample_vouchers=[str(sample["voucher_no"]) for sample in sample_rows if sample.get("voucher_no")],
            )
        )

    return issues
