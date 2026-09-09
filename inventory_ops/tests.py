from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, ProductUomConversion, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity
from numbering.models import DocumentNumberSeries, DocumentType
from posting.models import Entry, EntryStatus, InventoryMove, JournalLine, PostingBatch
from posting.models import TxnType
from posting.services.posting_service import IMInput, PostingService
from rbac.models import (
    DataAccessPolicy,
    Permission,
    Role,
    RoleDataAccessPolicy,
    RolePermission,
    UserRoleAssignment,
)
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService
from inventory_ops.models import InventoryAdjustment, InventoryTransfer
from inventory_ops.services import InventoryAdjustmentService, InventoryTransferService


@override_settings(ROOT_URLCONF='FA.urls', AUTH_PASSWORD_VALIDATORS=[])
class InventoryOpsTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f'inventory-ops-user-{suffix}',
            email=f'inventory-ops-{suffix}@example.com',
            password='pass123',
        )
        self.client.force_authenticate(user=self.user)

        self.gst_type = GstRegistrationType.objects.create(Name='Regular', Description='Regular')
        self.entity = Entity.objects.create(
            entityname='Inventory Ops Entity',
            entitydesc='Inventory operations test entity',
            legalname='Inventory Ops Entity Pvt Ltd',
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
        self.entityfin_alt = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc='FY 2026-27',
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.subentity_alt = SubEntity.objects.create(entity=self.entity, subentityname='Branch B')

        self.source = Godown.objects.create(
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
        self.destination = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name='Secondary Warehouse',
            code='WH-02',
            address='Phase 2',
            city='Ludhiana',
            state='Punjab',
            pincode='141002',
            is_active=True,
        )
        self.source_alt = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity_alt,
            name='Branch B Warehouse',
            code='WH-B1',
            address='Branch B Area',
            city='Ludhiana',
            state='Punjab',
            pincode='141003',
            is_active=True,
        )
        self.destination_alt = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity_alt,
            name='Branch B Overflow',
            code='WH-B2',
            address='Branch B Phase 2',
            city='Ludhiana',
            state='Punjab',
            pincode='141004',
            is_active=True,
        )

        self.category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname='Finished Goods',
            level=1,
        )
        self.uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code='PCS',
            description='Pieces',
            uqc='NOS',
        )
        self.box_uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code='BOX',
            description='Boxes',
            uqc='BOX',
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
        ProductUomConversion.objects.create(
            product=self.product,
            from_uom=self.uom,
            to_uom=self.box_uom,
            factor=Decimal('0.1000'),
        )
        self.batch_product = Product.objects.create(
            entity=self.entity,
            productname='Medicine Strip',
            sku='MED-001',
            productdesc='Batch managed medicine',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=True,
            is_serialized=False,
            is_expiry_tracked=True,
        )
        self.expiry_only_product = Product.objects.create(
            entity=self.entity,
            productname='Yogurt Cup',
            sku='YG-001',
            productdesc='Expiry-tracked product without manual batch',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
            is_expiry_tracked=True,
            shelf_life_days=30,
            expiry_warning_days=7,
        )

        self.role = Role.objects.create(
            entity=self.entity,
            name='Inventory Ops Viewer',
            code=f'inventory_ops_viewer_{uuid4().hex[:8]}',
            role_level=Role.LEVEL_ENTITY,
            is_system_role=False,
            is_assignable=True,
            priority=20,
            createdby=self.user,
        )
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=self.role,
            assigned_by=self.user,
            is_primary=True,
        )
        self._grant_inventory_permission('inventory.transfer.view')
        self._grant_inventory_permission('inventory.transfer.create')
        self._grant_inventory_permission('inventory.transfer.update')
        self._grant_inventory_permission('inventory.transfer.post')
        self._grant_inventory_permission('inventory.transfer.unpost')
        self._grant_inventory_permission('inventory.transfer.cancel')
        self._grant_inventory_permission('inventory.adjustment.view')
        self._grant_inventory_permission('inventory.adjustment.create')
        self._grant_inventory_permission('inventory.adjustment.update')
        self._grant_inventory_permission('inventory.adjustment.post')
        self._grant_inventory_permission('inventory.adjustment.unpost')
        self._grant_inventory_permission('inventory.adjustment.cancel')
        self._grant_inventory_permission('inventory.location.view')
        self._grant_inventory_permission('inventory.location.create')
        self._grant_inventory_permission('inventory.location.update')
        self._grant_inventory_permission('inventory.location.delete')
        self._seed_source_stock()

    def _seed_source_stock(self):
        InventoryAdjustmentService.create_adjustment(
            payload={
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
                'adjustment_date': '2025-04-10',
                'location': self.source.id,
                'reference_no': 'ADJ-SEED-BASE',
                'narration': 'Seed stock for transfer tests',
                'lines': [
                    {
                        'product': self.product.id,
                        'direction': 'INCREASE',
                        'qty': '20.0000',
                        'unit_cost': '25000.0000',
                        'note': 'Initial stock',
                    },
                    {
                        'product': self.batch_product.id,
                        'direction': 'INCREASE',
                        'qty': '5.0000',
                        'unit_cost': '15.0000',
                        'batch_number': 'B-1',
                        'expiry_date': '2026-05-01',
                        'note': 'Initial batch stock',
                    },
                    {
                        'product': self.expiry_only_product.id,
                        'direction': 'INCREASE',
                        'qty': '6.0000',
                        'unit_cost': '50.0000',
                        'expiry_date': '2026-08-15',
                        'note': 'Initial expiry-only stock',
                    },
                ],
            },
            user_id=self.user.id,
        )

    def _grant_inventory_permission(self, permission_code: str):
        action = permission_code.rsplit('.', 1)[-1]
        permission, _ = Permission.objects.get_or_create(
            code=permission_code,
            defaults={
                'name': permission_code,
                'module': 'inventory',
                'resource': 'transfer',
                'action': action,
                'description': permission_code,
                'scope_type': Permission.SCOPE_ENTITY,
                'is_system_defined': True,
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=['isactive'])

        RolePermission.objects.get_or_create(
            role=self.role,
            permission=permission,
            defaults={'effect': RolePermission.EFFECT_ALLOW},
        )

    def _transfer_payload(self):
        return {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'transfer_date': '2025-04-12',
            'source_location': self.source.id,
            'destination_location': self.destination.id,
            'reference_no': 'REF-1001',
            'narration': 'Warehouse to warehouse transfer',
            'lines': [
                {
                    'product': self.product.id,
                    'qty': '5.0000',
                    'unit_cost': '25000.0000',
                    'note': 'Primary movement',
                }
            ],
        }

    def _stock_qty(
        self,
        *,
        location_id: int | None = None,
        product: Product | None = None,
        batch_number: str | None = None,
    ) -> Decimal:
        moves = InventoryMove.objects.filter(entity=self.entity, product=product or self.product)
        if location_id is not None:
            moves = moves.filter(location_id=location_id)
        if batch_number is not None:
            moves = moves.filter(batch_number=batch_number)
        total = Decimal('0.0000')
        for move_type, base_qty in moves.values_list('move_type', 'base_qty'):
            qty = Decimal(base_qty or 0)
            total += -abs(qty) if move_type == InventoryMove.MoveType.OUT else abs(qty)
        return total.quantize(Decimal('0.0001'))

    def _post_inventory_event(
        self,
        *,
        txn_type: str,
        txn_id: int,
        voucher_no: str,
        posting_date: str,
        location_id: int,
        qty: str,
        move_type: str,
        movement_nature: str,
        product: Product | None = None,
        batch_number: str = '',
    ) -> Entry:
        target_product = product or self.product
        return PostingService(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            user_id=self.user.id,
        ).post(
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            voucher_date=posting_date,
            posting_date=posting_date,
            narration=f'Deterministic chain event {voucher_no}',
            jl_inputs=[],
            im_inputs=[
                IMInput(
                    product_id=target_product.id,
                    qty=Decimal(qty),
                    base_qty=Decimal(qty),
                    uom_id=target_product.base_uom_id,
                    base_uom_id=target_product.base_uom_id,
                    unit_cost=Decimal('25000.0000'),
                    move_type=move_type,
                    cost_source=InventoryMove.CostSource.PURCHASE,
                    location_id=location_id,
                    source_location_id=location_id if move_type == InventoryMove.MoveType.OUT else None,
                    destination_location_id=location_id if move_type == InventoryMove.MoveType.IN_ else None,
                    movement_nature=movement_nature,
                    movement_reason=voucher_no,
                    batch_number=batch_number,
                )
            ],
        )

    def test_deterministic_cross_module_stock_chain_reconciles_locations_and_reports(self):
        self._grant_inventory_permission('reports.inventory.stock_summary.view')
        self._grant_inventory_permission('reports.inventory.location_stock.view')
        baseline = (self._stock_qty(location_id=self.source.id), self._stock_qty(location_id=self.destination.id))
        self.assertEqual(baseline, (Decimal('20.0000'), Decimal('0.0000')))

        purchase_entry = self._post_inventory_event(
            txn_type=TxnType.PURCHASE,
            txn_id=91001,
            voucher_no='CHAIN-PUR-001',
            posting_date='2025-04-11',
            location_id=self.source.id,
            qty='10.0000',
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
        )
        self.assertEqual(self._stock_qty(location_id=self.source.id), Decimal('30.0000'))

        transfer = InventoryTransferService.create_transfer(
            payload={**self._transfer_payload(), 'reference_no': 'CHAIN-TRN-001'},
            user_id=self.user.id,
        )
        InventoryTransferService.post_transfer(transfer_id=transfer.transfer.id, user_id=self.user.id)
        self.assertEqual(
            (self._stock_qty(location_id=self.source.id), self._stock_qty(location_id=self.destination.id)),
            (Decimal('25.0000'), Decimal('5.0000')),
        )

        adjustment = InventoryAdjustmentService.create_adjustment(
            payload={
                **self._adjustment_payload(),
                'location': self.destination.id,
                'reference_no': 'CHAIN-ADJ-001',
                'lines': [{
                    'product': self.product.id,
                    'direction': 'DECREASE',
                    'qty': '1.0000',
                    'unit_cost': '25000.0000',
                    'note': 'Deterministic shrinkage',
                }],
            },
            user_id=self.user.id,
        )
        InventoryAdjustmentService.post_adjustment(adjustment_id=adjustment.adjustment.id, user_id=self.user.id)
        self.assertEqual(self._stock_qty(location_id=self.destination.id), Decimal('4.0000'))

        sales_entry = self._post_inventory_event(
            txn_type=TxnType.SALES,
            txn_id=91002,
            voucher_no='CHAIN-SAL-001',
            posting_date='2025-04-13',
            location_id=self.destination.id,
            qty='2.0000',
            move_type=InventoryMove.MoveType.OUT,
            movement_nature=InventoryMove.MovementNature.SALE,
        )
        self.assertEqual(self._stock_qty(location_id=self.destination.id), Decimal('2.0000'))

        return_entry = self._post_inventory_event(
            txn_type=TxnType.SALES_RETURN,
            txn_id=91003,
            voucher_no='CHAIN-RET-001',
            posting_date='2025-04-14',
            location_id=self.destination.id,
            qty='1.0000',
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.RETURN,
        )
        self.assertEqual(
            (self._stock_qty(location_id=self.source.id), self._stock_qty(location_id=self.destination.id), self._stock_qty()),
            (Decimal('25.0000'), Decimal('3.0000'), Decimal('28.0000')),
        )

        for entry in (purchase_entry, sales_entry, return_entry):
            self.assertEqual(entry.status, EntryStatus.POSTED)
            self.assertEqual(entry.posting_inventory_moves.count(), 1)

        report_scope = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'as_of_date': '2025-04-30',
            'search': self.product.sku,
        }
        summary = self.client.get(reverse('reports_api:inventory-stock-summary'), report_scope)
        self.assertEqual(summary.status_code, 200, summary.json())
        summary_row = next(row for row in summary.json()['rows'] if row['product_id'] == self.product.id)
        self.assertEqual(summary_row['closing_qty'], '28.0000')

        location_report = self.client.get(reverse('reports_api:inventory-location-stock'), report_scope)
        self.assertEqual(location_report.status_code, 200, location_report.json())
        location_rows = {
            row['location_id']: row
            for row in location_report.json()['rows']
        }
        self.assertEqual(location_rows[self.source.id]['closing_qty'], '25.0000')
        self.assertEqual(location_rows[self.destination.id]['closing_qty'], '3.0000')

    def test_batch_managed_cross_module_stock_chain_preserves_lot_and_location(self):
        batch = 'B-1'
        self.assertEqual(
            self._stock_qty(location_id=self.source.id, product=self.batch_product, batch_number=batch),
            Decimal('5.0000'),
        )
        self._post_inventory_event(
            txn_type=TxnType.PURCHASE,
            txn_id=92001,
            voucher_no='CHAIN-BATCH-PUR-001',
            posting_date='2025-04-11',
            location_id=self.source.id,
            qty='10.0000',
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.PURCHASE,
            product=self.batch_product,
            batch_number=batch,
        )

        transfer_payload = self._transfer_payload()
        transfer_payload.update({'reference_no': 'CHAIN-BATCH-TRN-001'})
        transfer_payload['lines'] = [{
            'product': self.batch_product.id,
            'qty': '2.0000',
            'unit_cost': '15.0000',
            'batch_number': batch,
            'expiry_date': '2026-05-01',
            'note': 'Batch transfer',
        }]
        transfer = InventoryTransferService.create_transfer(payload=transfer_payload, user_id=self.user.id)
        InventoryTransferService.post_transfer(transfer_id=transfer.transfer.id, user_id=self.user.id)

        adjustment_payload = self._adjustment_payload()
        adjustment_payload.update({'location': self.destination.id, 'reference_no': 'CHAIN-BATCH-ADJ-001'})
        adjustment_payload['lines'] = [{
            'product': self.batch_product.id,
            'direction': 'DECREASE',
            'qty': '1.0000',
            'unit_cost': '15.0000',
            'batch_number': batch,
            'expiry_date': '2026-05-01',
            'note': 'Batch shrinkage',
        }]
        adjustment = InventoryAdjustmentService.create_adjustment(payload=adjustment_payload, user_id=self.user.id)
        InventoryAdjustmentService.post_adjustment(adjustment_id=adjustment.adjustment.id, user_id=self.user.id)

        self._post_inventory_event(
            txn_type=TxnType.SALES,
            txn_id=92002,
            voucher_no='CHAIN-BATCH-SAL-001',
            posting_date='2025-04-13',
            location_id=self.destination.id,
            qty='1.0000',
            move_type=InventoryMove.MoveType.OUT,
            movement_nature=InventoryMove.MovementNature.SALE,
            product=self.batch_product,
            batch_number=batch,
        )
        self._post_inventory_event(
            txn_type=TxnType.SALES_RETURN,
            txn_id=92003,
            voucher_no='CHAIN-BATCH-RET-001',
            posting_date='2025-04-14',
            location_id=self.destination.id,
            qty='0.5000',
            move_type=InventoryMove.MoveType.IN_,
            movement_nature=InventoryMove.MovementNature.RETURN,
            product=self.batch_product,
            batch_number=batch,
        )

        source_qty = self._stock_qty(location_id=self.source.id, product=self.batch_product, batch_number=batch)
        destination_qty = self._stock_qty(location_id=self.destination.id, product=self.batch_product, batch_number=batch)
        entity_qty = self._stock_qty(product=self.batch_product, batch_number=batch)
        self.assertEqual((source_qty, destination_qty, entity_qty), (
            Decimal('13.0000'),
            Decimal('0.5000'),
            Decimal('13.5000'),
        ))

        movement_locators = (
            (TxnType.PURCHASE, 92001, 1),
            (TxnType.INVENTORY_TRANSFER, transfer.transfer.id, 2),
            (TxnType.INVENTORY_ADJUSTMENT, adjustment.adjustment.id, 1),
            (TxnType.SALES, 92002, 1),
            (TxnType.SALES_RETURN, 92003, 1),
        )
        located_moves = []
        for txn_type, txn_id, expected_count in movement_locators:
            moves = list(InventoryMove.objects.filter(
                entity=self.entity,
                product=self.batch_product,
                txn_type=txn_type,
                txn_id=txn_id,
            ))
            self.assertEqual(len(moves), expected_count)
            located_moves.extend(moves)
        self.assertEqual(len(located_moves), 6)
        self.assertTrue(all(move.batch_number == batch for move in located_moves))

    def test_godown_list_returns_rows(self):
        response = self.client.get(reverse('inventory_ops:inventory-godowns'), {'entity': self.entity.id})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()['rows']), 2)

    def test_godown_master_crud_supports_branch_defaults(self):
        response = self.client.get(reverse('inventory_ops:inventory-godown-master'), {'entity': self.entity.id})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()['rows']), 2)

        create_payload = {
            'entity': self.entity.id,
            'subentity': self.subentity.id,
            'name': 'Front Room',
            'code': 'FR-01',
            'address': 'Ground Floor',
            'city': 'Ludhiana',
            'state': 'Punjab',
            'pincode': '141001',
            'capacity': '100.00',
            'is_active': True,
            'is_default': True,
        }
        create_resp = self.client.post(reverse('inventory_ops:inventory-godown-master'), create_payload, format='json')
        self.assertEqual(create_resp.status_code, 201)
        self.assertTrue(create_resp.json()['is_default'])
        godown_id = create_resp.json()['id']

        patch_resp = self.client.patch(
            reverse('inventory_ops:inventory-godown-master-detail', kwargs={'pk': godown_id}),
            {
                'entity': self.entity.id,
                'subentity': self.subentity.id,
                'name': 'Front Room A',
                'code': 'FR-01',
                'address': 'Ground Floor',
                'city': 'Ludhiana',
                'state': 'Punjab',
                'pincode': '141001',
                'capacity': '120.00',
                'is_active': True,
                'is_default': True,
            },
            format='json',
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()['name'], 'Front Room A')

        delete_resp = self.client.delete(reverse('inventory_ops:inventory-godown-master-detail', kwargs={'pk': godown_id}))
        self.assertEqual(delete_resp.status_code, 204)

    def test_godown_create_rejects_oversized_fields(self):
        response = self.client.post(
            reverse('inventory_ops:inventory-godown-master'),
            {
                'entity': self.entity.id,
                'subentity': self.subentity.id,
                'name': 'N' * 151,
                'code': 'C' * 51,
                'address': 'A' * 256,
                'city': 'Y' * 256,
                'state': 'S' * 256,
                'pincode': '1' * 21,
                'capacity': '100.00',
                'is_active': True,
                'is_default': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json())
        self.assertIn('code', response.json())
        self.assertIn('address', response.json())
        self.assertIn('city', response.json())
        self.assertIn('state', response.json())
        self.assertIn('pincode', response.json())

    def test_create_transfer_saves_draft_without_posting_moves(self):
        response = self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['transfer']['status'], 'DRAFT')
        self.assertTrue(body['transfer']['action_flags']['can_edit'])
        self.assertTrue(body['transfer']['action_flags']['can_post'])
        self.assertTrue(body['transfer']['action_flags']['can_cancel'])
        self.assertFalse(body['transfer']['action_flags']['can_unpost'])
        self.assertIsNone(body['transfer']['posting_entry_id'])
        self.assertAlmostEqual(float(body['transfer']['total_qty']), 5.0)
        self.assertAlmostEqual(float(body['transfer']['total_value']), 125000.0)

        transfer_id = body['transfer']['id']
        self.assertTrue(body['transfer']['transfer_no'].startswith('ITF-'))
        self.assertEqual(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').count(), 0)

    def test_create_transfer_rejects_oversized_fields(self):
        payload = self._transfer_payload()
        payload['reference_no'] = 'R' * 101
        payload['narration'] = 'N' * 501
        payload['lines'][0]['batch_number'] = 'B' * 81
        payload['lines'][0]['note'] = 'T' * 201

        response = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('reference_no', response.json())
        self.assertIn('narration', response.json())

    def test_create_transfer_requires_source_and_destination_locations(self):
        payload = self._transfer_payload()
        payload['source_location'] = None

        missing_source = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')

        self.assertEqual(missing_source.status_code, 400)
        self.assertEqual(missing_source.json()['source_location'][0], 'Source location is required.')

        payload = self._transfer_payload()
        payload['destination_location'] = None

        missing_destination = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')

        self.assertEqual(missing_destination.status_code, 400)
        self.assertEqual(missing_destination.json()['destination_location'][0], 'Destination location is required.')

    def test_create_transfer_rejects_same_source_and_destination_without_partial_header(self):
        payload = self._transfer_payload()
        payload['reference_no'] = f'REF-SAME-{uuid4().hex[:8]}'
        payload['destination_location'] = payload['source_location']

        response = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('must be different', str(response.json()))
        self.assertFalse(InventoryTransfer.objects.filter(reference_no=payload['reference_no']).exists())

    def test_create_transfer_rolls_back_header_when_later_line_fails_service_validation(self):
        payload = self._transfer_payload()
        payload['reference_no'] = 'REF-ROLLBACK'
        payload['lines'].append({
            'product': self.batch_product.id,
            'qty': '1.0000',
            'unit_cost': '15.0000',
            'batch_number': '',
        })

        response = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Batch number is required', str(response.json()))
        self.assertFalse(InventoryTransfer.objects.filter(reference_no='REF-ROLLBACK').exists())

    def test_transfer_post_unpost_and_cancel_flow(self):
        created = self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')
        self.assertEqual(created.status_code, 201)
        transfer_id = created.json()['transfer']['id']

        post_resp = self.client.post(reverse('inventory_ops:inventory-transfer-post', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual(post_resp.json()['transfer']['status'], 'POSTED')
        self.assertTrue(post_resp.json()['transfer']['action_flags']['can_unpost'])
        self.assertTrue(post_resp.json()['transfer']['action_flags']['is_read_only'])
        self.assertEqual(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').count(), 2)

        moves = list(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').order_by('id'))
        self.assertEqual(moves[0].movement_nature, InventoryMove.MovementNature.TRANSFER)
        self.assertEqual(moves[0].source_location_id, self.source.id)
        self.assertEqual(moves[0].destination_location_id, self.destination.id)
        self.assertEqual(moves[1].movement_nature, InventoryMove.MovementNature.TRANSFER)
        self.assertEqual(moves[1].source_location_id, self.source.id)
        self.assertEqual(moves[1].destination_location_id, self.destination.id)

        repeated_post = self.client.post(reverse('inventory_ops:inventory-transfer-post', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(repeated_post.status_code, 200)
        self.assertEqual(repeated_post.json()['transfer']['posting_entry_id'], post_resp.json()['transfer']['posting_entry_id'])
        self.assertEqual(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').count(), 2)

        unpost_resp = self.client.post(reverse('inventory_ops:inventory-transfer-unpost', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(unpost_resp.status_code, 200)
        self.assertEqual(unpost_resp.json()['transfer']['status'], 'DRAFT')
        self.assertEqual(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').count(), 0)
        reversal_entry_id = unpost_resp.json()['transfer']['posting_entry_id']
        reversal_entry = Entry.objects.get(pk=reversal_entry_id)
        self.assertEqual(reversal_entry.status, EntryStatus.REVERSED)
        self.assertEqual(JournalLine.objects.filter(entry_id=reversal_entry_id).count(), 0)
        self.assertTrue(PostingBatch.objects.get(pk=reversal_entry.posting_batch_id).is_active)

        cancel_resp = self.client.post(reverse('inventory_ops:inventory-transfer-cancel', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()['transfer']['status'], 'CANCELLED')
        repeated_cancel = self.client.post(reverse('inventory_ops:inventory-transfer-cancel', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(repeated_cancel.status_code, 200)
        self.assertEqual(repeated_cancel.json()['transfer']['status'], 'CANCELLED')

    def test_transfer_update_replaces_lines_for_draft(self):
        created = self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')
        transfer_id = created.json()['transfer']['id']
        payload = self._transfer_payload()
        payload['lines'][0]['qty'] = '3.0000'
        payload['lines'][0]['note'] = 'Updated quantity'
        response = self.client.patch(reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer_id}), payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transfer']['status'], 'DRAFT')
        self.assertAlmostEqual(float(response.json()['transfer']['total_qty']), 3.0)
        self.assertEqual(response.json()['transfer']['lines'][0]['note'], 'Updated quantity')

    def test_transfer_derives_unit_cost_from_source_stock_when_missing(self):
        payload = self._transfer_payload()
        payload['lines'][0]['unit_cost'] = None
        response = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')
        self.assertEqual(response.status_code, 201)
        transfer = response.json()['transfer']
        self.assertEqual(transfer['status'], 'DRAFT')
        self.assertAlmostEqual(float(transfer['lines'][0]['unit_cost']), 25000.0)

    def test_transfer_supports_alternate_uom_and_posts_base_qty(self):
        payload = self._transfer_payload()
        payload['lines'][0]['uom_id'] = self.box_uom.id
        payload['lines'][0]['qty'] = '2.0000'
        payload['lines'][0]['unit_cost'] = '250000.0000'
        created = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')
        self.assertEqual(created.status_code, 201)
        body = created.json()['transfer']
        self.assertEqual(body['lines'][0]['uom_id'], self.box_uom.id)
        self.assertEqual(body['lines'][0]['uom_name'], 'BOX')

        transfer_id = body['id']
        post_resp = self.client.post(reverse('inventory_ops:inventory-transfer-post', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(post_resp.status_code, 200)
        moves = list(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').order_by('id'))
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves[0].uom_id, self.box_uom.id)
        self.assertEqual(str(moves[0].qty), '2.0000')
        self.assertEqual(str(moves[0].base_qty), '20.0000')
        self.assertEqual(str(moves[0].uom_factor), '10.00000000')
        self.assertEqual(str(moves[0].unit_cost), '25000.0000')

    def test_fractional_alternate_uom_post_and_unpost_has_no_quantity_rounding_residue(self):
        source_before = self._stock_qty(location_id=self.source.id)
        destination_before = self._stock_qty(location_id=self.destination.id)

        transfer_payload = self._transfer_payload()
        transfer_payload['reference_no'] = 'TRN-UOM-PRECISION-1'
        transfer_payload['lines'][0].update({
            'uom_id': self.box_uom.id,
            'qty': '0.3333',
            'unit_cost': '250000.0000',
        })
        created = self.client.post(reverse('inventory_ops:inventory-transfers'), transfer_payload, format='json')
        self.assertEqual(created.status_code, 201, created.json())
        transfer_id = created.json()['transfer']['id']

        posted = self.client.post(
            reverse('inventory_ops:inventory-transfer-post', kwargs={'pk': transfer_id}), {}, format='json'
        )
        self.assertEqual(posted.status_code, 200, posted.json())
        transfer_moves = list(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').order_by('id'))
        self.assertEqual([move.base_qty for move in transfer_moves], [Decimal('3.3330'), Decimal('3.3330')])
        self.assertEqual(self._stock_qty(location_id=self.source.id), source_before - Decimal('3.3330'))
        self.assertEqual(self._stock_qty(location_id=self.destination.id), destination_before + Decimal('3.3330'))

        unposted = self.client.post(
            reverse('inventory_ops:inventory-transfer-unpost', kwargs={'pk': transfer_id}), {}, format='json'
        )
        self.assertEqual(unposted.status_code, 200, unposted.json())
        self.assertFalse(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').exists())
        self.assertEqual(self._stock_qty(location_id=self.source.id), source_before)
        self.assertEqual(self._stock_qty(location_id=self.destination.id), destination_before)

        adjustment_payload = self._adjustment_payload()
        adjustment_payload.update({
            'location': self.destination.id,
            'reference_no': 'ADJ-UOM-PRECISION-1',
        })
        adjustment_payload['lines'][0].update({
            'uom_id': self.box_uom.id,
            'qty': '0.1667',
            'unit_cost': '250000.0000',
        })
        adjustment = self.client.post(
            reverse('inventory_ops:inventory-adjustments'), adjustment_payload, format='json'
        )
        self.assertEqual(adjustment.status_code, 201, adjustment.json())
        adjustment_id = adjustment.json()['adjustment']['id']
        adjustment_posted = self.client.post(
            reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}, format='json'
        )
        self.assertEqual(adjustment_posted.status_code, 200, adjustment_posted.json())
        adjustment_move = InventoryMove.objects.get(txn_id=adjustment_id, txn_type='IA')
        self.assertEqual(adjustment_move.base_qty, Decimal('1.6670'))
        self.assertEqual(self._stock_qty(location_id=self.destination.id), destination_before + Decimal('1.6670'))

        adjustment_unposted = self.client.post(
            reverse('inventory_ops:inventory-adjustment-unpost', kwargs={'pk': adjustment_id}), {}, format='json'
        )
        self.assertEqual(adjustment_unposted.status_code, 200, adjustment_unposted.json())
        self.assertFalse(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').exists())
        self.assertEqual(self._stock_qty(location_id=self.destination.id), destination_before)

    def test_transfer_requires_batch_for_batch_managed_items(self):
        payload = self._transfer_payload()
        payload['lines'] = [
            {
                'product': self.batch_product.id,
                'qty': '1.0000',
                'unit_cost': '10.0000',
                'note': 'Batch stock',
            }
        ]
        response = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Batch number is required', str(response.json()))

    def test_transfer_rejects_shortage_at_source_location(self):
        payload = self._transfer_payload()
        payload['lines'][0]['qty'] = '999.0000'
        response = self.client.post(reverse('inventory_ops:inventory-transfers'), payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Insufficient stock', str(response.json()))

    def test_detail_returns_saved_transfer(self):
        created = self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json').json()
        transfer_id = created['transfer']['id']
        response = self.client.get(reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transfer_no'], created['transfer']['transfer_no'])
        self.assertIn('action_flags', response.json())

    def test_transfer_list_returns_rows(self):
        self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')
        response = self.client.get(reverse('inventory_ops:inventory-transfers-list'), {'entity': self.entity.id})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()['rows']), 1)

    def test_transfer_list_honors_entityfinid_and_subentity_scope(self):
        self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')

        InventoryAdjustmentService.create_adjustment(
            payload={
                'entity': self.entity.id,
                'entityfinid': self.entityfin_alt.id,
                'subentity': self.subentity_alt.id,
                'adjustment_date': '2026-04-10',
                'location': self.source_alt.id,
                'reference_no': 'ALT-SEED',
                'narration': 'Seed alternate branch stock',
                'lines': [
                    {
                        'product': self.product.id,
                        'direction': 'INCREASE',
                        'qty': '10.0000',
                        'unit_cost': '25000.0000',
                        'note': 'Alternate branch stock',
                    }
                ],
            },
            user_id=self.user.id,
        )

        other_scope_payload = self._transfer_payload()
        other_scope_payload['entityfinid'] = self.entityfin_alt.id
        other_scope_payload['subentity'] = self.subentity_alt.id
        other_scope_payload['source_location'] = self.source_alt.id
        other_scope_payload['destination_location'] = self.destination_alt.id
        other_scope_payload['reference_no'] = 'REF-ALT'
        other_created = self.client.post(reverse('inventory_ops:inventory-transfers'), other_scope_payload, format='json')
        self.assertEqual(other_created.status_code, 201)

        response = self.client.get(
            reverse('inventory_ops:inventory-transfers-list'),
            {'entity': self.entity.id, 'entityfinid': self.entityfin.id, 'subentity': self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        reference_nos = {row['reference_no'] for row in response.json()['rows']}
        self.assertIn('REF-1001', reference_nos)
        self.assertNotIn('REF-ALT', reference_nos)

    def _adjustment_payload(self):
        return {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'adjustment_date': '2025-04-12',
            'location': self.source.id,
            'reference_no': 'ADJ-1001',
            'narration': 'Stock count variance',
            'lines': [
                {
                    'product': self.product.id,
                    'direction': 'INCREASE',
                    'qty': '2.0000',
                    'unit_cost': '25000.0000',
                    'note': 'Count gain',
                }
            ],
        }

    def test_transfer_post_rolls_back_entry_and_movements_when_final_save_fails(self):
        created = InventoryTransferService.create_transfer(
            payload=self._transfer_payload(),
            user_id=self.user.id,
        ).transfer

        with patch.object(type(created), 'save', side_effect=RuntimeError('injected final save failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected final save failure'):
                InventoryTransferService.post_transfer(
                    transfer_id=created.id,
                    user_id=self.user.id,
                )

        created.refresh_from_db()
        self.assertEqual(created.status, 'DRAFT')
        self.assertIsNone(created.posting_entry_id)
        self.assertFalse(
            Entry.objects.filter(
                entity=self.entity,
                txn_type=TxnType.INVENTORY_TRANSFER,
                txn_id=created.id,
            ).exists()
        )
        self.assertFalse(
            InventoryMove.objects.filter(
                entity=self.entity,
                txn_type=TxnType.INVENTORY_TRANSFER,
                txn_id=created.id,
            ).exists()
        )

    def test_adjustment_create_rolls_back_header_when_line_persistence_fails(self):
        with patch.object(
            InventoryAdjustmentService,
            '_build_adjustment_lines_and_inputs',
            side_effect=RuntimeError('injected line persistence failure'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'injected line persistence failure'):
                InventoryAdjustmentService.create_adjustment(
                    payload=self._adjustment_payload(),
                    user_id=self.user.id,
                )

        self.assertFalse(
            InventoryAdjustment.objects.filter(
                entity=self.entity,
                reference_no='ADJ-1001',
            ).exists()
        )

    def test_stale_transfer_and_adjustment_updates_return_conflict_without_mutation(self):
        transfer = InventoryTransferService.create_transfer(
            payload=self._transfer_payload(),
            user_id=self.user.id,
        ).transfer
        stale_transfer_version = transfer.updated_at
        InventoryTransfer.objects.filter(pk=transfer.id).update(
            reference_no='NEWER-TRANSFER',
            updated_at=timezone.now(),
        )
        transfer_payload = self._transfer_payload()
        transfer_payload['expected_updated_at'] = stale_transfer_version.isoformat()
        transfer_payload['reference_no'] = 'STALE-TRANSFER'
        transfer_response = self.client.patch(
            reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer.id}),
            transfer_payload,
            format='json',
        )
        self.assertEqual(transfer_response.status_code, 409)
        self.assertEqual(transfer_response.json()['code'], 'stale_object')
        transfer.refresh_from_db()
        self.assertEqual(transfer.reference_no, 'NEWER-TRANSFER')

        adjustment = InventoryAdjustmentService.create_adjustment(
            payload=self._adjustment_payload(),
            user_id=self.user.id,
            auto_post=False,
        ).adjustment
        stale_adjustment_version = adjustment.updated_at
        InventoryAdjustment.objects.filter(pk=adjustment.id).update(
            reference_no='NEWER-ADJUSTMENT',
            updated_at=timezone.now(),
        )
        adjustment_payload = self._adjustment_payload()
        adjustment_payload['expected_updated_at'] = stale_adjustment_version.isoformat()
        adjustment_payload['reference_no'] = 'STALE-ADJUSTMENT'
        adjustment_response = self.client.patch(
            reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': adjustment.id}),
            adjustment_payload,
            format='json',
        )
        self.assertEqual(adjustment_response.status_code, 409)
        self.assertEqual(adjustment_response.json()['code'], 'stale_object')
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.reference_no, 'NEWER-ADJUSTMENT')

    def test_direct_object_actions_require_permissions_without_partial_mutation(self):
        transfer_resp = self.client.post(
            reverse('inventory_ops:inventory-transfers'),
            self._transfer_payload(),
            format='json',
        )
        adjustment_resp = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            self._adjustment_payload(),
            format='json',
        )
        self.assertEqual(transfer_resp.status_code, 201)
        self.assertEqual(adjustment_resp.status_code, 201)
        transfer_id = transfer_resp.json()['transfer']['id']
        adjustment_id = adjustment_resp.json()['adjustment']['id']

        outsider = User.objects.create_user(
            username=f'inventory-outsider-{uuid4().hex[:8]}',
            email=f'inventory-outsider-{uuid4().hex[:8]}@example.com',
            password='pass123',
        )
        self.client.force_authenticate(user=outsider)
        self.assertEqual(
            self.client.get(reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer_id})).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}, format='json').status_code,
            403,
        )
        self.client.force_authenticate(user=self.user)

        denied_codes = [
            'inventory.transfer.view',
            'inventory.transfer.update',
            'inventory.transfer.post',
            'inventory.transfer.unpost',
            'inventory.transfer.cancel',
            'inventory.adjustment.view',
            'inventory.adjustment.update',
            'inventory.adjustment.post',
            'inventory.adjustment.unpost',
            'inventory.adjustment.cancel',
        ]
        RolePermission.objects.filter(role=self.role, permission__code__in=denied_codes).delete()

        denied_requests = [
            ('get', reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer_id}), None),
            ('patch', reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer_id}), self._transfer_payload()),
            ('post', reverse('inventory_ops:inventory-transfer-post', kwargs={'pk': transfer_id}), {}),
            ('post', reverse('inventory_ops:inventory-transfer-unpost', kwargs={'pk': transfer_id}), {'reason': 'Denied'}),
            ('post', reverse('inventory_ops:inventory-transfer-cancel', kwargs={'pk': transfer_id}), {'reason': 'Denied'}),
            ('get', reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': adjustment_id}), None),
            ('patch', reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': adjustment_id}), self._adjustment_payload()),
            ('post', reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}),
            ('post', reverse('inventory_ops:inventory-adjustment-unpost', kwargs={'pk': adjustment_id}), {'reason': 'Denied'}),
            ('post', reverse('inventory_ops:inventory-adjustment-cancel', kwargs={'pk': adjustment_id}), {'reason': 'Denied'}),
        ]
        for method, url, payload in denied_requests:
            response = getattr(self.client, method)(url, payload, format='json') if payload is not None else getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403, f'{method.upper()} {url} should be denied')

        self.assertEqual(InventoryTransfer.objects.get(pk=transfer_id).status, 'DRAFT')
        self.assertEqual(InventoryAdjustment.objects.get(pk=adjustment_id).status, 'DRAFT')
        self.assertFalse(Entry.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer_id).exists())
        self.assertFalse(Entry.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment_id).exists())
        self.assertFalse(InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer_id).exists())
        self.assertFalse(InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment_id).exists())

    def test_branch_scoped_user_cannot_access_or_post_other_branch_objects(self):
        branch_a_response = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            self._adjustment_payload(),
            format='json',
        )
        self.assertEqual(branch_a_response.status_code, 201)

        branch_b_payload = self._adjustment_payload()
        branch_b_payload.update({
            'entityfinid': self.entityfin_alt.id,
            'subentity': self.subentity_alt.id,
            'adjustment_date': '2026-04-12',
            'location': self.source_alt.id,
            'reference_no': 'ADJ-BRANCH-B',
        })
        branch_b_response = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            branch_b_payload,
            format='json',
        )
        self.assertEqual(branch_b_response.status_code, 201)

        branch_user = User.objects.create_user(
            username=f'inventory-branch-user-{uuid4().hex[:8]}',
            email=f'inventory-branch-user-{uuid4().hex[:8]}@example.com',
            password='pass123',
        )
        self.entity.refresh_from_db()
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=branch_user,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.user,
        )
        branch_role = Role.objects.create(
            entity=self.entity,
            name='Branch A Inventory Operator',
            code=f'inventory_branch_a_{uuid4().hex[:8]}',
            role_level=Role.LEVEL_ENTITY,
            createdby=self.user,
        )
        for role_permission in RolePermission.objects.filter(role=self.role, isactive=True):
            RolePermission.objects.create(
                role=branch_role,
                permission=role_permission.permission,
                effect=role_permission.effect,
            )
        UserRoleAssignment.objects.create(
            user=branch_user,
            entity=self.entity,
            role=branch_role,
            subentity=self.subentity,
            assigned_by=self.user,
        )

        branch_a_id = branch_a_response.json()['adjustment']['id']
        branch_b_id = branch_b_response.json()['adjustment']['id']
        self.client.force_authenticate(user=branch_user)

        self.assertEqual(
            self.client.get(
                reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': branch_a_id})
            ).status_code,
            200,
        )
        denied_detail = self.client.get(
            reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': branch_b_id})
        )
        denied_post = self.client.post(
            reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': branch_b_id}),
            {},
            format='json',
        )
        self.assertEqual(denied_detail.status_code, 403)
        self.assertEqual(denied_post.status_code, 403)

        branch_b_adjustment = InventoryAdjustment.objects.get(pk=branch_b_id)
        self.assertEqual(branch_b_adjustment.status, 'DRAFT')
        self.assertFalse(
            InventoryMove.objects.filter(
                txn_type=TxnType.INVENTORY_ADJUSTMENT,
                txn_id=branch_b_id,
            ).exists()
        )

    def test_financial_year_policy_blocks_direct_access_and_post_without_mutation(self):
        current_response = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            self._adjustment_payload(),
            format='json',
        )
        self.assertEqual(current_response.status_code, 201)

        alternate_payload = self._adjustment_payload()
        alternate_payload.update({
            'entityfinid': self.entityfin_alt.id,
            'adjustment_date': '2026-04-12',
            'reference_no': 'ADJ-RESTRICTED-FY',
        })
        alternate_response = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            alternate_payload,
            format='json',
        )
        self.assertEqual(alternate_response.status_code, 201)

        policy = DataAccessPolicy.objects.create(
            entity=self.entity,
            name='Current FY only',
            code=f'current_fy_only_{uuid4().hex[:8]}',
            policy_type=DataAccessPolicy.TYPE_FINANCIAL_YEAR,
            scope_mode=DataAccessPolicy.MODE_INCLUDE,
            configuration={'ids': [self.entityfin.id]},
        )
        RoleDataAccessPolicy.objects.create(role=self.role, policy=policy)

        current_id = current_response.json()['adjustment']['id']
        alternate_id = alternate_response.json()['adjustment']['id']
        self.assertEqual(
            self.client.get(
                reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': current_id})
            ).status_code,
            200,
        )
        denied_detail = self.client.get(
            reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': alternate_id})
        )
        denied_post = self.client.post(
            reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': alternate_id}),
            {},
            format='json',
        )
        self.assertEqual(denied_detail.status_code, 403)
        self.assertEqual(denied_post.status_code, 403)
        list_response = self.client.get(
            reverse('inventory_ops:inventory-adjustments-list'),
            {'entity': self.entity.id},
        )
        self.assertEqual(list_response.status_code, 200)
        listed_ids = {row['id'] for row in list_response.json()['rows']}
        self.assertIn(current_id, listed_ids)
        self.assertNotIn(alternate_id, listed_ids)
        restricted_adjustment = InventoryAdjustment.objects.get(pk=alternate_id)
        self.assertEqual(restricted_adjustment.status, 'DRAFT')
        self.assertFalse(
            InventoryMove.objects.filter(
                txn_type=TxnType.INVENTORY_ADJUSTMENT,
                txn_id=alternate_id,
            ).exists()
        )

    def test_warehouse_policy_blocks_same_branch_direct_access_and_post(self):
        allowed_response = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            self._adjustment_payload(),
            format='json',
        )
        self.assertEqual(allowed_response.status_code, 201)

        restricted_payload = self._adjustment_payload()
        restricted_payload.update({
            'location': self.destination.id,
            'reference_no': 'ADJ-RESTRICTED-WAREHOUSE',
        })
        restricted_response = self.client.post(
            reverse('inventory_ops:inventory-adjustments'),
            restricted_payload,
            format='json',
        )
        self.assertEqual(restricted_response.status_code, 201)

        policy = DataAccessPolicy.objects.create(
            entity=self.entity,
            name='Main warehouse only',
            code=f'main_warehouse_only_{uuid4().hex[:8]}',
            policy_type=DataAccessPolicy.TYPE_WAREHOUSE,
            scope_mode=DataAccessPolicy.MODE_INCLUDE,
            configuration={'ids': [self.source.id]},
        )
        RoleDataAccessPolicy.objects.create(role=self.role, policy=policy)

        allowed_id = allowed_response.json()['adjustment']['id']
        restricted_id = restricted_response.json()['adjustment']['id']
        self.assertEqual(
            self.client.get(
                reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': allowed_id})
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': restricted_id})
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': restricted_id}),
                {},
                format='json',
            ).status_code,
            403,
        )
        list_response = self.client.get(
            reverse('inventory_ops:inventory-adjustments-list'),
            {'entity': self.entity.id},
        )
        self.assertEqual(list_response.status_code, 200)
        listed_ids = {row['id'] for row in list_response.json()['rows']}
        self.assertIn(allowed_id, listed_ids)
        self.assertNotIn(restricted_id, listed_ids)
        restricted_adjustment = InventoryAdjustment.objects.get(pk=restricted_id)
        self.assertEqual(restricted_adjustment.status, 'DRAFT')
        self.assertFalse(
            InventoryMove.objects.filter(
                txn_type=TxnType.INVENTORY_ADJUSTMENT,
                txn_id=restricted_id,
            ).exists()
        )

        denied_transfer = self.client.post(
            reverse('inventory_ops:inventory-transfers'),
            self._transfer_payload(),
            format='json',
        )
        self.assertEqual(denied_transfer.status_code, 403)
        self.assertFalse(
            InventoryTransfer.objects.filter(reference_no='REF-1001').exists()
        )

    def test_create_adjustment_saves_draft_without_posting_moves(self):
        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), self._adjustment_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['adjustment']['status'], 'DRAFT')
        self.assertTrue(body['adjustment']['action_flags']['can_edit'])
        self.assertTrue(body['adjustment']['action_flags']['can_post'])
        self.assertTrue(body['adjustment']['action_flags']['can_cancel'])
        self.assertFalse(body['adjustment']['action_flags']['can_unpost'])
        self.assertEqual(body['adjustment']['location_id'], self.source.id)
        self.assertAlmostEqual(float(body['adjustment']['total_qty']), 2.0)
        self.assertAlmostEqual(float(body['adjustment']['total_value']), 50000.0)
        adjustment_id = body['adjustment']['id']
        self.assertEqual(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').count(), 0)

    def test_create_adjustment_rolls_back_header_when_later_line_fails_service_validation(self):
        payload = self._adjustment_payload()
        payload['reference_no'] = 'ADJ-ROLLBACK'
        payload['lines'].append({
            'product': self.batch_product.id,
            'direction': 'DECREASE',
            'qty': '1.0000',
            'unit_cost': '15.0000',
            'batch_number': '',
        })

        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Batch number is required', str(response.json()))
        self.assertFalse(InventoryAdjustment.objects.filter(reference_no='ADJ-ROLLBACK').exists())

    def test_create_adjustment_rejects_oversized_fields(self):
        payload = self._adjustment_payload()
        payload['reference_no'] = 'R' * 101
        payload['narration'] = 'N' * 501
        payload['lines'][0]['batch_number'] = 'B' * 81
        payload['lines'][0]['note'] = 'T' * 201

        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('reference_no', response.json())
        self.assertIn('narration', response.json())

    def test_create_adjustment_rejects_unknown_warehouse_before_service(self):
        payload = self._adjustment_payload()
        payload['location'] = 999999

        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['warehouse'], 'Warehouse is not valid for this entity.')

    def test_adjustment_post_unpost_and_cancel_flow(self):
        created = self.client.post(reverse('inventory_ops:inventory-adjustments'), self._adjustment_payload(), format='json')
        self.assertEqual(created.status_code, 201)
        adjustment_id = created.json()['adjustment']['id']

        post_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual(post_resp.json()['adjustment']['status'], 'POSTED')
        self.assertTrue(post_resp.json()['adjustment']['action_flags']['can_unpost'])
        self.assertTrue(post_resp.json()['adjustment']['action_flags']['is_read_only'])
        self.assertEqual(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').count(), 1)

        repeated_post = self.client.post(reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(repeated_post.status_code, 200)
        self.assertEqual(repeated_post.json()['adjustment']['posting_entry_id'], post_resp.json()['adjustment']['posting_entry_id'])
        self.assertEqual(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').count(), 1)

        unpost_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-unpost', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(unpost_resp.status_code, 200)
        self.assertEqual(unpost_resp.json()['adjustment']['status'], 'DRAFT')
        self.assertEqual(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').count(), 0)
        reversal_entry_id = unpost_resp.json()['adjustment']['posting_entry_id']
        reversal_entry = Entry.objects.get(pk=reversal_entry_id)
        self.assertEqual(reversal_entry.status, EntryStatus.REVERSED)
        self.assertEqual(JournalLine.objects.filter(entry_id=reversal_entry_id).count(), 0)
        self.assertTrue(PostingBatch.objects.get(pk=reversal_entry.posting_batch_id).is_active)

        cancel_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-cancel', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()['adjustment']['status'], 'CANCELLED')
        repeated_cancel = self.client.post(reverse('inventory_ops:inventory-adjustment-cancel', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(repeated_cancel.status_code, 200)
        self.assertEqual(repeated_cancel.json()['adjustment']['status'], 'CANCELLED')

    def test_adjustment_update_replaces_lines_for_draft(self):
        created = self.client.post(reverse('inventory_ops:inventory-adjustments'), self._adjustment_payload(), format='json')
        adjustment_id = created.json()['adjustment']['id']
        payload = self._adjustment_payload()
        payload['lines'][0]['qty'] = '3.0000'
        payload['lines'][0]['note'] = 'Updated quantity'
        response = self.client.patch(reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': adjustment_id}), payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['adjustment']['status'], 'DRAFT')
        self.assertAlmostEqual(float(response.json()['adjustment']['total_qty']), 3.0)
        self.assertEqual(response.json()['adjustment']['lines'][0]['note'], 'Updated quantity')

    def test_increase_adjustment_requires_cost_when_no_default_exists(self):
        unstocked_product = Product.objects.create(
            entity=self.entity,
            productname='Projector',
            sku='PRJ-001',
            productdesc='Unstocked product without default cost',
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_serialized=False,
        )
        payload = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'adjustment_date': '2025-04-12',
            'location': self.source.id,
            'reference_no': 'ADJ-1003',
            'narration': 'Stock gain',
            'lines': [
                {
                    'product': unstocked_product.id,
                    'direction': 'INCREASE',
                    'qty': '1.0000',
                    'note': 'Count gain',
                }
            ],
        }
        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unit cost is required', str(response.json()))

    def test_increase_adjustment_uses_default_cost_when_explicit_cost_is_omitted(self):
        payload = self._adjustment_payload()
        payload['reference_no'] = 'ADJ-1002A'
        payload['lines'][0].pop('unit_cost', None)
        payload['lines'][0]['qty'] = '1.0000'
        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')
        self.assertEqual(response.status_code, 201)
        line = response.json()['adjustment']['lines'][0]
        self.assertAlmostEqual(float(line['unit_cost']), 25000.0)

    def test_adjustment_supports_alternate_uom_and_posts_base_qty(self):
        payload = self._adjustment_payload()
        payload['reference_no'] = 'ADJ-UOM-1'
        payload['lines'][0]['uom_id'] = self.box_uom.id
        payload['lines'][0]['qty'] = '2.0000'
        payload['lines'][0]['unit_cost'] = '250000.0000'
        created = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')
        self.assertEqual(created.status_code, 201)
        body = created.json()['adjustment']
        self.assertEqual(body['lines'][0]['uom_id'], self.box_uom.id)
        self.assertEqual(body['lines'][0]['uom_name'], 'BOX')

        adjustment_id = body['id']
        post_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(post_resp.status_code, 200)
        moves = list(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').order_by('id'))
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].uom_id, self.box_uom.id)
        self.assertEqual(str(moves[0].qty), '2.0000')
        self.assertEqual(str(moves[0].base_qty), '20.0000')
        self.assertEqual(str(moves[0].uom_factor), '10.00000000')
        self.assertEqual(str(moves[0].unit_cost), '25000.0000')

    def test_adjustment_detail_returns_location_id(self):
        created = self.client.post(reverse('inventory_ops:inventory-adjustments'), self._adjustment_payload(), format='json')
        self.assertEqual(created.status_code, 201)
        adjustment_id = created.json()['adjustment']['id']
        response = self.client.get(reverse('inventory_ops:inventory-adjustment-detail', kwargs={'pk': adjustment_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['location_id'], self.source.id)
        self.assertIn('action_flags', response.json())

    def test_inventory_entry_meta_returns_products_policy_and_actions(self):
        response = self.client.get(
            reverse('inventory_ops:inventory-entry-meta'),
            {
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['entity_id'], self.entity.id)
        self.assertEqual(body['entityfinid_id'], self.entityfin.id)
        self.assertEqual(body['subentity_id'], self.subentity.id)
        self.assertTrue(any(row['id'] == self.product.id for row in body['products']))
        self.assertIn('policy', body)
        self.assertEqual(body['policy']['transfer_shortage_rule'], 'block')
        self.assertIn('actions', body)
        self.assertTrue(body['actions']['can_view_transfer'])
        self.assertTrue(body['actions']['can_create_adjustment'])

    def test_inventory_stock_hint_returns_available_stock_for_transfer(self):
        response = self.client.get(
            reverse('inventory_ops:inventory-stock-hint'),
            {
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
                'operation': 'transfer',
                'product': self.product.id,
                'location': self.source.id,
                'qty': '5.0000',
                'doc_date': '2025-04-12',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['operation'], 'transfer')
        self.assertEqual(body['resolved_location_id'], self.source.id)
        self.assertEqual(body['available_qty'], '20.0000')
        self.assertEqual(body['shortage_qty'], '0.0000')
        self.assertEqual(body['status'], 'info')

    def test_inventory_stock_hint_surfaces_adjustment_shortage(self):
        response = self.client.get(
            reverse('inventory_ops:inventory-stock-hint'),
            {
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
                'operation': 'adjustment',
                'product': self.product.id,
                'location': self.source.id,
                'qty': '25.0000',
                'doc_date': '2025-04-12',
                'direction': 'DECREASE',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['operation'], 'adjustment')
        self.assertEqual(body['direction'], 'DECREASE')
        self.assertEqual(body['available_qty'], '20.0000')
        self.assertEqual(body['shortage_qty'], '5.0000')
        self.assertEqual(body['status'], 'danger')

    def test_decrease_adjustment_requires_batch_and_available_stock_for_batch_item(self):
        missing_batch_payload = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'adjustment_date': '2025-04-12',
            'location': self.source.id,
            'reference_no': 'ADJ-1004',
            'narration': 'Batch decrease',
            'lines': [
                {
                    'product': self.batch_product.id,
                    'direction': 'DECREASE',
                    'qty': '1.0000',
                }
            ],
        }
        missing_batch_resp = self.client.post(reverse('inventory_ops:inventory-adjustments'), missing_batch_payload, format='json')
        self.assertEqual(missing_batch_resp.status_code, 400)
        self.assertIn('Batch number is required', str(missing_batch_resp.json()))

        shortage_payload = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'adjustment_date': '2025-04-12',
            'location': self.source.id,
            'reference_no': 'ADJ-1005',
            'narration': 'Batch decrease shortage',
            'lines': [
                {
                    'product': self.batch_product.id,
                    'direction': 'DECREASE',
                    'qty': '8.0000',
                    'batch_number': 'B-1',
                    'expiry_date': '2026-05-01',
                }
            ],
        }
        shortage_resp = self.client.post(reverse('inventory_ops:inventory-adjustments'), shortage_payload, format='json')
        self.assertEqual(shortage_resp.status_code, 400)
        self.assertIn('Insufficient stock', str(shortage_resp.json()))

    def test_expiry_only_adjustment_generates_internal_lot_and_depletes_stock(self):
        payload = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'adjustment_date': '2025-04-12',
            'location': self.source.id,
            'reference_no': 'ADJ-EXP-1',
            'narration': 'Expiry lot shrinkage',
            'lines': [
                {
                    'product': self.expiry_only_product.id,
                    'direction': 'DECREASE',
                    'qty': '2.0000',
                    'expiry_date': '2026-08-15',
                }
            ],
        }
        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')
        self.assertEqual(response.status_code, 201)
        line = response.json()['adjustment']['lines'][0]
        self.assertEqual(line['batch_number'], f'EXP-{self.expiry_only_product.id}-20260815')
        adjustment_id = response.json()['adjustment']['id']

        post_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-post', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(post_resp.status_code, 200)
        move = InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').get()
        self.assertEqual(move.batch_number, f'EXP-{self.expiry_only_product.id}-20260815')
        self.assertEqual(str(move.base_qty), '2.0000')

    def test_inventory_stock_hint_uses_expiry_only_internal_lot(self):
        response = self.client.get(
            reverse('inventory_ops:inventory-stock-hint'),
            {
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
                'operation': 'adjustment',
                'product': self.expiry_only_product.id,
                'location': self.source.id,
                'qty': '8.0000',
                'doc_date': '2025-04-12',
                'direction': 'DECREASE',
                'expiry_date': '2026-08-15',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['batch_number'], f'EXP-{self.expiry_only_product.id}-20260815')
        self.assertEqual(body['available_qty'], '6.0000')
        self.assertEqual(body['shortage_qty'], '2.0000')
        self.assertEqual(body['status'], 'danger')

    def test_adjustment_list_returns_rows(self):
        payload = {
            **self._adjustment_payload(),
            'reference_no': 'ADJ-1002',
            'lines': [
                {
                    'product': self.product.id,
                    'direction': 'DECREASE',
                    'qty': '1.0000',
                    'unit_cost': '25000.0000',
                    'note': 'Count loss',
                }
            ],
        }
        self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')
        response = self.client.get(reverse('inventory_ops:inventory-adjustments-list'), {'entity': self.entity.id})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()['rows']), 1)

    def test_adjustment_list_honors_entityfinid_and_subentity_scope(self):
        payload = {**self._adjustment_payload(), 'reference_no': 'ADJ-SCOPE-A'}
        self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')

        other_scope_payload = {
            **self._adjustment_payload(),
            'entityfinid': self.entityfin_alt.id,
            'subentity': self.subentity_alt.id,
            'location': self.source_alt.id,
            'reference_no': 'ADJ-SCOPE-B',
        }
        other_created = self.client.post(reverse('inventory_ops:inventory-adjustments'), other_scope_payload, format='json')
        self.assertEqual(other_created.status_code, 201)

        response = self.client.get(
            reverse('inventory_ops:inventory-adjustments-list'),
            {'entity': self.entity.id, 'entityfinid': self.entityfin.id, 'subentity': self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        reference_nos = {row['reference_no'] for row in response.json()['rows']}
        self.assertIn('ADJ-SCOPE-A', reference_nos)
        self.assertNotIn('ADJ-SCOPE-B', reference_nos)

    def test_inventory_settings_returns_defaults_and_numbering_rows(self):
        response = self.client.get(
            reverse('inventory_ops:inventory-settings'),
            {'entity': self.entity.id, 'entityfinid': self.entityfin.id, 'subentity': self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['settings']['default_doc_code_transfer'], 'ITF')
        self.assertEqual(body['settings']['default_doc_code_adjustment'], 'IAD')
        self.assertEqual(len(body['numbering_series']), 2)
        self.assertTrue(DocumentType.objects.filter(module='inventory_ops', doc_key='INVENTORY_TRANSFER').exists())

    def test_inventory_settings_patch_updates_codes_and_series(self):
        response = self.client.patch(
            reverse('inventory_ops:inventory-settings'),
            {
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
                'settings': {
                    'default_doc_code_transfer': 'TRF',
                    'default_doc_code_adjustment': 'ADJ',
                    'default_workflow_action': 'draft',
                    'auto_derive_transfer_cost': True,
                    'allow_manual_transfer_cost_override': False,
                    'require_batch_for_batch_managed_items': True,
                },
                'numbering_series': [
                    {
                        'series_key': 'inventory_transfer',
                        'doc_code': 'TRF',
                        'prefix': 'TRF',
                        'suffix': '',
                        'starting_number': 10,
                        'current_number': 12,
                        'number_padding': 4,
                        'separator': '/',
                        'reset_frequency': 'yearly',
                        'include_year': False,
                        'include_month': False,
                        'custom_format': '',
                        'is_active': True,
                    },
                    {
                        'series_key': 'inventory_adjustment',
                        'doc_code': 'ADJ',
                        'prefix': 'ADJ',
                        'suffix': '',
                        'starting_number': 2,
                        'current_number': 3,
                        'number_padding': 4,
                        'separator': '/',
                        'reset_frequency': 'yearly',
                        'include_year': False,
                        'include_month': False,
                        'custom_format': '',
                        'is_active': True,
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['settings']['default_doc_code_transfer'], 'TRF')
        self.assertEqual(body['settings']['default_doc_code_adjustment'], 'ADJ')
        transfer_series = DocumentNumberSeries.objects.get(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_code='TRF',
        )
        self.assertEqual(transfer_series.prefix, 'TRF')
        self.assertEqual(transfer_series.current_number, 12)


    def test_batch_policy_filters_and_blocks_inventory_documents_without_mutation(self):
        def batch_payload(batch_number, reference):
            payload = self._adjustment_payload()
            payload["reference_no"] = reference
            payload["lines"] = [{
                "product": self.batch_product.id,
                "direction": "INCREASE",
                "qty": "2.0000",
                "unit_cost": "100.0000",
                "batch_number": batch_number,
                "expiry_date": "2026-04-30",
                "note": "Batch scope proof",
            }]
            return payload

        allowed = self.client.post(
            reverse("inventory_ops:inventory-adjustments"),
            batch_payload("LOT-ALLOWED", "ADJ-BATCH-ALLOWED"),
            format="json",
        )
        restricted = self.client.post(
            reverse("inventory_ops:inventory-adjustments"),
            batch_payload("LOT-RESTRICTED", "ADJ-BATCH-RESTRICTED"),
            format="json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.json())
        self.assertEqual(restricted.status_code, 201, restricted.json())

        policy = DataAccessPolicy.objects.create(
            entity=self.entity,
            name="Allowed inventory lots",
            code=f"allowed_inventory_lots_{uuid4().hex[:8]}",
            policy_type=DataAccessPolicy.TYPE_BATCH,
            scope_mode=DataAccessPolicy.MODE_INCLUDE,
            configuration={"values": ["LOT-ALLOWED"]},
        )
        RoleDataAccessPolicy.objects.create(role=self.role, policy=policy)

        allowed_id = allowed.json()["adjustment"]["id"]
        restricted_id = restricted.json()["adjustment"]["id"]
        self.assertEqual(self.client.get(
            reverse("inventory_ops:inventory-adjustment-detail", kwargs={"pk": allowed_id})
        ).status_code, 200)
        self.assertEqual(self.client.get(
            reverse("inventory_ops:inventory-adjustment-detail", kwargs={"pk": restricted_id})
        ).status_code, 403)
        self.assertEqual(self.client.post(
            reverse("inventory_ops:inventory-adjustment-post", kwargs={"pk": restricted_id}),
            {},
            format="json",
        ).status_code, 403)

        listed = self.client.get(
            reverse("inventory_ops:inventory-adjustments-list"),
            {"entity": self.entity.id},
        )
        listed_ids = {row["id"] for row in listed.json()["rows"]}
        self.assertIn(allowed_id, listed_ids)
        self.assertNotIn(restricted_id, listed_ids)

        denied_create = self.client.post(
            reverse("inventory_ops:inventory-adjustments"),
            batch_payload("LOT-DENIED-NEW", "ADJ-BATCH-DENIED-NEW"),
            format="json",
        )
        self.assertEqual(denied_create.status_code, 403)
        self.assertFalse(InventoryAdjustment.objects.filter(reference_no="ADJ-BATCH-DENIED-NEW").exists())
        restricted_document = InventoryAdjustment.objects.get(pk=restricted_id)
        self.assertEqual(restricted_document.status, "DRAFT")
        self.assertFalse(InventoryMove.objects.filter(
            txn_type=TxnType.INVENTORY_ADJUSTMENT,
            txn_id=restricted_id,
        ).exists())


@skipUnless(connection.vendor == 'postgresql', 'Concurrent posting requires PostgreSQL row locking.')
@override_settings(ROOT_URLCONF='FA.urls', AUTH_PASSWORD_VALIDATORS=[])
class InventoryOpsConcurrencyTests(APITransactionTestCase):
    setUp = InventoryOpsTests.setUp
    _grant_inventory_permission = InventoryOpsTests._grant_inventory_permission
    _seed_source_stock = InventoryOpsTests._seed_source_stock
    _transfer_payload = InventoryOpsTests._transfer_payload
    _adjustment_payload = InventoryOpsTests._adjustment_payload

    def _post_concurrently(self, callback):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callback()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        return results

    def _capture_callbacks_concurrently(self, *callbacks):
        barrier = Barrier(len(callbacks))

        def worker(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callback()
            except Exception as exc:  # The losing transition is part of the asserted outcome.
                return exc
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(callbacks)) as executor:
            return list(executor.map(worker, callbacks))

    def test_simultaneous_transfer_post_and_retry_create_one_posting(self):
        transfer = InventoryTransferService.create_transfer(
            payload=self._transfer_payload(),
            user_id=self.user.id,
        ).transfer

        results = self._post_concurrently(
            lambda: InventoryTransferService.post_transfer(
                transfer_id=transfer.id,
                user_id=self.user.id,
            )
        )
        retry = InventoryTransferService.post_transfer(
            transfer_id=transfer.id,
            user_id=self.user.id,
        )

        entry_ids = {result.entry_id for result in results}
        entry_ids.add(retry.entry_id)
        self.assertEqual(len(entry_ids), 1)
        self.assertEqual(
            Entry.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id).count(),
            1,
        )
        self.assertEqual(
            PostingBatch.objects.filter(
                txn_type=TxnType.INVENTORY_TRANSFER,
                txn_id=transfer.id,
                is_active=True,
            ).count(),
            1,
        )
        moves = InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id)
        self.assertEqual(moves.count(), 2)
        self.assertEqual(set(moves.values_list('move_type', flat=True)), {'IN', 'OUT'})

    def test_simultaneous_adjustment_post_and_retry_create_one_posting(self):
        adjustment = InventoryAdjustmentService.create_adjustment(
            payload={
                'entity': self.entity.id,
                'entityfinid': self.entityfin.id,
                'subentity': self.subentity.id,
                'adjustment_date': '2025-04-13',
                'location': self.destination.id,
                'reference_no': 'ADJ-CONCURRENT-1',
                'narration': 'Concurrent posting regression',
                'lines': [
                    {
                        'product': self.product.id,
                        'direction': 'INCREASE',
                        'qty': '2.5000',
                        'unit_cost': '25000.0000',
                        'note': 'Concurrent increase',
                    }
                ],
            },
            user_id=self.user.id,
            auto_post=False,
        ).adjustment

        results = self._post_concurrently(
            lambda: InventoryAdjustmentService.post_adjustment(
                adjustment_id=adjustment.id,
                user_id=self.user.id,
            )
        )
        retry = InventoryAdjustmentService.post_adjustment(
            adjustment_id=adjustment.id,
            user_id=self.user.id,
        )

        entry_ids = {result.entry_id for result in results}
        entry_ids.add(retry.entry_id)
        self.assertEqual(len(entry_ids), 1)
        self.assertEqual(
            Entry.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id).count(),
            1,
        )
        self.assertEqual(
            PostingBatch.objects.filter(
                txn_type=TxnType.INVENTORY_ADJUSTMENT,
                txn_id=adjustment.id,
                is_active=True,
            ).count(),
            1,
        )
        moves = InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id)
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.get().base_qty, Decimal('2.5000'))

    def test_simultaneous_unpost_creates_one_reversal_for_each_document_type(self):
        transfer = InventoryTransferService.create_transfer(
            payload=self._transfer_payload(),
            user_id=self.user.id,
        ).transfer
        InventoryTransferService.post_transfer(transfer_id=transfer.id, user_id=self.user.id)

        transfer_results = self._capture_callbacks_concurrently(
            lambda: InventoryTransferService.unpost_transfer(transfer_id=transfer.id, user_id=self.user.id),
            lambda: InventoryTransferService.unpost_transfer(transfer_id=transfer.id, user_id=self.user.id),
        )
        transfer.refresh_from_db()
        self.assertEqual(sum(not isinstance(result, Exception) for result in transfer_results), 1)
        self.assertEqual(transfer.status, 'DRAFT')
        self.assertEqual(
            Entry.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id).count(),
            1,
        )
        self.assertEqual(
            InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id).count(),
            0,
        )
        self.assertEqual(Entry.objects.get(pk=transfer.posting_entry_id).status, EntryStatus.REVERSED)

        adjustment_payload = self._adjustment_payload()
        adjustment_payload['reference_no'] = 'ADJ-CONCURRENT-UNPOST'
        adjustment = InventoryAdjustmentService.create_adjustment(
            payload=adjustment_payload,
            user_id=self.user.id,
            auto_post=False,
        ).adjustment
        InventoryAdjustmentService.post_adjustment(adjustment_id=adjustment.id, user_id=self.user.id)

        adjustment_results = self._capture_callbacks_concurrently(
            lambda: InventoryAdjustmentService.unpost_adjustment(adjustment_id=adjustment.id, user_id=self.user.id),
            lambda: InventoryAdjustmentService.unpost_adjustment(adjustment_id=adjustment.id, user_id=self.user.id),
        )
        adjustment.refresh_from_db()
        self.assertEqual(sum(not isinstance(result, Exception) for result in adjustment_results), 1)
        self.assertEqual(adjustment.status, 'DRAFT')
        self.assertEqual(
            Entry.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id).count(),
            1,
        )
        self.assertEqual(
            InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id).count(),
            0,
        )
        self.assertEqual(Entry.objects.get(pk=adjustment.posting_entry_id).status, EntryStatus.REVERSED)

    def test_simultaneous_cancel_is_idempotent_for_each_document_type(self):
        transfer = InventoryTransferService.create_transfer(
            payload=self._transfer_payload(),
            user_id=self.user.id,
        ).transfer
        transfer_results = self._post_concurrently(
            lambda: InventoryTransferService.cancel_transfer(transfer_id=transfer.id, user_id=self.user.id)
        )
        transfer.refresh_from_db()
        self.assertEqual({result.transfer.status for result in transfer_results}, {'CANCELLED'})
        self.assertEqual(transfer.status, 'CANCELLED')
        self.assertFalse(Entry.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id).exists())

        adjustment_payload = self._adjustment_payload()
        adjustment_payload['reference_no'] = 'ADJ-CONCURRENT-CANCEL'
        adjustment = InventoryAdjustmentService.create_adjustment(
            payload=adjustment_payload,
            user_id=self.user.id,
            auto_post=False,
        ).adjustment
        adjustment_results = self._post_concurrently(
            lambda: InventoryAdjustmentService.cancel_adjustment(adjustment_id=adjustment.id, user_id=self.user.id)
        )
        adjustment.refresh_from_db()
        self.assertEqual({result.adjustment.status for result in adjustment_results}, {'CANCELLED'})
        self.assertEqual(adjustment.status, 'CANCELLED')
        self.assertFalse(Entry.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id).exists())

    def test_simultaneous_update_and_post_leave_one_complete_posting(self):
        transfer = InventoryTransferService.create_transfer(
            payload=self._transfer_payload(),
            user_id=self.user.id,
        ).transfer
        updated_payload = self._transfer_payload()
        updated_payload['reference_no'] = 'REF-CONCURRENT-UPDATE'
        updated_payload['lines'][0]['qty'] = '3.0000'

        results = self._capture_callbacks_concurrently(
            lambda: InventoryTransferService.update_transfer(
                transfer_id=transfer.id,
                payload=updated_payload,
                user_id=self.user.id,
            ),
            lambda: InventoryTransferService.post_transfer(transfer_id=transfer.id, user_id=self.user.id),
        )
        transfer.refresh_from_db()
        self.assertGreaterEqual(sum(not isinstance(result, Exception) for result in results), 1)
        self.assertEqual(transfer.status, 'POSTED')
        self.assertEqual(
            Entry.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id).count(),
            1,
        )
        moves = InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_TRANSFER, txn_id=transfer.id)
        self.assertEqual(moves.count(), 2)
        outbound_qty = abs(moves.get(move_type=InventoryMove.MoveType.OUT).base_qty)
        self.assertIn(outbound_qty, {Decimal('3.0000'), Decimal('5.0000')})

        adjustment_payload = self._adjustment_payload()
        adjustment_payload['reference_no'] = 'ADJ-CONCURRENT-UPDATE-POST'
        adjustment = InventoryAdjustmentService.create_adjustment(
            payload=adjustment_payload,
            user_id=self.user.id,
            auto_post=False,
        ).adjustment
        updated_adjustment_payload = self._adjustment_payload()
        updated_adjustment_payload['reference_no'] = 'ADJ-CONCURRENT-UPDATED'
        updated_adjustment_payload['lines'][0]['qty'] = '1.2500'

        results = self._capture_callbacks_concurrently(
            lambda: InventoryAdjustmentService.update_adjustment(
                adjustment_id=adjustment.id,
                payload=updated_adjustment_payload,
                user_id=self.user.id,
            ),
            lambda: InventoryAdjustmentService.post_adjustment(
                adjustment_id=adjustment.id,
                user_id=self.user.id,
            ),
        )
        adjustment.refresh_from_db()
        self.assertGreaterEqual(sum(not isinstance(result, Exception) for result in results), 1)
        self.assertEqual(adjustment.status, 'POSTED')
        self.assertEqual(
            Entry.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id).count(),
            1,
        )
        moves = InventoryMove.objects.filter(txn_type=TxnType.INVENTORY_ADJUSTMENT, txn_id=adjustment.id)
        self.assertEqual(moves.count(), 1)
        self.assertIn(abs(moves.get().base_qty), {Decimal('1.2500'), Decimal('2.0000')})
