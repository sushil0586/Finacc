from io import StringIO
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from Authentication.models import User
from catalog.models import Product, ProductCategory, ProductUomConversion, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity
from posting.models import Entry, EntryStatus, InventoryMove, PostingBatch, TxnType
from purchase.models import PurchaseInvoiceHeader, PurchaseInvoiceLine
from sales.models import SalesInvoiceHeader, SalesInvoiceLine


class InventoryMoveUomBackfillCommandTests(TestCase):
    def setUp(self):
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"inv-uom-backfill-{suffix}",
            email=f"inv-uom-backfill-{suffix}@example.com",
            password="pass123",
            email_verified=True,
        )
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Inventory Backfill Entity",
            legalname="Inventory Backfill Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.location = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name="Warehouse A",
            code="WH-A",
            address="Industrial Area",
            city="Ludhiana",
            state="Punjab",
            pincode="141001",
            is_active=True,
        )
        self.category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname="Finished Goods",
            level=1,
        )
        self.gms = UnitOfMeasure.objects.create(entity=self.entity, code="GMS", description="Grams", uqc="GMS")
        self.kg = UnitOfMeasure.objects.create(entity=self.entity, code="KG", description="Kilograms", uqc="KGS")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Flour",
            sku="FLR-001",
            productdesc="Wheat flour",
            productcategory=self.category,
            base_uom=self.gms,
            is_service=False,
        )
        ProductUomConversion.objects.create(
            product=self.product,
            from_uom=self.kg,
            to_uom=self.gms,
            factor=Decimal("1000"),
        )

    def _make_purchase_move(self) -> InventoryMove:
        header = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            bill_date=date(2025, 4, 10),
            posting_date=date(2025, 4, 10),
            doc_code="PINV",
            purchase_number="PINV-1001",
            grand_total=Decimal("500.00"),
            total_taxable=Decimal("500.00"),
        )
        line = PurchaseInvoiceLine.objects.create(
            header=header,
            line_no=1,
            product=self.product,
            uom=self.kg,
            qty=Decimal("2.0000"),
            free_qty=Decimal("0.0000"),
            rate=Decimal("250.00"),
            taxable_value=Decimal("500.00"),
            line_total=Decimal("500.00"),
        )
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            voucher_no=header.purchase_number,
            created_by=self.user,
            is_active=True,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            voucher_no=header.purchase_number,
            voucher_date=header.bill_date,
            posting_date=header.posting_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Purchase posting",
            created_by=self.user,
        )
        return InventoryMove.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            detail_id=line.id,
            voucher_no=header.purchase_number,
            product=self.product,
            location=self.location,
            uom=self.kg,
            base_uom=self.gms,
            qty=Decimal("2.0000"),
            uom_factor=Decimal("1"),
            base_qty=Decimal("2.0000"),
            unit_cost=Decimal("0.2500"),
            ext_cost=Decimal("0.50"),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
            destination_location=self.location,
            movement_reason="purchase",
            posting_date=header.posting_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

    def _make_sales_move(self) -> InventoryMove:
        header = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            bill_date=date(2025, 4, 12),
            posting_date=date(2025, 4, 12),
            doc_code="SINV",
            invoice_number="SINV-1001",
            grand_total=Decimal("300.00"),
            total_taxable_value=Decimal("300.00"),
            affects_inventory=True,
        )
        line = SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=header,
            line_no=1,
            product=self.product,
            uom=self.kg,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("300.0000"),
            taxable_value=Decimal("300.00"),
            line_total=Decimal("300.00"),
        )
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            created_by=self.user,
            is_active=True,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            voucher_date=header.bill_date,
            posting_date=header.posting_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Sales posting",
            created_by=self.user,
        )
        return InventoryMove.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            detail_id=line.id,
            voucher_no=header.invoice_number,
            product=self.product,
            location=self.location,
            uom=self.kg,
            base_uom=self.gms,
            qty=Decimal("1.0000"),
            uom_factor=Decimal("1"),
            base_qty=Decimal("1.0000"),
            unit_cost=Decimal("0.2500"),
            ext_cost=Decimal("0.25"),
            cost_source=InventoryMove.CostSource.FIFO,
            move_type=InventoryMove.MoveType.OUT,
            movement_nature=InventoryMove.MovementNature.SALE,
            source_location=self.location,
            movement_reason="sale",
            posting_date=header.posting_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

    def test_backfill_dry_run_does_not_write(self):
        move = self._make_purchase_move()

        out = StringIO()
        call_command("backfill_inventory_move_uom", entity_id=self.entity.id, dry_run=True, stdout=out)

        move.refresh_from_db()
        self.assertEqual(move.uom_factor, Decimal("1"))
        self.assertEqual(move.base_qty, Decimal("2.0000"))
        self.assertEqual(move.ext_cost, Decimal("0.50"))
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("Mismatched moves: 1", out.getvalue())
        self.assertIn("Moves updated: 0", out.getvalue())

    def test_backfill_updates_purchase_and_sales_moves(self):
        purchase_move = self._make_purchase_move()
        sales_move = self._make_sales_move()

        out = StringIO()
        call_command("backfill_inventory_move_uom", entity_id=self.entity.id, stdout=out)

        purchase_move.refresh_from_db()
        sales_move.refresh_from_db()

        self.assertEqual(purchase_move.uom_factor, Decimal("1000.00000000"))
        self.assertEqual(purchase_move.base_qty, Decimal("2000.0000"))
        self.assertEqual(purchase_move.ext_cost, Decimal("500.00"))

        self.assertEqual(sales_move.uom_factor, Decimal("1000.00000000"))
        self.assertEqual(sales_move.base_qty, Decimal("1000.0000"))
        self.assertEqual(sales_move.ext_cost, Decimal("250.00"))

        output = out.getvalue()
        self.assertIn("APPLIED", output)
        self.assertIn("Mismatched moves: 2", output)
        self.assertIn("Moves updated: 2", output)
