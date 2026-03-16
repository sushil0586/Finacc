from django.core.management.base import BaseCommand, CommandError

from payroll.services.payroll_seed_service import PayrollSeedService


class Command(BaseCommand):
    help = "Seed payroll master/setup data safely and idempotently."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity-id",
            type=int,
            help="Seed entity-scoped payroll masters only for the specified active entity id.",
        )

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        try:
            summary = PayrollSeedService.seed_all(entity_id=entity_id)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Payroll master seeding completed."))
        for section, result in summary.items():
            if section == "totals":
                continue
            self.stdout.write(
                f"- {section}: created={result['created']} updated={result['updated']} skipped={result['skipped']}"
            )
            for note in result.get("notes", []):
                self.stdout.write(f"  note: {note}")

        totals = summary["totals"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Totals: created={totals['created']} updated={totals['updated']} skipped={totals['skipped']}"
            )
        )
