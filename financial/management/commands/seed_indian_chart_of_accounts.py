from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from financial.seeding import FinancialSeedService


class Command(BaseCommand):
    help = "Seed the final Indian accounting chart of accounts for a new or existing entity."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        try:
            entity = Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist as exc:
            raise CommandError(f"Entity {entity_id} does not exist.") from exc

        summary = FinancialSeedService.seed_entity(
            entity=entity,
            actor=None,
            template_code="indian_accounting_final",
        )

        self.stdout.write(self.style.SUCCESS("Indian chart of accounts seeded successfully."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")
