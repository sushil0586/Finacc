from django.core.management.base import BaseCommand, CommandError

from payroll.services.payroll_global_seed_service import PayrollGlobalSeedService


class Command(BaseCommand):
    help = "Seed the global payroll component and salary template catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview seed output without committing writes.")
        parser.add_argument("--force", action="store_true", help="Update existing global catalog records instead of skipping them.")
        parser.add_argument("--country", default="IN", help="Country code for seeded defaults. Defaults to IN.")
        parser.add_argument(
            "--only",
            default="all",
            choices=["groups", "components", "templates", "all"],
            help="Seed only one section or all sections.",
        )
        parser.add_argument("--verbose", action="store_true", dest="seed_verbose", help="Show detailed warnings and conflicts.")

    def handle(self, *args, **options):
        try:
            result = PayrollGlobalSeedService.seed_default_catalog(
                country=options["country"],
                force=options["force"],
                dry_run=options["dry_run"],
                only=options["only"],
                verbose=options["seed_verbose"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if result["conflicts"]:
            raise CommandError("\n".join(result["conflicts"]))

        mode = "Dry run completed" if result["dry_run"] else "Global payroll catalog seeded successfully"
        self.stdout.write(self.style.SUCCESS(mode))
        self.stdout.write(f"Country: {result['country']}")
        self.stdout.write(f"Seed target: {result['only']}")
        self.stdout.write(f"Force update: {'yes' if result['force'] else 'no'}")
        for label in ("groups", "components", "templates", "lines"):
            section = result[label]
            self.stdout.write(
                f"{label.title()}: created={section['created']} updated={section['updated']} skipped={section['skipped']}"
            )

        if options["seed_verbose"] and result["warnings"]:
            self.stdout.write(self.style.WARNING("Warnings:"))
            for warning in result["warnings"]:
                self.stdout.write(f"- {warning}")
