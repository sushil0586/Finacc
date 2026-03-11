from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from financial.seeding import FinancialSeedService


class Command(BaseCommand):
    help = "Apply the financial seed template to an entity."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--template-code", type=str, default=FinancialSeedService.DEFAULT_TEMPLATE)

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        template_code = options["template_code"]

        try:
            entity = Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist as exc:
            raise CommandError(f"Entity {entity_id} does not exist.") from exc

        summary = FinancialSeedService.seed_entity(
            entity=entity,
            actor=None,
            template_code=template_code,
        )

        self.stdout.write(self.style.SUCCESS("Financial seed applied successfully."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")
