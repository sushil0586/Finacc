from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from posting.models import StaticAccount, EntityStaticAccountMap


class StaticAccountCodes:
    # Purchase base (optional)
    PURCHASE_DEFAULT = "PURCHASE_DEFAULT"

    # Sales base (optional)
    SALES_DEFAULT = "SALES_DEFAULT"

    # Expense buckets
    PURCHASE_MISC_EXPENSE = "PURCHASE_MISC_EXPENSE"
    SALES_MISC_EXPENSE = "SALES_MISC_EXPENSE"

    ITC_BLOCKED_EXPENSE = "ITC_BLOCKED_EXPENSE"

    # Round-off
    ROUND_OFF_INCOME = "ROUND_OFF_INCOME"
    ROUND_OFF_EXPENSE = "ROUND_OFF_EXPENSE"

    # Input GST (ITC)
    INPUT_CGST = "INPUT_CGST"
    INPUT_SGST = "INPUT_SGST"
    INPUT_IGST = "INPUT_IGST"
    INPUT_CESS = "INPUT_CESS"

    # Output GST (Sales)
    OUTPUT_CGST = "OUTPUT_CGST"
    OUTPUT_SGST = "OUTPUT_SGST"
    OUTPUT_IGST = "OUTPUT_IGST"
    OUTPUT_CESS = "OUTPUT_CESS"

    # RCM Payable (liability)
    RCM_CGST_PAYABLE = "RCM_CGST_PAYABLE"
    RCM_SGST_PAYABLE = "RCM_SGST_PAYABLE"
    RCM_IGST_PAYABLE = "RCM_IGST_PAYABLE"
    RCM_CESS_PAYABLE = "RCM_CESS_PAYABLE"


@dataclass
class StaticAccountResolver:
    """
    Resolve StaticAccount.code -> mapped ledger account_id for an entity.
    Caches per resolver instance.
    """
    entity_id: int
    _cache: Dict[str, int] = None

    def __post_init__(self):
        if self._cache is None:
            self._cache = {}

    def get_account_id(self, code: str, *, required: bool = True) -> Optional[int]:
        if code in self._cache:
            return self._cache[code]

        sa_id = (
            StaticAccount.objects
            .filter(code=code, is_active=True)
            .values_list("id", flat=True)
            .first()
        )
        if not sa_id:
            if required:
                raise ValueError(f"StaticAccount missing for code='{code}'. Seed StaticAccount first.")
            return None

        acct_id = (
            EntityStaticAccountMap.objects
            .filter(entity_id=self.entity_id, static_account_id=sa_id, is_active=True)
            .values_list("account_id", flat=True)
            .first()
        )
        if not acct_id:
            if required:
                raise ValueError(
                    f"StaticAccount '{code}' not mapped for entity_id={self.entity_id}. "
                    f"Add mapping in Posting admin."
                )
            return None

        self._cache[code] = int(acct_id)
        return int(acct_id)
