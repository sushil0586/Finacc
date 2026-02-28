from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from entity.models import Entity, SubEntity
from purchase.models.purchase_config import PurchaseChoiceOverride


class Command(BaseCommand):
    help = "Seed PurchaseChoiceOverride for all supported choice types (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--subentity", type=int, default=None, help="Subentity ID (optional)")

    @transaction.atomic
    def handle(self, *args, **opts):
        entity_id = opts["entity"]
        subentity_id = opts.get("subentity")

        ent = Entity.objects.get(pk=entity_id)
        sub = SubEntity.objects.get(pk=subentity_id) if subentity_id else None

        self.stdout.write(self.style.SUCCESS("🔹 Seeding PurchaseChoiceOverride masters..."))

        # ------------------------------------------------------------------
        # All supported choice groups & keys
        # ------------------------------------------------------------------
        CHOICES = {
            # Header-level
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
            # ITC / Compliance
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
            # Boolean-style choices (governance)
            "ReverseCharge": [
                "YES",
                "NO",
            ],
            "ServiceType": [
                "GOODS",
                "SERVICES",
            ],
        }

        created = 0
        updated = 0

        for group, keys in CHOICES.items():
            for key in keys:
                obj, was_created = PurchaseChoiceOverride.objects.update_or_create(
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
                f"✅ PurchaseChoiceOverride seeding done | created={created}, updated={updated}"
            )
        )
