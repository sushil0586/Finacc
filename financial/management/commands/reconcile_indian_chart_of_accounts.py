from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from financial.seeding import FinancialSeedService


class Command(BaseCommand):
    help = "Reconcile existing entity ledgers/accounts to the final Indian accounting chart."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Entity id to reconcile.")
        parser.add_argument("--all", action="store_true", help="Reconcile all entities.")

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        reconcile_all = bool(options.get("all"))

        if not entity_id and not reconcile_all:
            raise CommandError("Provide --entity-id or use --all.")

        qs = Entity.objects.all()
        if entity_id:
            qs = qs.filter(pk=entity_id)
        if not qs.exists():
            raise CommandError("No matching entities found.")

        for entity in qs.iterator():
            summary = FinancialSeedService.reconcile_entity(
                entity=entity,
                actor=None,
                template_code="indian_accounting_final",
            )
            self.stdout.write(self.style.SUCCESS(f"Reconciled entity {entity.id} - {entity.entityname}"))
            for key, value in summary.items():
                self.stdout.write(f"  {key}: {value}")
