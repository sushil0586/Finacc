from decimal import Decimal

from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce

from posting.models import EntryStatus, JournalLine


ZERO2 = Decimal("0.00")


def ledger_balance_map(
    *,
    entity_id,
    fin_start,
    fin_end,
    ledger_ids=None,
    accounthead_ids=None,
):
    """
    Aggregate financial balances from posted journal lines.

    Prefer native JournalLine.ledger storage. Fall back to account->ledger for
    older rows that were posted before additive ledger storage was introduced.
    """
    qs = JournalLine.objects.filter(
        entity_id=entity_id,
        posting_date__range=(fin_start, fin_end),
        entry__status=EntryStatus.POSTED,
    ).annotate(
        resolved_ledger_id=Coalesce(F("ledger_id"), F("account__ledger_id"))
    )
    qs = qs.filter(resolved_ledger_id__isnull=False)

    if ledger_ids:
        qs = qs.filter(resolved_ledger_id__in=ledger_ids)
    if accounthead_ids:
        qs = qs.filter(
            Q(ledger__accounthead_id__in=accounthead_ids) |
            Q(ledger__isnull=True, account__ledger__accounthead_id__in=accounthead_ids)
        )

    rows = (
        qs.values("resolved_ledger_id")
        .annotate(
            debit=Coalesce(Sum("amount", filter=Q(drcr=True)), Value(ZERO2)),
            credit=Coalesce(Sum("amount", filter=Q(drcr=False)), Value(ZERO2)),
        )
    )

    balance_map = {}
    for row in rows:
        debit = row["debit"] or ZERO2
        credit = row["credit"] or ZERO2
        balance_map[row["resolved_ledger_id"]] = {
            "debit": debit,
            "credit": credit,
            "balance": debit - credit,
        }
    return balance_map
