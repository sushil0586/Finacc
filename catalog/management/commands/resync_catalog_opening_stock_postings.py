from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from catalog.models import OpeningStockByLocation
from catalog.services.opening_stock_posting import sync_catalog_opening_stock_posting


class Command(BaseCommand):
    help = (
        "Rebuild posting rows for catalog product opening-stock records so they carry "
        "the correct financial year, inventory move, and balanced journal lines."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Restrict to one entity.")
        parser.add_argument("--product-id", type=int, help="Restrict to one product.")
        parser.add_argument("--row-id", type=int, help="Restrict to one opening stock row.")
        parser.add_argument("--limit", type=int, help="Process at most N rows.")
        parser.add_argument("--dry-run", action="store_true", help="Preview rows without reposting.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Stop on the first reposting error instead of continuing.",
        )

    def handle(self, *args, **options):
        queryset = (
            OpeningStockByLocation.objects
            .select_related("entity", "product", "branch", "godown")
            .order_by("entity_id", "product_id", "as_of_date", "id")
        )

        if options.get("entity_id"):
            queryset = queryset.filter(entity_id=options["entity_id"])
        if options.get("product_id"):
            queryset = queryset.filter(product_id=options["product_id"])
        if options.get("row_id"):
            queryset = queryset.filter(pk=options["row_id"])
        if options.get("limit"):
            queryset = queryset[: max(int(options["limit"]), 0)]

        rows = list(queryset)
        if not rows:
            self.stdout.write(self.style.WARNING("No opening stock rows matched the selection."))
            return

        processed = 0
        failed = 0
        for row in rows:
            label = (
                f"row={row.id} entity={row.entity_id} product={row.product_id} "
                f"branch={row.branch_id} godown={row.godown_id} date={row.as_of_date}"
            )
            if options["dry_run"]:
                self.stdout.write(f"[DRY-RUN] {label}")
                processed += 1
                continue

            try:
                entry = sync_catalog_opening_stock_posting(row)
            except Exception as exc:
                failed += 1
                message = f"Failed to resync {label}: {exc}"
                if options["strict"]:
                    raise CommandError(message) from exc
                self.stderr.write(self.style.ERROR(message))
                continue

            processed += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Resynced {label} -> entry={getattr(entry, 'id', None)}"
                )
            )

        summary = f"Processed {processed} row(s)"
        if failed:
            summary += f", failed {failed}"
        self.stdout.write(self.style.SUCCESS(summary) if not failed else self.style.WARNING(summary))
