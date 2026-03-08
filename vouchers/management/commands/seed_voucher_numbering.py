from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from numbering.models import DocumentNumberSeries, DocumentType

VOUCHER_TYPE_CONFIG = {
    "CASH": ("CASH_VOUCHER", "Cash Voucher", "CV"),
    "BANK": ("BANK_VOUCHER", "Bank Voucher", "BV"),
    "JOURNAL": ("JOURNAL_VOUCHER", "Journal Voucher", "JV"),
}


class Command(BaseCommand):
    help = "Seed vouchers document types + numbering series."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True)
        parser.add_argument("--entityfinid", type=int, required=True)
        parser.add_argument("--subentity", type=int, default=None)
        parser.add_argument("--voucher-type", type=str, choices=sorted(VOUCHER_TYPE_CONFIG.keys()), default=None)
        parser.add_argument("--start", type=int, default=1)
        parser.add_argument("--padding", type=int, default=5)
        parser.add_argument("--reset", type=str, default="yearly", choices=["none", "monthly", "yearly"])

    @transaction.atomic
    def handle(self, *args, **options):
        entity_id = int(options["entity"])
        entityfinid_id = int(options["entityfinid"])
        subentity_id = options.get("subentity")
        start = int(options.get("start") or 1)
        padding = int(options.get("padding") or 5)
        reset = options.get("reset") or "yearly"
        voucher_type = options.get("voucher_type")
        if start < 1:
            raise CommandError("--start must be >= 1")
        targets = {voucher_type: VOUCHER_TYPE_CONFIG[voucher_type]} if voucher_type else VOUCHER_TYPE_CONFIG

        for _, (doc_key, label, default_code) in targets.items():
            doc_type, _ = DocumentType.objects.get_or_create(
                module="vouchers",
                doc_key=doc_key,
                defaults={"name": label, "default_code": default_code, "is_active": True},
            )
            changed = False
            if doc_type.name != label:
                doc_type.name = label
                changed = True
            if doc_type.default_code != default_code:
                doc_type.default_code = default_code
                changed = True
            if not doc_type.is_active:
                doc_type.is_active = True
                changed = True
            if changed:
                doc_type.save()

            series, _ = DocumentNumberSeries.objects.get_or_create(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type=doc_type,
                doc_code=default_code,
                defaults={
                    "prefix": default_code,
                    "suffix": "",
                    "starting_number": start,
                    "current_number": start,
                    "number_padding": padding,
                    "reset_frequency": reset,
                    "include_year": True,
                    "include_month": False,
                    "separator": "-",
                    "custom_format": "{doc_code}-{year}-{number}",
                    "is_active": True,
                },
            )
            series_changed = False
            if series.prefix != default_code:
                series.prefix = default_code
                series_changed = True
            if series.number_padding != padding:
                series.number_padding = padding
                series_changed = True
            if series.reset_frequency != reset:
                series.reset_frequency = reset
                series_changed = True
            if not series.is_active:
                series.is_active = True
                series_changed = True
            if series_changed:
                series.save()
            self.stdout.write(self.style.SUCCESS(f"Seeded {doc_key} ({default_code}) for entity={entity_id}, fin={entityfinid_id}, sub={subentity_id}"))
