from __future__ import annotations
from typing import Optional
from posting.models import Entry, PostingBatch


def get_active_batch(entity_id: int, entityfin_id: Optional[int], subentity_id: Optional[int], txn_type: str, txn_id: int) -> Optional[PostingBatch]:
    return (
        PostingBatch.objects
        .filter(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
            is_active=True,
        )
        .first()
    )


def get_entry(entity_id: int, entityfin_id: Optional[int], subentity_id: Optional[int], txn_type: str, txn_id: int) -> Optional[Entry]:
    return (
        Entry.objects
        .filter(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            txn_type=txn_type,
            txn_id=txn_id,
        )
        .first()
    )
