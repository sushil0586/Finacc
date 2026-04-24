from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from entity.models import EntityFinancialYear, SubEntity
from financial.models import AccountAddress, account
from sales.models import SalesChargeType, SalesChoiceOverride, SalesSettings, SalesStockPolicy
from withholding.models import WithholdingSection

from helpers.utils.meta_cache import (
    PURCHASE_META_NAMESPACES,
    SALES_META_NAMESPACES,
    bump_meta_namespaces,
)


@receiver([post_save, post_delete], sender=SalesSettings)
@receiver([post_save, post_delete], sender=SalesChoiceOverride)
@receiver([post_save, post_delete], sender=SalesStockPolicy)
@receiver([post_save, post_delete], sender=SalesChargeType)
def invalidate_sales_meta_cache_on_sales_config_change(sender, **kwargs):
    bump_meta_namespaces(SALES_META_NAMESPACES)


@receiver([post_save, post_delete], sender=account)
@receiver([post_save, post_delete], sender=AccountAddress)
@receiver([post_save, post_delete], sender=SubEntity)
@receiver([post_save, post_delete], sender=EntityFinancialYear)
@receiver([post_save, post_delete], sender=WithholdingSection)
def invalidate_meta_cache_on_shared_master_change(sender, **kwargs):
    # Shared masters participate in both Sales and Purchase metadata payloads.
    bump_meta_namespaces(SALES_META_NAMESPACES + PURCHASE_META_NAMESPACES)
