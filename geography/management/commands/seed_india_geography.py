from django.core.management.base import BaseCommand

from geography.seeding import GeographySeedService


class Command(BaseCommand):
    help = "Seed baseline India geography data for fresh environments."

    def handle(self, *args, **options):
        summary = GeographySeedService.seed_india_baseline()

        self.stdout.write(self.style.SUCCESS("India geography seeded successfully."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")
