from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce

from financial.models import Ledger
from posting.models import EntryStatus, JournalLine, TxnType
from reports.selectors.financial import ensure_date, journal_lines_for_scope, resolve_date_window

ZERO = Decimal("0.00")


def posted_opening_map_for_ledgers(
    *,
    entity_id: int,
    entityfin_id: int | None,
    subentity_id: int | None,
    ledger_ids: list[int] | tuple[int, ...] | None = None,
    posted_only: bool = True,
) -> dict[int, Decimal]:
    qs = JournalLine.objects.filter(entity_id=entity_id, txn_type=TxnType.OPENING_BALANCE).annotate(
        resolved_ledger_id=Coalesce(F("ledger_id"), F("account__ledger_id"))
    ).exclude(resolved_ledger_id__isnull=True)
    if posted_only:
        qs = qs.filter(entry__status=EntryStatus.POSTED)
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity_id__isnull=True))
    if ledger_ids:
        qs = qs.filter(resolved_ledger_id__in=list(ledger_ids))

    rows = (
        qs.values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=ZERO),
            credit=Sum("amount", filter=Q(drcr=False), default=ZERO),
        )
    )
    return {
        int(row["resolved_ledger_id"]): (row.get("debit") or ZERO) - (row.get("credit") or ZERO)
        for row in rows
        if row.get("resolved_ledger_id") is not None
    }


def effective_opening_map_for_ledgers(
    *,
    entity_id: int,
    entityfin_id: int | None,
    subentity_id: int | None,
    ledgers: list[Ledger] | tuple[Ledger, ...],
    from_date=None,
    posted_only: bool = True,
) -> dict[int, Decimal]:
    ledger_ids = [int(ledger.id) for ledger in ledgers if getattr(ledger, "id", None) is not None]
    posted_map = posted_opening_map_for_ledgers(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        ledger_ids=ledger_ids,
        posted_only=posted_only,
    )
    opening_map = {
        int(ledger.id): posted_map.get(int(ledger.id), ZERO)
        for ledger in ledgers
        if getattr(ledger, "id", None) is not None
    }

    report_from = ensure_date(from_date)
    if not entityfin_id or not report_from:
        return opening_map

    fy_start, _ = resolve_date_window(entityfin_id, None, None)
    fy_start = ensure_date(fy_start)
    if not fy_start or report_from <= fy_start:
        return opening_map

    prior_to = report_from - timedelta(days=1)
    prior_rows = (
        journal_lines_for_scope(
            entity_id,
            entityfin_id,
            subentity_id,
            fy_start,
            prior_to,
            posted_only=posted_only,
        )
        .exclude(txn_type=TxnType.OPENING_BALANCE)
        .filter(resolved_ledger_id__in=ledger_ids)
        .values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=ZERO),
            credit=Sum("amount", filter=Q(drcr=False), default=ZERO),
        )
    )
    for row in prior_rows:
        ledger_id = row.get("resolved_ledger_id")
        if ledger_id is None:
            continue
        opening_map[int(ledger_id)] = opening_map.get(int(ledger_id), ZERO) + (row.get("debit") or ZERO) - (row.get("credit") or ZERO)

    return opening_map
