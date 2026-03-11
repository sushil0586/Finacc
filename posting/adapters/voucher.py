from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional

from django.db import transaction

from posting.models import Entry, EntryStatus, TxnType
from posting.services.posting_service import JLInput, PostingService
from vouchers.models.voucher_core import VoucherHeader

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


@dataclass(frozen=True)
class VoucherPostingConfig:
    totals_tolerance: Decimal = Decimal("0.05")


class VoucherPostingAdapter:
    @staticmethod
    def _txn_type_for_header(header: Any) -> str:
        voucher_type = str(getattr(header, "voucher_type", VoucherHeader.VoucherType.JOURNAL))
        if voucher_type == VoucherHeader.VoucherType.CASH:
            return TxnType.JOURNAL_CASH
        if voucher_type == VoucherHeader.VoucherType.BANK:
            return TxnType.JOURNAL_BANK
        return TxnType.JOURNAL

    @staticmethod
    def _build_journal_lines(*, lines: Iterable[Any], reverse: bool = False) -> list[JLInput]:
        jl_inputs: list[JLInput] = []
        for row in list(lines or []):
            dr_amount = q2(getattr(row, "dr_amount", ZERO2))
            cr_amount = q2(getattr(row, "cr_amount", ZERO2))
            account_id = int(getattr(row, "account_id", 0) or 0)
            ledger_id = int(getattr(row, "ledger_id", 0) or getattr(getattr(row, "account", None), "ledger_id", 0) or 0)
            if account_id <= 0:
                raise ValueError(f"Voucher line {getattr(row, 'id', '')}: account is required.")
            if dr_amount > ZERO2:
                jl_inputs.append(JLInput(account_id=account_id, ledger_id=ledger_id or None, drcr=not reverse, amount=dr_amount, description=str(getattr(row, "narration", "") or ""), detail_id=getattr(row, "id", None)))
            if cr_amount > ZERO2:
                jl_inputs.append(JLInput(account_id=account_id, ledger_id=ledger_id or None, drcr=reverse, amount=cr_amount, description=str(getattr(row, "narration", "") or ""), detail_id=getattr(row, "id", None)))
        return jl_inputs

    @staticmethod
    @transaction.atomic
    def post_voucher(*, header: Any, lines: Iterable[Any], user_id: Optional[int], config: Optional[VoucherPostingConfig] = None) -> Entry:
        _ = config or VoucherPostingConfig()
        jl_inputs = VoucherPostingAdapter._build_journal_lines(lines=lines, reverse=False)
        svc = PostingService(
            entity_id=int(header.entity_id),
            entityfin_id=int(header.entityfinid_id) if getattr(header, "entityfinid_id", None) else None,
            subentity_id=int(header.subentity_id) if getattr(header, "subentity_id", None) else None,
            user_id=int(user_id) if user_id else None,
        )
        txn_type = VoucherPostingAdapter._txn_type_for_header(header)
        return svc.post(
            txn_type=txn_type,
            txn_id=int(header.id),
            voucher_no=str(getattr(header, "voucher_code", "") or ""),
            voucher_date=getattr(header, "voucher_date", None),
            posting_date=getattr(header, "voucher_date", None),
            narration=f"Voucher {getattr(header, 'voucher_code', '')}",
            jl_inputs=jl_inputs,
            im_inputs=[],
            use_advisory_lock=True,
            mark_posted=True,
        )

    @staticmethod
    @transaction.atomic
    def unpost_voucher(*, header: Any, lines: Iterable[Any], user_id: Optional[int]) -> Entry:
        jl_inputs = VoucherPostingAdapter._build_journal_lines(lines=lines, reverse=True)
        svc = PostingService(
            entity_id=int(header.entity_id),
            entityfin_id=int(header.entityfinid_id) if getattr(header, "entityfinid_id", None) else None,
            subentity_id=int(header.subentity_id) if getattr(header, "subentity_id", None) else None,
            user_id=int(user_id) if user_id else None,
        )
        txn_type = VoucherPostingAdapter._txn_type_for_header(header)
        entry = svc.post(
            txn_type=txn_type,
            txn_id=int(header.id),
            voucher_no=str(getattr(header, "voucher_code", "") or ""),
            voucher_date=getattr(header, "voucher_date", None),
            posting_date=getattr(header, "voucher_date", None),
            narration=f"Voucher Reversal {getattr(header, 'voucher_code', '')}",
            jl_inputs=jl_inputs,
            im_inputs=[],
            use_advisory_lock=True,
            mark_posted=True,
        )
        Entry.objects.filter(pk=entry.pk).update(status=EntryStatus.REVERSED, narration=f"Reversed voucher {getattr(header, 'voucher_code', '')}")
        entry.refresh_from_db()
        return entry
