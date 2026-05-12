from __future__ import annotations

from django.db import transaction

from posting.models import Entry, InventoryMove, JournalLine, PostingBatch


@transaction.atomic
def purge_posting_locator(
    *,
    entity_id: int,
    entityfin_id: int | None,
    subentity_id: int | None,
    txn_type: str,
    txn_id: int,
) -> dict[str, int | str | None]:
    locator = {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "txn_type": txn_type,
        "txn_id": txn_id,
    }

    entry_qs = Entry.objects.select_for_update().filter(**locator)
    batch_qs = PostingBatch.objects.select_for_update().filter(**locator)

    entry = entry_qs.order_by("-id").first()
    batch = batch_qs.order_by("-id").first()

    journal_lines_deleted = JournalLine.objects.filter(**locator).count()
    inventory_moves_deleted = InventoryMove.objects.filter(**locator).count()
    entries_deleted = entry_qs.count()
    batches_deleted = batch_qs.count()

    # Delete the entry header first so journal/inventory rows cascade cleanly.
    if entries_deleted:
        entry_qs.delete()
    if batches_deleted:
        batch_qs.delete()

    return {
        "entry_id": getattr(entry, "id", None),
        "posting_batch_id": str(getattr(batch, "id", None)) if getattr(batch, "id", None) is not None else None,
        "voucher_no": getattr(entry, "voucher_no", None) or getattr(batch, "voucher_no", None),
        "journal_lines_deleted": journal_lines_deleted,
        "inventory_moves_deleted": inventory_moves_deleted,
        "entries_deleted": entries_deleted,
        "batches_deleted": batches_deleted,
    }
