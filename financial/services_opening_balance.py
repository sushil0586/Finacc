from __future__ import annotations

from decimal import Decimal

from financial.helper_posting import validate_opening_balance_edit
from posting.adapters.account_opening import AccountOpeningPostingAdapter
from posting.models import Entry, JournalLine, PostingBatch, TxnType
from posting.services.posting_service import PostingService, q2

ZERO = Decimal("0.00")
ACCOUNT_OPENING_TXN_ID_BASE = 1_000_000_000


def account_opening_txn_id(account_id: int) -> int:
    return ACCOUNT_OPENING_TXN_ID_BASE + int(account_id)


def opening_pair_for_account(acc) -> tuple[Decimal, Decimal]:
    ledger = getattr(acc, "ledger", None)
    opening_dr = q2(getattr(ledger, "openingbdr", None) or ZERO)
    opening_cr = q2(getattr(ledger, "openingbcr", None) or ZERO)
    return opening_dr, opening_cr


def _opening_value_or_zero(value) -> Decimal:
    return q2(value or ZERO)


def _delete_opening_locator(*, entity_id: int, entityfin_id: int, txn_id: int) -> None:
    locator = {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": None,
        "txn_type": TxnType.OPENING_BALANCE,
        "txn_id": txn_id,
    }
    JournalLine.objects.filter(**locator).delete()
    Entry.objects.filter(**locator).delete()
    PostingBatch.objects.filter(**locator).delete()


def clear_account_opening_posting(acc, *, opening_date=None) -> None:
    adapter = AccountOpeningPostingAdapter(entity_id=acc.entity_id)
    financial_year = adapter.resolve_financial_year(acc, opening_date=opening_date)
    _delete_opening_locator(
        entity_id=acc.entity_id,
        entityfin_id=int(financial_year.id),
        txn_id=account_opening_txn_id(acc.id),
    )


def sync_account_opening_posting(
    acc,
    *,
    old_opening_dr=None,
    old_opening_cr=None,
    opening_date=None,
    actor=None,
):
    new_opening_dr, new_opening_cr = opening_pair_for_account(acc)
    old_dr = _opening_value_or_zero(old_opening_dr)
    old_cr = _opening_value_or_zero(old_opening_cr)

    validate_opening_balance_edit(
        acc,
        old_opening_dr=old_dr,
        old_opening_cr=old_cr,
        new_opening_dr=new_opening_dr,
        new_opening_cr=new_opening_cr,
    )

    adapter = AccountOpeningPostingAdapter(entity_id=acc.entity_id)
    payload = adapter.build_post_payload(acc, opening_date=opening_date)
    if payload is None:
        if old_dr > ZERO or old_cr > ZERO:
            _delete_opening_locator(
                entity_id=acc.entity_id,
                entityfin_id=int(adapter.resolve_financial_year(acc, opening_date=opening_date).id),
                txn_id=account_opening_txn_id(acc.id),
            )
        return None

    posting_service = PostingService(
        entity_id=acc.entity_id,
        entityfin_id=payload.entityfin_id,
        subentity_id=None,
        user_id=getattr(actor, "id", None),
    )
    return posting_service.post(
        txn_type=TxnType.OPENING_BALANCE,
        txn_id=account_opening_txn_id(acc.id),
        voucher_no=payload.voucher_no,
        voucher_date=payload.voucher_date,
        posting_date=payload.posting_date,
        narration=payload.narration,
        jl_inputs=payload.jl_inputs,
        use_advisory_lock=True,
        mark_posted=True,
    )
