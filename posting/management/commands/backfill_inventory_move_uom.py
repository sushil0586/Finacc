from django.core.management.base import BaseCommand

from posting.services.inventory_uom_backfill import TARGET_TXN_TYPES, backfill_inventory_move_uom_base_qty


class Command(BaseCommand):
    help = "Backfill InventoryMove UOM normalization fields (uom_factor/base_qty/base_uom/ext_cost) for historical purchase and sales postings."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--txn-type",
            action="append",
            dest="txn_types",
            default=None,
            help=f"Optional repeatable txn type filter. Defaults to: {', '.join(TARGET_TXN_TYPES)}",
        )

    def handle(self, *args, **options):
        result = backfill_inventory_move_uom_base_qty(
            entity_id=options["entity_id"],
            dry_run=options["dry_run"],
            txn_types=options["txn_types"],
            limit=options["limit"],
        )

        mode = "DRY RUN" if options["dry_run"] else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"InventoryMove UOM backfill complete ({mode})."))
        self.stdout.write(f"Moves scanned: {result['moves_scanned']}")
        self.stdout.write(f"Mismatched moves: {result['mismatched_moves']}")
        self.stdout.write(f"Moves updated: {result['moves_updated']}")
        self.stdout.write(f"Skipped missing line: {result['skipped_missing_line']}")
        self.stdout.write(f"Skipped missing product: {result['skipped_missing_product']}")
        self.stdout.write(f"Skipped missing conversion: {result['skipped_missing_conversion']}")
        if result["samples"]:
            self.stdout.write("Sample mismatches:")
            for sample in result["samples"]:
                self.stdout.write(
                    f"  move={sample['move_id']} txn={sample['txn_type']}#{sample['txn_id']} "
                    f"detail={sample['detail_id']} product={sample['product_id']} "
                    f"fields={','.join(sample['fields'])} factor={sample['expected_factor']} "
                    f"base_qty={sample['expected_base_qty']}"
                )
