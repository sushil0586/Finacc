from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


from entity.models import Entity, SubEntity
from sales.models.sales_settings import SalesChoiceOverride
from sales.models.sales_core import SalesInvoiceHeader


class Command(BaseCommand):
    help = "Seed SalesChoiceOverride for all supported choice types (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--subentity", type=int, default=None, help="Subentity ID (optional)")

    @transaction.atomic
    def handle(self, *args, **opts):
        entity_id = opts["entity"]
        subentity_id = opts.get("subentity")

        ent = Entity.objects.get(pk=entity_id)
        sub = SubEntity.objects.get(pk=subentity_id) if subentity_id else None

        self.stdout.write(self.style.SUCCESS("🔹 Seeding SalesChoiceOverride masters..."))

        # ------------------------------------------------------------------
        # All supported choice groups & keys (Sales)
        # ------------------------------------------------------------------
        CHOICES = {
            # Header-level enums (from SalesInvoiceHeader)
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

            # Compliance / Governance for UI
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

            # Ship-to / Bill-to governance (optional UI toggles)
            "BillToShipTo": [
                "SAME",
                "DIFFERENT",
            ],
        }

        created = 0
        updated = 0

        for group, keys in CHOICES.items():
            for key in keys:
                obj, was_created = SalesChoiceOverride.objects.update_or_create(
                    entity=ent,
                    subentity=sub,
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

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ SalesChoiceOverride seeding done | created={created}, updated={updated}"
            )
        )
