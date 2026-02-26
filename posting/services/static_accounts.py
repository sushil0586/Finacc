# posting/services/static_accounts.py
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Dict, List

from posting.models import StaticAccount, EntityStaticAccountMap, StaticAccountGroup


@dataclass(frozen=True)
class StaticAccountResolved:
    code: str
    account_id: int


class StaticAccountService:
    """
    Fast lookup of entity static accounts by code/group.
    Cache is per-process; invalidate if you change mappings frequently.
    (You can later add Redis cache if needed.)
    """

    @staticmethod
    @lru_cache(maxsize=2048)
    def _entity_map(entity_id: int) -> Dict[str, int]:
        qs = (
            EntityStaticAccountMap.objects
            .filter(entity_id=entity_id, is_active=True, static_account__is_active=True)
            .select_related("static_account")
            .values_list("static_account__code", "account_id")
        )
        return {code: acc_id for code, acc_id in qs}

    @staticmethod
    def invalidate(entity_id: int) -> None:
        # Clear whole cache (simple and safe). If needed, implement per-key invalidation later.
        StaticAccountService._entity_map.cache_clear()

    @staticmethod
    def get_account_id(entity_id: int, code: str, *, required: bool = True) -> Optional[int]:
        m = StaticAccountService._entity_map(entity_id)
        acc_id = m.get(code)
        if required and not acc_id:
            raise ValueError(f"Missing static account mapping: entity={entity_id} code={code}")
        return acc_id

    @staticmethod
    def get_group(entity_id: int, group: str) -> Dict[str, int]:
        # return only codes belonging to group
        codes = list(
            StaticAccount.objects
            .filter(group=group, is_active=True)
            .values_list("code", flat=True)
        )
        m = StaticAccountService._entity_map(entity_id)
        return {c: m.get(c) for c in codes if c in m}

    @staticmethod
    def missing_required_codes(entity_id: int) -> List[str]:
        required_codes = list(
            StaticAccount.objects
            .filter(is_required=True, is_active=True)
            .values_list("code", flat=True)
        )
        m = StaticAccountService._entity_map(entity_id)
        return [c for c in required_codes if c not in m]
