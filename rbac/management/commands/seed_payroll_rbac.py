from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from rbac.seeding import PayrollRBACSeedService


class Command(BaseCommand):
    help = "Seed payroll RBAC permissions, menus, and entity role mappings."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Seed payroll roles for a single entity id.")
        parser.add_argument("--all-entities", action="store_true", help="Seed payroll roles for all active entities.")
        parser.add_argument("--catalog-only", action="store_true", help="Seed only the global permission/menu catalog.")

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        all_entities = options.get("all_entities")
        catalog_only = options.get("catalog_only")

        if entity_id and all_entities:
            raise CommandError("Use either --entity-id or --all-entities, not both.")

        catalog = PayrollRBACSeedService.seed_global_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded payroll RBAC catalog: {len(catalog['permissions'])} permissions, {len(catalog['menus'])} menus."
            )
        )

        if catalog_only:
            return

        if entity_id:
            entities = Entity.objects.filter(id=entity_id, isactive=True)
            if not entities.exists():
                raise CommandError(f"Active entity not found for entity_id={entity_id}.")
        elif all_entities:
            entities = Entity.objects.filter(isactive=True).order_by("id")
        else:
            raise CommandError("Provide --entity-id, --all-entities, or --catalog-only.")

        for entity in entities:
            result = PayrollRBACSeedService.seed_entity_roles(entity=entity, actor=getattr(entity, "createdby", None))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded payroll RBAC roles for entity={entity.id}: {len(result['roles'])} roles mapped."
                )
            )
