from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity, UnitType
from posting.models import InventoryMove
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


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

        self.unit_type = UnitType.objects.create(UnitName='Business', UnitDesc='Business')
        self.gst_type = GstRegistrationType.objects.create(Name='Regular', Description='Regular')
        self.entity = Entity.objects.create(
            entityname='Inventory Ops Entity',
            legalname='Inventory Ops Entity Pvt Ltd',
            unitType=self.unit_type,
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
        self._grant_inventory_permission('inventory.adjustment.view')
        self._grant_inventory_permission('inventory.adjustment.create')
        self._grant_inventory_permission('inventory.location.view')
        self._grant_inventory_permission('inventory.location.create')
        self._grant_inventory_permission('inventory.location.update')
        self._grant_inventory_permission('inventory.location.delete')

    def _grant_inventory_permission(self, permission_code: str):
        permission, _ = Permission.objects.get_or_create(
            code=permission_code,
            defaults={
                'name': permission_code,
                'module': 'inventory',
                'resource': 'transfer',
                'action': 'create' if permission_code.endswith('.create') else 'view',
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

    def test_create_transfer_posts_inventory_only_moves(self):
        response = self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['transfer']['status'], 'POSTED')
        self.assertIsNotNone(body['transfer']['posting_entry_id'])
        self.assertAlmostEqual(float(body['transfer']['total_qty']), 5.0)
        self.assertAlmostEqual(float(body['transfer']['total_value']), 125000.0)

        transfer_id = body['transfer']['id']
        self.assertTrue(body['transfer']['transfer_no'].startswith('ITF-'))
        self.assertEqual(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').count(), 2)

        moves = list(InventoryMove.objects.filter(txn_id=transfer_id, txn_type='IT').order_by('id'))
        self.assertEqual(moves[0].movement_nature, InventoryMove.MovementNature.TRANSFER)
        self.assertEqual(moves[0].source_location_id, self.source.id)
        self.assertEqual(moves[0].destination_location_id, self.destination.id)
        self.assertEqual(moves[1].movement_nature, InventoryMove.MovementNature.TRANSFER)
        self.assertEqual(moves[1].source_location_id, self.source.id)
        self.assertEqual(moves[1].destination_location_id, self.destination.id)

    def test_detail_returns_saved_transfer(self):
        created = self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json').json()
        transfer_id = created['transfer']['id']
        response = self.client.get(reverse('inventory_ops:inventory-transfer-detail', kwargs={'pk': transfer_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transfer_no'], created['transfer']['transfer_no'])

    def test_transfer_list_returns_rows(self):
        self.client.post(reverse('inventory_ops:inventory-transfers'), self._transfer_payload(), format='json')
        response = self.client.get(reverse('inventory_ops:inventory-transfers-list'), {'entity': self.entity.id})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()['rows']), 1)

    def test_create_adjustment_posts_inventory_moves(self):
        payload = {
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
        response = self.client.post(reverse('inventory_ops:inventory-adjustments'), payload, format='json')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['adjustment']['status'], 'POSTED')
        self.assertAlmostEqual(float(body['adjustment']['total_qty']), 2.0)
        self.assertAlmostEqual(float(body['adjustment']['total_value']), 50000.0)
        adjustment_id = body['adjustment']['id']
        self.assertEqual(InventoryMove.objects.filter(txn_id=adjustment_id, txn_type='IA').count(), 1)

    def test_adjustment_list_returns_rows(self):
        payload = {
            'entity': self.entity.id,
            'entityfinid': self.entityfin.id,
            'subentity': self.subentity.id,
            'adjustment_date': '2025-04-12',
            'location': self.source.id,
            'reference_no': 'ADJ-1002',
            'narration': 'Adjustment list test',
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
