from django.core.management.base import BaseCommand

from financial.services import backfill_missing_account_profiles


class Command(BaseCommand):
    help = "One-time backfill for missing normalized account profiles (compliance/commercial/address)."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = backfill_missing_account_profiles(
            entity_id=options["entity_id"],
            dry_run=options["dry_run"],
        )

        mode = "DRY RUN" if options["dry_run"] else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"Account profile backfill complete ({mode})."))
        self.stdout.write(f"Accounts scanned: {result['accounts_scanned']}")
        self.stdout.write(f"Missing compliance profiles: {result['missing_compliance']}")
        self.stdout.write(f"Missing commercial profiles: {result['missing_commercial']}")
        self.stdout.write(f"Missing primary addresses: {result['missing_primary_address']}")
        self.stdout.write(f"Accounts updated: {result['accounts_updated']}")
