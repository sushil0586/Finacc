from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import HsnSac, Product, ProductCategory, ProductGstRate, ProductPlanning, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from posting.models import Entry, EntryStatus, InventoryMove, PostingBatch, TxnType
from reports.services.inventory.stock_summary import build_inventory_stock_summary
from reports.api.inventory_views import _format_scope_date


@override_settings(ROOT_URLCONF='FA.urls', AUTH_PASSWORD_VALIDATORS=[])
class InventoryReportAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f'inventory-report-user-{suffix}',
            email=f'inventory-{suffix}@example.com',
            password='pass123',
        )
        self.client.force_authenticate(user=self.user)
        self.gst_type = GstRegistrationType.objects.create(Name='Regular', Description='Regular')
        self.entity = Entity.objects.create(
            entityname='Inventory Entity',
            legalname='Inventory Entity Pvt Ltd',
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname='Branch A')
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc='FY 2025-26',
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.godown = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Main Warehouse',
            code='WH-01',
            address='Industrial Area',
            city='Ludhiana',
            state='Punjab',
            pincode='141001',
            is_active=True,
        )
        self.category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname='Finished Goods',
            level=1,
        )
        self.hsn = HsnSac.objects.create(
            entity=self.entity,
            code='8471',
            description='Computing machines',
            is_service=False,
        )
        self.uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code='PCS',
            description='Piece',
            uqc='NOS',
        )
        self.product = Product.objects.create(
            entity=self.entity,
            productname='Laptop',
            sku='LP-001',
            productdesc='Business laptop',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )
        ProductPlanning.objects.create(
            product=self.product,
            min_stock=Decimal('5.00'),
            max_stock=Decimal('50.00'),
            reorder_level=Decimal('10.00'),
            reorder_qty=Decimal('20.00'),
            lead_time_days=7,
            abc_class='A',
            fsn_class='F',
        )
        ProductGstRate.objects.create(
            product=self.product,
            hsn=self.hsn,
            sgst=Decimal('9.00'),
            cgst=Decimal('9.00'),
            igst=Decimal('18.00'),
            gst_rate=Decimal('18.00'),
            isdefault=True,
        )
        self.batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=1001,
            voucher_no='PUR-1001',
            created_by=self.user,
            is_active=True,
        )
        self.entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=1001,
            voucher_no='PUR-1001',
            voucher_date='2025-04-10',
            posting_date='2025-04-10',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=self.batch,
            narration='Purchase of laptops',
            created_by=self.user,
        )

        InventoryMove.objects.create(
            entry=self.entry,
            posting_batch=self.batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=1001,
            detail_id=1,
            voucher_no='PUR-1001',
            product=self.product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('15.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('15.0000'),
            unit_cost=Decimal('40000.0000'),
            ext_cost=Decimal('600000.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
            destination_location=self.godown,
            movement_reason='purchase',
            posting_date='2025-04-10',
            posted_at=timezone.now(),
            created_by=self.user,
        )
        self._grant_inventory_permission('reports.inventory.stock_summary.view')
        self._grant_inventory_permission('reports.inventory.stock_ledger.view')
        self._grant_inventory_permission('reports.inventory.stock_aging.view')
        self._grant_inventory_permission('reports.inventory.stock_movement.view')
        self._grant_inventory_permission('reports.inventory.stock_day_book.view')
        self._grant_inventory_permission('reports.inventory.stock_book_summary.view')
        self._grant_inventory_permission('reports.inventory.stock_book_detail.view')
        self._grant_inventory_permission('reports.inventory.location_stock.view')
        self._grant_inventory_permission('reports.inventory.non_moving_stock.view')
        self._grant_inventory_permission('reports.inventory.reorder_status.view')
        self._grant_inventory_permission('reports.inventory.slow_moving_dead_stock.view')

    def test_inventory_export_dates_use_dd_mmm_yyyy_format(self):
        self.assertEqual(_format_scope_date(date(2025, 4, 30)), "30-Apr-2025")
        self.assertEqual(_format_scope_date(datetime(2025, 4, 30, 10, 15, 0)), "30-Apr-2025")
        self.assertEqual(_format_scope_date("2025-04-30"), "30-Apr-2025")
        self.assertEqual(_format_scope_date("2025-04-30T12:45:00"), "30-Apr-2025")

    def _scope(self, **extra):
        params = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'as_of_date': '2025-04-30',
        }
        params.update(extra)
        return params

    def _grant_inventory_permission(self, permission_code: str):
        permission, _ = Permission.objects.get_or_create(
            code=permission_code,
            defaults={
                'name': permission_code,
                'module': 'reports',
                'resource': 'inventory',
                'action': 'view',
                'description': permission_code,
                'scope_type': Permission.SCOPE_ENTITY,
                'is_system_defined': True,
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=['isactive'])

        role = Role.objects.create(
            entity=self.entity,
            name='Inventory Report Viewer',
            code=f'inventory_report_viewer_{uuid4().hex[:8]}',
            role_level=Role.LEVEL_ENTITY,
            is_system_role=False,
            is_assignable=True,
            priority=20,
            createdby=self.user,
        )
        RolePermission.objects.get_or_create(
            role=role,
            permission=permission,
            defaults={'effect': RolePermission.EFFECT_ALLOW},
        )
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=role,
            assigned_by=self.user,
            is_primary=True,
        )

    def _create_purchase_stock(
        self,
        *,
        productname: str,
        sku: str,
        qty: Decimal,
        unit_cost: Decimal,
        reorder_level: Decimal,
        min_stock: Decimal,
        max_stock: Decimal,
        posting_date: str,
        txn_id: int,
        category: ProductCategory | None = None,
        hsn: HsnSac | None = None,
        location: Godown | None = None,
    ) -> Product:
        product = Product.objects.create(
            entity=self.entity,
            productname=productname,
            sku=sku,
            productdesc=f'{productname} description',
            productcategory=category or self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )
        ProductPlanning.objects.create(
            product=product,
            min_stock=min_stock,
            max_stock=max_stock,
            reorder_level=reorder_level,
            reorder_qty=Decimal('20.00'),
            lead_time_days=7,
            abc_class='B',
            fsn_class='M',
        )
        ProductGstRate.objects.create(
            product=product,
            hsn=hsn or self.hsn,
            sgst=Decimal('9.00'),
            cgst=Decimal('9.00'),
            igst=Decimal('18.00'),
            gst_rate=Decimal('18.00'),
            isdefault=True,
        )

        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=txn_id,
            voucher_no=f'PUR-{txn_id}',
            created_by=self.user,
            is_active=True,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=txn_id,
            voucher_no=f'PUR-{txn_id}',
            voucher_date=posting_date,
            posting_date=posting_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration=f'Purchase of {productname}',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=txn_id,
            detail_id=1,
            voucher_no=f'PUR-{txn_id}',
            product=product,
            location=location or self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=qty,
            uom_factor=Decimal('1'),
            base_qty=qty,
            unit_cost=unit_cost,
            ext_cost=(qty * unit_cost).quantize(Decimal('0.01')),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
            destination_location=location or self.godown,
            movement_reason='purchase',
            posting_date=posting_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        return product

    def test_inventory_meta_returns_report_catalog_and_filter_choices(self):
        response = self.client.get(reverse('reports_api:inventory-meta'), {'entity': self.entity.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['entity_id'], self.entity.id)
        self.assertTrue(any(report['code'] == 'inventory_stock_summary' for report in data['reports']))
        self.assertTrue(any(report['code'] == 'inventory_stock_ledger' for report in data['reports']))
        self.assertTrue(any(report['code'] == 'inventory_stock_aging' for report in data['reports']))
        self.assertTrue(any(choice['value'] == 'fifo' for choice in data['choices']['valuation_method']))
        self.assertEqual(len(data['financial_years']), 1)
        self.assertEqual(len(data['categories']), 1)
        self.assertEqual(len(data['hsns']), 1)
        self.assertEqual(len(data['locations']), 1)
        self.assertIn('filter_relations', data)
        self.assertIn('product_category_hsn', data['filter_relations'])

    def test_inventory_stock_summary_returns_rows_and_totals(self):
        response = self.client.get(reverse('reports_api:inventory-stock-summary'), self._scope())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_stock_summary')
        self.assertEqual(data['summary']['product_count'], 1)
        self.assertEqual(data['summary']['total_qty'], '15.0000')
        self.assertEqual(data['totals']['closing_value'], '600000.00')
        self.assertEqual(data['rows'][0]['product_name'], 'Laptop')
        self.assertEqual(data['rows'][0]['hsn_code'], '8471')
        self.assertEqual(data['rows'][0]['reorder_level'], '10.00')
        self.assertEqual(data['rows'][0]['stock_status'], 'ok')
        self.assertIn('available_exports', data)
        self.assertEqual(data['available_exports'], ['excel', 'pdf', 'csv', 'print'])
        self.assertIn('export_urls', data['actions'])
        self.assertIn('print', data['actions']['export_urls'])

    def test_inventory_stock_summary_normalizes_mixed_uom_movements(self):
        gms_uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code='GMS',
            description='Grams',
            uqc='GMS',
        )
        kg_uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code='KG',
            description='Kilogram',
            uqc='KGS',
        )
        flour = Product.objects.create(
            entity=self.entity,
            productname='Flour',
            sku='FL-001',
            productdesc='Wheat flour',
            productcategory=self.category,
            base_uom=gms_uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )

        purchase_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2001,
            voucher_no='PUR-2001',
            created_by=self.user,
            is_active=True,
        )
        purchase_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2001,
            voucher_no='PUR-2001',
            voucher_date='2025-04-12',
            posting_date='2025-04-12',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=purchase_batch,
            narration='Purchase of flour',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=purchase_entry,
            posting_batch=purchase_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2001,
            detail_id=1,
            voucher_no='PUR-2001',
            product=flour,
            location=self.godown,
            uom=kg_uom,
            base_uom=gms_uom,
            qty=Decimal('1.0000'),
            uom_factor=Decimal('1000'),
            base_qty=Decimal('1000.0000'),
            unit_cost=Decimal('0.0400'),
            ext_cost=Decimal('40.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
            destination_location=self.godown,
            movement_reason='purchase',
            posting_date='2025-04-12',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        sales_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=2002,
            voucher_no='SAL-2002',
            created_by=self.user,
            is_active=True,
        )
        sales_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=2002,
            voucher_no='SAL-2002',
            voucher_date='2025-04-15',
            posting_date='2025-04-15',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=sales_batch,
            narration='Sale of flour',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=sales_entry,
            posting_batch=sales_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=2002,
            detail_id=1,
            voucher_no='SAL-2002',
            product=flour,
            location=self.godown,
            uom=gms_uom,
            base_uom=gms_uom,
            qty=Decimal('250.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('250.0000'),
            unit_cost=Decimal('0.0400'),
            ext_cost=Decimal('10.00'),
            cost_source=InventoryMove.CostSource.FIFO,
            move_type=InventoryMove.MoveType.OUT,
            movement_nature=InventoryMove.MovementNature.SALE,
            source_location=self.godown,
            movement_reason='sale',
            posting_date='2025-04-15',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        report = build_inventory_stock_summary(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date='2025-04-30',
        )
        flour_row = next(row for row in report['rows'] if row['product_name'] == 'Flour')
        self.assertEqual(flour_row['closing_qty'], '750.0000')

    def test_inventory_stock_summary_handles_expiry_only_internal_lots(self):
        yogurt = Product.objects.create(
            entity=self.entity,
            productname='Yogurt',
            sku='YG-001',
            productdesc='Expiry tracked yogurt',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_expiry_tracked=True,
            shelf_life_days=30,
            expiry_warning_days=7,
        )

        purchase_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3001,
            voucher_no='PUR-3001',
            created_by=self.user,
            is_active=True,
        )
        purchase_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3001,
            voucher_no='PUR-3001',
            voucher_date='2025-04-12',
            posting_date='2025-04-12',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=purchase_batch,
            narration='Purchase of yogurt',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=purchase_entry,
            posting_batch=purchase_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3001,
            detail_id=1,
            voucher_no='PUR-3001',
            product=yogurt,
            batch_number=f'EXP-{yogurt.id}-20260520',
            expiry_date=date(2026, 5, 20),
            location=self.godown,
            destination_location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('8.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('8.0000'),
            unit_cost=Decimal('25.0000'),
            ext_cost=Decimal('200.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
            movement_reason='purchase',
            posting_date='2025-04-12',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        sales_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=3002,
            voucher_no='SAL-3002',
            created_by=self.user,
            is_active=True,
        )
        sales_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=3002,
            voucher_no='SAL-3002',
            voucher_date='2025-04-15',
            posting_date='2025-04-15',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=sales_batch,
            narration='Sale of yogurt',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=sales_entry,
            posting_batch=sales_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=3002,
            detail_id=1,
            voucher_no='SAL-3002',
            product=yogurt,
            batch_number=f'EXP-{yogurt.id}-20260520',
            expiry_date=date(2026, 5, 20),
            location=self.godown,
            source_location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('3.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('3.0000'),
            unit_cost=Decimal('25.0000'),
            ext_cost=Decimal('75.00'),
            cost_source=InventoryMove.CostSource.FIFO,
            move_type=InventoryMove.MoveType.OUT,
            movement_nature=InventoryMove.MovementNature.SALE,
            movement_reason='sale',
            posting_date='2025-04-15',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        report = build_inventory_stock_summary(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date='2025-04-30',
        )
        yogurt_row = next(row for row in report['rows'] if row['product_name'] == 'Yogurt')
        self.assertEqual(yogurt_row['closing_qty'], '5.0000')

    def test_inventory_stock_summary_export_routes_return_files(self):
        excel = self.client.get(reverse('reports_api:inventory-stock-summary-excel'), self._scope())
        csv_response = self.client.get(reverse('reports_api:inventory-stock-summary-csv'), self._scope())
        pdf = self.client.get(reverse('reports_api:inventory-stock-summary-pdf'), self._scope())
        print_response = self.client.get(reverse('reports_api:inventory-stock-summary-print'), self._scope())
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', excel.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', csv_response.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', pdf.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_stock_summary_respects_category_hsn_location_and_search_filters(self):
        alternate_category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname='Accessories',
            level=1,
        )
        alternate_hsn = HsnSac.objects.create(
            entity=self.entity,
            code='8504',
            description='Electrical transformers',
            is_service=False,
        )
        alternate_location = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Overflow Warehouse',
            code='WH-02',
            address='Outer Ring Road',
            city='Ludhiana',
            state='Punjab',
            pincode='141002',
            is_active=True,
        )
        self._create_purchase_stock(
            productname='Keyboard',
            sku='KB-001',
            qty=Decimal('4.0000'),
            unit_cost=Decimal('1000.00'),
            reorder_level=Decimal('10.00'),
            min_stock=Decimal('5.00'),
            max_stock=Decimal('20.00'),
            posting_date='2025-04-12',
            txn_id=3001,
            category=alternate_category,
            hsn=alternate_hsn,
            location=alternate_location,
        )

        category_response = self.client.get(
            reverse('reports_api:inventory-stock-summary'),
            self._scope(as_of_date='2025-04-30', category_ids=str(self.category.id)),
        )
        self.assertEqual(category_response.status_code, 200)
        self.assertEqual([row['product_name'] for row in category_response.json()['rows']], ['Laptop'])

        hsn_response = self.client.get(
            reverse('reports_api:inventory-stock-summary'),
            self._scope(as_of_date='2025-04-30', hsn_ids=str(self.hsn.id)),
        )
        self.assertEqual(hsn_response.status_code, 200)
        self.assertEqual([row['product_name'] for row in hsn_response.json()['rows']], ['Laptop'])

        location_response = self.client.get(
            reverse('reports_api:inventory-stock-summary'),
            self._scope(as_of_date='2025-04-30', location_ids=str(self.godown.id)),
        )
        self.assertEqual(location_response.status_code, 200)
        self.assertEqual([row['product_name'] for row in location_response.json()['rows']], ['Laptop'])

        search_response = self.client.get(
            reverse('reports_api:inventory-stock-summary'),
            self._scope(as_of_date='2025-04-30', search='laptop'),
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual([row['product_name'] for row in search_response.json()['rows']], ['Laptop'])

    def test_inventory_stock_summary_uses_valuation_method_for_mixed_cost_layers(self):
        valuation_product = Product.objects.create(
            entity=self.entity,
            productname='Server',
            sku='SV-001',
            productdesc='Application server',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )
        ProductPlanning.objects.create(
            product=valuation_product,
            min_stock=Decimal('2.00'),
            max_stock=Decimal('20.00'),
            reorder_level=Decimal('4.00'),
            reorder_qty=Decimal('8.00'),
            lead_time_days=5,
            abc_class='B',
            fsn_class='M',
        )

        purchase_batch_1 = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2001,
            voucher_no='PUR-2001',
            created_by=self.user,
            is_active=True,
        )
        purchase_entry_1 = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2001,
            voucher_no='PUR-2001',
            voucher_date='2025-04-05',
            posting_date='2025-04-05',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=purchase_batch_1,
            narration='First server purchase',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=purchase_entry_1,
            posting_batch=purchase_batch_1,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2001,
            detail_id=1,
            voucher_no='PUR-2001',
            product=valuation_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('10.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('10.0000'),
            unit_cost=Decimal('100.0000'),
            ext_cost=Decimal('1000.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            posting_date='2025-04-05',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        purchase_batch_2 = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2002,
            voucher_no='PUR-2002',
            created_by=self.user,
            is_active=True,
        )
        purchase_entry_2 = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2002,
            voucher_no='PUR-2002',
            voucher_date='2025-04-15',
            posting_date='2025-04-15',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=purchase_batch_2,
            narration='Second server purchase',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=purchase_entry_2,
            posting_batch=purchase_batch_2,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=2002,
            detail_id=1,
            voucher_no='PUR-2002',
            product=valuation_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('10.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('10.0000'),
            unit_cost=Decimal('200.0000'),
            ext_cost=Decimal('2000.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            posting_date='2025-04-15',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        issue_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=2003,
            voucher_no='SAL-2003',
            created_by=self.user,
            is_active=True,
        )
        issue_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=2003,
            voucher_no='SAL-2003',
            voucher_date='2025-04-20',
            posting_date='2025-04-20',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=issue_batch,
            narration='Server sale',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=issue_entry,
            posting_batch=issue_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=2003,
            detail_id=1,
            voucher_no='SAL-2003',
            product=valuation_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('5.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('5.0000'),
            unit_cost=Decimal('0.0000'),
            ext_cost=Decimal('0.00'),
            cost_source=InventoryMove.CostSource.MANUAL,
            move_type=InventoryMove.MoveType.OUT,
            posting_date='2025-04-20',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        fifo = build_inventory_stock_summary(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date='2025-04-30',
            valuation_method='fifo',
            product_ids=[valuation_product.id],
            paginate=False,
        )
        lifo = build_inventory_stock_summary(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date='2025-04-30',
            valuation_method='lifo',
            product_ids=[valuation_product.id],
            paginate=False,
        )
        self.assertEqual(fifo['rows'][0]['closing_qty'], '15.0000')
        self.assertEqual(lifo['rows'][0]['closing_qty'], '15.0000')
        self.assertNotEqual(fifo['rows'][0]['closing_value'], lifo['rows'][0]['closing_value'])
        self.assertNotEqual(fifo['rows'][0]['rate'], lifo['rows'][0]['rate'])

    def test_inventory_non_moving_stock_returns_rows_and_exports(self):
        response = self.client.get(
            reverse('reports_api:inventory-non-moving-stock'),
            self._scope(as_of_date='2025-08-01', non_moving_days=30, sort_by='age_days', sort_order='desc'),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_non_moving_stock')
        self.assertEqual(data['summary']['product_count'], 1)
        self.assertEqual(data['summary']['non_moving_days'], 30)
        self.assertEqual(data['rows'][0]['product_name'], 'Laptop')
        self.assertGreaterEqual(int(data['rows'][0]['age_days']), 30)
        self.assertEqual(data['available_exports'], ['excel', 'pdf', 'csv', 'print'])
        self.assertIn('inventory_stock_summary', [item['code'] for item in data['available_drilldowns']])
        self.assertIn('inventory_stock_ledger', [item['code'] for item in data['available_drilldowns']])

        excel = self.client.get(reverse('reports_api:inventory-non-moving-stock-excel'), self._scope(as_of_date='2025-08-01', non_moving_days=30))
        pdf = self.client.get(reverse('reports_api:inventory-non-moving-stock-pdf'), self._scope(as_of_date='2025-08-01', non_moving_days=30))
        print_response = self.client.get(reverse('reports_api:inventory-non-moving-stock-print'), self._scope(as_of_date='2025-08-01', non_moving_days=30))
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', excel.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', pdf.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_reorder_status_returns_rows_and_exports(self):
        self._create_purchase_stock(
            productname='Keyboard',
            sku='KB-001',
            qty=Decimal('4.0000'),
            unit_cost=Decimal('1000.00'),
            reorder_level=Decimal('10.00'),
            min_stock=Decimal('5.00'),
            max_stock=Decimal('20.00'),
            posting_date='2025-04-12',
            txn_id=3001,
        )

        response = self.client.get(
            reverse('reports_api:inventory-reorder-status'),
            self._scope(as_of_date='2025-04-30', sort_by='reorder_gap', sort_order='asc'),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_reorder_status')
        self.assertEqual(data['summary']['product_count'], 1)
        self.assertEqual(data['rows'][0]['product_name'], 'Keyboard')
        self.assertEqual(data['rows'][0]['stock_status'], 'low')
        self.assertEqual(data['available_exports'], ['excel', 'pdf', 'csv', 'print'])
        self.assertIn('inventory_stock_summary', [item['code'] for item in data['available_drilldowns']])
        self.assertIn('inventory_stock_ledger', [item['code'] for item in data['available_drilldowns']])

        csv_response = self.client.get(reverse('reports_api:inventory-reorder-status-csv'), self._scope(as_of_date='2025-04-30'))
        print_response = self.client.get(reverse('reports_api:inventory-reorder-status-print'), self._scope(as_of_date='2025-04-30'))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', csv_response.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_slow_moving_dead_stock_returns_rows_and_exports(self):
        self._create_purchase_stock(
            productname='Slow Mouse',
            sku='SM-001',
            qty=Decimal('6.0000'),
            unit_cost=Decimal('500.00'),
            reorder_level=Decimal('2.00'),
            min_stock=Decimal('1.00'),
            max_stock=Decimal('10.00'),
            posting_date='2025-03-15',
            txn_id=3010,
        )
        self._create_purchase_stock(
            productname='Dead Camera',
            sku='DC-001',
            qty=Decimal('3.0000'),
            unit_cost=Decimal('1500.00'),
            reorder_level=Decimal('1.00'),
            min_stock=Decimal('1.00'),
            max_stock=Decimal('5.00'),
            posting_date='2024-12-15',
            txn_id=3011,
        )

        response = self.client.get(
            reverse('reports_api:inventory-slow-moving-dead-stock'),
            self._scope(as_of_date='2025-08-01', non_moving_days=90, dead_stock_days=180, sort_by='age_days', sort_order='desc'),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_slow_moving_dead_stock')
        self.assertGreaterEqual(data['summary']['product_count'], 2)
        self.assertGreaterEqual(data['summary']['slow_moving_count'], 1)
        self.assertEqual(data['summary']['dead_stock_count'], 1)
        classes = {row['product_name']: row['movement_class'] for row in data['rows']}
        self.assertEqual(classes['Dead Camera'], 'dead_stock')
        self.assertEqual(classes['Slow Mouse'], 'slow_moving')
        self.assertEqual(data['available_exports'], ['excel', 'pdf', 'csv', 'print'])
        self.assertIn('inventory_stock_summary', [item['code'] for item in data['available_drilldowns']])
        self.assertIn('inventory_stock_ledger', [item['code'] for item in data['available_drilldowns']])

        excel = self.client.get(reverse('reports_api:inventory-slow-moving-dead-stock-excel'), self._scope(as_of_date='2025-08-01', non_moving_days=90, dead_stock_days=180))
        print_response = self.client.get(reverse('reports_api:inventory-slow-moving-dead-stock-print'), self._scope(as_of_date='2025-08-01', non_moving_days=90, dead_stock_days=180))
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', excel.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_slow_moving_dead_stock_returns_active_dead_stock_filters(self):
        self._create_purchase_stock(
            productname='Legacy Camera',
            sku='LC-001',
            qty=Decimal('1.0000'),
            unit_cost=Decimal('2500.00'),
            reorder_level=Decimal('1.00'),
            min_stock=Decimal('1.00'),
            max_stock=Decimal('3.00'),
            posting_date='2024-10-01',
            txn_id=3050,
        )

        response = self.client.get(
            reverse('reports_api:inventory-slow-moving-dead-stock'),
            self._scope(as_of_date='2025-08-01', non_moving_days=60, dead_stock_days=240),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['filters']['non_moving_days'], 60)
        self.assertEqual(data['filters']['dead_stock_days'], 240)

    def test_inventory_stock_ledger_uses_valuation_method_for_mixed_cost_layers(self):
        valuation_product = Product.objects.create(
            entity=self.entity,
            productname='Router',
            sku='RT-001',
            productdesc='Network router',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )
        ProductPlanning.objects.create(
            product=valuation_product,
            min_stock=Decimal('2.00'),
            max_stock=Decimal('20.00'),
            reorder_level=Decimal('4.00'),
            reorder_qty=Decimal('8.00'),
            lead_time_days=5,
            abc_class='B',
            fsn_class='M',
        )

        purchase_batch_1 = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3001,
            voucher_no='PUR-3001',
            created_by=self.user,
            is_active=True,
        )
        purchase_entry_1 = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3001,
            voucher_no='PUR-3001',
            voucher_date='2025-04-05',
            posting_date='2025-04-05',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=purchase_batch_1,
            narration='First router purchase',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=purchase_entry_1,
            posting_batch=purchase_batch_1,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3001,
            detail_id=1,
            voucher_no='PUR-3001',
            product=valuation_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('10.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('10.0000'),
            unit_cost=Decimal('100.0000'),
            ext_cost=Decimal('1000.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            posting_date='2025-04-05',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        purchase_batch_2 = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3002,
            voucher_no='PUR-3002',
            created_by=self.user,
            is_active=True,
        )
        purchase_entry_2 = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3002,
            voucher_no='PUR-3002',
            voucher_date='2025-04-15',
            posting_date='2025-04-15',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=purchase_batch_2,
            narration='Second router purchase',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=purchase_entry_2,
            posting_batch=purchase_batch_2,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=3002,
            detail_id=1,
            voucher_no='PUR-3002',
            product=valuation_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('10.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('10.0000'),
            unit_cost=Decimal('200.0000'),
            ext_cost=Decimal('2000.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            posting_date='2025-04-15',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        issue_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=3003,
            voucher_no='SAL-3003',
            created_by=self.user,
            is_active=True,
        )
        issue_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=3003,
            voucher_no='SAL-3003',
            voucher_date='2025-04-20',
            posting_date='2025-04-20',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=issue_batch,
            narration='Router sale',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=issue_entry,
            posting_batch=issue_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=3003,
            detail_id=1,
            voucher_no='SAL-3003',
            product=valuation_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('5.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('5.0000'),
            unit_cost=Decimal('0.0000'),
            ext_cost=Decimal('0.00'),
            cost_source=InventoryMove.CostSource.MANUAL,
            move_type=InventoryMove.MoveType.OUT,
            posting_date='2025-04-20',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        fifo = self.client.get(
            reverse('reports_api:inventory-stock-ledger'),
            {
                **self._scope(),
                'from_date': '2025-04-01',
                'to_date': '2025-04-30',
                'valuation_method': 'fifo',
                'product_ids': [valuation_product.id],
            }
        )
        lifo = self.client.get(
            reverse('reports_api:inventory-stock-ledger'),
            {
                **self._scope(),
                'from_date': '2025-04-01',
                'to_date': '2025-04-30',
                'valuation_method': 'lifo',
                'product_ids': [valuation_product.id],
            }
        )
        self.assertEqual(fifo.status_code, 200)
        self.assertEqual(lifo.status_code, 200)
        fifo_data = fifo.json()
        lifo_data = lifo.json()
        self.assertEqual(fifo_data['summary']['closing_qty'], '15.0000')
        self.assertEqual(lifo_data['summary']['closing_qty'], '15.0000')
        self.assertNotEqual(fifo_data['summary']['closing_value'], lifo_data['summary']['closing_value'])
        fifo_issue = next(row for row in fifo_data['rows'] if row['move_type'] == 'OUT')
        lifo_issue = next(row for row in lifo_data['rows'] if row['move_type'] == 'OUT')
        self.assertNotEqual(fifo_issue['line_value'], lifo_issue['line_value'])

    def test_inventory_stock_ledger_returns_rows_and_totals(self):
        response = self.client.get(
            reverse('reports_api:inventory-stock-ledger'),
            {
                **self._scope(),
                'from_date': '2025-04-01',
                'to_date': '2025-04-30',
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_stock_ledger')
        self.assertEqual(data['summary']['movement_count'], 1)
        self.assertEqual(data['summary']['closing_qty'], '15.0000')
        self.assertEqual(data['summary']['closing_value'], '600000.00')
        self.assertEqual(data['rows'][0]['product_name'], 'Laptop')
        self.assertEqual(data['rows'][0]['running_qty'], '15.0000')
        self.assertIn('available_exports', data)
        self.assertEqual(data['available_exports'], ['excel', 'pdf', 'csv', 'print'])

    def test_inventory_stock_movement_respects_category_hsn_location_and_search_filters(self):
        alternate_category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname='Peripheral Goods',
            level=1,
        )
        alternate_hsn = HsnSac.objects.create(
            entity=self.entity,
            code='8528',
            description='Monitors and projectors',
            is_service=False,
        )
        alternate_location = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Remote Warehouse',
            code='WH-03',
            address='Industrial Road',
            city='Jalandhar',
            state='Punjab',
            pincode='144001',
            is_active=True,
        )
        self._create_purchase_stock(
            productname='Monitor',
            sku='MN-001',
            qty=Decimal('2.0000'),
            unit_cost=Decimal('12000.00'),
            reorder_level=Decimal('3.00'),
            min_stock=Decimal('2.00'),
            max_stock=Decimal('10.00'),
            posting_date='2025-04-11',
            txn_id=4001,
            category=alternate_category,
            hsn=alternate_hsn,
            location=alternate_location,
        )

        response = self.client.get(
            reverse('reports_api:inventory-stock-movement'),
            self._scope(
                from_date='2025-04-01',
                to_date='2025-04-30',
                category_ids=str(self.category.id),
                hsn_ids=str(self.hsn.id),
                location_ids=str(self.godown.id),
                group_by_location='true',
                search='laptop',
            ),
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()['rows']
        self.assertEqual([row['product_name'] for row in rows], ['Laptop'])
        self.assertEqual([row['location_name'] for row in rows], ['Main Warehouse'])

    def test_inventory_stock_ledger_export_routes_return_files(self):
        excel = self.client.get(reverse('reports_api:inventory-stock-ledger-excel'), self._scope())
        csv_response = self.client.get(reverse('reports_api:inventory-stock-ledger-csv'), self._scope())
        pdf = self.client.get(reverse('reports_api:inventory-stock-ledger-pdf'), self._scope())
        print_response = self.client.get(reverse('reports_api:inventory-stock-ledger-print'), self._scope())
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', excel.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', csv_response.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', pdf.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_stock_aging_returns_rows_and_totals(self):
        stale_product = Product.objects.create(
            entity=self.entity,
            productname='Switch',
            sku='SW-001',
            productdesc='Managed switch',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )
        ProductPlanning.objects.create(
            product=stale_product,
            min_stock=Decimal('1.00'),
            max_stock=Decimal('10.00'),
            reorder_level=Decimal('3.00'),
            reorder_qty=Decimal('5.00'),
            lead_time_days=4,
            abc_class='B',
            fsn_class='S',
        )
        stale_batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=4001,
            voucher_no='PUR-4001',
            created_by=self.user,
            is_active=True,
        )
        stale_entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=4001,
            voucher_no='PUR-4001',
            voucher_date='2025-01-10',
            posting_date='2025-01-10',
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=stale_batch,
            narration='Old switch purchase',
            created_by=self.user,
        )
        InventoryMove.objects.create(
            entry=stale_entry,
            posting_batch=stale_batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=4001,
            detail_id=1,
            voucher_no='PUR-4001',
            product=stale_product,
            location=self.godown,
            uom=self.uom,
            base_uom=self.uom,
            qty=Decimal('8.0000'),
            uom_factor=Decimal('1'),
            base_qty=Decimal('8.0000'),
            unit_cost=Decimal('300.0000'),
            ext_cost=Decimal('2400.00'),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=InventoryMove.MoveType.IN_,
            posting_date='2025-01-10',
            posted_at=timezone.now(),
            created_by=self.user,
        )

        response = self.client.get(
            reverse('reports_api:inventory-stock-aging'),
            {
                **self._scope(as_of_date='2025-04-30', bucket_ends='30,60,90,120,150', group_by_location=True),
                'valuation_method': 'fifo',
                'product_ids': str(stale_product.id),
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_stock_aging')
        self.assertEqual(data['summary']['product_count'], 1)
        self.assertEqual(data['summary']['total_qty'], '8.0000')
        self.assertEqual(data['summary']['total_value'], '2400.00')
        self.assertEqual(data['rows'][0]['product_name'], 'Switch')
        self.assertEqual(data['rows'][0]['age_bucket'], '91-120')
        self.assertIn('bucket_totals', data['summary'])
        self.assertIn('91-120', data['summary']['bucket_totals'])
        self.assertIn('available_exports', data)
        self.assertEqual(data['available_exports'], ['excel', 'pdf', 'csv', 'print'])

    def test_inventory_stock_aging_export_routes_return_files(self):
        aging_scope = self._scope(as_of_date='2025-04-30', bucket_ends='30,60,90,120,150', product_ids=str(self.product.id))
        excel = self.client.get(reverse('reports_api:inventory-stock-aging-excel'), aging_scope)
        csv_response = self.client.get(reverse('reports_api:inventory-stock-aging-csv'), aging_scope)
        pdf = self.client.get(reverse('reports_api:inventory-stock-aging-pdf'), aging_scope)
        print_response = self.client.get(reverse('reports_api:inventory-stock-aging-print'), aging_scope)
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', excel.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', csv_response.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', pdf.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_location_stock_returns_rows_and_exports(self):
        secondary_godown = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Secondary Warehouse',
            code='WH-02',
            address='Export Zone',
            city='Delhi',
            state='Delhi',
            pincode='110001',
            is_active=True,
        )
        self._create_purchase_stock(
            productname='Router',
            sku='RT-001',
            qty=Decimal('8.0000'),
            unit_cost=Decimal('12000.0000'),
            reorder_level=Decimal('3.0000'),
            min_stock=Decimal('2.0000'),
            max_stock=Decimal('20.0000'),
            posting_date='2025-04-08',
            txn_id=3001,
            location=self.godown,
        )
        self._create_purchase_stock(
            productname='Switch',
            sku='SW-001',
            qty=Decimal('12.0000'),
            unit_cost=Decimal('8000.0000'),
            reorder_level=Decimal('4.0000'),
            min_stock=Decimal('2.0000'),
            max_stock=Decimal('18.0000'),
            posting_date='2025-04-09',
            txn_id=3002,
            location=secondary_godown,
        )

        response = self.client.get(reverse('reports_api:inventory-location-stock'), self._scope())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['report_code'], 'inventory_location_stock')
        self.assertEqual(data['summary']['location_count'], 2)
        self.assertEqual(len(data['rows']), 2)
        self.assertTrue(any(row['location_name'] == 'Main Warehouse' for row in data['rows']))
        self.assertTrue(any(row['location_name'] == 'Secondary Warehouse' for row in data['rows']))

        excel = self.client.get(reverse('reports_api:inventory-location-stock-excel'), self._scope())
        csv_response = self.client.get(reverse('reports_api:inventory-location-stock-csv'), self._scope())
        pdf = self.client.get(reverse('reports_api:inventory-location-stock-pdf'), self._scope())
        print_response = self.client.get(reverse('reports_api:inventory-location-stock-print'), self._scope())
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(print_response.status_code, 200)
        self.assertIn('attachment', excel.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', csv_response.headers.get('Content-Disposition', '').lower())
        self.assertIn('attachment', pdf.headers.get('Content-Disposition', '').lower())
        self.assertIn('inline', print_response.headers.get('Content-Disposition', '').lower())

    def test_inventory_location_stock_respects_category_hsn_location_and_search_filters(self):
        alternate_category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname='Accessories',
            level=1,
        )
        alternate_hsn = HsnSac.objects.create(
            entity=self.entity,
            code='8504',
            description='Electrical transformers',
            is_service=False,
        )
        secondary_godown = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Secondary Warehouse',
            code='WH-02',
            address='Export Zone',
            city='Delhi',
            state='Delhi',
            pincode='110001',
            is_active=True,
        )
        self._create_purchase_stock(
            productname='Keyboard',
            sku='KB-001',
            qty=Decimal('4.0000'),
            unit_cost=Decimal('1000.00'),
            reorder_level=Decimal('10.00'),
            min_stock=Decimal('5.00'),
            max_stock=Decimal('20.00'),
            posting_date='2025-04-12',
            txn_id=3015,
            category=alternate_category,
            hsn=alternate_hsn,
            location=secondary_godown,
        )

        response = self.client.get(
            reverse('reports_api:inventory-location-stock'),
            self._scope(
                as_of_date='2025-04-30',
                category_ids=str(self.category.id),
                hsn_ids=str(self.hsn.id),
                location_ids=str(self.godown.id),
                search='laptop',
            ),
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()['rows']
        self.assertEqual([row['location_name'] for row in rows], ['Main Warehouse'])

    def test_inventory_operational_reports_return_rows_and_totals(self):
        scope = {
            **self._scope(),
            'from_date': '2025-04-01',
            'to_date': '2025-04-30',
        }

        movement = self.client.get(reverse('reports_api:inventory-stock-movement'), scope)
        day_book = self.client.get(reverse('reports_api:inventory-stock-day-book'), scope)
        book_summary = self.client.get(reverse('reports_api:inventory-stock-book-summary'), scope)
        book_detail = self.client.get(reverse('reports_api:inventory-stock-book-detail'), scope)

        for response in [movement, day_book, book_summary, book_detail]:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['available_exports'], ['excel', 'pdf', 'csv', 'print'])
        self.assertTrue(response.json()['actions']['can_drilldown'])

        movement_data = movement.json()
        day_book_data = day_book.json()
        book_summary_data = book_summary.json()
        book_detail_data = book_detail.json()
        self.assertEqual(movement_data['report_code'], 'inventory_stock_movement')
        self.assertEqual(book_summary_data['report_code'], 'inventory_stock_book_summary')
        self.assertEqual(book_detail_data['report_code'], 'inventory_stock_book_detail')
        self.assertEqual(day_book_data['report_code'], 'inventory_stock_day_book')
        self.assertGreaterEqual(len(movement_data['rows']), 1)
        self.assertGreaterEqual(len(day_book_data['rows']), 1)
        self.assertGreaterEqual(len(book_summary_data['rows']), 1)
        self.assertGreaterEqual(len(book_detail_data['rows']), 1)
        self.assertTrue(any(item['code'] == 'inventory_stock_book_detail' for item in movement_data['available_drilldowns']))
        self.assertTrue(any(item['code'] == 'inventory_stock_movement' for item in day_book_data['available_drilldowns']))
        self.assertTrue(any(item['code'] == 'inventory_stock_book_detail' for item in book_summary_data['available_drilldowns']))
        self.assertTrue(any(item['code'] == 'inventory_stock_ledger' for item in book_detail_data['available_drilldowns']))
        self.assertEqual(movement_data['summary']['closing_qty'], '15.0000')
        self.assertEqual(day_book_data['summary']['closing_qty'], '15.0000')
        self.assertEqual(book_summary_data['summary']['closing_qty'], '15.0000')
        self.assertEqual(book_detail_data['summary']['closing_qty'], '15.0000')
        self.assertEqual(book_detail_data['rows'][0]['movement_nature'], 'PURCHASE')
        self.assertEqual(book_detail_data['rows'][0]['destination_location_name'], 'Main Warehouse')

    def test_inventory_operational_reports_respect_scope_filters(self):
        alternate_category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname='Peripheral Goods',
            level=1,
        )
        alternate_hsn = HsnSac.objects.create(
            entity=self.entity,
            code='8528',
            description='Monitors and projectors',
            is_service=False,
        )
        secondary_godown = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Secondary Warehouse',
            code='WH-02',
            address='Export Zone',
            city='Delhi',
            state='Delhi',
            pincode='110001',
            is_active=True,
        )
        self._create_purchase_stock(
            productname='Monitor',
            sku='MN-001',
            qty=Decimal('2.0000'),
            unit_cost=Decimal('12000.00'),
            reorder_level=Decimal('3.00'),
            min_stock=Decimal('2.00'),
            max_stock=Decimal('10.00'),
            posting_date='2025-04-11',
            txn_id=4020,
            category=alternate_category,
            hsn=alternate_hsn,
            location=secondary_godown,
        )
        scoped = self._scope(
            from_date='2025-04-01',
            to_date='2025-04-30',
            category_ids=str(self.category.id),
            hsn_ids=str(self.hsn.id),
            location_ids=str(self.godown.id),
            search='laptop',
            group_by_location='true',
        )

        movement = self.client.get(reverse('reports_api:inventory-stock-movement'), scoped)
        day_book = self.client.get(reverse('reports_api:inventory-stock-day-book'), scoped)
        book_summary = self.client.get(reverse('reports_api:inventory-stock-book-summary'), scoped)
        book_detail = self.client.get(reverse('reports_api:inventory-stock-book-detail'), scoped)

        for response in [movement, day_book, book_summary, book_detail]:
            self.assertEqual(response.status_code, 200)

        movement_rows = movement.json()['rows']
        self.assertEqual([row['product_name'] for row in movement_rows], ['Laptop'])
        self.assertEqual([row['location_name'] for row in movement_rows], ['Main Warehouse'])

        day_book_data = day_book.json()
        self.assertEqual(day_book_data['summary']['movement_count'], 1)
        self.assertEqual([row['posting_date'] for row in day_book_data['rows']], ['2025-04-10'])

        book_summary_rows = book_summary.json()['rows']
        self.assertEqual([row['product_name'] for row in book_summary_rows], ['Laptop'])

        book_detail_rows = book_detail.json()['rows']
        self.assertEqual([row['product_name'] for row in book_detail_rows], ['Laptop'])
        self.assertEqual([row['location_name'] for row in book_detail_rows], ['Main Warehouse'])

    def test_inventory_operational_export_routes_return_files(self):
        scope = {
            **self._scope(),
            'from_date': '2025-04-01',
            'to_date': '2025-04-30',
        }

        export_routes = [
            'reports_api:inventory-stock-movement-excel',
            'reports_api:inventory-stock-movement-pdf',
            'reports_api:inventory-stock-movement-csv',
            'reports_api:inventory-stock-movement-print',
            'reports_api:inventory-stock-day-book-excel',
            'reports_api:inventory-stock-day-book-pdf',
            'reports_api:inventory-stock-day-book-csv',
            'reports_api:inventory-stock-day-book-print',
            'reports_api:inventory-stock-book-summary-excel',
            'reports_api:inventory-stock-book-summary-pdf',
            'reports_api:inventory-stock-book-summary-csv',
            'reports_api:inventory-stock-book-summary-print',
            'reports_api:inventory-stock-book-detail-excel',
            'reports_api:inventory-stock-book-detail-pdf',
            'reports_api:inventory-stock-book-detail-csv',
            'reports_api:inventory-stock-book-detail-print',
        ]
        for route_name in export_routes:
            response = self.client.get(reverse(route_name), scope)
            self.assertEqual(response.status_code, 200)
            disposition = response.headers.get('Content-Disposition', '').lower()
            if route_name.endswith('print'):
                self.assertIn('inline', disposition)
            else:
                self.assertIn('attachment', disposition)
