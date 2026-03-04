from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from numbering.models import DocumentType, DocumentNumberSeries


class Command(BaseCommand):
    help = "Seed payments document type + numbering series for PAYMENT_VOUCHER (PPV)."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--entityfinid", type=int, required=True, help="Entity Financial Year ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional Subentity ID")
        parser.add_argument("--doc-code", type=str, default="PPV", help="Document code (default PPV)")
        parser.add_argument("--prefix", type=str, default="PPV", help="Series prefix (default PPV)")
        parser.add_argument("--start", type=int, default=1, help="Starting/current number (default 1)")
        parser.add_argument("--padding", type=int, default=5, help="Number padding (default 5)")
        parser.add_argument("--reset", type=str, default="yearly", choices=["none", "monthly", "yearly"], help="Reset frequency")

    @transaction.atomic
    def handle(self, *args, **options):
        entity_id = int(options["entity"])
        entityfinid_id = int(options["entityfinid"])
        subentity_id = options.get("subentity")
        doc_code = (options.get("doc_code") or "PPV").strip().upper()
        prefix = (options.get("prefix") or doc_code).strip()
        start = int(options.get("start") or 1)
        padding = int(options.get("padding") or 5)
        reset = options.get("reset") or "yearly"

        if start < 1:
            raise CommandError("--start must be >= 1")
        if padding < 0:
            raise CommandError("--padding must be >= 0")

        doc_type, dt_created = DocumentType.objects.get_or_create(
            module="payments",
            doc_key="PAYMENT_VOUCHER",
            defaults={
                "name": "Payment Voucher",
                "default_code": doc_code,
                "is_active": True,
            },
        )

        # Keep default_code aligned if doc type already existed with blank/default mismatch.
        updates = []
        if not doc_type.default_code:
            doc_type.default_code = doc_code
            updates.append("default_code")
        if not doc_type.is_active:
            doc_type.is_active = True
            updates.append("is_active")
        if updates:
            doc_type.save(update_fields=updates + ["updated_at"])

        series, created = DocumentNumberSeries.objects.get_or_create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type.id,
            doc_code=doc_code,
            defaults={
                "prefix": prefix,
                "suffix": "",
                "starting_number": start,
                "current_number": start,
                "number_padding": padding,
                "include_year": True,
                "include_month": False,
                "separator": "-",
                "reset_frequency": reset,
                "is_active": True,
            },
        )

        if not created:
            changed = []
            if not series.is_active:
                series.is_active = True
                changed.append("is_active")
            if not series.prefix:
                series.prefix = prefix
                changed.append("prefix")
            if changed:
                series.save(update_fields=changed + ["updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"PAYMENT_VOUCHER seeded: DocumentType(id={doc_type.id}, created={dt_created}), "
                f"Series(id={series.id}, created={created})"
            )
        )
