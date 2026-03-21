from django.core.management.base import BaseCommand

from Authentication.models import User
from entity.seeding import EntitySeedService


class Command(BaseCommand):
    help = "Seed entity-domain master data like constitutions, GST registration types, and unit types."

    def add_arguments(self, parser):
        parser.add_argument("--actor-id", type=int, required=False)

    def handle(self, *args, **options):
        actor = None
        actor_id = options.get("actor_id")
        if actor_id:
            actor = User.objects.filter(pk=actor_id).first()
            if actor is None:
                self.stderr.write(self.style.WARNING(f"Actor {actor_id} not found. Seeding without actor."))

        summary = EntitySeedService.seed_master_data(actor=actor)

        self.stdout.write(self.style.SUCCESS("Entity master data seeded successfully."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")
