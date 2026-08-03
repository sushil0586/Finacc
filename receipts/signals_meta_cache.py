from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from entity.models import EntityFinancialYear, SubEntity
from financial.models import AccountAddress, account
from receipts.models import ReceiptMode
from receipts.models.receipt_config import ReceiptChoiceOverride, ReceiptSettings
from withholding.models import WithholdingSection

from helpers.utils.meta_cache import (
    PAYMENT_META_NAMESPACES,
    RECEIPT_META_NAMESPACES,
    bump_meta_namespaces,
)


@receiver([post_save, post_delete], sender=ReceiptSettings)
@receiver([post_save, post_delete], sender=ReceiptChoiceOverride)
@receiver([post_save, post_delete], sender=ReceiptMode)
def invalidate_receipt_meta_cache_on_config_change(sender, **kwargs):
    bump_meta_namespaces(RECEIPT_META_NAMESPACES)


@receiver([post_save, post_delete], sender=account)
@receiver([post_save, post_delete], sender=AccountAddress)
@receiver([post_save, post_delete], sender=SubEntity)
@receiver([post_save, post_delete], sender=EntityFinancialYear)
@receiver([post_save, post_delete], sender=WithholdingSection)
def invalidate_payment_receipt_meta_cache_on_shared_master_change(sender, **kwargs):
    bump_meta_namespaces(PAYMENT_META_NAMESPACES + RECEIPT_META_NAMESPACES)
