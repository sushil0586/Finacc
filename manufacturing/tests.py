from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from django.db.models import Sum
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity
from inventory_ops.services import InventoryAdjustmentService
from posting.models import InventoryMove, TxnType
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from manufacturing.models import ManufacturingOperationStatus


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class ManufacturingPhaseOneTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"manufacturing-user-{suffix}",
            email=f"manufacturing-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Manufacturing Entity",
            entitydesc="Manufacturing entity",
            legalname="Manufacturing Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Plant A")
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
            name="Manufacturing Floor",
            code="MFG-01",
            address="Plant",
            city="Ludhiana",
            state="Punjab",
            pincode="141001",
            is_active=True,
        )
        self.finished_location = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name="Finished Goods Store",
            code="FG-01",
            address="Store",
            city="Ludhiana",
            state="Punjab",
            pincode="141002",
            is_active=True,
        )
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Inventory", level=1)
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="KG", description="Kilogram", uqc="KGS")
        self.pack_uom = UnitOfMeasure.objects.create(entity=self.entity, code="PKT", description="Packet", uqc="NOS")
        self.bulk_sugar = Product.objects.create(
            entity=self.entity,
            productname="Sugar Bulk",
            sku="SUG-BULK",
            productdesc="Bulk sugar",
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
        )
        self.pouch = Product.objects.create(
            entity=self.entity,
            productname="Sugar Pouch",
            sku="SUG-POUCH",
            productdesc="Packaging pouch",
            productcategory=self.category,
            base_uom=self.pack_uom,
            is_service=False,
        )
        self.finished_pack = Product.objects.create(
            entity=self.entity,
            productname="Sugar 1kg Pack",
            sku="SUG-1KG",
            productdesc="Packed sugar",
            productcategory=self.category,
            base_uom=self.pack_uom,
            is_service=False,
            is_batch_managed=True,
            is_expiry_tracked=True,
        )
        self.sugar_dust = Product.objects.create(
            entity=self.entity,
            productname="Sugar Dust",
            sku="SUG-DUST",
            productdesc="Saleable sugar dust byproduct",
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            is_expiry_tracked=False,
        )
        self.role = Role.objects.create(
            entity=self.entity,
            name="Manufacturing Operator",
            code=f"manufacturing_operator_{uuid4().hex[:8]}",
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
        for code in (
            "manufacturing.settings.view",
            "manufacturing.bom.view",
            "manufacturing.bom.create",
            "manufacturing.bom.update",
            "manufacturing.bom.delete",
            "manufacturing.workorder.view",
            "manufacturing.workorder.create",
            "manufacturing.workorder.update",
            "manufacturing.workorder.post",
            "manufacturing.workorder.unpost",
            "manufacturing.workorder.cancel",
        ):
            self._grant_permission(code)
        self._seed_stock()

    def _grant_permission(self, permission_code: str):
        action = permission_code.rsplit(".", 1)[-1]
        permission, _ = Permission.objects.get_or_create(
            code=permission_code,
            defaults={
                "name": permission_code,
                "module": "manufacturing",
                "resource": "workorder",
                "action": action,
                "description": permission_code,
                "scope_type": Permission.SCOPE_ENTITY,
                "is_system_defined": True,
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=["isactive"])
        RolePermission.objects.get_or_create(
            role=self.role,
            permission=permission,
            defaults={"effect": RolePermission.EFFECT_ALLOW},
        )

    def _seed_stock(self):
        InventoryAdjustmentService.create_adjustment(
            payload={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "adjustment_date": "2025-04-10",
                "location": self.location.id,
                "reference_no": "MFG-SEED",
                "narration": "Seed manufacturing stock",
                "lines": [
                    {"product": self.bulk_sugar.id, "direction": "INCREASE", "qty": "100.0000", "unit_cost": "45.0000", "note": "Bulk stock"},
                    {"product": self.pouch.id, "direction": "INCREASE", "qty": "100.0000", "unit_cost": "2.0000", "note": "Pouch stock"},
                ],
            },
            user_id=self.user.id,
        )

    def _bom_payload(self):
        return {
            "entity": self.entity.id,
            "subentity": self.subentity.id,
            "code": "BOM-SUG-1KG",
            "name": "Sugar 1kg Packing BOM",
            "description": "Pack 1kg sugar into pouches",
            "finished_product": self.finished_pack.id,
            "output_qty": "10.0000",
            "materials": [
                {"material_product": self.bulk_sugar.id, "qty": "10.0000", "waste_percent": "0.0000", "note": "Bulk sugar"},
                {"material_product": self.pouch.id, "qty": "10.0000", "waste_percent": "0.0000", "note": "Pouches"},
            ],
        }

    def _route_payload(self):
        return {
            "entity": self.entity.id,
            "subentity": self.subentity.id,
            "code": "ROUTE-SUGAR-PACK",
            "name": "Sugar Packing Route",
            "description": "Blend and pack sequence",
            "steps": [
                {"sequence_no": 1, "step_code": "BLEND", "step_name": "Blend", "description": "Blend material"},
                {"sequence_no": 2, "step_code": "PACK", "step_name": "Pack", "description": "Pack finished goods"},
            ],
        }

    def _work_order_payload(self, bom_id: int):
        return {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "production_date": "2025-04-12",
            "bom": bom_id,
            "planned_output_qty": "10.0000",
            "source_location": self.location.id,
            "destination_location": self.finished_location.id,
            "reference_no": "WO-REF-1",
            "narration": "Pack sugar",
            "outputs": [
                {
                    "finished_product": self.finished_pack.id,
                    "planned_qty": "10.0000",
                    "actual_qty": "10.0000",
                    "batch_number": "FG-APR-001",
                    "expiry_date": "2026-04-30",
                }
            ],
        }

    def test_bom_crud_and_meta(self):
        route_resp = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json")
        self.assertEqual(route_resp.status_code, 201)
        route_id = route_resp.json()["id"]

        meta = self.client.get(reverse("manufacturing:manufacturing-bom-form-meta"), {"entity": self.entity.id, "subentity": self.subentity.id})
        self.assertEqual(meta.status_code, 200)
        self.assertGreaterEqual(len(meta.json()["products"]), 3)
        self.assertGreaterEqual(len(meta.json()["routes"]), 1)

        bom_payload = self._bom_payload()
        bom_payload["route"] = route_id
        create = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json")
        self.assertEqual(create.status_code, 201)
        bom_id = create.json()["id"]
        self.assertEqual(create.json()["route_id"], route_id)

        listed = self.client.get(reverse("manufacturing:manufacturing-boms"), {"entity": self.entity.id, "subentity": self.subentity.id})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["rows"]), 1)
        self.assertEqual(listed.json()["rows"][0]["route_code"], "ROUTE-SUGAR-PACK")

        detail = self.client.get(reverse("manufacturing:manufacturing-bom-detail", kwargs={"pk": bom_id}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["code"], "BOM-SUG-1KG")

        payload = bom_payload
        payload["name"] = "Sugar 1kg Packing BOM Updated"
        update = self.client.put(reverse("manufacturing:manufacturing-bom-detail", kwargs={"pk": bom_id}), payload, format="json")
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["name"], "Sugar 1kg Packing BOM Updated")

    def test_work_order_create_post_unpost_cancel_flow(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        self.assertEqual(work_order["status"], "DRAFT")
        self.assertEqual(len(work_order["materials"]), 2)
        self.assertEqual(len(work_order["outputs"]), 1)
        self.assertEqual(len(work_order["operations"]), 2)
        self.assertEqual(len(work_order["trace_links"]), 2)
        self.assertEqual(work_order["operations"][0]["status"], ManufacturingOperationStatus.READY)
        self.assertEqual(float(work_order["operations"][0]["input_qty"]), 10.0)
        self.assertEqual(float(work_order["operations"][0]["output_qty"]), 10.0)
        self.assertEqual(float(work_order["operations"][0]["scrap_qty"]), 0.0)
        self.assertIn(work_order["outputs"][0]["manufacture_date"], {"2025-04-12", "12-04-2025"})
        self.assertEqual(work_order["trace_links"][0]["output_batch_number"], "FG-APR-001")
        self.assertFalse(work_order["operations_complete"])
        work_order_id = work_order["id"]

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 400)
        self.assertIn("Complete all manufacturing operations", str(post_resp.json()))

        start_1 = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": work_order["operations"][0]["id"]}),
            {},
            format="json",
        )
        self.assertEqual(start_1.status_code, 200)
        complete_1 = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": work_order["operations"][0]["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Done"},
            format="json",
        )
        self.assertEqual(complete_1.status_code, 200)
        self.assertEqual(complete_1.json()["work_order"]["operations"][1]["status"], ManufacturingOperationStatus.READY)

        start_2 = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": work_order["operations"][1]["id"]}),
            {},
            format="json",
        )
        self.assertEqual(start_2.status_code, 200)
        complete_2 = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": work_order["operations"][1]["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Packed"},
            format="json",
        )
        self.assertEqual(complete_2.status_code, 200)
        self.assertTrue(complete_2.json()["work_order"]["operations_complete"])

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]
        self.assertEqual(posted["status"], "POSTED")
        self.assertTrue(posted["posting_entry_id"])
        self.assertEqual(InventoryMove.objects.filter(txn_id=work_order_id, txn_type=TxnType.MANUFACTURING_WORK_ORDER).count(), 3)

        source_bulk_balance = InventoryMove.objects.filter(
            entity_id=self.entity.id,
            product_id=self.bulk_sugar.id,
            location_id=self.location.id,
        ).aggregate(total=Sum("base_qty"))
        self.assertIsNotNone(source_bulk_balance)

        unpost_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-unpost", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(unpost_resp.status_code, 200)
        self.assertEqual(unpost_resp.json()["work_order"]["status"], "DRAFT")
        self.assertEqual(InventoryMove.objects.filter(txn_id=work_order_id, txn_type=TxnType.MANUFACTURING_WORK_ORDER).count(), 0)

        cancel_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-cancel", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()["work_order"]["status"], "CANCELLED")

    def test_work_order_meta_and_negative_stock_validation(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        meta = self.client.get(
            reverse("manufacturing:manufacturing-work-order-form-meta"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(meta.status_code, 200)
        self.assertIn("settings", meta.json())
        self.assertGreaterEqual(len(meta.json()["godowns"]), 2)
        self.assertGreaterEqual(len(meta.json()["routes"]), 1)

        payload = self._work_order_payload(bom["id"])
        payload["materials"] = [
            {"material_product": self.bulk_sugar.id, "required_qty": "999.0000", "actual_qty": "999.0000"},
            {"material_product": self.pouch.id, "required_qty": "10.0000", "actual_qty": "10.0000"},
        ]
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        route_ops = work_order_resp.json()["work_order"]["operations"]
        for operation in route_ops:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000"},
                format="json",
            )

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 400)
        self.assertIn("Insufficient stock", str(post_resp.json()))

        bad_payload = self._work_order_payload(bom["id"])
        bad_payload["outputs"][0]["manufacture_date"] = "2025-05-01"
        bad_payload["outputs"][0]["expiry_date"] = "2025-04-01"
        invalid_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), bad_payload, format="json")
        self.assertEqual(invalid_resp.status_code, 400)
        self.assertIn("Expiry date cannot be earlier", str(invalid_resp.json()))

    def test_work_order_with_saleable_byproduct(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        payload = self._work_order_payload(bom["id"])
        payload["outputs"] = [
            {
                "finished_product": self.finished_pack.id,
                "output_type": "MAIN",
                "planned_qty": "10.0000",
                "actual_qty": "10.0000",
                "batch_number": "FG-APR-002",
                "expiry_date": "2026-04-30",
            },
            {
                "finished_product": self.sugar_dust.id,
                "output_type": "SALEABLE_SCRAP",
                "planned_qty": "2.0000",
                "actual_qty": "2.0000",
                "estimated_recovery_unit_value": "5.0000",
                "note": "Collected saleable dust",
            },
        ]
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]
        self.assertEqual(len(posted["outputs"]), 2)
        main_output = next(row for row in posted["outputs"] if row["output_type"] == "MAIN")
        byproduct_output = next(row for row in posted["outputs"] if row["output_type"] == "SALEABLE_SCRAP")
        self.assertEqual(float(byproduct_output["unit_cost"]), 5.0)
        self.assertEqual(float(main_output["unit_cost"]), 46.0)
        self.assertEqual(InventoryMove.objects.filter(txn_id=work_order_id, txn_type=TxnType.MANUFACTURING_WORK_ORDER).count(), 4)

    def test_work_order_cost_snapshot_and_variance(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        payload = self._work_order_payload(bom["id"])
        payload["materials"] = [
            {
                "material_product": self.bulk_sugar.id,
                "required_qty": "10.0000",
                "actual_qty": "10.2000",
                "unit_cost": "45.0000",
            },
            {
                "material_product": self.pouch.id,
                "required_qty": "10.0000",
                "actual_qty": "10.0000",
                "unit_cost": "2.0000",
            },
        ]
        payload["outputs"] = [
            {
                "finished_product": self.finished_pack.id,
                "output_type": "MAIN",
                "planned_qty": "10.0000",
                "actual_qty": "9.8000",
                "batch_number": "FG-APR-003",
                "expiry_date": "2026-04-30",
            }
        ]
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]

        self.assertEqual(float(posted["standard_material_cost_snapshot"]), 470.0)
        self.assertEqual(float(posted["actual_material_cost_snapshot"]), 479.0)
        self.assertEqual(float(posted["material_variance_value_snapshot"]), 9.0)
        self.assertEqual(float(posted["standard_output_qty_snapshot"]), 10.0)
        self.assertEqual(float(posted["actual_output_qty_snapshot"]), 9.8)
        self.assertEqual(float(posted["yield_variance_qty_snapshot"]), -0.2)
        self.assertEqual(float(posted["yield_variance_percent_snapshot"]), -2.0)
        self.assertAlmostEqual(float(posted["standard_unit_cost_snapshot"]), 47.0, places=4)
        self.assertAlmostEqual(float(posted["actual_unit_cost_snapshot"]), 48.8776, places=4)

        material_rows = posted["materials"]
        sugar_row = next(row for row in material_rows if row["material_product_id"] == self.bulk_sugar.id)
        self.assertEqual(float(sugar_row["standard_cost"]), 450.0)
        self.assertEqual(float(sugar_row["actual_cost"]), 459.0)
        self.assertEqual(float(sugar_row["qty_variance_qty"]), 0.2)
        self.assertEqual(float(sugar_row["cost_variance_value"]), 9.0)

    def test_work_order_additional_cost_increases_fg_cost(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        payload = self._work_order_payload(bom["id"])
        payload["additional_costs"] = [
            {"cost_type": "LABOUR", "amount": "30.0000", "note": "Packing labour"},
            {"cost_type": "ELECTRICITY", "amount": "20.0000", "note": "Machine power"},
        ]
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]
        main_output = next(row for row in posted["outputs"] if row["output_type"] == "MAIN")

        self.assertEqual(float(posted["total_additional_cost_snapshot"]), 50.0)
        self.assertEqual(float(posted["net_production_cost_snapshot"]), 520.0)
        self.assertEqual(float(posted["actual_unit_cost_snapshot"]), 52.0)
        self.assertEqual(float(main_output["unit_cost"]), 52.0)
        self.assertEqual(len(posted["additional_costs"]), 2)
