from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity

from catalog.seeding import CatalogSeedService


class Command(BaseCommand):
    help = "Seed idempotent catalog master data for one entity or for all entities."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, default=None)

    def handle(self, *args, **options):
        entity_id = options["entity_id"]

        if entity_id is not None:
            entities = list(Entity.objects.filter(pk=entity_id))
            if not entities:
                raise CommandError(f"Entity {entity_id} does not exist.")
        else:
            entities = list(Entity.objects.order_by("id"))
            if not entities:
                raise CommandError("No entities found. Create an entity before seeding catalog masters.")

        for entity in entities:
            summary = CatalogSeedService.seed_entity(entity=entity)
            self.stdout.write(self.style.SUCCESS(f"Catalog master seed applied for entity {entity.id} - {entity}"))
            for key, value in summary.items():
                self.stdout.write(f"{key}: {value}")
