from __future__ import annotations

from django.core.management.base import BaseCommand

from purchase.services.asset_purchase_posting_repair import repair_posted_asset_purchase_postings


class Command(BaseCommand):
    help = (
        "Repair historical posted asset-purchase journal lines and linked CWIP assets so they align "
        "with the asset category CWIP/asset ledger mapping. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, dest="entity_id")
        parser.add_argument("--subentity-id", type=int, dest="subentity_id")
        parser.add_argument("--header-id", type=int, dest="header_id")
        parser.add_argument("--purchase-number", dest="purchase_number")
        parser.add_argument("--apply", action="store_true", dest="apply")

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))
        summary = repair_posted_asset_purchase_postings(
            entity_id=options.get("entity_id"),
            subentity_id=options.get("subentity_id"),
            header_id=options.get("header_id"),
            purchase_number=options.get("purchase_number"),
            apply=apply,
        )

        mode = "APPLY" if apply else "DRY RUN"
        self.stdout.write(self.style.SUCCESS(f"Asset purchase posting repair ({mode})"))
        self.stdout.write(f"  scanned_lines: {summary['scanned_lines']}")
        self.stdout.write(f"  flagged_lines: {summary['flagged_lines']}")
        self.stdout.write(f"  journal_repairs: {summary['journal_repairs']}")
        self.stdout.write(f"  asset_repairs: {summary['asset_repairs']}")

        for row in summary["rows"]:
            if not (row.note or row.needs_journal_repair or row.needs_asset_repair):
                continue
            self.stdout.write(
                "  row:"
                f" purchase={row.purchase_number}"
                f" line={row.line_no}"
                f" entry_id={row.entry_id}"
                f" asset={row.asset_code or '-'}"
                f" expected={row.expected_ledger_name or row.expected_ledger_id}"
                f" current_journal={row.current_journal_ledger_name or row.current_journal_ledger_id or '-'}"
                f" current_asset={row.current_asset_ledger_name or row.current_asset_ledger_id or '-'}"
                f" journal_fix={row.needs_journal_repair}"
                f" asset_fix={row.needs_asset_repair}"
                f" actionable={row.actionable}"
                f" note={row.note or '-'}"
            )
