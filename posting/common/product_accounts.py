from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

# ✅ Adjust import to your actual Product model
from catalog.models import Product


@dataclass
class ProductAccountResolver:
    """
    Batch resolver for product-level accounts.
    Use once per adapter call to avoid N+1 queries.

    Assumes Product has FK fields:
      - purchase_account (-> purchase_account_id)
      - sales_account (-> sales_account_id)
    Rename these if your schema differs.
    """
    product_ids: Iterable[int]
    _purchase_map: Dict[int, int] = None
    _sales_map: Dict[int, int] = None

    def __post_init__(self):
        ids = {int(x) for x in (self.product_ids or []) if x}
        self._purchase_map = {}
        self._sales_map = {}
        if not ids:
            return

        # Pull both in one query
        rows = Product.objects.filter(id__in=ids).values_list(
            "id",
            "purchase_account_id",
            "sales_account_id",
        )
        for pid, purch_ac, sales_ac in rows:
            pid = int(pid)
            if purch_ac:
                self._purchase_map[pid] = int(purch_ac)
            if sales_ac:
                self._sales_map[pid] = int(sales_ac)

    def purchase_account_id(self, product_id: Optional[int]) -> Optional[int]:
        if not product_id:
            return None
        return self._purchase_map.get(int(product_id))

    def sales_account_id(self, product_id: Optional[int]) -> Optional[int]:
        if not product_id:
            return None
        return self._sales_map.get(int(product_id))
