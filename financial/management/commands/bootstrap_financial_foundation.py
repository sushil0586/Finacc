from django.core.management.base import BaseCommand

from entity.models import Entity
from financial.services import (
    bootstrap_financial_settings_for_all_entities,
    get_or_create_financial_settings,
    resync_ledgers,
)


class Command(BaseCommand):
    help = "Bootstrap additive financial foundation data: ensure FinancialSettings and resync Ledger rows."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, default=None)

    def handle(self, *args, **options):
        entity_id = options["entity_id"]

        if entity_id is None:
            created_settings = bootstrap_financial_settings_for_all_entities(Entity)
            synced_ledgers = resync_ledgers()
            self.stdout.write(self.style.SUCCESS("Financial foundation bootstrap complete."))
            self.stdout.write(f"FinancialSettings created: {created_settings}")
            self.stdout.write(f"Ledgers synced: {synced_ledgers}")
            return

        entity = Entity.objects.filter(id=entity_id).first()
        if not entity:
            self.stdout.write(self.style.ERROR(f"Entity {entity_id} not found."))
            return

        _, created = get_or_create_financial_settings(entity)
        synced_ledgers = resync_ledgers(entity_id=entity_id)

        self.stdout.write(self.style.SUCCESS("Financial foundation bootstrap complete."))
        self.stdout.write(f"FinancialSettings created: {1 if created else 0}")
        self.stdout.write(f"Ledgers synced: {synced_ledgers}")
