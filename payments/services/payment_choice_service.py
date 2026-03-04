from __future__ import annotations

from typing import Dict, List, Type

from payments.models import PaymentVoucherHeader, PaymentVoucherAdjustment


class PaymentChoiceService:
    GROUP_ENUM_MAP: Dict[str, Type] = {
        "PaymentType": PaymentVoucherHeader.PaymentType,
        "SupplyType": PaymentVoucherHeader.SupplyType,
        "Status": PaymentVoucherHeader.Status,
        "AdjustmentType": PaymentVoucherAdjustment.AdjType,
        "AdjustmentEffect": PaymentVoucherAdjustment.Effect,
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
