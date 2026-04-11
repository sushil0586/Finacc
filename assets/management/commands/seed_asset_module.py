from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity

from assets.seeding import AssetSeedService


class Command(BaseCommand):
    help = "Seed the asset module with starter ledgers, settings, and categories."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)

    def handle(self, *args, **options):
        entity_id = options["entity_id"]

        try:
            entity = Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist as exc:
            raise CommandError(f"Entity {entity_id} does not exist.") from exc

        summary = AssetSeedService.seed_entity(entity=entity, actor=None)

        self.stdout.write(self.style.SUCCESS("Asset module seed applied successfully."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")
