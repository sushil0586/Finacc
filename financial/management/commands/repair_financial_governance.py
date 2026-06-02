from django.core.management.base import BaseCommand, CommandError

from entity.models import Entity
from financial.seeding import FinancialSeedService


class Command(BaseCommand):
    help = "Repair ledger/account governance drift using seeded accounting governance rules."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Entity id to repair.")
        parser.add_argument("--all", action="store_true", help="Repair all entities.")
        parser.add_argument("--template-code", default="indian_accounting_final", help="Financial template code to use.")
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing them.")
        parser.add_argument("--report-rows", action="store_true", help="Print row-level repair details.")
        parser.add_argument("--row-limit", type=int, default=50, help="Maximum row-level items to print.")

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        repair_all = bool(options.get("all"))
        dry_run = bool(options.get("dry_run"))
        report_rows = bool(options.get("report_rows"))
        row_limit = max(1, int(options.get("row_limit") or 50))
        template_code = options.get("template_code") or "indian_accounting_final"

        if not entity_id and not repair_all:
            raise CommandError("Provide --entity-id or use --all.")

        qs = Entity.objects.all()
        if entity_id:
            qs = qs.filter(pk=entity_id)
        if not qs.exists():
            raise CommandError("No matching entities found.")

        mode = "DRY RUN" if dry_run else "APPLIED"
        for entity in qs.iterator():
            summary = FinancialSeedService.reconcile_entity(
                entity=entity,
                actor=None,
                template_code=template_code,
                dry_run=dry_run,
                include_rows=report_rows,
                row_limit=row_limit,
            )
            self.stdout.write(self.style.SUCCESS(f"Governance repair complete ({mode}) for entity {entity.id} - {entity.entityname}"))
            for key, value in summary.items():
                if key == "touched_rows":
                    continue
                self.stdout.write(f"  {key}: {value}")
            if report_rows:
                for row in summary.get("touched_rows", []):
                    self.stdout.write(
                        "  row:"
                        f" ledger_id={row['ledger_id']}"
                        f" code={row['ledger_code']}"
                        f" name={row['ledger_name']}"
                        f" mode={row['management_mode']}"
                        f" changes={','.join(row['changes'])}"
                    )
