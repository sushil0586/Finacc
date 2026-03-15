from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from payroll.services.payroll_cutover_service import PayrollCutoverService


class Command(BaseCommand):
    help = "Validate whether one payroll scope is safe for cutover."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True)
        parser.add_argument("--entityfinid", type=int, required=True)
        parser.add_argument("--subentity", type=int)
        parser.add_argument("--period-code", required=True)
        parser.add_argument("--run-id", type=int)
        parser.add_argument("--expected-employee-count", type=int)
        parser.add_argument("--legacy-frozen", action="store_true")

    def handle(self, *args, **options):
        result = PayrollCutoverService.validate_cutover(
            entity_id=options["entity"],
            entityfinid_id=options["entityfinid"],
            subentity_id=options.get("subentity"),
            period_code=options["period_code"],
            payroll_run_id=options.get("run_id"),
            expected_employee_count=options.get("expected_employee_count"),
            legacy_frozen=options.get("legacy_frozen", False),
        )
        self.stdout.write(json.dumps(result.as_dict(), indent=2))
        if not result.passed:
            raise CommandError("Payroll cutover validation failed.")
