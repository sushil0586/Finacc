from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, SubEntity
from gst_reconciliation.models import (
    GstImportedReturn,
    GstImportedReturnRow,
    GstMismatchReason,
    GstReconciliationItem,
    GstReconciliationRun,
)
from gst_reconciliation.services.item_workflow_service import GstReconciliationItemWorkflowService


class Command(BaseCommand):
    help = "Seed one demo GST reconciliation run for internal UAT."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True)
        parser.add_argument("--entityfinid", type=int, required=True)
        parser.add_argument("--user", type=int, required=True)
        parser.add_argument("--subentity", type=int, default=None)
        parser.add_argument("--return-period", type=str, default="2026-04")
        parser.add_argument("--gstin", type=str, default="29ABCDE1234F1Z5")

    @transaction.atomic
    def handle(self, *args, **options):
        entity = Entity.objects.filter(pk=options["entity"]).first()
        entityfin = EntityFinancialYear.objects.filter(pk=options["entityfinid"], entity_id=options["entity"]).first()
        user = User.objects.filter(pk=options["user"]).first()
        subentity = None
        if options.get("subentity"):
            subentity = SubEntity.objects.filter(pk=options["subentity"], entity_id=options["entity"]).first()
        if not entity or not entityfin or not user:
            raise CommandError("Valid entity, entityfinid, and user are required.")

        imported_return = GstImportedReturn.objects.create(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            gst_registration_gstin=options["gstin"],
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period=options["return_period"],
            source=GstImportedReturn.Source.MANUAL_ENTRY,
            status=GstImportedReturn.Status.CONSUMED,
            imported_by=user,
            imported_at=timezone.now(),
            created_by=user,
            updated_by=user,
            source_reference=f"demo:{options['return_period']}",
        )
        run = GstReconciliationRun.objects.create(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            gst_registration_gstin=options["gstin"],
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period=options["return_period"],
            period_from=date.fromisoformat(f"{options['return_period']}-01"),
            period_to=date.fromisoformat(f"{options['return_period']}-28"),
            source_mode=GstReconciliationRun.SourceMode.BOOKS_VS_IMPORTED,
            status=GstReconciliationRun.Status.IN_REVIEW,
            imported_return=imported_return,
            created_by=user,
            updated_by=user,
            reviewed_by=user,
            reviewed_at=timezone.now(),
        )

        missing_reason, _ = GstMismatchReason.objects.get_or_create(
            code="MISSING_IN_BOOKS",
            defaults={
                "category": "matching",
                "severity": "error",
                "message": "Invoice is missing in books.",
                "details_json": {},
                "created_by": user,
                "updated_by": user,
            },
        )
        tax_reason, _ = GstMismatchReason.objects.get_or_create(
            code="TOTAL_AMOUNT_MISMATCH",
            defaults={
                "category": "matching",
                "severity": "warning",
                "message": "Imported tax amount does not match books.",
                "details_json": {},
                "created_by": user,
                "updated_by": user,
            },
        )

        demo_rows = [
            ("GSTDEMO-001", "MATCHED", Decimal("1000.00"), Decimal("90.00"), "Vendor Matched"),
            ("GSTDEMO-002", "MISMATCHED", Decimal("1250.00"), Decimal("112.50"), "Vendor Mismatch"),
            ("GSTDEMO-003", "MISSING_IN_BOOKS", Decimal("900.00"), Decimal("81.00"), "Vendor Missing"),
            ("GSTDEMO-004", "IGNORED", Decimal("600.00"), Decimal("54.00"), "Vendor Ignored"),
            ("GSTDEMO-005", "MISMATCHED", Decimal("700.00"), Decimal("63.00"), "Vendor Accepted"),
        ]

        created_items = []
        for index, (invoice_number, match_status, taxable_value, tax_amount, supplier_name) in enumerate(demo_rows, start=1):
            row = GstImportedReturnRow.objects.create(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                imported_return=imported_return,
                row_no=index,
                row_hash=f"demo-{invoice_number}",
                doc_type_code="INV",
                counterparty_gstin="29SUPPLIER1234Z5",
                counterparty_gstin_normalized="29SUPPLIER1234Z5",
                counterparty_name=supplier_name,
                invoice_number=invoice_number,
                invoice_number_normalized=invoice_number,
                invoice_date=date.fromisoformat(f"{options['return_period']}-0{min(index,9)}"),
                taxable_value=taxable_value,
                cgst=tax_amount / 2,
                sgst=tax_amount / 2,
                igst=Decimal("0.00"),
                cess=Decimal("0.00"),
                total_amount=taxable_value + tax_amount,
                raw_row_json={"invoice_number": invoice_number},
                normalized_row_json={"invoice_number": invoice_number},
                created_by=user,
                updated_by=user,
            )
            item = GstReconciliationItem.objects.create(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                run=run,
                item_type=GstReconciliationItem.ItemType.INVOICE,
                direction=GstReconciliationItem.Direction.PURCHASE,
                match_key=f"{row.counterparty_gstin_normalized}|{invoice_number}",
                source_document_type="gst_imported_return_row",
                source_document_id=str(row.id),
                gstin=options["gstin"],
                counterparty_gstin=row.counterparty_gstin_normalized,
                invoice_number=invoice_number,
                invoice_date=row.invoice_date,
                doc_type_code="INV",
                taxable_value_imported=taxable_value,
                cgst_imported=tax_amount / 2,
                sgst_imported=tax_amount / 2,
                igst_imported=Decimal("0.00"),
                cess_imported=Decimal("0.00"),
                taxable_value_books=taxable_value if match_status != "MISSING_IN_BOOKS" else Decimal("0.00"),
                cgst_books=tax_amount / 2 if match_status != "MISSING_IN_BOOKS" else Decimal("0.00"),
                sgst_books=tax_amount / 2 if match_status != "MISSING_IN_BOOKS" else Decimal("0.00"),
                match_status=match_status,
                resolution_status=GstReconciliationItemWorkflowService.operational_status_for_match_status(match_status),
                match_confidence_score=Decimal("98.00") if match_status == "MATCHED" else Decimal("42.00"),
                mismatch_count=0 if match_status == "MATCHED" else 1,
                reviewer_note="Seeded for UAT",
                created_by=user,
                updated_by=user,
            )
            created_items.append(item)

        created_items[1].mismatch_reasons.add(tax_reason)
        created_items[2].mismatch_reasons.add(missing_reason)
        created_items[4].mismatch_reasons.add(tax_reason)
        GstReconciliationItemWorkflowService.ignore_item(item=created_items[3], user=user, note="Ignored for demo")
        GstReconciliationItemWorkflowService.accept_mismatch(item=created_items[4], user=user, note="Accepted mismatch for demo")

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo GST reconciliation run {run.id} created with {len(created_items)} items for entity {entity.id}."
            )
        )
