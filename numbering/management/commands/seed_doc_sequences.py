from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from master.models import Entity, entityfinancialyear, subentity as SubEntity  # adjust paths
from numbering.services import seed_sequences_for_entity

class Command(BaseCommand):
    help = "Seed default numbering sequences for an Entity & Financial Year (and optional Subentity)."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--finyear", type=int, required=True, help="entityfinancialyear ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional subentity ID")
        parser.add_argument("--start", type=int, default=1, help="Starting display number (default 1)")
        parser.add_argument("--intstart", type=int, default=1, help="Starting integer counter (default 1)")
        parser.add_argument("--yearly", action="store_true", help="Force yearly reset")
        parser.add_argument("--monthly", action="store_true", help="Force monthly reset")
        parser.add_argument("--none", action="store_true", help="Disable resets")
        parser.add_argument("--preview", action="store_true", help="Preview only (no write)")

    @transaction.atomic
    def handle(self, *args, **opts):
        ent_id = opts["entity"]
        fy_id  = opts["finyear"]
        sub_id = opts.get("subentity")

        try:
            ent = Entity.objects.get(id=ent_id)
        except Entity.DoesNotExist:
            raise CommandError(f"Entity id={ent_id} not found.")

        try:
            fin = entityfinancialyear.objects.get(id=fy_id)
        except entityfinancialyear.DoesNotExist:
            raise CommandError(f"entityfinancialyear id={fy_id} not found.")

        se = None
        if sub_id:
            try:
                se = SubEntity.objects.get(id=sub_id)
            except SubEntity.DoesNotExist:
                raise CommandError(f"subentity id={sub_id} not found.")

        override = None
        if opts["yearly"]:
            override = "yearly"
        elif opts["monthly"]:
            override = "monthly"
        elif opts["none"]:
            override = "none"

        created, skipped, msg = seed_sequences_for_entity(
            entity=ent, finyear=fin, subentity=se,
            start=opts["start"], intstart=opts["intstart"], override_reset=override
        )

        if opts["preview"]:
            raise CommandError(f"(Preview) {msg}; would create={created}, skip={skipped}")

        self.stdout.write(self.style.SUCCESS(f"{msg}; created={created}, skipped={skipped}"))
