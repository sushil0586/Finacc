from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from posting.models import EntryStatus, JournalLine, TxnType

from .models import (
    CapitalDistributionAccountMapping,
    CapitalDistributionLine,
    CapitalDistributionRun,
)


ZERO = Decimal("0.00")


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _journal_totals(rows) -> dict:
    debit = sum((row.amount for row in rows if row.drcr), ZERO)
    credit = sum((row.amount for row in rows if not row.drcr), ZERO)
    return {
        "debit": debit,
        "credit": credit,
        "variance": debit - credit,
        "balanced": debit == credit,
        "line_count": len(rows),
    }


def build_appropriation_statement(*, entity, entityfin, period_from, period_to, subentity=None) -> dict:
    runs = CapitalDistributionRun.objects.filter(
        entity=entity,
        entityfin=entityfin,
        period_to__gte=period_from,
        period_to__lte=period_to,
        isactive=True,
    )
    runs = runs.filter(subentity=subentity) if subentity else runs.filter(subentity__isnull=True)
    runs = list(
        runs.select_related("policy", "formation_profile", "posting_batch", "reversal_batch")
        .prefetch_related("lines__stakeholder__ownership")
        .order_by("period_to", "id")
    )

    ownership_ids = {
        line.stakeholder.ownership_id
        for run in runs
        for line in run.lines.all()
        if line.stakeholder.ownership_id
    }
    mappings = {
        row.ownership_id: row
        for row in CapitalDistributionAccountMapping.objects.filter(
            entity=entity,
            ownership_id__in=ownership_ids,
            isactive=True,
        ).select_related(
            "capital_account__ledger",
            "current_account__ledger",
        )
    }

    batch_ids = {
        batch_id
        for run in runs
        for batch_id in (run.posting_batch_id, run.reversal_batch_id)
        if batch_id
    }
    journal_by_batch = defaultdict(list)
    for row in JournalLine.objects.filter(posting_batch_id__in=batch_ids).select_related("ledger", "account"):
        journal_by_batch[row.posting_batch_id].append(row)

    partner_totals = defaultdict(lambda: {
        "debit": ZERO,
        "credit": ZERO,
        "effective_debit": ZERO,
        "effective_credit": ZERO,
    })
    partner_metadata = {}
    component_totals = defaultdict(lambda: {
        "debit": ZERO,
        "credit": ZERO,
        "effective_debit": ZERO,
        "effective_credit": ZERO,
    })
    statement_runs = []
    total_calculated_debit = ZERO
    total_calculated_credit = ZERO
    total_effective_debit = ZERO
    total_effective_credit = ZERO

    for run in runs:
        lines = list(
            run.lines.select_related("stakeholder__ownership")
            .order_by("stakeholder__sort_order", "component_type", "id")
        )
        original_rows = journal_by_batch.get(run.posting_batch_id, [])
        reversal_rows = journal_by_batch.get(run.reversal_batch_id, [])
        original_totals = _journal_totals(original_rows)
        reversal_totals = _journal_totals(reversal_rows)
        original_totals["available"] = bool(original_rows)
        original_totals["reconstructed_from_frozen_run"] = bool(run.posting_batch_id and not original_rows)
        reversal_totals["available"] = bool(reversal_rows)
        run_debit = sum((line.amount for line in lines if line.side == CapitalDistributionLine.Side.DEBIT), ZERO)
        run_credit = sum((line.amount for line in lines if line.side == CapitalDistributionLine.Side.CREDIT), ZERO)
        calculated_net = run_credit - run_debit
        expected_effective_net = calculated_net if run.status == CapitalDistributionRun.Status.POSTED else ZERO

        original_partner_net = ZERO
        reversal_partner_net = ZERO
        serialized_lines = []
        for line in lines:
            stakeholder_side_is_debit = line.side == CapitalDistributionLine.Side.DEBIT
            original_partner_amount = sum(
                (row.amount for row in original_rows if row.detail_id == line.id and row.drcr == stakeholder_side_is_debit),
                ZERO,
            )
            reversal_partner_amount = sum(
                (row.amount for row in reversal_rows if row.detail_id == line.id and row.drcr != stakeholder_side_is_debit),
                ZERO,
            )
            signed_original = -original_partner_amount if stakeholder_side_is_debit else original_partner_amount
            signed_reversal = reversal_partner_amount if stakeholder_side_is_debit else -reversal_partner_amount
            signed_original_for_effective = signed_original
            if run.posting_batch_id and not original_rows:
                signed_original_for_effective = -line.amount if stakeholder_side_is_debit else line.amount
            effective_amount = signed_original_for_effective + signed_reversal
            original_partner_net += signed_original
            reversal_partner_net += signed_reversal

            ownership_id = line.stakeholder.ownership_id
            partner_key = (ownership_id, line.stakeholder.target_name)
            mapping = mappings.get(ownership_id)
            destination = mapping.destination_account(line.stakeholder.destination_account_preference) if mapping else None
            partner_metadata[partner_key] = {
                "ownership": ownership_id,
                "stakeholder": line.stakeholder.target_name,
                "account": getattr(destination, "id", None),
                "account_name": getattr(destination, "accountname", None),
                "ledger": getattr(destination, "ledger_id", None),
                "ledger_name": getattr(getattr(destination, "ledger", None), "name", None),
                "destination_preference": line.stakeholder.destination_account_preference,
            }
            totals = partner_totals[partner_key]
            totals[line.side] += line.amount
            if effective_amount < 0:
                totals["effective_debit"] += abs(effective_amount)
            else:
                totals["effective_credit"] += effective_amount
            component_total = component_totals[line.component_type]
            component_total[line.side] += line.amount
            if effective_amount < 0:
                component_total["effective_debit"] += abs(effective_amount)
            else:
                component_total["effective_credit"] += effective_amount
            serialized_lines.append({
                "id": line.id,
                "ownership": ownership_id,
                "stakeholder": line.stakeholder.target_name,
                "account": getattr(destination, "id", None),
                "ledger": getattr(destination, "ledger_id", None),
                "component": line.component_type,
                "side": line.side,
                "calculated_amount": _money(line.amount),
                "posted_amount": _money(original_partner_amount),
                "reversed_amount": _money(reversal_partner_amount),
                "effective_amount": _money(effective_amount),
            })

        original_effective_basis = (
            original_partner_net
            if original_rows or not run.posting_batch_id
            else calculated_net
        )
        effective_net = original_effective_basis + reversal_partner_net
        has_expected_batches = (
            run.status not in (CapitalDistributionRun.Status.POSTED, CapitalDistributionRun.Status.REVERSED)
            or bool(run.posting_batch_id)
        ) and (run.status != CapitalDistributionRun.Status.REVERSED or bool(run.reversal_batch_id))
        journal_reconciled = (
            has_expected_batches
            and original_totals["balanced"]
            and reversal_totals["balanced"]
            and (not original_rows or original_partner_net == calculated_net)
            and (not run.reversal_batch_id or reversal_partner_net == -calculated_net)
            and effective_net == expected_effective_net
        )
        reconciliation_status = (
            "not_posted"
            if run.status not in (CapitalDistributionRun.Status.POSTED, CapitalDistributionRun.Status.REVERSED)
            else "reconciled" if journal_reconciled else "exception"
        )
        total_calculated_debit += run_debit
        total_calculated_credit += run_credit
        if effective_net < 0:
            total_effective_debit += abs(effective_net)
        else:
            total_effective_credit += effective_net
        statement_runs.append({
            "id": run.id,
            "period_from": run.period_from.isoformat(),
            "period_to": run.period_to.isoformat(),
            "status": run.status,
            "policy_version": run.policy.version_number,
            "calculated_debit": _money(run_debit),
            "calculated_credit": _money(run_credit),
            "calculated_net": _money(calculated_net),
            "original_journal": {key: _money(value) if isinstance(value, Decimal) else value for key, value in original_totals.items()},
            "reversal_journal": {key: _money(value) if isinstance(value, Decimal) else value for key, value in reversal_totals.items()},
            "effective_net": _money(effective_net),
            "expected_effective_net": _money(expected_effective_net),
            "reconciled": journal_reconciled if reconciliation_status != "not_posted" else None,
            "reconciliation_status": reconciliation_status,
            "lines": serialized_lines,
        })

    return {
        "scope": {
            "entity": entity.id,
            "entity_name": entity.entityname,
            "entityfinid": entityfin.id,
            "financial_year": entityfin.desc,
            "subentity": getattr(subentity, "id", None),
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
        },
        "summary": {
            "run_count": len(statement_runs),
            "reconciled_run_count": sum(1 for row in statement_runs if row["reconciliation_status"] == "reconciled"),
            "exception_count": sum(1 for row in statement_runs if row["reconciliation_status"] == "exception"),
            "calculated_debit": _money(total_calculated_debit),
            "calculated_credit": _money(total_calculated_credit),
            "effective_debit": _money(total_effective_debit),
            "effective_credit": _money(total_effective_credit),
        },
        "partners": [
            {
                **partner_metadata[key],
                **{name: _money(value) for name, value in totals.items()},
            }
            for key, totals in sorted(
                partner_totals.items(),
                key=lambda item: ((item[0][1] or "").lower(), item[0][0] or 0),
            )
        ],
        "components": [
            {"component": name, **{key: _money(value) for key, value in totals.items()}}
            for name, totals in sorted(component_totals.items())
        ],
        "runs": statement_runs,
    }


def build_financial_statement_disclosure(
    *,
    entity_id,
    entityfin_id,
    period_from,
    period_to,
    subentity_id=None,
) -> dict:
    """Return a report-safe appropriation disclosure without changing statement arithmetic."""
    from entity.models import EntityFinancialYear, SubEntity

    entityfin = EntityFinancialYear.objects.select_related("entity").get(
        pk=entityfin_id,
        entity_id=entity_id,
    )
    subentity = None
    if subentity_id:
        subentity = SubEntity.objects.get(pk=subentity_id, entity_id=entity_id)
    statement = build_appropriation_statement(
        entity=entityfin.entity,
        entityfin=entityfin,
        subentity=subentity,
        period_from=period_from,
        period_to=period_to,
    )
    posted_rows = JournalLine.objects.filter(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        txn_type=TxnType.CAPITAL_DISTRIBUTION,
        entry__status=EntryStatus.POSTED,
        posting_date__gte=period_from,
        posting_date__lte=period_to,
    ).select_related("account", "ledger")
    posted_rows = posted_rows.filter(subentity_id=subentity_id) if subentity_id else posted_rows
    posted_rows = list(posted_rows)

    posted_totals = _journal_totals(posted_rows)
    posted_run_ids = {row.txn_id for row in posted_rows}
    partner_metadata = {}
    active_mappings = CapitalDistributionAccountMapping.objects.filter(
        entity_id=entity_id,
        isactive=True,
    ).select_related(
        "ownership",
        "capital_account__ledger",
        "current_account__ledger",
    )
    for mapping in active_mappings:
        for preference, destination in (
            ("capital", mapping.capital_account),
            ("current", mapping.current_account),
        ):
            if destination and destination.ledger_id:
                partner_metadata[destination.ledger_id] = {
                    "ownership": mapping.ownership_id,
                    "stakeholder": mapping.ownership.name,
                    "account": destination.id,
                    "account_name": destination.accountname,
                    "ledger": destination.ledger_id,
                    "ledger_name": destination.ledger.name,
                    "destination_preference": preference,
                }
    posted_partner_totals = defaultdict(lambda: {"debit": ZERO, "credit": ZERO})
    for row in posted_rows:
        if row.ledger_id in partner_metadata:
            posted_partner_totals[row.ledger_id]["debit" if row.drcr else "credit"] += row.amount

    posted_partners = []
    for ledger_id, totals in sorted(
        posted_partner_totals.items(),
        key=lambda item: (partner_metadata[item[0]]["stakeholder"].lower(), item[0]),
    ):
        posted_partners.append({
            **{
                key: value
                for key, value in partner_metadata[ledger_id].items()
                if key not in {"debit", "credit", "effective_debit", "effective_credit"}
            },
            "debit": _money(totals["debit"]),
            "credit": _money(totals["credit"]),
            "net_equity_movement": _money(totals["credit"] - totals["debit"]),
        })

    pending_statuses = {
        CapitalDistributionRun.Status.DRAFT,
        CapitalDistributionRun.Status.CALCULATED,
        CapitalDistributionRun.Status.SUBMITTED,
        CapitalDistributionRun.Status.APPROVED,
        CapitalDistributionRun.Status.STALE,
    }
    pending_runs = [row for row in statement["runs"] if row["status"] in pending_statuses]
    pending_debit = sum((Decimal(row["calculated_debit"]) for row in pending_runs), ZERO)
    pending_credit = sum((Decimal(row["calculated_credit"]) for row in pending_runs), ZERO)
    posted_partner_debit = sum((row["debit"] for row in posted_partner_totals.values()), ZERO)
    posted_partner_credit = sum((row["credit"] for row in posted_partner_totals.values()), ZERO)
    return {
        "code": "capital_distribution",
        "label": "Profit and loss appropriation",
        "basis": "Posted journal entries only; frozen runs are retained as audit expectations",
        "operating_profit_impact": "0.00",
        "posted_accounting": {
            "run_count": len(posted_run_ids),
            "journal_line_count": posted_totals["line_count"],
            "journal_debit": _money(posted_totals["debit"]),
            "journal_credit": _money(posted_totals["credit"]),
            "journal_variance": _money(posted_totals["variance"]),
            "balanced": posted_totals["balanced"],
            "partner_debit": _money(posted_partner_debit),
            "partner_credit": _money(posted_partner_credit),
            "net_equity_movement": _money(posted_partner_credit - posted_partner_debit),
            "partners": posted_partners,
        },
        "pending_calculation": {
            "run_count": len(pending_runs),
            "calculated_debit": _money(pending_debit),
            "calculated_credit": _money(pending_credit),
            "runs": pending_runs,
            "affects_books": False,
        },
        "audit_reconciliation": {
            "reconciled_run_count": statement["summary"]["reconciled_run_count"],
            "exception_count": statement["summary"]["exception_count"],
            "runs": statement["runs"],
        },
    }
