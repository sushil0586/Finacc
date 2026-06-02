from __future__ import annotations

from django.db import transaction

from purchase.models.purchase_config import PurchaseChoiceOverride


PURCHASE_CHOICE_GROUPS = {
    "SupplyCategory": [
        "DOMESTIC",
        "IMPORT_GOODS",
        "IMPORT_SERVICES",
        "SEZ",
    ],
    "Taxability": [
        "TAXABLE",
        "EXEMPT",
        "NIL_RATED",
        "NON_GST",
    ],
    "TaxRegime": [
        "INTRA",
        "INTER",
    ],
    "DocType": [
        "TAX_INVOICE",
        "CREDIT_NOTE",
        "DEBIT_NOTE",
    ],
    "Status": [
        "DRAFT",
        "CONFIRMED",
        "POSTED",
        "CANCELLED",
    ],
    "ItcClaimStatus": [
        "PENDING",
        "CLAIMED",
        "REVERSED",
        "BLOCKED",
    ],
    "Gstr2bMatchStatus": [
        "NOT_CHECKED",
        "MATCHED",
        "MISMATCHED",
        "NOT_IN_2B",
        "PARTIAL",
    ],
    "ReverseCharge": [
        "YES",
        "NO",
    ],
    "ServiceType": [
        "GOODS",
        "SERVICES",
    ],
}


class PurchaseSeedService:
    @classmethod
    @transaction.atomic
    def seed_choice_overrides(cls, *, entity, subentity=None):
        created = 0
        updated = 0

        for group, keys in PURCHASE_CHOICE_GROUPS.items():
            for key in keys:
                _, was_created = PurchaseChoiceOverride.objects.update_or_create(
                    entity=entity,
                    subentity=subentity,
                    choice_group=group,
                    choice_key=key,
                    defaults={
                        "is_enabled": True,
                        "override_label": None,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        return {
            "created": created,
            "updated": updated,
            "groups": len(PURCHASE_CHOICE_GROUPS),
        }
