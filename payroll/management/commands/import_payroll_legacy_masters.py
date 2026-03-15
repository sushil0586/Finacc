from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from payroll.services.legacy_payroll_import_service import LegacyPayrollImportService


class Command(BaseCommand):
    help = "Import legacy payroll masters/config into the new payroll domain."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True)
        parser.add_argument("--entityfinid", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = LegacyPayrollImportService.import_masters(
            entity_id=options["entity"],
            entityfinid_id=options["entityfinid"],
            dry_run=options.get("dry_run", False),
        )
        self.stdout.write(json.dumps(result, indent=2))
