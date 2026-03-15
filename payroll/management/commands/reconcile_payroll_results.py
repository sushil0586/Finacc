from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from payroll.models import PayrollRun
from payroll.services.payroll_reconciliation_service import PayrollReconciliationService


class Command(BaseCommand):
    help = "Reconcile legacy/source payroll results against a payroll run."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--legacy-json", required=True, help="Path to legacy comparison JSON payload.")

    def handle(self, *args, **options):
        run = PayrollRun.objects.get(id=options["run_id"])
        payload = json.loads(Path(options["legacy_json"]).read_text())
        result = PayrollReconciliationService.reconcile_legacy_snapshot(payroll_run=run, legacy_snapshot=payload)
        self.stdout.write(json.dumps(result.as_dict(), indent=2))
        if not result.passed:
            raise CommandError("Payroll reconciliation failed.")
