from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from entity.models import EntityFinancialYear, SubEntity
from financial.models import AccountAddress, account
from posting.models import EntityStaticAccountMap

from helpers.utils.meta_cache import REPORTS_META_NAMESPACES, bump_meta_namespaces


@receiver([post_save, post_delete], sender=account)
@receiver([post_save, post_delete], sender=AccountAddress)
@receiver([post_save, post_delete], sender=SubEntity)
@receiver([post_save, post_delete], sender=EntityFinancialYear)
@receiver([post_save, post_delete], sender=EntityStaticAccountMap)
def invalidate_reports_meta_cache_on_shared_master_change(sender, **kwargs):
    bump_meta_namespaces(REPORTS_META_NAMESPACES)
