from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction

from assets.models import FixedAsset
from catalog.models import ProductPurchaseBehavior
from posting.models import Entry, JournalLine
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions


@dataclass
class AssetPurchasePostingRepairRow:
    header_id: int
    purchase_number: str
    line_id: int
    line_no: int
    entry_id: int | None
    asset_id: int | None
    asset_code: str
    expected_ledger_id: int | None
    expected_ledger_name: str
    current_journal_ledger_id: int | None
    current_journal_ledger_name: str
    current_asset_ledger_id: int | None
    current_asset_ledger_name: str
    needs_journal_repair: bool
    needs_asset_repair: bool
    actionable: bool
    note: str


def repair_posted_asset_purchase_postings(
    *,
    entity_id: int | None = None,
    subentity_id: int | None = None,
    header_id: int | None = None,
    purchase_number: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    queryset = (
        PurchaseInvoiceLine.objects.select_related(
            "header",
            "asset_record",
            "product__default_asset_category",
            "product__default_asset_category__cwip_ledger",
            "product__default_asset_category__asset_ledger",
        )
        .filter(header__status=PurchaseInvoiceHeader.Status.POSTED)
        .filter(purchase_behavior=ProductPurchaseBehavior.ASSET)
        .order_by("header_id", "line_no", "id")
    )

    if entity_id:
        queryset = queryset.filter(header__entity_id=entity_id)
    if subentity_id:
        queryset = queryset.filter(header__subentity_id=subentity_id)
    if header_id:
        queryset = queryset.filter(header_id=header_id)
    if purchase_number:
        queryset = queryset.filter(header__purchase_number=purchase_number)

    summary: dict[str, Any] = {
        "scanned_lines": 0,
        "flagged_lines": 0,
        "journal_repairs": 0,
        "asset_repairs": 0,
        "rows": [],
    }

    for line in queryset.iterator():
        summary["scanned_lines"] += 1
        header = line.header
        category = getattr(getattr(line, "product", None), "default_asset_category", None)
        expected_ledger = None
        if category is not None:
            expected_ledger = getattr(category, "cwip_ledger", None) or getattr(category, "asset_ledger", None)

        purchase_label = str(getattr(header, "purchase_number", None) or f"{getattr(header, 'doc_code', '')}-{getattr(header, 'doc_no', '')}").strip("-")
        if expected_ledger is None:
            summary["rows"].append(
                AssetPurchasePostingRepairRow(
                    header_id=header.id,
                    purchase_number=purchase_label,
                    line_id=line.id,
                    line_no=int(getattr(line, "line_no", 0) or 0),
                    entry_id=None,
                    asset_id=getattr(line, "asset_record_id", None),
                    asset_code=str(getattr(getattr(line, "asset_record", None), "asset_code", "") or ""),
                    expected_ledger_id=None,
                    expected_ledger_name="",
                    current_journal_ledger_id=None,
                    current_journal_ledger_name="",
                    current_asset_ledger_id=getattr(getattr(line, "asset_record", None), "ledger_id", None),
                    current_asset_ledger_name=str(getattr(getattr(getattr(line, "asset_record", None), "ledger", None), "name", "") or ""),
                    needs_journal_repair=False,
                    needs_asset_repair=False,
                    actionable=False,
                    note="Missing default asset category ledger mapping.",
                )
            )
            summary["flagged_lines"] += 1
            continue

        txn_type = PurchaseInvoiceActions._txn_type_for_header(header)
        entry = (
            Entry.objects.filter(
                entity_id=header.entity_id,
                entityfin_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                txn_type=txn_type,
                txn_id=header.id,
            )
            .only("id")
            .first()
        )

        journal_lines = list(
            JournalLine.objects.select_related("ledger")
            .filter(entry=entry, detail_id=line.id)
            .order_by("id")
        ) if entry else []

        note = ""
        journal_line = journal_lines[0] if len(journal_lines) == 1 else None
        if entry is None:
            note = "Posted entry not found."
        elif len(journal_lines) != 1:
            note = f"Expected exactly one base journal line for detail_id={line.id}, found {len(journal_lines)}."

        needs_journal_repair = bool(
            journal_line
            and (
                journal_line.ledger_id != expected_ledger.id
                or journal_line.account_id is not None
                or journal_line.accounthead_id != expected_ledger.accounthead_id
            )
        )

        asset = getattr(line, "asset_record", None)
        needs_asset_repair = bool(
            asset
            and asset.status in {FixedAsset.AssetStatus.DRAFT, FixedAsset.AssetStatus.CAPITAL_WIP}
            and asset.ledger_id != expected_ledger.id
        )

        actionable = bool(expected_ledger and journal_line and (needs_journal_repair or needs_asset_repair))
        if note or needs_journal_repair or needs_asset_repair:
            summary["flagged_lines"] += 1

        row = AssetPurchasePostingRepairRow(
            header_id=header.id,
            purchase_number=purchase_label,
            line_id=line.id,
            line_no=int(getattr(line, "line_no", 0) or 0),
            entry_id=getattr(entry, "id", None),
            asset_id=getattr(asset, "id", None),
            asset_code=str(getattr(asset, "asset_code", "") or ""),
            expected_ledger_id=expected_ledger.id,
            expected_ledger_name=str(getattr(expected_ledger, "name", "") or ""),
            current_journal_ledger_id=getattr(journal_line, "ledger_id", None),
            current_journal_ledger_name=str(getattr(getattr(journal_line, "ledger", None), "name", "") or ""),
            current_asset_ledger_id=getattr(asset, "ledger_id", None),
            current_asset_ledger_name=str(getattr(getattr(asset, "ledger", None), "name", "") or ""),
            needs_journal_repair=needs_journal_repair,
            needs_asset_repair=needs_asset_repair,
            actionable=actionable,
            note=note,
        )
        summary["rows"].append(row)

        if not apply or not actionable:
            continue

        with transaction.atomic():
            if needs_journal_repair and journal_line is not None:
                journal_line.account = None
                journal_line.accounthead_id = expected_ledger.accounthead_id
                journal_line.ledger_id = expected_ledger.id
                journal_line.save(update_fields=["account", "accounthead", "ledger"])
                summary["journal_repairs"] += 1

            if needs_asset_repair and asset is not None:
                asset.ledger_id = expected_ledger.id
                asset.save(update_fields=["ledger", "updated_at"])
                summary["asset_repairs"] += 1

    return summary
