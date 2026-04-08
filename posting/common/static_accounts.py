from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from posting.models import StaticAccount, EntityStaticAccountMap


class StaticAccountCodes:
    # Purchase base (optional)
    PURCHASE_DEFAULT = "PURCHASE_DEFAULT"
    SALES_REVENUE = "SALES_REVENUE"
    SALES_OTHER_CHARGES_INCOME  = "SALES_OTHER_CHARGES_INCOME"

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
    RCM_IGST_PAYABLE = "RCM_CGST_PAYABLE"
    RCM_SGST_PAYABLE = "RCM_SGST_PAYABLE"
    RCM_IGST_PAYABLE = "RCM_IGST_PAYABLE"
    RCM_CESS_PAYABLE = "RCM_CESS_PAYABLE"

    TDS_PAYABLE = "TDS_PAYABLE"
    GST_TDS_PAYABLE = "GST_TDS_PAYABLE"
    TCS_PAYABLE = "TCS_PAYABLE"


@dataclass
class StaticAccountResolver:
    """
    Resolve StaticAccount.code -> mapped ledger account_id for an entity.
    Caches per resolver instance.
    """
    entity_id: int
    _cache: Dict[str, Dict[str, Optional[int]]] = None

    def __post_init__(self):
        if self._cache is None:
            self._cache = {}

    def get_account_id(self, code: str, *, required: bool = True) -> Optional[int]:
        if code in self._cache:
            return self._cache[code]["account_id"]

        row = (
            EntityStaticAccountMap.objects
            .filter(entity_id=self.entity_id, static_account__code=code, static_account__is_active=True, is_active=True)
            .values("account_id", "ledger_id")
            .first()
        )
        if not row:
            if required:
                raise ValueError(
                    f"StaticAccount '{code}' not mapped for entity_id={self.entity_id}. "
                    f"Add mapping in Posting admin."
                )
            return None

        self._cache[code] = {
            "account_id": int(row["account_id"]) if row.get("account_id") else None,
            "ledger_id": int(row["ledger_id"]) if row.get("ledger_id") else None,
        }
        return self._cache[code]["account_id"]

    def get_ledger_id(self, code: str, *, required: bool = True) -> Optional[int]:
        if code not in self._cache:
            _ = self.get_account_id(code, required=required)
        ledger_id = self._cache.get(code, {}).get("ledger_id")
        if required and not ledger_id:
            raise ValueError(
                f"StaticAccount '{code}' has no ledger mapping for entity_id={self.entity_id}. "
                f"Update Posting static account mapping."
            )
        return ledger_id
