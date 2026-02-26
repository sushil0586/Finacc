from __future__ import annotations

from typing import Dict, List

from sales.models import SalesChoiceOverride, SalesInvoiceHeader,SalesInvoiceLine


def _enum_choices_to_payload(enum_cls) -> List[dict]:
    """
    Converts Django IntegerChoices/TextChoices into:
      [{"value": 1, "key": "DOMESTIC_B2B", "label": "Domestic B2B", "enabled": true}, ...]
    """
    out = []
    for value, label in enum_cls.choices:
        key = None
        # Find matching key name
        for k, v in enum_cls.__dict__.items():
            if v == value:
                key = k
                break
        out.append({"value": value, "key": key or str(value), "label": str(label), "enabled": True})
    return out


class SalesChoicesService:
    @staticmethod
    def get_choices(*, entity_id: int, subentity_id: int | None) -> Dict[str, list]:
        payload = {
            "DocType": _enum_choices_to_payload(SalesInvoiceHeader.DocType),
            "SupplyCategory": _enum_choices_to_payload(SalesInvoiceHeader.SupplyCategory),
            "Taxability": _enum_choices_to_payload(SalesInvoiceHeader.Taxability),
            "TaxRegime": _enum_choices_to_payload(SalesInvoiceHeader.TaxRegime),
            "GstComplianceMode": _enum_choices_to_payload(SalesInvoiceHeader.GstComplianceMode),
            "Status": _enum_choices_to_payload(SalesInvoiceHeader.Status),
            "DiscountType": _enum_choices_to_payload(SalesInvoiceLine.DiscountType),
        }

        overrides = list(
            SalesChoiceOverride.objects.filter(entity_id=entity_id, subentity_id=subentity_id)
        ) + list(
            SalesChoiceOverride.objects.filter(entity_id=entity_id, subentity__isnull=True)
        )

        # Apply overrides (subentity-specific can override entity-level)
        # simplest: apply in order -> entity first then subentity last
        overrides.sort(key=lambda x: (0 if x.subentity_id is None else 1))

        for o in overrides:
            group = o.choice_group
            key = o.choice_key
            if group not in payload:
                continue
            for item in payload[group]:
                if item["key"] == key:
                    item["enabled"] = bool(o.is_enabled)
                    if o.override_label:
                        item["label"] = o.override_label
                    break

        return payload
