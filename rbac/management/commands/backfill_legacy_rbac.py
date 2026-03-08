from django.core.management.base import BaseCommand

from rbac.backfill import LegacyRBACBackfillService


class Command(BaseCommand):
    help = "Backfill RBAC roles, permissions, menu catalog, and assignments from legacy entity/auth tables."

    def handle(self, *args, **options):
        LegacyRBACBackfillService.run()
        self.stdout.write(self.style.SUCCESS("Legacy RBAC backfill completed."))
