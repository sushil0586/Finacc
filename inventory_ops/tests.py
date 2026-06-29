from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, ProductUomConversion, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity
from numbering.models import DocumentNumberSeries, DocumentType
from posting.models import InventoryMove
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from inventory_ops.services import InventoryAdjustmentService


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

        unpost_resp = self.client.post(reverse('inventory_ops:inventory-transfer-unpost', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(unpost_resp.status_code, 200)
        self.assertEqual(unpost_resp.json()['transfer']['status'], 'DRAFT')
        self.assertEqual(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').count(), 0)

        cancel_resp = self.client.post(reverse('inventory_ops:inventory-transfer-cancel', kwargs={'pk': transfer_id}), {}, format='json')
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()['transfer']['status'], 'CANCELLED')

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

        unpost_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-unpost', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(unpost_resp.status_code, 200)
        self.assertEqual(unpost_resp.json()['adjustment']['status'], 'DRAFT')
        self.assertEqual(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').count(), 0)

        cancel_resp = self.client.post(reverse('inventory_ops:inventory-adjustment-cancel', kwargs={'pk': adjustment_id}), {}, format='json')
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()['adjustment']['status'], 'CANCELLED')

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
