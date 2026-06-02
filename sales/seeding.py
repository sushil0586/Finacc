from __future__ import annotations

from django.db import transaction

from sales.models.sales_settings import SalesChoiceOverride


SALES_CHOICE_GROUPS = {
    "SupplyCategory": [
        "DOMESTIC_B2B",
        "DOMESTIC_B2C",
        "EXPORT_WITH_IGST",
        "EXPORT_WITHOUT_IGST",
        "SEZ_WITH_IGST",
        "SEZ_WITHOUT_IGST",
        "DEEMED_EXPORT",
    ],
    "Taxability": [
        "TAXABLE",
        "EXEMPT",
        "NIL_RATED",
        "NON_GST",
    ],
    "TaxRegime": [
        "INTRA_STATE",
        "INTER_STATE",
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
    "GstComplianceMode": [
        "NONE",
        "EINVOICE_ONLY",
        "EWAY_ONLY",
        "EINVOICE_AND_EWAY",
    ],
    "EInvoiceApplicable": [
        "YES",
        "NO",
    ],
    "EWayApplicable": [
        "YES",
        "NO",
    ],
    "BillToShipTo": [
        "SAME",
        "DIFFERENT",
    ],
}


class SalesSeedService:
    @classmethod
    @transaction.atomic
    def seed_choice_overrides(cls, *, entity, subentity=None):
        created = 0
        updated = 0

        for group, keys in SALES_CHOICE_GROUPS.items():
            for key in keys:
                _, was_created = SalesChoiceOverride.objects.update_or_create(
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
            "groups": len(SALES_CHOICE_GROUPS),
        }
