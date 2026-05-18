from django.core.management.base import BaseCommand, CommandError

from hrms.services.hrms_global_seed_service import HrmsGlobalSeedService


class Command(BaseCommand):
    help = "Seed the global HRMS onboarding catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview the seed without committing writes.")
        parser.add_argument("--force", action="store_true", help="Update existing catalog records.")

    def handle(self, *args, **options):
        try:
            result = HrmsGlobalSeedService.seed_default_catalog(
                force=options["force"],
                dry_run=options["dry_run"],
            )
        except Exception as exc:  # pragma: no cover - command wrapper
            raise CommandError(str(exc)) from exc

        mode = "Dry run completed" if result["dry_run"] else "Global HRMS catalog seeded successfully"
        self.stdout.write(self.style.SUCCESS(mode))
        for key in (
            "leave_types",
            "leave_policies",
            "leave_policy_rules",
            "shifts",
            "holiday_calendars",
            "attendance_policies",
            "hr_policies",
        ):
            section = result[key]
            self.stdout.write(
                f"{key}: created={section['created']} updated={section['updated']} skipped={section['skipped']}"
            )
