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
        duplicates_removed = 0

        for group, keys in PURCHASE_CHOICE_GROUPS.items():
            for key in keys:
                scoped = PurchaseChoiceOverride.objects.filter(
                    entity=entity,
                    subentity=subentity,
                    choice_group=group,
                    choice_key=key,
                ).order_by("id")
                choice = scoped.first()
                if choice is None:
                    PurchaseChoiceOverride.objects.create(
                        entity=entity,
                        subentity=subentity,
                        choice_group=group,
                        choice_key=key,
                        is_enabled=True,
                        override_label=None,
                    )
                    created += 1
                else:
                    duplicate_ids = list(scoped.values_list("id", flat=True)[1:])
                    if duplicate_ids:
                        PurchaseChoiceOverride.objects.filter(id__in=duplicate_ids).delete()
                        duplicates_removed += len(duplicate_ids)
                    choice.is_enabled = True
                    choice.override_label = None
                    choice.save(update_fields=["is_enabled", "override_label", "updated_at"])
                    updated += 1

        return {
            "created": created,
            "updated": updated,
            "duplicates_removed": duplicates_removed,
            "groups": len(PURCHASE_CHOICE_GROUPS),
        }
