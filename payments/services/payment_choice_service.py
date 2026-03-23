from __future__ import annotations

from typing import Optional

from django.db.models import Q

from typing import Dict, List, Type

from payments.models import PaymentVoucherHeader, PaymentVoucherAdjustment
from payments.models.payment_config import PaymentChoiceOverride


class PaymentChoiceService:
    GROUP_ENUM_MAP: Dict[str, Type] = {
        "PaymentType": PaymentVoucherHeader.PaymentType,
        "SupplyType": PaymentVoucherHeader.SupplyType,
        "Status": PaymentVoucherHeader.Status,
        "AdjustmentType": PaymentVoucherAdjustment.AdjType,
        "AdjustmentEffect": PaymentVoucherAdjustment.Effect,
    }

    @staticmethod
    def _load_overrides(entity_id: int, subentity_id: Optional[int], groups: List[str]) -> Dict[str, Dict[str, PaymentChoiceOverride]]:
        qs = PaymentChoiceOverride.objects.filter(entity_id=entity_id, choice_group__in=groups)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

        out: Dict[str, Dict[str, PaymentChoiceOverride]] = {g: {} for g in groups}
        for ov in qs.order_by("subentity_id"):
            out.setdefault(ov.choice_group, {})
            out[ov.choice_group][ov.choice_key] = ov
        return out

    @classmethod
    def compile_choices(cls, entity_id: Optional[int] = None, subentity_id: Optional[int] = None) -> Dict[str, List[dict]]:
        compiled: Dict[str, List[dict]] = {}
        groups = list(cls.GROUP_ENUM_MAP.keys())
        overrides = cls._load_overrides(entity_id, subentity_id, groups) if entity_id else {}
        for group, enum_cls in cls.GROUP_ENUM_MAP.items():
            items: List[dict] = []
            group_overrides = overrides.get(group, {})
            for value, label in enum_cls.choices:
                key = enum_cls(value).name
                ov = group_overrides.get(key)
                items.append({
                    "value": value,
                    "key": key,
                    "label": (ov.override_label.strip() if ov and ov.override_label else str(label)),
                    "enabled": bool(ov.is_enabled if ov else True),
                })
            compiled[group] = items
        return compiled
