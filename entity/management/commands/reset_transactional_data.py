from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import FileField, Model, QuerySet

from entity.models import Entity, EntityFinancialYear, SubEntity


@dataclass(frozen=True)
class CleanupSpec:
    label: str
    app_label: str
    model_name: str
    entity_field: str = "entity_id"
    entityfin_field: str = "entityfinid_id"
    subentity_field: str = "subentity_id"
    cleanup_files: bool = False


class Command(BaseCommand):
    help = (
        "Delete transactional data for a specific entity/entityfinid/subentity scope. "
        "Masters, settings, RBAC, numbering, and other setup data are preserved."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--entityfinid", type=int, required=True, help="Entity financial year ID")
        parser.add_argument(
            "--subentity",
            type=int,
            required=True,
            help="Subentity ID. Use 0 for root-scoped records where subentity is null.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview how many rows will be deleted without making changes.",
        )

    def handle(self, *args, **options):
        entity_id = int(options["entity"])
        entityfinid_id = int(options["entityfinid"])
        raw_subentity_id = int(options["subentity"])
        subentity_id = None if raw_subentity_id == 0 else raw_subentity_id
        dry_run = bool(options["dry_run"])

        entity = Entity.objects.filter(pk=entity_id).only("id", "entityname").first()
        if not entity:
            raise CommandError(f"Entity {entity_id} does not exist.")

        entity_fin = EntityFinancialYear.objects.filter(pk=entityfinid_id, entity_id=entity_id).only("id").first()
        if not entity_fin:
            raise CommandError(
                f"EntityFinancialYear {entityfinid_id} does not belong to entity {entity_id}."
            )

        if subentity_id is not None:
            subentity = SubEntity.objects.filter(pk=subentity_id, entity_id=entity_id).only("id").first()
            if not subentity:
                raise CommandError(f"SubEntity {subentity_id} does not belong to entity {entity_id}.")

        specs = self._build_specs()
        previews: list[tuple[CleanupSpec, int]] = []

        for spec in specs:
            qs = self._scoped_queryset(spec, entity_id, entityfinid_id, subentity_id)
            previews.append((spec, qs.count()))

        total_rows = sum(count for _, count in previews)

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Transactional data reset scope"))
        self.stdout.write(f"- Entity: {entity_id} ({getattr(entity, 'entityname', '')})")
        self.stdout.write(f"- Entity FY: {entityfinid_id}")
        self.stdout.write(f"- Subentity: {'root/null' if subentity_id is None else subentity_id}")
        self.stdout.write("")

        for spec, count in previews:
            self.stdout.write(f"{spec.label}: {count}")

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"Total rows matched: {total_rows}"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete. No data was deleted."))
            return

        with transaction.atomic():
            for spec, count in previews:
                if count == 0:
                    continue
                qs = self._scoped_queryset(spec, entity_id, entityfinid_id, subentity_id)
                deleted = self._delete_queryset(
                    qs,
                    cleanup_files=spec.cleanup_files,
                    spec=spec,
                )
                self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} rows from {spec.label}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Transactional data reset completed successfully."))

    def _build_specs(self) -> list[CleanupSpec]:
        return [
            CleanupSpec(
                "Purchase attachments",
                "purchase",
                "PurchaseAttachment",
                entity_field="header__entity_id",
                entityfin_field="header__entityfinid_id",
                subentity_field="header__subentity_id",
                cleanup_files=True,
            ),
            CleanupSpec(
                "Purchase Form16A official documents",
                "purchase",
                "PurchaseStatutoryForm16AOfficialDocument",
                entity_field="filing__entity_id",
                entityfin_field="filing__entityfinid_id",
                subentity_field="filing__subentity_id",
                cleanup_files=True,
            ),
            CleanupSpec(
                "Purchase Form16A certificate documents",
                "purchase",
                "PurchaseStatutoryForm16ACertificateDocument",
                entity_field="filing__entity_id",
                entityfin_field="filing__entityfinid_id",
                subentity_field="filing__subentity_id",
                cleanup_files=True,
            ),
            CleanupSpec(
                "Purchase Form16A deductee documents",
                "purchase",
                "PurchaseStatutoryForm16ADeducteeDocument",
                entity_field="filing__entity_id",
                entityfin_field="filing__entityfinid_id",
                subentity_field="filing__subentity_id",
                cleanup_files=True,
            ),
            CleanupSpec("Purchase statutory returns", "purchase", "PurchaseStatutoryReturn"),
            CleanupSpec("Purchase statutory challans", "purchase", "PurchaseStatutoryChallan"),
            CleanupSpec("GSTR-2B import batches", "purchase", "Gstr2bImportBatch"),
            CleanupSpec("Payment vouchers", "payments", "PaymentVoucherHeader"),
            CleanupSpec("Receipt vouchers", "receipts", "ReceiptVoucherHeader"),
            CleanupSpec("Journal/cash/bank vouchers", "vouchers", "VoucherHeader"),
            CleanupSpec("Vendor settlements", "purchase", "VendorSettlement"),
            CleanupSpec("Customer settlements", "sales", "CustomerSettlement"),
            CleanupSpec("Vendor advances", "purchase", "VendorAdvanceBalance"),
            CleanupSpec("Customer advances", "sales", "CustomerAdvanceBalance"),
            CleanupSpec(
                "Purchase ITC actions",
                "purchase",
                "PurchaseItcAction",
                entity_field="header__entity_id",
                entityfin_field="header__entityfinid_id",
                subentity_field="header__subentity_id",
            ),
            CleanupSpec(
                "Sales e-invoice artifacts",
                "sales",
                "SalesEInvoice",
                entity_field="invoice__entity_id",
                entityfin_field="invoice__entityfinid_id",
                subentity_field="invoice__subentity_id",
            ),
            CleanupSpec(
                "Sales e-way artifacts",
                "sales",
                "SalesEWayBill",
                entity_field="invoice__entity_id",
                entityfin_field="invoice__entityfinid_id",
                subentity_field="invoice__subentity_id",
            ),
            CleanupSpec(
                "Sales compliance action log",
                "sales",
                "SalesComplianceActionLog",
                entity_field="invoice__entity_id",
                entityfin_field="invoice__entityfinid_id",
                subentity_field="invoice__subentity_id",
            ),
            CleanupSpec(
                "Sales compliance exception queue",
                "sales",
                "SalesComplianceExceptionQueue",
                entity_field="invoice__entity_id",
                entityfin_field="invoice__entityfinid_id",
                subentity_field="invoice__subentity_id",
            ),
            CleanupSpec("Purchase invoices/notes", "purchase", "PurchaseInvoiceHeader"),
            CleanupSpec("Sales invoices/notes", "sales", "SalesInvoiceHeader"),
            CleanupSpec("Vendor open items", "purchase", "VendorBillOpenItem"),
            CleanupSpec("Customer open items", "sales", "CustomerBillOpenItem"),
            CleanupSpec("Posting inventory moves", "posting", "InventoryMove", entityfin_field="entityfin_id"),
            CleanupSpec("Posting journal lines", "posting", "JournalLine", entityfin_field="entityfin_id"),
            CleanupSpec("Posting entries", "posting", "Entry", entityfin_field="entityfin_id"),
            CleanupSpec("Posting batches", "posting", "PostingBatch", entityfin_field="entityfin_id"),
        ]

    def _scoped_queryset(
        self,
        spec: CleanupSpec,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
    ) -> QuerySet:
        model = apps.get_model(spec.app_label, spec.model_name)
        filters = {
            spec.entity_field: entity_id,
            spec.entityfin_field: entityfinid_id,
            spec.subentity_field: subentity_id,
        }
        return model.objects.filter(**filters)

    def _delete_queryset(self, queryset: QuerySet, *, cleanup_files: bool, spec: CleanupSpec) -> int:
        model: type[Model] = queryset.model

        if spec.app_label == "purchase" and spec.model_name == "PurchaseInvoiceHeader":
            return self._delete_purchase_headers(queryset)

        if spec.app_label == "sales" and spec.model_name == "SalesInvoiceHeader":
            return self._delete_sales_headers(queryset)

        if cleanup_files:
            file_fields = [
                field for field in model._meta.get_fields()
                if isinstance(field, FileField) and getattr(field, "attname", None)
            ]
            if file_fields:
                for row in queryset.iterator(chunk_size=200):
                    for field in file_fields:
                        file_value = getattr(row, field.name, None)
                        if file_value:
                            file_value.delete(save=False)

        deleted_count, _ = queryset.delete()
        return deleted_count

    def _delete_purchase_headers(self, queryset: QuerySet) -> int:
        deleted_total = 0
        pending_ids = set(queryset.values_list("id", flat=True))

        while pending_ids:
            leaf_qs = queryset.model.objects.filter(id__in=pending_ids, purchase_notes__isnull=True)
            leaf_ids = list(leaf_qs.values_list("id", flat=True))
            if not leaf_ids:
                raise CommandError(
                    "Could not resolve purchase document dependency order. "
                    "Please inspect circular references in PurchaseInvoiceHeader.ref_document."
                )
            deleted_count, _ = queryset.model.objects.filter(id__in=leaf_ids).delete()
            deleted_total += deleted_count
            pending_ids.difference_update(leaf_ids)

        return deleted_total

    def _delete_sales_headers(self, queryset: QuerySet) -> int:
        deleted_total = 0
        pending_ids = set(queryset.values_list("id", flat=True))

        while pending_ids:
            leaf_qs = queryset.model.objects.filter(id__in=pending_ids, adjustment_documents__isnull=True)
            leaf_ids = list(leaf_qs.values_list("id", flat=True))
            if not leaf_ids:
                raise CommandError(
                    "Could not resolve sales document dependency order. "
                    "Please inspect circular references in SalesInvoiceHeader.original_invoice."
                )
            deleted_count, _ = queryset.model.objects.filter(id__in=leaf_ids).delete()
            deleted_total += deleted_count
            pending_ids.difference_update(leaf_ids)

        return deleted_total
