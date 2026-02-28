from django.core.management.base import BaseCommand
from withholding.seed_withholding_service import WithholdingSeedService


class Command(BaseCommand):
    help = "Seed default TDS/TCS withholding sections"

    def handle(self, *args, **options):
        WithholdingSeedService.seed(verbose=True)
        self.stdout.write(self.style.SUCCESS("Withholding sections seeded successfully."))