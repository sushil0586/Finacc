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
from financial.models import Ledger, account
from inventory_ops.services import InventoryAdjustmentService
from numbering.models import DocumentNumberSeries
from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntityStaticAccountMap, InventoryMove, JournalLine, StaticAccount, TxnType
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from manufacturing.models import ManufacturingOperationStatus, ManufacturingSettings


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
        self.second_subentity = SubEntity.objects.create(entity=self.entity, subentityname="Plant B")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.second_entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
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
            "manufacturing.route.view",
            "manufacturing.route.create",
            "manufacturing.route.update",
            "manufacturing.route.delete",
            "manufacturing.bom.view",
            "manufacturing.bom.create",
            "manufacturing.bom.update",
            "manufacturing.bom.delete",
            "manufacturing.workorder.view",
            "manufacturing.workorder.create",
            "manufacturing.workorder.update",
            "manufacturing.workorder.operate",
            "manufacturing.workorder.qc_approve",
            "manufacturing.workorder.post",
            "manufacturing.workorder.unpost",
            "manufacturing.workorder.cancel",
        ):
            self._grant_permission(code)
        self._seed_manufacturing_static_accounts()
        self._seed_stock()

    def _grant_permission(self, permission_code: str):
        action = permission_code.rsplit(".", 1)[-1]
        resource = permission_code.split(".")[1] if "." in permission_code else "workorder"
        permission, _ = Permission.objects.get_or_create(
            code=permission_code,
            defaults={
                "name": permission_code,
                "module": "manufacturing",
                "resource": resource,
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

    def _seed_manufacturing_static_accounts(self):
        codes = (
            StaticAccountCodes.MANUFACTURING_WIP,
            StaticAccountCodes.MANUFACTURING_CONSUMPTION,
            StaticAccountCodes.MANUFACTURING_OVERHEAD_ABSORPTION,
            StaticAccountCodes.MANUFACTURING_FINISHED_GOODS,
            StaticAccountCodes.MANUFACTURING_MATERIAL_VARIANCE,
            StaticAccountCodes.MANUFACTURING_YIELD_VARIANCE,
            StaticAccountCodes.MANUFACTURING_ADDITIONAL_COST_EXPENSE,
        )
        for idx, code in enumerate(codes, start=1):
            static_account, _ = StaticAccount.objects.get_or_create(
                code=code,
                defaults={
                    "name": code.replace("_", " ").title(),
                    "group": "OTHER",
                    "is_active": True,
                },
            )
            ledger = Ledger.objects.create(
                entity=self.entity,
                ledger_code=7000 + idx,
                name=static_account.name,
                createdby=self.user,
            )
            acc = account.objects.create(
                entity=self.entity,
                accountname=static_account.name,
                ledger=ledger,
                createdby=self.user,
            )
            EntityStaticAccountMap.objects.create(
                entity=self.entity,
                static_account=static_account,
                account=acc,
                ledger=ledger,
                createdby=self.user,
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

    def _route_payload_with_qc(self):
        payload = self._route_payload()
        payload["steps"][0]["requires_qc"] = True
        return payload

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

    def test_bom_and_work_order_meta_include_shared_root_masters_for_branch_scope(self):
        branch_route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json")
        self.assertEqual(branch_route.status_code, 201)

        root_route_payload = self._route_payload()
        root_route_payload["code"] = "ROUTE-SUGAR-ROOT"
        root_route_payload["name"] = "Shared Sugar Packing Route"
        root_route_payload["subentity"] = None
        root_route = self.client.post(reverse("manufacturing:manufacturing-routes"), root_route_payload, format="json")
        self.assertEqual(root_route.status_code, 201)

        root_bom_payload = self._bom_payload()
        root_bom_payload["code"] = "BOM-SUG-ROOT"
        root_bom_payload["name"] = "Shared Sugar Packing BOM"
        root_bom_payload["subentity"] = None
        root_bom_payload["route"] = root_route.json()["id"]
        root_bom = self.client.post(reverse("manufacturing:manufacturing-boms"), root_bom_payload, format="json")
        self.assertEqual(root_bom.status_code, 201)

        route_list = self.client.get(
            reverse("manufacturing:manufacturing-routes"),
            {"entity": self.entity.id, "subentity": self.subentity.id},
        )
        self.assertEqual(route_list.status_code, 200)
        route_rows = route_list.json()["rows"]
        self.assertEqual(len(route_rows), 2)
        self.assertEqual({row["code"] for row in route_rows}, {"ROUTE-SUGAR-PACK", "ROUTE-SUGAR-ROOT"})
        root_route_row = next(row for row in route_rows if row["code"] == "ROUTE-SUGAR-ROOT")
        self.assertTrue(root_route_row["is_shared"])

        bom_list = self.client.get(
            reverse("manufacturing:manufacturing-boms"),
            {"entity": self.entity.id, "subentity": self.subentity.id},
        )
        self.assertEqual(bom_list.status_code, 200)
        bom_rows = bom_list.json()["rows"]
        self.assertEqual(len(bom_rows), 1)
        self.assertTrue(bom_rows[0]["is_shared"])

        bom_meta = self.client.get(reverse("manufacturing:manufacturing-bom-form-meta"), {"entity": self.entity.id, "subentity": self.subentity.id})
        self.assertEqual(bom_meta.status_code, 200)
        bom_route_codes = {row["code"] for row in bom_meta.json()["routes"]}
        self.assertIn("ROUTE-SUGAR-PACK", bom_route_codes)
        self.assertIn("ROUTE-SUGAR-ROOT", bom_route_codes)

        work_order_meta = self.client.get(
            reverse("manufacturing:manufacturing-work-order-form-meta"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(work_order_meta.status_code, 200)
        work_order_bom_codes = {row["code"] for row in work_order_meta.json()["boms"]}
        work_order_route_codes = {row["code"] for row in work_order_meta.json()["routes"]}
        self.assertIn("BOM-SUG-ROOT", work_order_bom_codes)
        self.assertIn("ROUTE-SUGAR-ROOT", work_order_route_codes)

        shared_work_order_payload = self._work_order_payload(root_bom.json()["id"])
        shared_work_order_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-orders"),
            shared_work_order_payload,
            format="json",
        )
        self.assertEqual(shared_work_order_resp.status_code, 201)
        self.assertEqual(shared_work_order_resp.json()["work_order"]["bom_id"], root_bom.json()["id"])

        shared_route_detail = self.client.get(
            reverse("manufacturing:manufacturing-route-detail", kwargs={"pk": root_route.json()["id"]}),
            {"subentity": self.subentity.id},
        )
        self.assertEqual(shared_route_detail.status_code, 200)
        self.assertTrue(shared_route_detail.json()["is_shared"])

        readonly_route_payload = dict(root_route_payload)
        readonly_route_payload["name"] = "Branch Attempt Update"
        readonly_route_update = self.client.put(
            reverse("manufacturing:manufacturing-route-detail", kwargs={"pk": root_route.json()["id"]}) + f"?subentity={self.subentity.id}",
            readonly_route_payload,
            format="json",
        )
        self.assertEqual(readonly_route_update.status_code, 403)

        shared_bom_detail = self.client.get(
            reverse("manufacturing:manufacturing-bom-detail", kwargs={"pk": root_bom.json()["id"]}),
            {"subentity": self.subentity.id},
        )
        self.assertEqual(shared_bom_detail.status_code, 200)
        self.assertTrue(shared_bom_detail.json()["is_shared"])

        readonly_bom_payload = dict(root_bom_payload)
        readonly_bom_payload["name"] = "Branch Attempt Update"
        readonly_bom_update = self.client.put(
            reverse("manufacturing:manufacturing-bom-detail", kwargs={"pk": root_bom.json()["id"]}) + f"?subentity={self.subentity.id}",
            readonly_bom_payload,
            format="json",
        )
        self.assertEqual(readonly_bom_update.status_code, 403)

    def test_route_create_rejects_oversized_fields(self):
        payload = self._route_payload()
        payload["code"] = "C" * 51
        payload["name"] = "N" * 151
        payload["description"] = "D" * 501
        payload["steps"][0]["description"] = "S" * 301

        response = self.client.post(reverse("manufacturing:manufacturing-routes"), payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.json())
        self.assertIn("name", response.json())
        self.assertIn("description", response.json())

    def test_route_crud_accepts_route_permissions_without_bom_permissions(self):
        RolePermission.objects.filter(
            role=self.role,
            permission__code__in=[
                "manufacturing.bom.view",
                "manufacturing.bom.create",
                "manufacturing.bom.update",
                "manufacturing.bom.delete",
            ],
        ).delete()

        create_resp = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json")
        self.assertEqual(create_resp.status_code, 201)
        route_id = create_resp.json()["id"]

        list_resp = self.client.get(reverse("manufacturing:manufacturing-routes"), {"entity": self.entity.id, "subentity": self.subentity.id})
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()["rows"]), 1)

        update_payload = self._route_payload()
        update_payload["name"] = "Route With Route Permission"
        update_resp = self.client.put(
            reverse("manufacturing:manufacturing-route-detail", kwargs={"pk": route_id}),
            update_payload,
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["name"], "Route With Route Permission")

    def test_bom_create_rejects_oversized_fields(self):
        payload = self._bom_payload()
        payload["code"] = "C" * 51
        payload["name"] = "N" * 151
        payload["description"] = "D" * 501
        payload["materials"][0]["note"] = "M" * 201

        response = self.client.post(reverse("manufacturing:manufacturing-boms"), payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.json())
        self.assertIn("name", response.json())
        self.assertIn("description", response.json())

    def test_bom_rejects_route_from_other_subentity_scope(self):
        local_route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json")
        self.assertEqual(local_route.status_code, 201)

        foreign_route_payload = self._route_payload()
        foreign_route_payload["code"] = "ROUTE-SUGAR-FOREIGN"
        foreign_route_payload["name"] = "Foreign Scope Route"
        foreign_route_payload["subentity"] = self.second_subentity.id
        foreign_route = self.client.post(reverse("manufacturing:manufacturing-routes"), foreign_route_payload, format="json")
        self.assertEqual(foreign_route.status_code, 201)

        bad_bom_payload = self._bom_payload()
        bad_bom_payload["route"] = foreign_route.json()["id"]
        create_resp = self.client.post(reverse("manufacturing:manufacturing-boms"), bad_bom_payload, format="json")
        self.assertEqual(create_resp.status_code, 400)
        self.assertIn("route", create_resp.json())

        valid_bom_payload = self._bom_payload()
        valid_bom_payload["route"] = local_route.json()["id"]
        bom_resp = self.client.post(reverse("manufacturing:manufacturing-boms"), valid_bom_payload, format="json")
        self.assertEqual(bom_resp.status_code, 201)

        valid_bom_payload["route"] = foreign_route.json()["id"]
        update_resp = self.client.put(
            reverse("manufacturing:manufacturing-bom-detail", kwargs={"pk": bom_resp.json()["id"]}),
            valid_bom_payload,
            format="json",
        )
        self.assertEqual(update_resp.status_code, 400)
        self.assertIn("route", update_resp.json())

    def test_settings_patch_requires_update_permission(self):
        read_resp = self.client.get(
            reverse("manufacturing:manufacturing-settings"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(read_resp.status_code, 200)

        patch_resp = self.client.patch(
            reverse("manufacturing:manufacturing-settings"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "settings": {"default_doc_code_work_order": "NEWMWO"},
            },
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 403)

        self._grant_permission("manufacturing.settings.update")
        patch_resp = self.client.patch(
            reverse("manufacturing:manufacturing-settings"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "settings": {"default_doc_code_work_order": "NEWMWO"},
            },
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["settings"]["default_doc_code_work_order"], "NEWMWO")

    def test_settings_patch_rejects_oversized_doc_code(self):
        self._grant_permission("manufacturing.settings.update")
        patch_resp = self.client.patch(
            reverse("manufacturing:manufacturing-settings"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "settings": {"default_doc_code_work_order": "W" * 11},
            },
            format="json",
        )

        self.assertEqual(patch_resp.status_code, 400)
        self.assertIn("default_doc_code_work_order", patch_resp.json())

    def test_settings_patch_updates_numbering_series(self):
        self._grant_permission("manufacturing.settings.update")
        patch_resp = self.client.patch(
            reverse("manufacturing:manufacturing-settings"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "numbering_series": [
                    {
                        "series_key": "manufacturing_work_order",
                        "doc_code": "MWOX",
                        "prefix": "MFG",
                        "suffix": "A",
                        "starting_number": 10,
                        "current_number": 12,
                        "number_padding": 5,
                        "separator": "/",
                        "reset_frequency": "monthly",
                        "include_year": True,
                        "include_month": True,
                        "custom_format": "{prefix}/{year}/{month}/{number}",
                        "is_active": True,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["settings"]["default_doc_code_work_order"], "MWOX")
        row = patch_resp.json()["numbering_series"][0]
        self.assertEqual(row["doc_code"], "MWOX")
        self.assertEqual(row["prefix"], "MFG")
        self.assertEqual(row["current_number"], 12)
        self.assertEqual(row["reset_frequency"], "monthly")

        series = DocumentNumberSeries.objects.get(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            doc_code="MWOX",
        )
        self.assertEqual(series.prefix, "MFG")
        self.assertEqual(series.suffix, "A")
        self.assertEqual(series.starting_number, 10)
        self.assertEqual(series.current_number, 12)
        self.assertEqual(series.number_padding, 5)
        self.assertEqual(series.separator, "/")
        self.assertEqual(series.reset_frequency, "monthly")
        self.assertTrue(series.include_year)
        self.assertTrue(series.include_month)
        self.assertEqual(series.custom_format, "{prefix}/{year}/{month}/{number}")

    def test_work_order_create_post_unpost_cancel_flow(self):
        def scoped_balance(product_id: int, location_id: int) -> Decimal:
            rows = InventoryMove.objects.filter(
                entity_id=self.entity.id,
                product_id=product_id,
                location_id=location_id,
            ).values("move_type").annotate(total=Sum("base_qty"))
            in_total = Decimal("0.0000")
            out_total = Decimal("0.0000")
            for row in rows:
                if row["move_type"] == InventoryMove.MoveType.IN_:
                    in_total += Decimal(row["total"] or 0)
                elif row["move_type"] == InventoryMove.MoveType.OUT:
                    out_total += Decimal(row["total"] or 0)
            return in_total - out_total

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
        opening_bulk_balance = scoped_balance(self.bulk_sugar.id, self.location.id)
        opening_pouch_balance = scoped_balance(self.pouch.id, self.location.id)
        opening_finished_balance = scoped_balance(self.finished_pack.id, self.finished_location.id)

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
        self.assertEqual(posted["posted_by_id"], self.user.id)
        self.assertEqual(posted["posted_by_name"], self.user.username)
        self.assertIsNotNone(posted["posted_at"])
        self.assertEqual(InventoryMove.objects.filter(txn_id=work_order_id, txn_type=TxnType.MANUFACTURING_WORK_ORDER).count(), 3)
        self.assertEqual(scoped_balance(self.bulk_sugar.id, self.location.id), Decimal("90.0000"))
        self.assertEqual(scoped_balance(self.pouch.id, self.location.id), Decimal("90.0000"))
        self.assertEqual(scoped_balance(self.finished_pack.id, self.finished_location.id), Decimal("10.0000"))
        journal_lines = list(
            JournalLine.objects.filter(
                txn_id=work_order_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            ).order_by("id")
        )
        self.assertEqual(len(journal_lines), 4)
        self.assertEqual(
            sum((line.amount for line in journal_lines if line.drcr), Decimal("0.00")),
            sum((line.amount for line in journal_lines if not line.drcr), Decimal("0.00")),
        )

        source_bulk_balance = InventoryMove.objects.filter(
            entity_id=self.entity.id,
            product_id=self.bulk_sugar.id,
            location_id=self.location.id,
        ).aggregate(total=Sum("base_qty"))
        self.assertIsNotNone(source_bulk_balance)

        unpost_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-unpost", kwargs={"pk": work_order_id}), {"reason": "Posting correction"}, format="json")
        self.assertEqual(unpost_resp.status_code, 200)
        unposted = unpost_resp.json()["work_order"]
        self.assertEqual(unposted["status"], "DRAFT")
        self.assertEqual(unposted["last_unposted_by_id"], self.user.id)
        self.assertEqual(unposted["last_unposted_by_name"], self.user.username)
        self.assertEqual(unposted["last_unpost_reason"], "Posting correction")
        self.assertIsNotNone(unposted["last_unposted_at"])
        self.assertEqual(InventoryMove.objects.filter(txn_id=work_order_id, txn_type=TxnType.MANUFACTURING_WORK_ORDER).count(), 0)
        self.assertEqual(scoped_balance(self.bulk_sugar.id, self.location.id), opening_bulk_balance)
        self.assertEqual(scoped_balance(self.pouch.id, self.location.id), opening_pouch_balance)
        self.assertEqual(scoped_balance(self.finished_pack.id, self.finished_location.id), opening_finished_balance)
        reversal_lines = list(
            JournalLine.objects.filter(
                txn_id=work_order_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            ).order_by("id")
        )
        self.assertEqual(len(reversal_lines), len(journal_lines))
        self.assertTrue(all(line.description.startswith("Reversal:") for line in reversal_lines))

        cancel_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-cancel", kwargs={"pk": work_order_id}), {"reason": "Superseded by fresh batch"}, format="json")
        self.assertEqual(cancel_resp.status_code, 200)
        cancelled = cancel_resp.json()["work_order"]
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(cancelled["cancelled_by_id"], self.user.id)
        self.assertEqual(cancelled["cancelled_by_name"], self.user.username)
        self.assertEqual(cancelled["cancel_reason"], "Superseded by fresh batch")
        self.assertIsNotNone(cancelled["cancelled_at"])

    def test_update_endpoints_reject_scope_reassignment(self):
        route_resp = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json")
        self.assertEqual(route_resp.status_code, 201)
        route_id = route_resp.json()["id"]

        route_update_payload = self._route_payload()
        route_update_payload["subentity"] = self.second_subentity.id
        route_update_resp = self.client.put(
            reverse("manufacturing:manufacturing-route-detail", kwargs={"pk": route_id}),
            route_update_payload,
            format="json",
        )
        self.assertEqual(route_update_resp.status_code, 400)
        self.assertIn("subentity", route_update_resp.json())

        bom_payload = self._bom_payload()
        bom_payload["route"] = route_id
        bom_resp = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json")
        self.assertEqual(bom_resp.status_code, 201)
        bom_id = bom_resp.json()["id"]

        bom_update_payload = self._bom_payload()
        bom_update_payload["route"] = route_id
        bom_update_payload["subentity"] = self.second_subentity.id
        bom_update_resp = self.client.put(
            reverse("manufacturing:manufacturing-bom-detail", kwargs={"pk": bom_id}),
            bom_update_payload,
            format="json",
        )
        self.assertEqual(bom_update_resp.status_code, 400)
        self.assertIn("subentity", bom_update_resp.json())

        work_order_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-orders"),
            self._work_order_payload(bom_id),
            format="json",
        )
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        work_order_update_payload = self._work_order_payload(bom_id)
        work_order_update_payload["entityfinid"] = self.second_entityfin.id
        work_order_update_resp = self.client.put(
            reverse("manufacturing:manufacturing-work-order-detail", kwargs={"pk": work_order_id}),
            work_order_update_payload,
            format="json",
        )
        self.assertEqual(work_order_update_resp.status_code, 400)
        self.assertIn("entityfinid", work_order_update_resp.json())

    def test_work_order_create_rejects_oversized_fields(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        payload = self._work_order_payload(bom["id"])
        payload["reference_no"] = "R" * 101
        payload["narration"] = "N" * 501
        payload["materials"] = [
            {
                "material_product": self.bulk_sugar.id,
                "required_qty": "10.0000",
                "actual_qty": "10.0000",
                "batch_number": "B" * 81,
                "note": "M" * 201,
            }
        ]
        payload["outputs"][0]["batch_number"] = "O" * 81
        payload["outputs"][0]["note"] = "P" * 201
        payload["additional_costs"] = [{"cost_type": "OTHER", "amount": "25.0000", "note": "A" * 201}]

        response = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("reference_no", response.json())
        self.assertIn("narration", response.json())

    def test_unpost_and_cancel_require_reason(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]

        for operation in work_order["operations"]:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {},
                format="json",
            )
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000"},
                format="json",
            )

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)

        unpost_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-unpost", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(unpost_resp.status_code, 400)
        self.assertIn("Reason is required", str(unpost_resp.json()))

        valid_unpost = self.client.post(
            reverse("manufacturing:manufacturing-work-order-unpost", kwargs={"pk": work_order_id}),
            {"reason": "Correcting production date"},
            format="json",
        )
        self.assertEqual(valid_unpost.status_code, 200)

        cancel_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-cancel", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(cancel_resp.status_code, 400)
        self.assertIn("Reason is required", str(cancel_resp.json()))

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
        created_work_order = work_order_resp.json()["work_order"]
        work_order_id = created_work_order["id"]
        self.assertEqual(len(created_work_order["trace_links"]), 4)

        sugar_trace_qty = sum(
            float(row["input_qty"])
            for row in created_work_order["trace_links"]
            if row["input_product_id"] == self.bulk_sugar.id
        )
        pouch_trace_qty = sum(
            float(row["input_qty"])
            for row in created_work_order["trace_links"]
            if row["input_product_id"] == self.pouch.id
        )
        self.assertAlmostEqual(sugar_trace_qty, 10.0, places=4)
        self.assertAlmostEqual(pouch_trace_qty, 10.0, places=4)
        self.assertTrue(
            all(float(row["input_qty"]) < 10.0 for row in created_work_order["trace_links"])
        )

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]
        self.assertEqual(len(posted["outputs"]), 2)
        main_output = next(row for row in posted["outputs"] if row["output_type"] == "MAIN")
        byproduct_output = next(row for row in posted["outputs"] if row["output_type"] == "SALEABLE_SCRAP")
        self.assertEqual(float(byproduct_output["unit_cost"]), 5.0)
        self.assertEqual(float(main_output["unit_cost"]), 46.0)
        self.assertEqual(InventoryMove.objects.filter(txn_id=work_order_id, txn_type=TxnType.MANUFACTURING_WORK_ORDER).count(), 4)

    def test_work_order_respects_bom_material_policy_and_waste(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom_payload["materials"][0]["waste_percent"] = "5.0000"
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()

        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity=self.entity, subentity=self.subentity)
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "auto_explode_materials_from_bom": True,
            "allow_manual_material_override": False,
        }
        settings_obj.save(update_fields=["policy_controls"])

        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        materials = work_order_resp.json()["work_order"]["materials"]
        self.assertEqual(float(materials[0]["required_qty"]), 10.5)
        self.assertEqual(float(materials[0]["waste_qty"]), 0.5)

        manual_override_payload = self._work_order_payload(bom["id"])
        manual_override_payload["materials"] = [
            {"material_product": self.bulk_sugar.id, "required_qty": "9.0000", "actual_qty": "9.0000"},
            {"material_product": self.pouch.id, "required_qty": "10.0000", "actual_qty": "10.0000"},
        ]
        override_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), manual_override_payload, format="json")
        self.assertEqual(override_resp.status_code, 400)
        self.assertIn("must follow the selected BOM", str(override_resp.json()))

        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "auto_explode_materials_from_bom": False,
            "allow_manual_material_override": True,
        }
        settings_obj.save(update_fields=["policy_controls"])

        no_material_payload = self._work_order_payload(bom["id"])
        no_material_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), no_material_payload, format="json")
        self.assertEqual(no_material_resp.status_code, 400)
        self.assertIn("auto explosion is disabled", str(no_material_resp.json()))

    def test_qc_required_operation_blocks_post_until_approved(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload_with_qc(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]
        qc_operation = work_order["operations"][0]
        next_operation = work_order["operations"][1]

        start_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {},
            format="json",
        )
        self.assertEqual(start_resp.status_code, 200)

        complete_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Awaiting QA"},
            format="json",
        )
        self.assertEqual(complete_resp.status_code, 200)
        operations = complete_resp.json()["work_order"]["operations"]
        self.assertEqual(operations[0]["status"], ManufacturingOperationStatus.AWAITING_QC)
        self.assertEqual(operations[1]["status"], ManufacturingOperationStatus.PENDING)
        self.assertEqual(operations[0]["started_by_id"], self.user.id)
        self.assertEqual(operations[0]["started_by_name"], self.user.username)
        self.assertEqual(operations[0]["completed_by_id"], self.user.id)
        self.assertEqual(operations[0]["completed_by_name"], self.user.username)

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 400)
        self.assertIn("Approve all QC-pending operations", str(post_resp.json()))

        reject_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-reject", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"remarks": "Seal damaged"},
            format="json",
        )
        self.assertEqual(reject_resp.status_code, 200)
        self.assertEqual(reject_resp.json()["work_order"]["operations"][0]["status"], ManufacturingOperationStatus.QC_REJECTED)

        restart_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {},
            format="json",
        )
        self.assertEqual(restart_resp.status_code, 200)

        recomplete_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Reworked"},
            format="json",
        )
        self.assertEqual(recomplete_resp.status_code, 200)
        self.assertEqual(recomplete_resp.json()["work_order"]["operations"][0]["status"], ManufacturingOperationStatus.AWAITING_QC)

        approve_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-approve", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"remarks": "Approved by QA"},
            format="json",
        )
        self.assertEqual(approve_resp.status_code, 200)
        operations = approve_resp.json()["work_order"]["operations"]
        self.assertEqual(operations[0]["status"], ManufacturingOperationStatus.COMPLETED)
        self.assertEqual(operations[1]["status"], ManufacturingOperationStatus.READY)
        self.assertEqual(operations[0]["qc_decision_by_id"], self.user.id)
        self.assertEqual(operations[0]["qc_decision_by_name"], self.user.username)
        self.assertIsNotNone(operations[0]["qc_decision_at"])

        start_2 = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": next_operation["id"]}),
            {},
            format="json",
        )
        self.assertEqual(start_2.status_code, 200)
        complete_2 = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": next_operation["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Packed"},
            format="json",
        )
        self.assertEqual(complete_2.status_code, 200)
        self.assertTrue(complete_2.json()["work_order"]["operations_complete"])

    def test_qc_approval_requires_dedicated_permission(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload_with_qc(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]
        qc_operation = work_order["operations"][0]

        self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {},
            format="json",
        )
        complete_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Awaiting QA"},
            format="json",
        )
        self.assertEqual(complete_resp.status_code, 200)
        self.assertEqual(complete_resp.json()["work_order"]["operations"][0]["status"], ManufacturingOperationStatus.AWAITING_QC)

        RolePermission.objects.filter(
            role=self.role,
            permission__code="manufacturing.workorder.qc_approve",
        ).delete()

        approve_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-approve", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"remarks": "Approved by QA"},
            format="json",
        )
        self.assertEqual(approve_resp.status_code, 403)
        self.assertIn("manufacturing.workorder.qc_approve", str(approve_resp.json()))

        reject_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-reject", kwargs={"pk": work_order_id, "operation_pk": qc_operation["id"]}),
            {"remarks": "Rejected by QA"},
            format="json",
        )
        self.assertEqual(reject_resp.status_code, 403)
        self.assertIn("manufacturing.workorder.qc_approve", str(reject_resp.json()))

    def test_operation_execution_requires_dedicated_permission(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]
        first_operation = work_order["operations"][0]

        RolePermission.objects.filter(
            role=self.role,
            permission__code="manufacturing.workorder.operate",
        ).delete()

        start_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": first_operation["id"]}),
            {},
            format="json",
        )
        self.assertEqual(start_resp.status_code, 403)
        self.assertIn("manufacturing.workorder.operate", str(start_resp.json()))

        complete_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": first_operation["id"]}),
            {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Done"},
            format="json",
        )
        self.assertEqual(complete_resp.status_code, 403)
        self.assertIn("manufacturing.workorder.operate", str(complete_resp.json()))

        skip_resp = self.client.post(
            reverse("manufacturing:manufacturing-work-order-operation-skip", kwargs={"pk": work_order_id, "operation_pk": first_operation["id"]}),
            {"remarks": "Skip check"},
            format="json",
        )
        self.assertEqual(skip_resp.status_code, 403)
        self.assertIn("manufacturing.workorder.operate", str(skip_resp.json()))

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
        journal_lines = list(
            JournalLine.objects.filter(
                txn_id=work_order_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            )
        )
        overhead_credit = next(
            line for line in journal_lines
            if (not line.drcr) and line.account and line.account.accountname == "Manufacturing Overhead Absorption"
        )
        self.assertEqual(overhead_credit.amount, Decimal("50.00"))

    def test_non_capitalized_additional_cost_posts_to_expense_and_not_fg_cost(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity=self.entity, subentity=self.subentity)
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "capitalized_additional_cost_types": ["LABOUR"],
        }
        settings_obj.save(update_fields=["policy_controls"])

        payload = self._work_order_payload(bom["id"])
        payload["additional_costs"] = [
            {"cost_type": "LABOUR", "amount": "30.0000", "note": "Packing labour"},
            {"cost_type": "ELECTRICITY", "amount": "20.0000", "note": "Utility charge"},
        ]
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]
        main_output = next(row for row in posted["outputs"] if row["output_type"] == "MAIN")

        self.assertEqual(float(posted["total_additional_cost_snapshot"]), 50.0)
        self.assertEqual(float(posted["capitalized_additional_cost_snapshot"]), 30.0)
        self.assertEqual(float(posted["expensed_additional_cost_snapshot"]), 20.0)
        self.assertEqual(float(posted["net_production_cost_snapshot"]), 500.0)
        self.assertEqual(float(posted["actual_unit_cost_snapshot"]), 50.0)
        self.assertEqual(float(main_output["unit_cost"]), 50.0)

        journal_lines = list(
            JournalLine.objects.filter(
                txn_id=work_order_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            )
        )
        expense_line = next(
            line for line in journal_lines
            if line.drcr and line.account and line.account.accountname == "Manufacturing Additional Cost Expense"
        )
        self.assertEqual(expense_line.amount, Decimal("20.00"))

    def test_non_capitalized_additional_cost_requires_expense_mapping(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity=self.entity, subentity=self.subentity)
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "capitalized_additional_cost_types": ["LABOUR"],
        }
        settings_obj.save(update_fields=["policy_controls"])

        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]

        for operation in work_order["operations"]:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {},
                format="json",
            )
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Done"},
                format="json",
            )

        EntityStaticAccountMap.objects.filter(
            entity=self.entity,
            static_account__code=StaticAccountCodes.MANUFACTURING_ADDITIONAL_COST_EXPENSE,
        ).delete()

        update_payload = self._work_order_payload(bom["id"])
        update_payload["additional_costs"] = [
            {"cost_type": "ELECTRICITY", "amount": "20.0000", "note": "Utility charge"},
        ]
        update_resp = self.client.put(
            reverse("manufacturing:manufacturing-work-order-detail", kwargs={"pk": work_order_id}),
            update_payload,
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200)

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 400)
        self.assertIn("Manufacturing Additional Cost Expense", str(post_resp.json()))

    def test_standard_cost_output_valuation_posts_variances_to_configured_ledgers(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity=self.entity, subentity=self.subentity)
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "output_valuation_basis": "standard_cost",
        }
        settings_obj.save(update_fields=["policy_controls"])

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
                "batch_number": "FG-APR-STD-001",
                "expiry_date": "2026-04-30",
            }
        ]
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), payload, format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order_id = work_order_resp.json()["work_order"]["id"]

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        posted = post_resp.json()["work_order"]
        self.assertEqual(float(posted["outputs"][0]["unit_cost"]), 47.0)
        self.assertEqual(float(posted["yield_variance_value_snapshot"]), 9.4)

        journal_lines = list(
            JournalLine.objects.filter(
                txn_id=work_order_id,
                txn_type=TxnType.MANUFACTURING_WORK_ORDER,
            ).order_by("id")
        )
        self.assertEqual(len(journal_lines), 6)
        material_variance = next(
            line for line in journal_lines
            if line.account and line.account.accountname == "Manufacturing Material Variance"
        )
        yield_variance = next(
            line for line in journal_lines
            if line.account and line.account.accountname == "Manufacturing Yield Variance"
        )
        self.assertTrue(material_variance.drcr)
        self.assertTrue(yield_variance.drcr)
        self.assertEqual(material_variance.amount, Decimal("9.00"))
        self.assertEqual(yield_variance.amount, Decimal("9.40"))
        self.assertEqual(
            sum((line.amount for line in journal_lines if line.drcr), Decimal("0.00")),
            sum((line.amount for line in journal_lines if not line.drcr), Decimal("0.00")),
        )

    def test_manufacturing_summary_endpoint(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]

        for operation in work_order["operations"]:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {},
                format="json",
            )
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Done"},
                format="json",
            )

        self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")

        summary_resp = self.client.get(
            reverse("manufacturing:manufacturing-summary"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(summary_resp.status_code, 200)
        payload = summary_resp.json()
        self.assertEqual(payload["overview"]["total_work_orders"], 1)
        self.assertEqual(payload["overview"]["posted_count"], 1)
        self.assertTrue(payload["setup"]["is_ready"])
        self.assertEqual(payload["setup"]["mapped_count"], 4)
        self.assertEqual(payload["accounting"]["output_valuation_basis"], "actual_cost")
        self.assertFalse(payload["accounting"]["uses_variance_ledgers"])
        self.assertEqual(len(payload["recent_work_orders"]), 1)
        self.assertGreaterEqual(len(payload["top_materials"]), 1)
        self.assertGreaterEqual(len(payload["top_outputs"]), 1)

    def test_work_order_list_filters_by_entityfinid(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()

        first_year_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(first_year_resp.status_code, 201)

        next_entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        second_payload = self._work_order_payload(bom["id"])
        second_payload["entityfinid"] = next_entityfin.id
        second_payload["production_date"] = "2026-04-15"
        second_payload["reference_no"] = "WO-REF-2"
        second_payload["outputs"][0]["batch_number"] = "FG-APR-002"
        second_payload["outputs"][0]["expiry_date"] = "2027-04-30"
        second_year_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), second_payload, format="json")
        self.assertEqual(second_year_resp.status_code, 201)

        first_year_list = self.client.get(
            reverse("manufacturing:manufacturing-work-orders"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(first_year_list.status_code, 200)
        self.assertEqual(len(first_year_list.json()["rows"]), 1)
        self.assertEqual(first_year_list.json()["rows"][0]["reference_no"], "WO-REF-1")

        second_year_list = self.client.get(
            reverse("manufacturing:manufacturing-work-orders"),
            {"entity": self.entity.id, "entityfinid": next_entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(second_year_list.status_code, 200)
        self.assertEqual(len(second_year_list.json()["rows"]), 1)
        self.assertEqual(second_year_list.json()["rows"][0]["reference_no"], "WO-REF-2")

    def test_work_order_list_supports_search_status_date_and_pagination(self):
        route = self.client.post(reverse("manufacturing:manufacturing-routes"), self._route_payload(), format="json").json()
        bom_payload = self._bom_payload()
        bom_payload["route"] = route["id"]
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), bom_payload, format="json").json()

        first_payload = self._work_order_payload(bom["id"])
        first_payload["reference_no"] = "FILTER-ME"
        first_payload["production_date"] = "2025-04-12"
        first_payload["outputs"][0]["batch_number"] = "FG-FILTER-001"
        first_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), first_payload, format="json")
        self.assertEqual(first_resp.status_code, 201)

        second_payload = self._work_order_payload(bom["id"])
        second_payload["reference_no"] = "PAGE-TWO"
        second_payload["production_date"] = "2025-04-13"
        second_payload["outputs"][0]["batch_number"] = "FG-FILTER-002"
        second_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), second_payload, format="json")
        self.assertEqual(second_resp.status_code, 201)

        second_work_order_id = second_resp.json()["work_order"]["id"]
        for operation in second_resp.json()["work_order"]["operations"]:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": second_work_order_id, "operation_pk": operation["id"]}),
                {},
                format="json",
            )
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": second_work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000"},
                format="json",
            )
        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": second_work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 200)

        filtered = self.client.get(
            reverse("manufacturing:manufacturing-work-orders"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "search": "FILTER-ME",
                "status": "DRAFT",
                "from_date": "2025-04-01",
                "to_date": "2025-04-12",
                "page": 1,
                "page_size": 1,
            },
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["total_count"], 1)
        self.assertEqual(filtered.json()["page"], 1)
        self.assertEqual(filtered.json()["page_size"], 1)
        self.assertFalse(filtered.json()["has_previous"])
        self.assertFalse(filtered.json()["has_next"])
        self.assertEqual(filtered.json()["rows"][0]["reference_no"], "FILTER-ME")

        paged = self.client.get(
            reverse("manufacturing:manufacturing-work-orders"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "page": 2,
                "page_size": 1,
            },
        )
        self.assertEqual(paged.status_code, 200)
        self.assertEqual(paged.json()["total_count"], 2)
        self.assertEqual(paged.json()["page"], 2)
        self.assertTrue(paged.json()["has_previous"])
        self.assertFalse(paged.json()["has_next"])
        self.assertEqual(len(paged.json()["rows"]), 1)

        material_resp = self.client.get(
            reverse("manufacturing:manufacturing-material-consumption"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(material_resp.status_code, 200)
        self.assertEqual(material_resp.json()["overview"]["work_order_count"], 2)
        self.assertGreaterEqual(len(material_resp.json()["rows"]), 1)

        output_resp = self.client.get(
            reverse("manufacturing:manufacturing-output-yield"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(output_resp.status_code, 200)
        self.assertEqual(output_resp.json()["overview"]["work_order_count"], 2)
        self.assertGreaterEqual(len(output_resp.json()["rows"]), 1)
        self.assertGreaterEqual(len(output_resp.json()["output_lines"]), 1)
        self.assertEqual(output_resp.json()["accounting"]["output_valuation_basis"], "actual_cost")

        audit_resp = self.client.get(
            reverse("manufacturing:manufacturing-posting-audit"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(audit_resp.status_code, 200)
        self.assertEqual(audit_resp.json()["overview"]["work_order_count"], 2)
        self.assertGreaterEqual(len(audit_resp.json()["rows"]), 1)

        wip_resp = self.client.get(
            reverse("manufacturing:manufacturing-wip-cost-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(wip_resp.status_code, 200)
        self.assertEqual(wip_resp.json()["overview"]["work_order_count"], 2)
        self.assertGreaterEqual(len(wip_resp.json()["rows"]), 1)

    def test_post_work_order_requires_manufacturing_static_account_setup(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]

        for operation in work_order["operations"]:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {},
                format="json",
            )
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Done"},
                format="json",
            )

        EntityStaticAccountMap.objects.filter(
            entity=self.entity,
            static_account__code=StaticAccountCodes.MANUFACTURING_WIP,
        ).delete()

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 400)
        self.assertIn("Manufacturing posting setup is incomplete", str(post_resp.json()))
        self.assertIn("Manufacturing WIP", str(post_resp.json()))

    def test_standard_cost_mode_requires_variance_ledgers(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity=self.entity, subentity=self.subentity)
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "output_valuation_basis": "standard_cost",
        }
        settings_obj.save(update_fields=["policy_controls"])

        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)
        work_order = work_order_resp.json()["work_order"]
        work_order_id = work_order["id"]

        for operation in work_order["operations"]:
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-start", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {},
                format="json",
            )
            self.client.post(
                reverse("manufacturing:manufacturing-work-order-operation-complete", kwargs={"pk": work_order_id, "operation_pk": operation["id"]}),
                {"input_qty": "10.0000", "output_qty": "10.0000", "scrap_qty": "0.0000", "remarks": "Done"},
                format="json",
            )

        EntityStaticAccountMap.objects.filter(
            entity=self.entity,
            static_account__code__in=[
                StaticAccountCodes.MANUFACTURING_MATERIAL_VARIANCE,
                StaticAccountCodes.MANUFACTURING_YIELD_VARIANCE,
            ],
        ).delete()

        post_resp = self.client.post(reverse("manufacturing:manufacturing-work-order-post", kwargs={"pk": work_order_id}), {}, format="json")
        self.assertEqual(post_resp.status_code, 400)
        self.assertIn("Manufacturing Material Variance", str(post_resp.json()))
        self.assertIn("Manufacturing Yield Variance", str(post_resp.json()))

    def test_standard_cost_mode_exposes_accounting_mode_in_summary_and_reports(self):
        bom = self.client.post(reverse("manufacturing:manufacturing-boms"), self._bom_payload(), format="json").json()
        settings_obj, _ = ManufacturingSettings.objects.get_or_create(entity=self.entity, subentity=self.subentity)
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "output_valuation_basis": "standard_cost",
        }
        settings_obj.save(update_fields=["policy_controls"])

        work_order_resp = self.client.post(reverse("manufacturing:manufacturing-work-orders"), self._work_order_payload(bom["id"]), format="json")
        self.assertEqual(work_order_resp.status_code, 201)

        summary_resp = self.client.get(
            reverse("manufacturing:manufacturing-summary"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(summary_resp.status_code, 200)
        self.assertEqual(summary_resp.json()["accounting"]["output_valuation_basis"], "standard_cost")
        self.assertTrue(summary_resp.json()["accounting"]["uses_variance_ledgers"])
        self.assertEqual(len(summary_resp.json()["setup"]["rows"]), 6)

        wip_resp = self.client.get(
            reverse("manufacturing:manufacturing-wip-cost-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(wip_resp.status_code, 200)
        self.assertEqual(wip_resp.json()["accounting"]["output_valuation_basis"], "standard_cost")
        self.assertTrue(wip_resp.json()["accounting"]["uses_variance_ledgers"])
