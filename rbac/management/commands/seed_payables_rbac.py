from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from rbac.models import Permission, Role
from rbac.services import RoleTemplateService


class Command(BaseCommand):
    help = "Seed the payables RBAC role for one entity or all active entities."

    PAYABLE_PERMISSION_CODES = (
        "reports.payables.view",
        "reports.vendoroutstanding.view",
        "reports.accountspayableaging.view",
        "reports.purchasebook.view",
        "reports.vendorledgerstatement.view",
        "reports.vendorsettlementhistory.view",
        "reports.vendornoteregister.view",
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Seed payables RBAC for a single entity id.")
        parser.add_argument("--all-entities", action="store_true", help="Seed payables RBAC for all active entities.")

    def _ensure_payables_permissions(self):
        touched = 0
        for code in self.PAYABLE_PERMISSION_CODES:
            module, resource, action = code.split(".", 2)
            permission, created = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "name": code.replace(".", " ").title(),
                    "module": module,
                    "resource": resource,
                    "action": action,
                    "scope_type": Permission.SCOPE_ENTITY,
                    "is_system_defined": True,
                    "isactive": True,
                    "metadata": {"seed": "payables_rbac_seed"},
                },
            )
            if not permission.isactive:
                permission.isactive = True
                permission.save(update_fields=["isactive", "updated_at"])
            touched += 1
        return touched

    def _upsert_payables_role(self, *, entity, actor):
        role, created = Role.objects.get_or_create(
            entity=entity,
            code="payables_user",
            defaults={
                "name": "Payables User",
                "description": "Core accounts payable reporting access.",
                "role_level": Role.LEVEL_ENTITY,
                "is_system_role": False,
                "is_assignable": True,
                "priority": 70,
                "createdby": actor,
                "isactive": True,
                "metadata": {"seed": "payables_rbac_seed", "template": "payables_user"},
            },
        )
        role.name = "Payables User"
        role.description = "Core accounts payable reporting access."
        role.role_level = Role.LEVEL_ENTITY
        role.is_system_role = False
        role.is_assignable = True
        role.priority = 70
        role.isactive = True
        role.metadata = {**(role.metadata or {}), "seed": "payables_rbac_seed", "template": "payables_user"}
        if actor and not role.createdby_id:
            role.createdby = actor
        role.save()
        RoleTemplateService.apply_template(role, "payables_user", [], actor=actor)
        return role, created

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        all_entities = options.get("all_entities")

        if entity_id and all_entities:
            raise CommandError("Use either --entity-id or --all-entities, not both.")
        if not entity_id and not all_entities:
            raise CommandError("Provide --entity-id or --all-entities.")

        if entity_id:
            entities = Entity.objects.filter(id=entity_id, isactive=True)
            if not entities.exists():
                raise CommandError(f"Active entity not found for entity_id={entity_id}.")
        else:
            entities = Entity.objects.filter(isactive=True).order_by("id")

        permission_count = self._ensure_payables_permissions()
        created_count = 0
        updated_count = 0

        for entity in entities:
            actor = getattr(entity, "createdby", None)
            role, created = self._upsert_payables_role(entity=entity, actor=actor)
            created_count += 1 if created else 0
            updated_count += 0 if created else 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded payables RBAC role for entity={entity.id} role_id={role.id} created={created}."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. permissions={permission_count} entities={entities.count()} created={created_count} updated={updated_count}."
            )
        )
