from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .models import TreasuryPaymentInstrument

ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    return Decimal(str(value or ZERO))


def _statement_amount(line) -> Decimal:
    credit = _money(getattr(line, "credit_amount", ZERO))
    return credit if credit > ZERO else _money(getattr(line, "debit_amount", ZERO))


def _normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _line_descriptor(line) -> str:
    raw_data = getattr(line, "raw_data", {}) or {}
    raw_parts = " ".join(str(value or "") for value in raw_data.values()) if isinstance(raw_data, dict) else ""
    return _normalize(
        " ".join(
            [
                getattr(line, "reference_no", "") or "",
                getattr(line, "cheque_no", "") or "",
                getattr(line, "narration", "") or "",
                raw_parts,
            ]
        )
    )


def _instrument_tokens(instrument: TreasuryPaymentInstrument) -> list[str]:
    tokens = [
        instrument.reference_no,
        instrument.instrument_no,
        getattr(instrument.cheque_leaf, "leaf_no", "") if instrument.cheque_leaf_id else "",
    ]
    return [token for token in (_normalize(value) for value in tokens) if token]


def _matches_statement_line(instrument: TreasuryPaymentInstrument, line) -> bool:
    descriptor = _line_descriptor(line)
    if not descriptor:
        return False
    return any(token in descriptor for token in _instrument_tokens(instrument))


def link_treasury_instruments_for_match(match) -> list[TreasuryPaymentInstrument]:
    if match.status not in {"confirmed", "partially_matched"}:
        return []
    run = match.run
    account_ids = set((run.metadata or {}).get("resolved_account_ids") or [])
    if not account_ids:
        try:
            from bank_reco.services.matching import resolve_bank_book_binding

            binding = resolve_bank_book_binding(entity=run.entity, bank_account=run.bank_account, metadata=run.metadata)
            account_ids = set(binding.account_ids)
        except Exception:
            account_ids = set()

    linked: list[TreasuryPaymentInstrument] = []
    for rel in match.bank_lines.select_related("statement_line"):
        line = rel.statement_line
        qs = (
            TreasuryPaymentInstrument.objects.select_related("batch", "cheque_leaf")
            .filter(
                batch__entity_id=run.entity_id,
                status=TreasuryPaymentInstrument.Status.CLEARED,
                amount=_statement_amount(line),
                reconciliation_match__isnull=True,
            )
            .filter(Q(reference_no__gt="") | Q(instrument_no__gt="") | Q(cheque_leaf__isnull=False))
        )
        if run.entityfin_id:
            qs = qs.filter(batch__entityfinid_id=run.entityfin_id)
        if run.subentity_id:
            qs = qs.filter(Q(batch__subentity_id=run.subentity_id) | Q(batch__subentity_id__isnull=True))
        if account_ids:
            qs = qs.filter(Q(source_account_id__in=account_ids) | Q(source_account__isnull=True))

        candidates = [instrument for instrument in qs[:20] if _matches_statement_line(instrument, line)]
        if len(candidates) != 1:
            continue
        instrument = candidates[0]
        metadata = dict(instrument.metadata_json or {})
        metadata["bank_reconciliation"] = {
            "match_id": match.id,
            "match_code": match.match_code,
            "run_id": run.id,
            "run_code": run.run_code,
            "statement_line_id": line.id,
            "statement_reference": getattr(line, "reference_no", "") or getattr(line, "cheque_no", ""),
            "linked_at": timezone.now().isoformat(),
        }
        instrument.reconciliation_match = match
        instrument.reconciled_bank_line = line
        instrument.reconciled_at = timezone.now()
        instrument.metadata_json = metadata
        instrument.save(
            update_fields=[
                "reconciliation_match",
                "reconciled_bank_line",
                "reconciled_at",
                "metadata_json",
                "updated_at",
            ]
        )
        linked.append(instrument)
    return linked


def clear_treasury_instrument_links_for_match(match) -> int:
    instruments = TreasuryPaymentInstrument.objects.filter(reconciliation_match=match)
    cleared = 0
    for instrument in instruments:
        metadata = dict(instrument.metadata_json or {})
        if isinstance(metadata.get("bank_reconciliation"), dict):
            metadata["bank_reconciliation"]["cleared_at"] = timezone.now().isoformat()
            metadata["bank_reconciliation"]["cleared_reason"] = "bank_reconciliation_match_cancelled"
        instrument.reconciliation_match = None
        instrument.reconciled_bank_line = None
        instrument.reconciled_at = None
        instrument.metadata_json = metadata
        instrument.save(
            update_fields=[
                "reconciliation_match",
                "reconciled_bank_line",
                "reconciled_at",
                "metadata_json",
                "updated_at",
            ]
        )
        cleared += 1
    return cleared
