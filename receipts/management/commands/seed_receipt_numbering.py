from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from entity.models import SubEntity
from numbering.models import DocumentType, DocumentNumberSeries


class Command(BaseCommand):
    help = "Seed payments document type + numbering series for RECEIPT_VOUCHER (RV)."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--entityfinid", type=int, required=True, help="Entity Financial Year ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional Subentity ID")
        parser.add_argument("--doc-code", type=str, default="RV", help="Document code (default RV)")
        parser.add_argument("--prefix", type=str, default="RV", help="Series prefix (default RV)")
        parser.add_argument("--start", type=int, default=1, help="Starting/current number (default 1)")
        parser.add_argument("--padding", type=int, default=5, help="Number padding (default 5)")
        parser.add_argument("--reset", type=str, default="yearly", choices=["none", "monthly", "yearly"], help="Reset frequency")

    @transaction.atomic
    def handle(self, *args, **options):
        entity_id = int(options["entity"])
        entityfinid_id = int(options["entityfinid"])
        subentity_id = options.get("subentity")
        doc_code = (options.get("doc_code") or "RV").strip().upper()
        prefix = (options.get("prefix") or doc_code).strip()
        start = int(options.get("start") or 1)
        padding = int(options.get("padding") or 5)
        reset = options.get("reset") or "yearly"

        if start < 1:
            raise CommandError("--start must be >= 1")
        if padding < 0:
            raise CommandError("--padding must be >= 0")

        doc_type, dt_created = DocumentType.objects.get_or_create(
            module="receipts",
            doc_key="RECEIPT_VOUCHER",
            defaults={
                "name": "Receipt Voucher",
                "default_code": doc_code,
                "is_active": True,
            },
        )

        updates = []
        if doc_type.name != "Receipt Voucher":
            doc_type.name = "Receipt Voucher"
            updates.append("name")
        if doc_type.default_code != doc_code:
            doc_type.default_code = doc_code
            updates.append("default_code")
        if not doc_type.is_active:
            doc_type.is_active = True
            updates.append("is_active")
        if updates:
            doc_type.save(update_fields=[*updates, "updated_at"])

        touched = []
        for scope_subentity_id in self._subentity_scope_ids(entity_id=entity_id, subentity_id=subentity_id):
            series, created = DocumentNumberSeries.objects.get_or_create(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=scope_subentity_id,
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

            changed = []
            if not series.is_active:
                series.is_active = True
                changed.append("is_active")
            if series.prefix != prefix:
                series.prefix = prefix
                changed.append("prefix")
            if series.number_padding != padding:
                series.number_padding = padding
                changed.append("number_padding")
            if series.reset_frequency != reset:
                series.reset_frequency = reset
                changed.append("reset_frequency")
            if changed:
                series.save(update_fields=[*changed, "updated_at"])

            touched.append(f"{scope_subentity_id if scope_subentity_id is not None else 'root'}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"RECEIPT_VOUCHER seeded: DocumentType(id={doc_type.id}, created={dt_created}), "
                    f"Series(id={series.id}, created={created}), sub={scope_subentity_id}"
                )
            )

        self.stdout.write(self.style.SUCCESS("Receipt numbering scopes touched -> " + ", ".join(touched)))

    @staticmethod
    def _subentity_scope_ids(*, entity_id: int, subentity_id: int | None) -> list[int | None]:
        if subentity_id is not None:
            return [subentity_id]
        return [None, *list(SubEntity.objects.filter(entity_id=entity_id, isactive=True).order_by("id").values_list("id", flat=True))]
