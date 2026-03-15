from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from payroll.services.payroll_rollout_validation_service import PayrollRolloutValidationService


class Command(BaseCommand):
    help = "Validate whether a payroll scope is configured for rollout."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True)
        parser.add_argument("--entityfinid", type=int, required=True)
        parser.add_argument("--subentity", type=int)
        parser.add_argument("--period-code")

    def handle(self, *args, **options):
        result = PayrollRolloutValidationService.validate_setup(
            entity_id=options["entity"],
            entityfinid_id=options["entityfinid"],
            subentity_id=options.get("subentity"),
            period_code=options.get("period_code"),
        )
        self.stdout.write(json.dumps(result.as_dict(), indent=2))
        if not result.passed:
            raise CommandError("Payroll rollout setup validation failed.")
