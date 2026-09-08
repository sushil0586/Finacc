import json

from django.core.management.base import BaseCommand

from platform_ops.operations import PlatformOperationService


class Command(BaseCommand):
    help = "Expire platform-operation approvals that exceeded the configured execution window."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report matching approvals without changing them.")
        parser.add_argument("--json", action="store_true", help="Emit one machine-readable JSON result line.")

    def handle(self, *args, **options):
        result = PlatformOperationService.expire_approved_operations(dry_run=options["dry_run"])
        result = {"dry_run": options["dry_run"], **result}
        if options["json"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        self.stdout.write(f"matched: {result['matched']}")
        self.stdout.write(f"expired: {result['expired']}")
        for operation_id in result["operation_ids"]:
            self.stdout.write(f"operation: {operation_id}")
