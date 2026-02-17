# posting/services/posting_service.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Iterable

from django.db import transaction, connection, models
from django.db.models import Sum, Q
from django.utils import timezone

from posting.models import (
    PostingBatch, Entry, JournalLine, InventoryMove,
    TxnType, EntryStatus
)

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


def q2(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


def q4(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.0000")


@dataclass
class JLInput:
    account_id: Optional[int] = None
    accounthead_id: Optional[int] = None
    drcr: bool = True
    amount: Decimal = ZERO2
    description: str = ""
    detail_id: Optional[int] = None


@dataclass
class IMInput:
    product_id: int
    qty: Decimal
    base_qty: Optional[Decimal] = None
    uom_id: Optional[int] = None
    base_uom_id: Optional[int] = None
    uom_factor: Decimal = Decimal("1")
    unit_cost: Decimal = Decimal("0.0000")
    move_type: str = "IN"
    cost_source: str = InventoryMove.CostSource.PURCHASE
    cost_meta: Optional[dict] = None
    detail_id: Optional[int] = None
    location_id: Optional[int] = None


class PostingService:
    """
    Cross-module posting engine.
    Modules compute business values; PostingService persists ledger rows safely.
    """

    def __init__(self, *, entity_id: int, entityfin_id: Optional[int], subentity_id: Optional[int], user_id: Optional[int] = None):
        self.entity_id = entity_id
        self.entityfin_id = entityfin_id
        self.subentity_id = subentity_id
        self.user_id = user_id

    # ---------- advisory lock (Postgres optional) ----------
    def _pg_advisory_lock(self, key: int) -> None:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [key])

    def _lock_for_txn(self, txn_type: str, txn_id: int) -> None:
        # stable int key: entity_id + txn_type hash + txn_id
        # safe enough for advisory locking
        h = abs(hash((self.entity_id, txn_type, txn_id))) % (2**31 - 1)
        self._pg_advisory_lock(h)

    # ---------- core ----------
    def _next_revision(self, txn_type: str, txn_id: int) -> int:
        prev = (
            PostingBatch.objects
            .filter(
                entity_id=self.entity_id,
                entityfin_id=self.entityfin_id,
                subentity_id=self.subentity_id,
                txn_type=txn_type,
                txn_id=txn_id,
            )
            .order_by("-revision")
            .values_list("revision", flat=True)
            .first()
        )
        return int(prev or 0) + 1

    def _deactivate_previous_batch(self, txn_type: str, txn_id: int) -> None:
        PostingBatch.objects.filter(
            entity_id=self.entity_id,
            entityfin_id=self.entityfin_id,
            subentity_id=self.subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
            is_active=True,
        ).update(is_active=False)

    def _delete_existing_rows(self, txn_type: str, txn_id: int) -> None:
        # Always delete by strong locator. Never delete by voucherno for new system.
        JournalLine.objects.filter(
            entity_id=self.entity_id,
            entityfin_id=self.entityfin_id,
            subentity_id=self.subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
        ).delete()

        InventoryMove.objects.filter(
            entity_id=self.entity_id,
            entityfin_id=self.entityfin_id,
            subentity_id=self.subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
        ).delete()

    def _assert_balanced(self, txn_type: str, txn_id: int) -> None:
        sums = (
            JournalLine.objects
            .filter(
                entity_id=self.entity_id,
                entityfin_id=self.entityfin_id,
                subentity_id=self.subentity_id,
                txn_type=txn_type,
                txn_id=txn_id,
            )
            .aggregate(
                dr=Sum("amount", filter=Q(drcr=True)),
                cr=Sum("amount", filter=Q(drcr=False)),
            )
        )
        dr = sums["dr"] or ZERO2
        cr = sums["cr"] or ZERO2
        if q2(dr) != q2(cr):
            raise ValueError(f"Unbalanced entry: Dr {dr} != Cr {cr} for {txn_type}#{txn_id}")

    @transaction.atomic
    def post(
        self,
        *,
        txn_type: str,
        txn_id: int,
        voucher_no: Optional[str],
        voucher_date,
        posting_date,
        narration: str = "",
        jl_inputs: Iterable[JLInput],
        im_inputs: Iterable[IMInput] = (),
        use_advisory_lock: bool = True,
        mark_posted: bool = True,
    ) -> Entry:
        if use_advisory_lock:
            # Postgres only; comment out if you need cross-db
            self._lock_for_txn(txn_type, txn_id)

        # 1) New batch revision and deactivate old
        revision = self._next_revision(txn_type, txn_id)
        self._deactivate_previous_batch(txn_type, txn_id)

        batch = PostingBatch.objects.create(
            entity_id=self.entity_id,
            entityfin_id=self.entityfin_id,
            subentity_id=self.subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            revision=revision,
            is_active=True,
            created_by_id=self.user_id,
        )

        # 2) delete existing ledger rows (strong locator delete)
        self._delete_existing_rows(txn_type, txn_id)

        # 3) create / update Entry header
        entry, _ = Entry.objects.update_or_create(
            entity_id=self.entity_id,
            entityfin_id=self.entityfin_id,
            subentity_id=self.subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
            defaults=dict(
                voucher_no=voucher_no,
                voucher_date=voucher_date,
                posting_date=posting_date,
                status=EntryStatus.POSTED if mark_posted else EntryStatus.DRAFT,
                posted_at=timezone.now() if mark_posted else None,
                posted_by_id=self.user_id if mark_posted else None,
                posting_batch=batch,
                narration=narration,
            ),
        )

        now_dt = timezone.now()

        # 4) Build JournalLine rows
        jl_rows: List[JournalLine] = []
        for x in jl_inputs:
            amt = q2(x.amount)
            if amt <= ZERO2:
                continue

            # XOR check at service layer (DB constraint also exists)
            if bool(x.account_id) == bool(x.accounthead_id):
                raise ValueError("JournalLine requires exactly one of account_id or accounthead_id")

            jl_rows.append(JournalLine(
                entry=entry,
                posting_batch=batch,
                entity_id=self.entity_id,
                entityfin_id=self.entityfin_id,
                subentity_id=self.subentity_id,
                txn_type=txn_type,
                txn_id=txn_id,
                detail_id=x.detail_id,
                voucher_no=voucher_no,
                account_id=x.account_id,
                accounthead_id=x.accounthead_id,
                drcr=bool(x.drcr),
                amount=amt,
                description=x.description or narration,
                posting_date=posting_date,
                posted_at=now_dt if mark_posted else None,
                created_by_id=self.user_id,
            ))

        # In-memory balance guard
        dr_mem = q2(sum(r.amount for r in jl_rows if r.drcr))
        cr_mem = q2(sum(r.amount for r in jl_rows if not r.drcr))
        if dr_mem != cr_mem:
            # Give helpful dump
            dump = [(("DR" if r.drcr else "CR"), r.amount, r.account_id, r.accounthead_id, r.detail_id, r.description) for r in jl_rows[:40]]
            raise ValueError(f"Pre-save imbalance: Dr {dr_mem} != Cr {cr_mem}. sample={dump}")

        JournalLine.objects.bulk_create(jl_rows, batch_size=2000)

        # 5) Build InventoryMove rows
        im_rows: List[InventoryMove] = []
        for m in im_inputs:
            qty = q4(m.qty)
            if qty == Decimal("0.0000"):
                continue

            uom_factor = Decimal(m.uom_factor or 1)
            base_qty = q4(m.base_qty) if m.base_qty is not None else q4(qty * uom_factor)

            unit_cost = q4(m.unit_cost)
            ext_cost = q2(abs(base_qty) * unit_cost)

            im_rows.append(InventoryMove(
                entry=entry,
                posting_batch=batch,
                entity_id=self.entity_id,
                entityfin_id=self.entityfin_id,
                subentity_id=self.subentity_id,
                txn_type=txn_type,
                txn_id=txn_id,
                detail_id=m.detail_id,
                voucher_no=voucher_no,

                product_id=m.product_id,
                location_id=m.location_id,
                uom_id=m.uom_id,
                base_uom_id=m.base_uom_id,

                qty=qty,
                uom_factor=uom_factor,
                base_qty=base_qty,

                unit_cost=unit_cost,
                ext_cost=ext_cost,

                cost_source=m.cost_source,
                cost_meta=m.cost_meta,

                move_type=m.move_type,
                posting_date=posting_date,
                posted_at=now_dt if mark_posted else None,
                created_by_id=self.user_id,
            ))

        if im_rows:
            InventoryMove.objects.bulk_create(im_rows, batch_size=2000)

        # 6) DB balance assertion
        self._assert_balanced(txn_type, txn_id)

        return entry
