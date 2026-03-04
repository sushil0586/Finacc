from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional

from django.db import transaction

from posting.models import TxnType, EntryStatus, Entry
from posting.services.posting_service import JLInput, PostingService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


@dataclass(frozen=True)
class PaymentVoucherPostingConfig:
    totals_tolerance: Decimal = Decimal("0.05")


class PaymentVoucherPostingAdapter:
    @staticmethod
    def _build_journal_lines(*, header: Any, adjustments: Iterable[Any], reverse: bool = False) -> list[JLInput]:
        cash_paid = q2(getattr(header, "cash_paid_amount", ZERO2))
        paid_from_id = int(getattr(header, "paid_from_id", 0) or 0)
        paid_to_id = int(getattr(header, "paid_to_id", 0) or 0)

        if paid_from_id <= 0:
            raise ValueError("paid_from is required for payment posting.")
        if paid_to_id <= 0:
            raise ValueError("paid_to is required for payment posting.")
        if cash_paid < ZERO2:
            raise ValueError("cash_paid_amount cannot be negative.")

        plus_total = ZERO2
        minus_total = ZERO2
        rows = []

        for adj in list(adjustments or []):
            amt = q2(getattr(adj, "amount", ZERO2))
            if amt <= ZERO2:
                continue
            ledger_id = int(getattr(adj, "ledger_account_id", 0) or 0)
            if ledger_id <= 0:
                raise ValueError(f"Adjustment {getattr(adj, 'id', '')}: ledger_account is required.")
            effect = str(getattr(adj, "settlement_effect", "PLUS")).upper().strip()

            if effect == "PLUS":
                plus_total = q2(plus_total + amt)
                rows.append(("CR", ledger_id, amt, f"Payment adjustment PLUS ({getattr(adj, 'adj_type', 'OTHER')})"))
            elif effect == "MINUS":
                minus_total = q2(minus_total + amt)
                rows.append(("DR", ledger_id, amt, f"Payment adjustment MINUS ({getattr(adj, 'adj_type', 'OTHER')})"))
            else:
                raise ValueError(f"Unsupported settlement_effect '{effect}'.")

        vendor_settlement = q2(cash_paid + plus_total - minus_total)
        if vendor_settlement <= ZERO2:
            raise ValueError("Computed vendor settlement amount must be > 0.")

        jl_inputs: list[JLInput] = []
        # Dr Vendor (paid_to)
        jl_inputs.append(JLInput(
            account_id=paid_to_id,
            drcr=True,
            amount=vendor_settlement,
            description=f"Payment voucher {getattr(header, 'voucher_code', '')} vendor settlement",
        ))
        # Cr Cash/Bank (paid_from)
        if cash_paid > ZERO2:
            jl_inputs.append(JLInput(
                account_id=paid_from_id,
                drcr=False,
                amount=cash_paid,
                description=f"Payment voucher {getattr(header, 'voucher_code', '')} cash/bank",
            ))

        for side, ledger_id, amt, desc in rows:
            jl_inputs.append(JLInput(
                account_id=ledger_id,
                drcr=(side == "DR"),
                amount=amt,
                description=f"{getattr(header, 'voucher_code', '')} {desc}",
            ))

        if reverse:
            flipped = []
            for x in jl_inputs:
                flipped.append(JLInput(
                    account_id=x.account_id,
                    accounthead_id=x.accounthead_id,
                    drcr=not bool(x.drcr),
                    amount=q2(x.amount),
                    description=f"Reversal: {x.description}",
                    detail_id=x.detail_id,
                ))
            return flipped
        return jl_inputs

    @staticmethod
    @transaction.atomic
    def post_payment_voucher(*, header: Any, adjustments: Iterable[Any], user_id: Optional[int], config: Optional[PaymentVoucherPostingConfig] = None) -> Entry:
        _ = config or PaymentVoucherPostingConfig()
        jl_inputs = PaymentVoucherPostingAdapter._build_journal_lines(header=header, adjustments=adjustments, reverse=False)
        svc = PostingService(
            entity_id=int(header.entity_id),
            entityfin_id=int(header.entityfinid_id) if getattr(header, "entityfinid_id", None) else None,
            subentity_id=int(header.subentity_id) if getattr(header, "subentity_id", None) else None,
            user_id=int(user_id) if user_id else None,
        )
        return svc.post(
            txn_type=TxnType.PAYMENT,
            txn_id=int(header.id),
            voucher_no=str(getattr(header, "voucher_code", "") or ""),
            voucher_date=getattr(header, "voucher_date", None),
            posting_date=getattr(header, "voucher_date", None),
            narration=f"Payment Voucher {getattr(header, 'voucher_code', '')}",
            jl_inputs=jl_inputs,
            im_inputs=[],
            use_advisory_lock=True,
            mark_posted=True,
        )

    @staticmethod
    @transaction.atomic
    def unpost_payment_voucher(*, header: Any, adjustments: Iterable[Any], user_id: Optional[int]) -> Entry:
        jl_inputs = PaymentVoucherPostingAdapter._build_journal_lines(header=header, adjustments=adjustments, reverse=True)
        svc = PostingService(
            entity_id=int(header.entity_id),
            entityfin_id=int(header.entityfinid_id) if getattr(header, "entityfinid_id", None) else None,
            subentity_id=int(header.subentity_id) if getattr(header, "subentity_id", None) else None,
            user_id=int(user_id) if user_id else None,
        )
        entry = svc.post(
            txn_type=TxnType.PAYMENT,
            txn_id=int(header.id),
            voucher_no=str(getattr(header, "voucher_code", "") or ""),
            voucher_date=getattr(header, "voucher_date", None),
            posting_date=getattr(header, "voucher_date", None),
            narration=f"Payment Voucher Reversal {getattr(header, 'voucher_code', '')}",
            jl_inputs=jl_inputs,
            im_inputs=[],
            use_advisory_lock=True,
            mark_posted=True,
        )
        Entry.objects.filter(pk=entry.pk).update(status=EntryStatus.REVERSED, narration=f"Reversed payment voucher {getattr(header, 'voucher_code', '')}")
        entry.refresh_from_db()
        return entry
