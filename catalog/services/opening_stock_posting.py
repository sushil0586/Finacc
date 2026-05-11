from __future__ import annotations

from decimal import Decimal

from entity.models import EntityFinancialYear
from posting.common.journal_descriptions import opening_stock_prefix
from posting.models import Entry, InventoryMove, JournalLine, PostingBatch, TxnType
from posting.common.static_accounts import StaticAccountCodes
from posting.services.posting_service import IMInput, JLInput, PostingService, q2, q4
from posting.services.static_accounts import StaticAccountService


def catalog_opening_stock_txn_id(row_id: int) -> int:
    return -int(row_id)


def clear_catalog_opening_stock_posting(opening_row) -> None:
    txn_id = catalog_opening_stock_txn_id(opening_row.id)
    locator = {
        "entity_id": opening_row.entity_id,
        "txn_type": TxnType.OPENING_BALANCE,
        "txn_id": txn_id,
    }
    JournalLine.objects.filter(**locator).delete()
    InventoryMove.objects.filter(**locator).delete()
    Entry.objects.filter(**locator).delete()
    PostingBatch.objects.filter(**locator).delete()


def _resolve_opening_stock_financial_year(opening_row) -> EntityFinancialYear:
    posting_date = getattr(opening_row, "as_of_date", None)
    fy = (
        EntityFinancialYear.objects
        .filter(
            entity_id=opening_row.entity_id,
            finstartyear__date__lte=posting_date,
            finendyear__date__gte=posting_date,
        )
        .only("id", "desc", "year_code")
        .order_by("-finstartyear", "-id")
        .first()
    )
    if fy is None:
        raise ValueError(
            f"No financial year covers {posting_date} for entity {opening_row.entity_id}. "
            "Please create or activate the correct financial year before posting opening stock."
        )
    return fy


def validate_catalog_opening_stock_prerequisites(*, entity_id: int, as_of_date) -> None:
    if not as_of_date:
        return

    fy_exists = EntityFinancialYear.objects.filter(
        entity_id=entity_id,
        finstartyear__date__lte=as_of_date,
        finendyear__date__gte=as_of_date,
    ).exists()
    if not fy_exists:
        raise ValueError(
            f"No financial year covers {as_of_date} for this entity. "
            "Create or activate the correct financial year before saving opening stock."
        )

    missing_codes: list[str] = []
    for code in (
        StaticAccountCodes.OPENING_INVENTORY_CARRY_FORWARD,
        StaticAccountCodes.OPENING_EQUITY_TRANSFER,
    ):
        if not StaticAccountService.get_account_id(entity_id, code, required=False):
            missing_codes.append(code)
    if missing_codes:
        joined = ", ".join(missing_codes)
        raise ValueError(
            f"Opening stock posting requires static account mapping for: {joined}."
        )


def sync_catalog_opening_stock_posting(opening_row) -> Entry | None:
    if not getattr(opening_row, "id", None) or not getattr(opening_row, "product_id", None):
        return None

    qty = q4(getattr(opening_row, "openingqty", None) or 0)
    if qty <= Decimal("0.0000"):
        clear_catalog_opening_stock_posting(opening_row)
        return None

    product = opening_row.product
    if getattr(product, "is_service", False):
        clear_catalog_opening_stock_posting(opening_row)
        return None

    unit_cost = q4(getattr(opening_row, "openingrate", None) or 0)
    opening_value = q2(getattr(opening_row, "openingvalue", None) or (qty * unit_cost))
    location_id = getattr(opening_row, "godown_id", None)
    branch_name = getattr(getattr(opening_row, "branch", None), "subentityname", "") or ""
    location_name = getattr(getattr(opening_row, "godown", None), "name", "") or ""
    scope_label = " / ".join(part for part in (branch_name, location_name) if part)
    validate_catalog_opening_stock_prerequisites(
        entity_id=opening_row.entity_id,
        as_of_date=getattr(opening_row, "as_of_date", None),
    )
    financial_year = _resolve_opening_stock_financial_year(opening_row)

    inventory_account_id = StaticAccountService.get_account_id(
        opening_row.entity_id,
        StaticAccountCodes.OPENING_INVENTORY_CARRY_FORWARD,
        required=True,
    )
    inventory_ledger_id = StaticAccountService.get_ledger_id(
        opening_row.entity_id,
        StaticAccountCodes.OPENING_INVENTORY_CARRY_FORWARD,
        required=False,
    )
    equity_account_id = StaticAccountService.get_account_id(
        opening_row.entity_id,
        StaticAccountCodes.OPENING_EQUITY_TRANSFER,
        required=True,
    )
    equity_ledger_id = StaticAccountService.get_ledger_id(
        opening_row.entity_id,
        StaticAccountCodes.OPENING_EQUITY_TRANSFER,
        required=False,
    )

    # Opening rows are regenerated from master data edits, so clear by strong txn locator
    # before reposting. This prevents stale null-FY rows from surviving older versions.
    clear_catalog_opening_stock_posting(opening_row)

    service = PostingService(
        entity_id=opening_row.entity_id,
        entityfin_id=financial_year.id,
        subentity_id=getattr(opening_row, "branch_id", None),
        user_id=None,
    )
    prefix = opening_stock_prefix(
        product=product,
        branch_name=branch_name,
        location_name=location_name,
        voucher_no=f"CAT-OPEN-{opening_row.product_id}-{opening_row.id}",
    )
    return service.post(
        txn_type=TxnType.OPENING_BALANCE,
        txn_id=catalog_opening_stock_txn_id(opening_row.id),
        voucher_no=f"CAT-OPEN-{opening_row.product_id}-{opening_row.id}",
        voucher_date=opening_row.as_of_date,
        posting_date=opening_row.as_of_date,
        narration=prefix,
        jl_inputs=[
            JLInput(
                account_id=inventory_account_id,
                ledger_id=inventory_ledger_id,
                drcr=True,
                amount=opening_value,
                description=f"{prefix} | Inventory capitalization",
                detail_id=opening_row.id,
            ),
            JLInput(
                account_id=equity_account_id,
                ledger_id=equity_ledger_id,
                drcr=False,
                amount=opening_value,
                description=f"{prefix} | Opening equity offset",
                detail_id=opening_row.id,
            ),
        ],
        im_inputs=[
            IMInput(
                product_id=opening_row.product_id,
                qty=qty,
                base_qty=qty,
                uom_id=getattr(product, "base_uom_id", None),
                base_uom_id=getattr(product, "base_uom_id", None),
                uom_factor=Decimal("1"),
                unit_cost=unit_cost,
                move_type=InventoryMove.MoveType.IN_,
                cost_source=InventoryMove.CostSource.MANUAL,
                movement_nature=InventoryMove.MovementNature.OPENING,
                movement_reason="catalog_opening_stock",
                detail_id=opening_row.id,
                location_id=location_id,
                destination_location_id=location_id,
                cost_meta={
                    "source": "catalog_opening_stock",
                    "opening_stock_id": opening_row.id,
                    "entityfin_id": financial_year.id,
                    "branch_id": getattr(opening_row, "branch_id", None),
                    "godown_id": location_id,
                    "openingvalue": str(getattr(opening_row, "openingvalue", None) or "0"),
                },
            )
        ],
        use_advisory_lock=True,
        mark_posted=True,
    )
