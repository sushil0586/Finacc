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
        parser.add_argument(
            "--sync-legacy-profiles",
            action="store_true",
            help="Also hydrate normalized profiles from legacy account columns during ledger resync.",
        )

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        sync_legacy_profiles = options["sync_legacy_profiles"]

        if entity_id is None:
            created_settings = bootstrap_financial_settings_for_all_entities(Entity)
            synced_ledgers = resync_ledgers(sync_legacy_profiles=sync_legacy_profiles)
            self.stdout.write(self.style.SUCCESS("Financial foundation bootstrap complete."))
            self.stdout.write(f"FinancialSettings created: {created_settings}")
            self.stdout.write(f"Ledgers synced: {synced_ledgers}")
            self.stdout.write(f"Legacy profile sync: {'enabled' if sync_legacy_profiles else 'disabled'}")
            return

        entity = Entity.objects.filter(id=entity_id).first()
        if not entity:
            self.stdout.write(self.style.ERROR(f"Entity {entity_id} not found."))
            return

        _, created = get_or_create_financial_settings(entity)
        synced_ledgers = resync_ledgers(entity_id=entity_id, sync_legacy_profiles=sync_legacy_profiles)

        self.stdout.write(self.style.SUCCESS("Financial foundation bootstrap complete."))
        self.stdout.write(f"FinancialSettings created: {1 if created else 0}")
        self.stdout.write(f"Ledgers synced: {synced_ledgers}")
        self.stdout.write(f"Legacy profile sync: {'enabled' if sync_legacy_profiles else 'disabled'}")
