from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from rbac.seeding import HrmsRBACSeedService


class Command(BaseCommand):
    help = "Seed HRMS RBAC permissions, menus, and entity role mappings."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Seed HRMS roles for a single entity id.")
        parser.add_argument("--all-entities", action="store_true", help="Seed HRMS roles for all active entities.")

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        all_entities = options.get("all_entities")
        if not entity_id and not all_entities:
            raise CommandError("Pass either --entity-id <id> or --all-entities.")

        catalog = HrmsRBACSeedService.seed_global_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded HRMS RBAC catalog: {len(catalog['permissions'])} permissions, {len(catalog['menus'])} menus."
            )
        )

        entities = Entity.objects.none()
        if entity_id:
            entities = Entity.objects.filter(pk=entity_id)
            if not entities.exists():
                raise CommandError(f"Entity {entity_id} not found.")
        elif all_entities:
            entities = Entity.objects.filter(isactive=True)

        for entity in entities.iterator():
            result = HrmsRBACSeedService.seed_entity_roles(entity=entity, actor=getattr(entity, "createdby", None))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded HRMS RBAC roles for entity={entity.id}: {len(result['roles'])} roles mapped."
                )
            )
