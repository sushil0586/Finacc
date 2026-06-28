from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from assets.models import FixedAsset
from assets.services.asset_service import AssetService
from catalog.models import ProductPurchaseBehavior


class PurchaseAssetIntakeService:
    @staticmethod
    def _line_external_reference(line) -> str:
        return f"purchase-line:{getattr(line, 'id', '')}"

    @staticmethod
    def _line_asset_name(line) -> str:
        product_name = getattr(getattr(line, "product", None), "productname", None)
        fallback = (getattr(line, "product_desc", "") or "").strip()
        return (product_name or fallback or f"Purchase line {getattr(line, 'line_no', '-')}" or "").strip()

    @staticmethod
    def _line_asset_category(line):
        product = getattr(line, "product", None)
        return getattr(product, "default_asset_category", None)

    @staticmethod
    def _line_asset_ledger(category):
        return getattr(category, "cwip_ledger", None) or getattr(category, "asset_ledger", None)

    @staticmethod
    @transaction.atomic
    def create_intake_for_posted_line(*, header, line, user_id: int | None = None):
        if getattr(line, "purchase_behavior", None) != ProductPurchaseBehavior.ASSET:
            return None
        if getattr(line, "asset_record_id", None):
            return getattr(line, "asset_record", None)

        external_reference = PurchaseAssetIntakeService._line_external_reference(line)
        existing_asset = FixedAsset.objects.filter(
            entity=header.entity,
            external_reference=external_reference,
        ).first()
        if existing_asset is not None:
            line.asset_record = existing_asset
            line.save(update_fields=["asset_record"])
            return existing_asset

        category = PurchaseAssetIntakeService._line_asset_category(line)
        if category is None:
            raise ValueError(
                f"Purchase line {getattr(line, 'line_no', '-')}: asset product is missing a default asset category."
            )

        asset = AssetService.create_asset(
            data={
                "entity": header.entity,
                "entityfinid": getattr(header, "entityfinid", None),
                "subentity": getattr(header, "subentity", None),
                "category": category,
                "ledger": PurchaseAssetIntakeService._line_asset_ledger(category),
                "asset_name": PurchaseAssetIntakeService._line_asset_name(line),
                "status": FixedAsset.AssetStatus.CAPITAL_WIP,
                "acquisition_date": header.bill_date,
                "quantity": getattr(line, "qty", Decimal("1.0000")) or Decimal("1.0000"),
                "gross_block": getattr(line, "taxable_value", Decimal("0.00")) or Decimal("0.00"),
                "vendor_account": getattr(header, "vendor", None),
                "purchase_document_no": getattr(header, "purchase_number", None),
                "external_reference": external_reference,
                "notes": f"Auto-created from purchase invoice {getattr(header, 'purchase_number', '')} line {getattr(line, 'line_no', '-')}.",
            },
            user_id=user_id,
        )
        line.asset_record = asset
        line.save(update_fields=["asset_record"])
        return asset

    @staticmethod
    @transaction.atomic
    def sync_asset_intakes_for_posted_header(*, header, lines, user_id: int | None = None) -> None:
        for line in lines:
            PurchaseAssetIntakeService.create_intake_for_posted_line(header=header, line=line, user_id=user_id)

    @staticmethod
    @transaction.atomic
    def revert_asset_intakes_for_unpost(*, header) -> None:
        lines = list(
            header.lines.select_related("asset_record").filter(
                purchase_behavior=ProductPurchaseBehavior.ASSET,
                asset_record__isnull=False,
            )
        )
        for line in lines:
            asset = getattr(line, "asset_record", None)
            if asset is None:
                continue
            if asset.status not in {FixedAsset.AssetStatus.DRAFT, FixedAsset.AssetStatus.CAPITAL_WIP}:
                raise ValueError(
                    f"Cannot unpost purchase document: linked asset '{asset.asset_code}' has progressed beyond draft/CWIP."
                )
            if getattr(asset, "capitalization_posting_batch_id", None):
                raise ValueError(
                    f"Cannot unpost purchase document: linked asset '{asset.asset_code}' has already been capitalized."
                )
            line.asset_record = None
            line.save(update_fields=["asset_record"])
            AssetService.archive_asset(asset=asset, user_id=None)
