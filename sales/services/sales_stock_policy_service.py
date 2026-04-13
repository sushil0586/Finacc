from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sales.models.sales_settings import SalesStockPolicy


DEFAULT_STOCK_POLICY = {
    "mode": SalesStockPolicy.Mode.RELAXED,
    "allow_negative_stock": True,
    "batch_required_for_sales": False,
    "expiry_validation_required": False,
    "fefo_required": False,
    "allow_manual_batch_override": True,
    "allow_oversell": False,
}

STOCK_POLICY_BOOLEAN_KEYS = (
    "allow_negative_stock",
    "batch_required_for_sales",
    "expiry_validation_required",
    "fefo_required",
    "allow_manual_batch_override",
    "allow_oversell",
)


@dataclass(frozen=True)
class ResolvedSalesStockPolicy:
    policy: SalesStockPolicy | None
    scope_level: str
    scope_key: str
    is_default: bool = False

    @property
    def mode(self) -> str:
        if self.policy:
            return self.policy.mode
        return DEFAULT_STOCK_POLICY["mode"]

    @property
    def allow_negative_stock(self) -> bool:
        if self.policy:
            return bool(self.policy.allow_negative_stock)
        return bool(DEFAULT_STOCK_POLICY["allow_negative_stock"])

    @property
    def batch_required_for_sales(self) -> bool:
        if self.policy:
            return bool(self.policy.batch_required_for_sales)
        return bool(DEFAULT_STOCK_POLICY["batch_required_for_sales"])

    @property
    def expiry_validation_required(self) -> bool:
        if self.policy:
            return bool(self.policy.expiry_validation_required)
        return bool(DEFAULT_STOCK_POLICY["expiry_validation_required"])

    @property
    def fefo_required(self) -> bool:
        if self.policy:
            return bool(self.policy.fefo_required)
        return bool(DEFAULT_STOCK_POLICY["fefo_required"])

    @property
    def allow_manual_batch_override(self) -> bool:
        if self.policy:
            return bool(self.policy.allow_manual_batch_override)
        return bool(DEFAULT_STOCK_POLICY["allow_manual_batch_override"])

    @property
    def allow_oversell(self) -> bool:
        if self.policy:
            return bool(self.policy.allow_oversell)
        return bool(DEFAULT_STOCK_POLICY["allow_oversell"])


class SalesStockPolicyService:
    """
    Resolves stock policy using most-specific scope first:
      1. entity + subentity + financial year
      2. entity + subentity
      3. entity + financial year
      4. entity
    """

    @staticmethod
    def _scope_key(entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int], scope_level: str) -> str:
        parts = [f"entity:{entity_id}"]
        if entityfinid_id:
            parts.append(f"fy:{entityfinid_id}")
        if subentity_id:
            parts.append(f"sub:{subentity_id}")
        parts.append(f"scope:{scope_level}")
        return "|".join(parts)

    @classmethod
    def resolve(cls, *, entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int]) -> ResolvedSalesStockPolicy:
        candidates = []
        if entityfinid_id and subentity_id:
            candidates.append(
                (
                    SalesStockPolicy.ScopeLevel.ENTITY_SUBENTITY_FY,
                    {
                        "entity_id": entity_id,
                        "entityfinid_id": entityfinid_id,
                        "subentity_id": subentity_id,
                    },
                )
            )
        if subentity_id:
            candidates.append(
                (
                    SalesStockPolicy.ScopeLevel.ENTITY_SUBENTITY,
                    {
                        "entity_id": entity_id,
                        "entityfinid__isnull": True,
                        "subentity_id": subentity_id,
                    },
                )
            )
        if entityfinid_id:
            candidates.append(
                (
                    SalesStockPolicy.ScopeLevel.ENTITY_FY,
                    {
                        "entity_id": entity_id,
                        "entityfinid_id": entityfinid_id,
                        "subentity__isnull": True,
                    },
                )
            )
        candidates.append(
            (
                SalesStockPolicy.ScopeLevel.ENTITY,
                {
                    "entity_id": entity_id,
                    "entityfinid__isnull": True,
                    "subentity__isnull": True,
                },
            )
        )

        for scope_level, filters in candidates:
            policy = SalesStockPolicy.objects.filter(scope_level=scope_level, **filters).order_by("-id").first()
            if policy:
                return ResolvedSalesStockPolicy(
                    policy=policy,
                    scope_level=policy.scope_level,
                    scope_key=policy.scope_key,
                    is_default=False,
                )

        default_scope = cls._scope_key(entity_id, subentity_id, entityfinid_id, SalesStockPolicy.ScopeLevel.ENTITY)
        return ResolvedSalesStockPolicy(
            policy=None,
            scope_level=SalesStockPolicy.ScopeLevel.ENTITY,
            scope_key=default_scope,
            is_default=True,
        )
