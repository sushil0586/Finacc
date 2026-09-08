import json

from django.core.management.base import BaseCommand

from platform_ops.services import PlatformAccessService


class Command(BaseCommand):
    help = "Expire elapsed platform-role assignments and revoke orphaned platform sessions."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report matches without changing access.")
        parser.add_argument("--json", action="store_true", help="Emit one machine-readable JSON result line.")

    def handle(self, *args, **options):
        result = PlatformAccessService.expire_assignments(dry_run=options["dry_run"])
        result = {"dry_run": options["dry_run"], **result}
        if options["json"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        self.stdout.write(f"matched: {result['matched']}")
        self.stdout.write(f"expired: {result['expired']}")
        self.stdout.write(f"sessions revoked: {result['sessions_revoked']}")
        for assignment_id in result["assignment_ids"]:
            self.stdout.write(f"assignment: {assignment_id}")
