from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum, Q

from financial.models import Credit, Debit, Ledger
from reports.selectors.financial import (
    journal_lines_for_scope,
    normalize_scope_ids,
    resolve_date_window,
    resolve_scope_names,
)


def build_trial_balance(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    lines = journal_lines_for_scope(entity_id, entityfin_id, subentity_id, from_date, to_date)
    movement_rows = (
        lines.values("resolved_ledger_id")
        .annotate(
            debit=Sum("amount", filter=Q(drcr=True), default=Decimal("0.00")),
            credit=Sum("amount", filter=Q(drcr=False), default=Decimal("0.00")),
        )
    )
    movement_map = {row["resolved_ledger_id"]: row for row in movement_rows}

    ledger_ids = list(movement_map.keys())
    if not ledger_ids:
        return {
            "entity_id": entity_id,
            "entity_name": scope_names["entity_name"],
            "entityfin_id": entityfin_id,
            "entityfin_name": scope_names["entityfin_name"],
            "subentity_id": subentity_id,
            "subentity_name": scope_names["subentity_name"],
            "from_date": from_date,
            "to_date": to_date,
            "rows": [],
            "totals": {"opening": "0.00", "debit": "0.00", "credit": "0.00", "closing": "0.00"},
        }

    ledgers = (
        Ledger.objects.filter(id__in=ledger_ids)
        .select_related("accounthead", "accounttype")
        .order_by("ledger_code", "name")
    )

    rows = []
    totals = defaultdict(lambda: Decimal("0.00"))
    for ledger in ledgers:
        movement = movement_map.get(ledger.id, {})
        opening_dr = ledger.openingbdr or Decimal("0.00")
        opening_cr = ledger.openingbcr or Decimal("0.00")
        opening = opening_dr - opening_cr
        debit = movement.get("debit") or Decimal("0.00")
        credit = movement.get("credit") or Decimal("0.00")
        closing = opening + debit - credit
        rows.append(
            {
                "ledger_id": ledger.id,
                "ledger_code": ledger.ledger_code,
                "ledger_name": ledger.name,
                "accounthead_id": ledger.accounthead_id,
                "accounthead_name": ledger.accounthead.name if ledger.accounthead_id else None,
                "accounttype_id": ledger.accounttype_id,
                "accounttype_name": ledger.accounttype.accounttypename if ledger.accounttype_id else None,
                "normal_balance": ledger.accounthead.drcreffect if ledger.accounthead_id else Debit,
                "opening": f"{opening:.2f}",
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
                "closing": f"{closing:.2f}",
            }
        )
        totals["opening"] += opening
        totals["debit"] += debit
        totals["credit"] += credit
        totals["closing"] += closing

    return {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "rows": rows,
        "totals": {k: f"{v:.2f}" for k, v in totals.items()},
    }
