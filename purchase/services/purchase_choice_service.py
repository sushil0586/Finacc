from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from django.db.models import Q

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.models.purchase_config import PurchaseChoiceOverride


@dataclass(frozen=True)
class ChoiceResolved:
    group: str
    value: int
    key: str
    label: str
    enabled: bool


class PurchaseChoiceService:
    """
    Compiles UI-ready choice lists for Purchase module and applies PurchaseChoiceOverride.
    """

    # Map UI group -> IntegerChoices enum class
    GROUP_ENUM_MAP: Dict[str, Type] = {
        "SupplyCategory": PurchaseInvoiceHeader.SupplyCategory,
        "Taxability": PurchaseInvoiceHeader.Taxability,
        "TaxRegime": PurchaseInvoiceHeader.TaxRegime,
        "DocType": PurchaseInvoiceHeader.DocType,
        "Status": PurchaseInvoiceHeader.Status,
        "Gstr2bMatchStatus": PurchaseInvoiceHeader.Gstr2bMatchStatus,
        "ItcClaimStatus": PurchaseInvoiceHeader.ItcClaimStatus,
    }

    @staticmethod
    def _load_overrides(entity_id: int, subentity_id: Optional[int], groups: List[str]) -> Dict[str, Dict[str, PurchaseChoiceOverride]]:
        """
        Returns overrides indexed as overrides[group][choice_key] = override_obj.
        """
        qs = PurchaseChoiceOverride.objects.filter(entity_id=entity_id, choice_group__in=groups)

        # subentity matching:
        # prefer subentity-specific if exists, else allow entity-level (subentity null)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

        # Build map with precedence: subentity-specific overrides win over null-subentity
        out: Dict[str, Dict[str, PurchaseChoiceOverride]] = {g: {} for g in groups}
        for ov in qs.order_by("subentity_id"):  # null first, then specific overwrites
            out.setdefault(ov.choice_group, {})
            out[ov.choice_group][ov.choice_key] = ov
        return out

    @classmethod
    def compile_choices(cls, entity_id: int, subentity_id: Optional[int] = None) -> Dict[str, List[dict]]:
        """
        Returns:
        {
          "SupplyCategory": [{"value":1,"key":"DOMESTIC","label":"Domestic","enabled":true}, ...],
          ...
        }
        """
        groups = list(cls.GROUP_ENUM_MAP.keys())
        overrides = cls._load_overrides(entity_id, subentity_id, groups)

        compiled: Dict[str, List[dict]] = {}

        for group, enum_cls in cls.GROUP_ENUM_MAP.items():
            items: List[dict] = []
            group_overrides = overrides.get(group, {})

            for value, default_label in enum_cls.choices:
                # Convert enum value -> stable key (name)
                key = enum_cls(value).name  # e.g. 2 -> "IMPORT_GOODS"

                ov = group_overrides.get(key)
                enabled = ov.is_enabled if ov else True
                label = (ov.override_label.strip() if ov and ov.override_label else default_label)

                items.append({
                    "value": int(value),
                    "key": key,
                    "label": label,
                    "enabled": bool(enabled),
                })

            compiled[group] = items

        return compiled

    @classmethod
    def resolve_choice(cls, entity_id: int, subentity_id: Optional[int], choice_group: str, value: int) -> ChoiceResolved:
        """
        Small helper for validations:
        input: entity_id, subentity_id, choice_group, integer value
        output: enabled + final label (+ key/value)
        """
        if choice_group not in cls.GROUP_ENUM_MAP:
            raise ValueError(f"Unsupported choice_group: {choice_group}")

        enum_cls = cls.GROUP_ENUM_MAP[choice_group]
        key = enum_cls(value).name
        default_label = enum_cls(value).label

        overrides = cls._load_overrides(entity_id, subentity_id, [choice_group])
        ov = overrides.get(choice_group, {}).get(key)

        enabled = ov.is_enabled if ov else True
        label = (ov.override_label.strip() if ov and ov.override_label else default_label)

        return ChoiceResolved(
            group=choice_group,
            value=int(value),
            key=key,
            label=label,
            enabled=bool(enabled),
        )
