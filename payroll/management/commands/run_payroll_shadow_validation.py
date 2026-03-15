from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from payroll.models import PayrollRun
from payroll.services.payroll_shadow_run_service import PayrollShadowRunService


class Command(BaseCommand):
    help = "Validate a payroll run in shadow mode."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--expected-employee-count", type=int)
        parser.add_argument("--verify-posting", action="store_true")

    def handle(self, *args, **options):
        run = PayrollRun.objects.get(id=options["run_id"])
        result = PayrollShadowRunService.validate_shadow_run(
            payroll_run=run,
            expected_employee_count=options.get("expected_employee_count"),
            verify_posting=options.get("verify_posting", False),
        )
        self.stdout.write(json.dumps(result.as_dict(), indent=2))
        if not result.passed:
            raise CommandError("Shadow payroll validation failed.")
