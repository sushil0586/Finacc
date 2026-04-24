from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from purchase.models import PurchaseChargeType, PurchaseChoiceOverride, PurchaseSettings
from withholding.models import EntityWithholdingConfig

from helpers.utils.meta_cache import PURCHASE_META_NAMESPACES, bump_meta_namespaces


@receiver([post_save, post_delete], sender=PurchaseSettings)
@receiver([post_save, post_delete], sender=PurchaseChoiceOverride)
@receiver([post_save, post_delete], sender=PurchaseChargeType)
@receiver([post_save, post_delete], sender=EntityWithholdingConfig)
def invalidate_purchase_meta_cache_on_config_change(sender, **kwargs):
    bump_meta_namespaces(PURCHASE_META_NAMESPACES)
