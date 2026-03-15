from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from payroll.models import PayrollRun
from payroll.services.payroll_posting_verification_service import PayrollPostingVerificationService


class Command(BaseCommand):
    help = "Verify payroll posting quality for one payroll run."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)

    def handle(self, *args, **options):
        run = PayrollRun.objects.get(id=options["run_id"])
        result = PayrollPostingVerificationService.verify_run_posting(run=run)
        self.stdout.write(json.dumps(result.as_dict(), indent=2))
        if not result.passed:
            raise CommandError("Payroll posting verification failed.")
