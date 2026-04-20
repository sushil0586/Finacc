from collections import defaultdict

from django.core.management.base import BaseCommand

from catalog.models import ProductBarcode


class Command(BaseCommand):
    help = "Report duplicate barcode values within the same entity."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, default=None, help="Optional entity id to scope the audit.")

    def handle(self, *args, **options):
        entity_id = options.get("entity")
        qs = ProductBarcode.objects.exclude(entity__isnull=True).exclude(barcode__isnull=True).exclude(barcode="")
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)

        grouped = defaultdict(list)
        for row in qs.select_related("product", "entity").order_by("entity_id", "barcode", "id"):
            grouped[(row.entity_id, row.barcode)].append(row)

        duplicate_groups = [(key, rows) for key, rows in grouped.items() if len(rows) > 1]
        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS("No duplicate barcodes found within the selected scope."))
            return

        self.stdout.write(self.style.WARNING("Duplicate barcode groups found:"))
        for (entity_pk, barcode), rows in duplicate_groups:
            product_labels = ", ".join(
                f"{row.id}:{getattr(row.product, 'productname', '')}" for row in rows
            )
            self.stdout.write(f"entity={entity_pk} barcode={barcode} rows=[{product_labels}]")

