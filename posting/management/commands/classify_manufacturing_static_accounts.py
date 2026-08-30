from __future__ import annotations

from django.core.management.base import BaseCommand

from posting.services.manufacturing_static_accounts import classify_manufacturing_static_account_heads


class Command(BaseCommand):
    help = "Attach report account heads to manufacturing static-account ledgers for an entity."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--code", action="append", help="Limit to one or more manufacturing static-account codes.")
        parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag the command is a dry run.")

    def handle(self, *args, **options):
        summary = classify_manufacturing_static_account_heads(
            entity_id=options["entity_id"],
            codes=options.get("code") or None,
            apply_changes=bool(options.get("apply")),
        )
        mode_label = "APPLIED" if options.get("apply") else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS(f"{mode_label} manufacturing static-account classification for entity {options['entity_id']}."))
        self.stdout.write(
            " ".join(
                [
                    f"types_created={summary['types_created']}",
                    f"heads_created={summary['heads_created']}",
                    f"ledgers_updated={summary['ledgers_updated']}",
                ]
            )
        )
        if summary["touched_codes"]:
            self.stdout.write("Touched codes:")
            for code in summary["touched_codes"]:
                self.stdout.write(f"  - {code}")
        if summary["missing_mappings"]:
            self.stdout.write(self.style.WARNING("Missing mappings:"))
            for code in summary["missing_mappings"]:
                self.stdout.write(f"  - {code}")
