from __future__ import annotations

from django.core.management.base import BaseCommand

from entity.models import Entity, SubEntity
from purchase.seeding import PurchaseSeedService


class Command(BaseCommand):
    help = "Seed PurchaseChoiceOverride for all supported choice types (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--subentity", type=int, default=None, help="Subentity ID (optional)")

    def handle(self, *args, **opts):
        entity_id = opts["entity"]
        subentity_id = opts.get("subentity")

        ent = Entity.objects.get(pk=entity_id)
        sub = SubEntity.objects.get(pk=subentity_id) if subentity_id else None

        self.stdout.write(self.style.SUCCESS("🔹 Seeding PurchaseChoiceOverride masters..."))
        summary = PurchaseSeedService.seed_choice_overrides(entity=ent, subentity=sub)

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ PurchaseChoiceOverride seeding done | created={summary['created']}, updated={summary['updated']}"
            )
        )
