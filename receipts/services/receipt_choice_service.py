from __future__ import annotations

from typing import Dict, List, Type

from receipts.models import ReceiptVoucherHeader, ReceiptVoucherAdjustment


class ReceiptChoiceService:
    GROUP_ENUM_MAP: Dict[str, Type] = {
        "ReceiptType": ReceiptVoucherHeader.ReceiptType,
        "SupplyType": ReceiptVoucherHeader.SupplyType,
        "Status": ReceiptVoucherHeader.Status,
        "AdjustmentType": ReceiptVoucherAdjustment.AdjType,
        "AdjustmentEffect": ReceiptVoucherAdjustment.Effect,
    }

    @classmethod
    def compile_choices(cls) -> Dict[str, List[dict]]:
        compiled: Dict[str, List[dict]] = {}
        for group, enum_cls in cls.GROUP_ENUM_MAP.items():
            items: List[dict] = []
            for value, label in enum_cls.choices:
                items.append({
                    "value": value,
                    "key": str(value),
                    "label": str(label),
                    "enabled": True,
                })
            compiled[group] = items
        return compiled
