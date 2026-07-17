from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from Authentication.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import Product, ProductCategory, ProductPurchaseBehavior, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import Ledger, accountHead
from posting.models import Entry, EntryStatus, JournalLine
from purchase.models.purchase_core import PurchaseInvoiceHeader
from subscriptions.models import PlanLimit
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from .models import AssetBulkJob, AssetCategory, DepreciationRun, FixedAsset
from .seeding import AssetSeedService
from .services.settings import AssetSettingsService


class AssetApiScopeTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="asset-owner",
            email="asset-owner@example.com",
            password="Password@123",
        )
        self.foreign_owner = User.objects.create_user(
            username="asset-foreign",
            email="asset-foreign@example.com",
            password="Password@123",
        )

        self.entity = Entity.objects.create(entityname="Assets Entity", createdby=self.owner)
        self.foreign_entity = Entity.objects.create(entityname="Foreign Entity", createdby=self.foreign_owner)
        self.account = SubscriptionService.register_entity_creation(entity=self.entity, owner=self.owner)
        self.foreign_account = SubscriptionService.register_entity_creation(entity=self.foreign_entity, owner=self.foreign_owner)

        subscription = SubscriptionService.ensure_active_subscription(customer_account=self.account)
        PlanLimit.objects.update_or_create(
            plan=subscription.plan,
            key=SubscriptionLimitCodes.FEATURE_ASSETS,
            defaults={
                "label": "Assets Module",
                "limit_type": PlanLimit.LimitType.BOOLEAN,
                "bool_value": True,
            },
        )
        PlanLimit.objects.update_or_create(
            plan=subscription.plan,
            key=SubscriptionLimitCodes.FEATURE_REPORTING,
            defaults={
                "label": "Reporting",
                "limit_type": PlanLimit.LimitType.BOOLEAN,
                "bool_value": True,
            },
        )

        foreign_subscription = SubscriptionService.ensure_active_subscription(customer_account=self.foreign_account)
        PlanLimit.objects.update_or_create(
            plan=foreign_subscription.plan,
            key=SubscriptionLimitCodes.FEATURE_ASSETS,
            defaults={
                "label": "Assets Module",
                "limit_type": PlanLimit.LimitType.BOOLEAN,
                "bool_value": True,
            },
        )
        PlanLimit.objects.update_or_create(
            plan=foreign_subscription.plan,
            key=SubscriptionLimitCodes.FEATURE_REPORTING,
            defaults={
                "label": "Reporting",
                "limit_type": PlanLimit.LimitType.BOOLEAN,
                "bool_value": True,
            },
        )

        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch", is_head_office=True)
        self.foreign_subentity = SubEntity.objects.create(entity=self.foreign_entity, subentityname="Foreign Branch", is_head_office=True)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            finendyear=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            createdby=self.owner,
        )

        self.entity_head = accountHead.objects.create(entity=self.entity, name="Asset Head", code=101, drcreffect="Debit")
        self.foreign_head = accountHead.objects.create(entity=self.foreign_entity, name="Foreign Head", code=201, drcreffect="Debit")

        self.asset_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1001, name="Asset Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.acc_dep_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1002, name="Accum Dep Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.dep_exp_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1003, name="Dep Exp Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.impairment_exp_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1004, name="Impairment Exp Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.impairment_reserve_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1005, name="Impairment Reserve Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.gain_on_sale_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1006, name="Gain On Sale Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.loss_on_sale_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1007, name="Loss On Sale Ledger", accounthead=self.entity_head, createdby=self.owner)
        self.foreign_ledger = Ledger.objects.create(entity=self.foreign_entity, ledger_code=2001, name="Foreign Ledger", accounthead=self.foreign_head, createdby=self.foreign_owner)

        self.category = AssetCategory.objects.create(
            entity=self.entity,
            subentity=None,
            code="CAT-001",
            name="Office Equipment",
            asset_ledger=self.asset_ledger,
            accumulated_depreciation_ledger=self.acc_dep_ledger,
            depreciation_expense_ledger=self.dep_exp_ledger,
            impairment_expense_ledger=self.impairment_exp_ledger,
            impairment_reserve_ledger=self.impairment_reserve_ledger,
            gain_on_sale_ledger=self.gain_on_sale_ledger,
            loss_on_sale_ledger=self.loss_on_sale_ledger,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.asset = FixedAsset.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            category=self.category,
            asset_code="FA-000001",
            asset_name="Office Printer",
            acquisition_date=date(2026, 4, 1),
            gross_block="5000.00",
            residual_value="0.00",
            net_book_value="5000.00",
            location_name="Head Office",
            department_name="Admin",
            custodian_name="A. Kumar",
            created_by=self.owner,
            updated_by=self.owner,
        )
        foreign_category = AssetCategory.objects.create(
            entity=self.foreign_entity,
            code="CAT-FOREIGN",
            name="Foreign Category",
            created_by=self.foreign_owner,
            updated_by=self.foreign_owner,
        )
        self.foreign_asset = FixedAsset.objects.create(
            entity=self.foreign_entity,
            category=foreign_category,
            asset_code="FB-000001",
            asset_name="Foreign Asset",
            acquisition_date=date(2026, 4, 1),
            gross_block="1200.00",
            residual_value="0.00",
            net_book_value="1200.00",
            created_by=self.foreign_owner,
            updated_by=self.foreign_owner,
        )

        self.client.force_authenticate(self.owner)

    def _create_vendor_account(self, name: str):
        from financial.models import account

        return account.objects.create(entity=self.entity, accountname=name)

    def _create_purchase_intake_asset_fixture(self):
        vendor_account = self._create_vendor_account("Vendor One")
        product_category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Equipment")
        uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces")
        asset_product = Product.objects.create(
            entity=self.entity,
            productname="Laptop",
            sku="LAP-001",
            productcategory=product_category,
            base_uom=uom,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            default_asset_category=self.category,
        )
        purchase_header = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=vendor_account,
            bill_date=date(2026, 4, 10),
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            doc_code="PINV",
            doc_no=1009,
            purchase_number="PI/PINV/2026/1009",
            status=PurchaseInvoiceHeader.Status.POSTED,
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA,
        )
        purchase_asset = FixedAsset.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            category=self.category,
            asset_code="CWIP-0001",
            asset_name="Laptop Intake",
            acquisition_date=date(2026, 4, 10),
            gross_block="75000.00",
            residual_value="0.00",
            net_book_value="75000.00",
            status=FixedAsset.AssetStatus.CAPITAL_WIP,
            vendor_account=vendor_account,
            purchase_document_no=purchase_header.purchase_number,
            created_by=self.owner,
            updated_by=self.owner,
        )
        purchase_line = purchase_header.lines.create(
            line_no=1,
            product=asset_product,
            product_desc="Laptop Intake",
            is_service=False,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            uom=uom,
            qty="1.0000",
            rate="75000.00",
            taxable_value="75000.00",
            line_total="88500.00",
            asset_record=purchase_asset,
        )
        return purchase_asset, purchase_line, purchase_header

    def _set_asset_policy(self, *, entity_id, subentity_id=None, **controls):
        AssetSettingsService.upsert_settings(
            entity_id=entity_id,
            subentity_id=subentity_id,
            updates={"policy_controls": controls},
            user_id=self.owner.id,
        )

    def test_list_scopes_assets_to_requested_entity(self):
        response = self.client.get(
            reverse("assets_api:fixed-asset-list-create"),
            {"entity": self.entity.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {row["id"] for row in response.data}
        self.assertIn(self.asset.id, returned_ids)
        self.assertNotIn(self.foreign_asset.id, returned_ids)

    def test_asset_settings_accept_traceability_advisory_controls(self):
        AssetSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={
                "policy_controls": {
                    "require_serial_number_rule": "warn",
                    "require_manufacturer_rule": "warn",
                    "require_model_number_rule": "off",
                    "require_vendor_account_rule": "warn",
                }
            },
            user_id=self.owner.id,
        )

        settings_obj = AssetSettingsService.get_settings(self.entity.id, self.subentity.id)
        controls = AssetSettingsService.resolve_policy_controls(settings_obj)

        self.assertEqual(controls["require_serial_number_rule"], "warn")
        self.assertEqual(controls["require_manufacturer_rule"], "warn")
        self.assertEqual(controls["require_model_number_rule"], "off")
        self.assertEqual(controls["require_vendor_account_rule"], "warn")

    def test_asset_settings_accept_category_accounting_policy_controls(self):
        AssetSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={
                "policy_controls": {
                    "require_asset_ledger_rule": "hard",
                    "require_depreciation_ledgers_rule": "warn",
                    "require_impairment_ledgers_rule": "off",
                    "require_disposal_ledgers_rule": "hard",
                    "require_cwip_ledger_rule": "warn",
                }
            },
            user_id=self.owner.id,
        )

        settings_obj = AssetSettingsService.get_settings(self.entity.id, self.subentity.id)
        controls = AssetSettingsService.resolve_policy_controls(settings_obj)

        self.assertEqual(controls["require_asset_ledger_rule"], "hard")
        self.assertEqual(controls["require_depreciation_ledgers_rule"], "warn")
        self.assertEqual(controls["require_impairment_ledgers_rule"], "off")
        self.assertEqual(controls["require_disposal_ledgers_rule"], "hard")
        self.assertEqual(controls["require_cwip_ledger_rule"], "warn")

    def test_category_traceability_controls_override_scope_settings(self):
        AssetSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={
                "policy_controls": {
                    "require_serial_number_rule": "off",
                    "require_manufacturer_rule": "warn",
                    "require_model_number_rule": "off",
                    "require_vendor_account_rule": "warn",
                }
            },
            user_id=self.owner.id,
        )
        self.category.traceability_controls = {
            "serial_number_rule": "warn",
            "manufacturer_rule": "off",
            "model_number_rule": "inherit",
            "vendor_account_rule": "inherit",
        }
        self.category.save(update_fields=["traceability_controls", "updated_at"])

        settings_obj = AssetSettingsService.get_settings(self.entity.id, self.subentity.id)
        resolved = AssetSettingsService.resolve_category_traceability_controls(self.category, settings_obj)

        self.assertEqual(resolved["serial_number_rule"], "warn")
        self.assertEqual(resolved["manufacturer_rule"], "off")
        self.assertEqual(resolved["model_number_rule"], "off")
        self.assertEqual(resolved["vendor_account_rule"], "warn")

    def test_category_accounting_controls_override_scope_settings(self):
        AssetSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={
                "policy_controls": {
                    "require_asset_ledger_rule": "off",
                    "require_depreciation_ledgers_rule": "warn",
                    "require_impairment_ledgers_rule": "hard",
                    "require_disposal_ledgers_rule": "warn",
                    "require_cwip_ledger_rule": "off",
                }
            },
            user_id=self.owner.id,
        )
        self.category.accounting_controls = {
            "asset_ledger_rule": "hard",
            "depreciation_ledgers_rule": "inherit",
            "impairment_ledgers_rule": "off",
            "disposal_ledgers_rule": "inherit",
            "cwip_ledger_rule": "warn",
        }
        self.category.save(update_fields=["accounting_controls", "updated_at"])

        settings_obj = AssetSettingsService.get_settings(self.entity.id, self.subentity.id)
        resolved = AssetSettingsService.resolve_category_accounting_controls(self.category, settings_obj)

        self.assertEqual(resolved["asset_ledger_rule"], "hard")
        self.assertEqual(resolved["depreciation_ledgers_rule"], "warn")
        self.assertEqual(resolved["impairment_ledgers_rule"], "off")
        self.assertEqual(resolved["disposal_ledgers_rule"], "warn")
        self.assertEqual(resolved["cwip_ledger_rule"], "warn")

    def test_category_create_blocks_missing_asset_ledger_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            require_asset_ledger_rule="hard",
        )

        response = self.client.post(
            reverse("assets_api:asset-category-list-create"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "code": "MACH",
                "name": "Machinery",
                "nature": "TANGIBLE",
                "depreciation_method": "SLM",
                "useful_life_months": 60,
                "traceability_controls": {"serial_number_rule": "inherit"},
                "accounting_controls": {"asset_ledger_rule": "inherit"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("asset_ledger", response.data)

    def test_category_create_rejects_oversized_fields(self):
        response = self.client.post(
            reverse("assets_api:asset-category-list-create"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "code": "C" * 31,
                "name": "N" * 256,
                "nature": "TANGIBLE",
                "depreciation_method": "SLM",
                "useful_life_months": 60,
                "traceability_controls": {"serial_number_rule": "inherit"},
                "accounting_controls": {"asset_ledger_rule": "inherit"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)

    def test_detail_blocks_asset_from_unrelated_entity(self):
        response = self.client.get(reverse("assets_api:fixed-asset-detail", args=[self.foreign_asset.id]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_register_blocks_foreign_entity_scope(self):
        response = self.client.get(
            reverse("reports:fixed-asset-register"),
            {"entity": self.foreign_entity.id},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_history_blocks_foreign_asset_scope(self):
        response = self.client.get(
            reverse("reports:fixed-asset-history"),
            {"entity": self.foreign_entity.id, "asset": self.foreign_asset.id},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_location_custodian_blocks_foreign_entity_scope(self):
        response = self.client.get(
            reverse("reports:asset-location-custodian"),
            {"entity": self.foreign_entity.id},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_location_custodian_returns_asset_assignment_fields(self):
        response = self.client.get(
            reverse("reports:asset-location-custodian"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["report_name"], "Asset Location / Custodian Report")
        self.assertEqual(response.data["summary"]["asset_count"], 1)
        self.assertEqual(response.data["summary"]["location_count"], 1)
        self.assertEqual(response.data["summary"]["custodian_count"], 1)
        self.assertEqual(response.data["rows"][0]["location_name"], "Head Office")
        self.assertEqual(response.data["rows"][0]["custodian_name"], "A. Kumar")

    def test_asset_dashboard_summary_returns_bundled_sections(self):
        response = self.client.get(
            reverse("reports:asset-dashboard-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "as_of_date": "2026-06-02",
                "from_date": "2026-04-01",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["report_name"], "Asset Dashboard Summary")
        self.assertIn("register", response.data)
        self.assertIn("location", response.data)
        self.assertIn("depreciation", response.data)
        self.assertIn("events", response.data)
        self.assertEqual(response.data["register"]["summary"]["asset_count"], 1)
        self.assertEqual(response.data["summary"]["asset_count"], 1)

    def test_create_rejects_foreign_entity_ledger(self):
        payload = {
            "entity": self.entity.id,
            "subentity": self.subentity.id,
            "category": self.category.id,
            "ledger": self.foreign_ledger.id,
            "asset_name": "Invalid Asset",
            "acquisition_date": "2026-04-01",
            "gross_block": "1000.00",
            "residual_value": "0.00",
        }

        response = self.client.post(reverse("assets_api:fixed-asset-list-create"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FixedAsset.objects.filter(asset_name="Invalid Asset").exists())

    def test_list_review_queue_purchase_returns_purchase_intake_assets(self):
        purchase_asset, _, _ = self._create_purchase_intake_asset_fixture()
        response = self.client.get(
            reverse("assets_api:fixed-asset-list-create"),
            {"entity": self.entity.id, "review_queue": "purchase"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {row["id"] for row in response.data}
        self.assertIn(purchase_asset.id, returned_ids)
        self.assertNotIn(self.asset.id, returned_ids)

    def test_list_serializer_includes_purchase_traceability_fields(self):
        purchase_asset, purchase_line, purchase_header = self._create_purchase_intake_asset_fixture()
        response = self.client.get(
            reverse("assets_api:fixed-asset-detail", args=[purchase_asset.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_purchase_intake"])
        self.assertEqual(response.data["source_purchase_line_ids"], [purchase_line.id])
        self.assertIn(purchase_header.purchase_number, response.data["source_purchase_numbers"])

    def test_regular_asset_is_not_flagged_as_purchase_intake(self):
        response = self.client.get(
            reverse("assets_api:fixed-asset-detail", args=[self.asset.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_purchase_intake"])
        self.assertEqual(response.data["source_purchase_line_ids"], [])
        self.assertEqual(response.data["source_purchase_numbers"], [])

    def test_capitalize_blocks_purchase_intake_when_review_fields_missing(self):
        purchase_asset, _, _ = self._create_purchase_intake_asset_fixture()
        purchase_asset.location_name = ""
        purchase_asset.custodian_name = ""
        purchase_asset.save(update_fields=["location_name", "custodian_name", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[purchase_asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-12",
                "narration": "Capitalize purchase intake",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("purchase intake asset review is incomplete", response.data["detail"].lower())
        self.assertIn("location", response.data["detail"].lower())
        self.assertIn("custodian", response.data["detail"].lower())

    def test_capitalize_accepts_inline_purchase_review_fields(self):
        purchase_asset, _, _ = self._create_purchase_intake_asset_fixture()
        purchase_asset.location_name = ""
        purchase_asset.department_name = ""
        purchase_asset.custodian_name = ""
        purchase_asset.save(update_fields=["location_name", "department_name", "custodian_name", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[purchase_asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-12",
                "narration": "Capitalize purchase intake",
                "location_name": "Head Office",
                "department_name": "IT",
                "custodian_name": "A. Kumar",
                "notes": "Reviewed during capitalization",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        purchase_asset.refresh_from_db()
        self.assertEqual(purchase_asset.location_name, "Head Office")
        self.assertEqual(purchase_asset.department_name, "IT")
        self.assertEqual(purchase_asset.custodian_name, "A. Kumar")
        self.assertEqual(purchase_asset.notes, "Reviewed during capitalization")
        self.assertEqual(purchase_asset.status, FixedAsset.AssetStatus.ACTIVE)

    def test_create_rejects_system_managed_asset_fields(self):
        payload = {
            "entity": self.entity.id,
            "subentity": self.subentity.id,
            "category": self.category.id,
            "asset_name": "Unsafe Asset",
            "asset_code": "FA-UNSAFE",
            "acquisition_date": "2026-04-01",
            "gross_block": "1000.00",
            "residual_value": "0.00",
            "accumulated_depreciation": "10.00",
            "net_book_value": "990.00",
        }

        response = self.client.post(reverse("assets_api:fixed-asset-list-create"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("accumulated_depreciation", response.data)
        self.assertIn("net_book_value", response.data)

    def test_asset_settings_reject_oversized_doc_codes(self):
        response = self.client.put(
            reverse("assets_api:asset-settings"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "default_doc_code_asset": "A" * 11,
                "default_doc_code_disposal": "D" * 11,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("default_doc_code_asset", response.data)
        self.assertIn("default_doc_code_disposal", response.data)

    def test_create_asset_rejects_oversized_fields(self):
        payload = {
            "entity": self.entity.id,
            "subentity": self.subentity.id,
            "entityfinid": self.entityfin.id,
            "category": self.category.id,
            "ledger": self.asset_ledger.id,
            "asset_code": "A" * 51,
            "asset_name": "N" * 256,
            "asset_tag": "T" * 101,
            "serial_number": "S" * 101,
            "manufacturer": "M" * 256,
            "model_number": "D" * 101,
            "acquisition_date": "2026-04-01",
            "gross_block": "1000.00",
            "residual_value": "0.00",
            "location_name": "L" * 256,
            "department_name": "P" * 256,
            "custodian_name": "C" * 256,
            "purchase_document_no": "Q" * 101,
            "external_reference": "E" * 101,
            "notes": "X" * 501,
        }

        response = self.client.post(reverse("assets_api:fixed-asset-list-create"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("asset_code", response.data)
        self.assertIn("asset_name", response.data)
        self.assertIn("asset_tag", response.data)
        self.assertIn("serial_number", response.data)
        self.assertIn("manufacturer", response.data)
        self.assertIn("model_number", response.data)
        self.assertIn("location_name", response.data)
        self.assertIn("department_name", response.data)
        self.assertIn("custodian_name", response.data)
        self.assertIn("purchase_document_no", response.data)
        self.assertIn("external_reference", response.data)
        self.assertIn("notes", response.data)

    def test_update_rejects_manual_active_status_change(self):
        response = self.client.put(
            reverse("assets_api:fixed-asset-detail", args=[self.asset.id]),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "entityfinid": self.entityfin.id,
                "category": self.category.id,
                "asset_code": self.asset.asset_code,
                "asset_name": self.asset.asset_name,
                "acquisition_date": "2026-04-01",
                "gross_block": "5000.00",
                "residual_value": "0.00",
                "status": "ACTIVE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_create_blocks_missing_location_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            require_location_rule="hard",
        )
        payload = {
            "entity": self.entity.id,
            "subentity": self.subentity.id,
            "entityfinid": self.entityfin.id,
            "category": self.category.id,
            "ledger": self.asset_ledger.id,
            "asset_name": "Tracked Asset",
            "asset_code": "FA-TRACK-001",
            "acquisition_date": "2026-04-01",
            "gross_block": "1000.00",
            "residual_value": "0.00",
            "depreciation_method": "SLM",
            "useful_life_months": 12,
            "location_name": "",
        }

        response = self.client.post(reverse("assets_api:fixed-asset-list-create"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("location_name", response.data)

    def test_update_blocks_missing_custodian_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            require_custodian_rule="hard",
        )

        response = self.client.put(
            reverse("assets_api:fixed-asset-detail", args=[self.asset.id]),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "entityfinid": self.entityfin.id,
                "category": self.category.id,
                "ledger": self.asset_ledger.id,
                "asset_code": self.asset.asset_code,
                "asset_name": self.asset.asset_name,
                "acquisition_date": "2026-04-01",
                "gross_block": "5000.00",
                "residual_value": "0.00",
                "depreciation_method": "SLM",
                "useful_life_months": 60,
                "custodian_name": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("custodian_name", response.data)

    def test_capitalize_rejects_foreign_counter_ledger(self):
        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.foreign_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.capitalization_date)

    def test_archive_unposted_asset_deletes_record(self):
        response = self.client.delete(
            reverse("assets_api:fixed-asset-archive", args=[self.asset.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FixedAsset.objects.filter(pk=self.asset.id).exists())

    def test_archive_posted_asset_soft_deactivates_record(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        response = self.client.delete(
            reverse("assets_api:fixed-asset-archive", args=[self.asset.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.asset.refresh_from_db()
        self.assertFalse(self.asset.is_active)

    def test_transfer_allows_clearing_notes(self):
        self.asset.status = FixedAsset.AssetStatus.ACTIVE
        self.asset.notes = "Needs reassignment"
        self.asset.save(update_fields=["status", "notes", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-transfer", args=[self.asset.id]),
            {
                "subentity_id": self.subentity.id,
                "location_name": "Main Branch",
                "department_name": "Admin",
                "custodian_name": "A. Kumar",
                "notes": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.notes, "")

    def test_transfer_precheck_returns_allowed_payload_for_valid_transfer(self):
        self.asset.status = FixedAsset.AssetStatus.ACTIVE
        self.asset.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-transfer-precheck", args=[self.asset.id]),
            {
                "subentity_id": self.subentity.id,
                "location_name": "Main Branch",
                "department_name": "Admin",
                "custodian_name": "A. Kumar",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["action"], "transfer")
        self.assertTrue(response.data["allowed"])
        self.assertEqual(response.data["snapshot"]["posting_batch_id"], None)
        self.assertEqual(response.data["snapshot"]["posting_date"], None)

    def test_transfer_precheck_blocks_invalid_status(self):
        self.asset.status = FixedAsset.AssetStatus.DISPOSED
        self.asset.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-transfer-precheck", args=[self.asset.id]),
            {
                "subentity_id": self.subentity.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data["allowed"])
        self.assertIn("Only active, held-for-sale, or capital-WIP assets can be transferred.", response.data["blocking_reasons"])

    def test_transfer_precheck_blocks_invalid_subentity(self):
        self.asset.status = FixedAsset.AssetStatus.ACTIVE
        self.asset.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-transfer-precheck", args=[self.asset.id]),
            {
                "subentity_id": self.foreign_subentity.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data["allowed"])
        self.assertIn("Selected subentity belongs to a different entity or is inactive.", response.data["blocking_reasons"])

    def test_capitalize_blocks_below_threshold_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            capitalization_threshold_rule="hard",
        )
        self.category.capitalization_threshold = "6000.00"
        self.category.save(update_fields=["capitalization_threshold", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("threshold", response.data["detail"].lower())

    def test_capitalize_blocks_backdated_date_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            backdated_capitalization_rule="hard",
        )

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-03-31",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("acquisition date", response.data["detail"].lower())

    def test_capitalize_blocks_missing_tag_when_policy_disallows_posting_without_tag(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            allow_posting_without_tag="off",
        )

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("asset tag is required", response.data["detail"].lower())

    def test_capitalize_blocks_same_counter_ledger_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            counter_ledger_match_rule="hard",
        )

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("counter ledger matches the asset ledger", response.data["detail"].lower())

    def test_capitalize_allows_incomplete_purchase_review_when_policy_is_off(self):
        purchase_asset, _, _ = self._create_purchase_intake_asset_fixture()
        purchase_asset.location_name = ""
        purchase_asset.custodian_name = ""
        purchase_asset.save(update_fields=["location_name", "custodian_name", "updated_at"])
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            purchase_review_completeness_rule="off",
        )

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[purchase_asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-12",
                "narration": "Capitalize purchase intake",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


    def test_disposal_blocks_backdated_date_when_policy_is_hard(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            backdated_disposal_rule="hard",
        )

        response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-04-01",
                "sale_proceeds": "0.00",
                "narration": "Dispose asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("capitalization date", response.data["detail"].lower())

    def test_impairment_blocks_locked_period_when_policy_is_hard(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        self.category.impairment_expense_ledger = self.dep_exp_ledger
        self.category.impairment_reserve_ledger = self.acc_dep_ledger
        self.category.save(update_fields=["impairment_expense_ledger", "impairment_reserve_ledger", "updated_at"])
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            depreciation_lock_rule="hard",
        )
        self.entityfin.books_locked_until = date(2026, 4, 30)
        self.entityfin.save(update_fields=["books_locked_until", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-impair", args=[self.asset.id]),
            {
                "impairment_amount": "500.00",
                "posting_date": "2026-04-30",
                "narration": "Impair asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked books period", response.data["detail"].lower())

    def test_disposal_blocks_locked_period_when_policy_is_hard(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            depreciation_lock_rule="hard",
        )
        self.entityfin.books_locked_until = date(2026, 4, 30)
        self.entityfin.save(update_fields=["books_locked_until", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-04-30",
                "sale_proceeds": "0.00",
                "narration": "Dispose asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked books period", response.data["detail"].lower())

    def test_disposal_rejects_negative_sale_proceeds(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-04-30",
                "sale_proceeds": "-10.00",
                "narration": "Dispose asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sale proceeds cannot be negative", response.data["detail"].lower())

    def test_disposal_requires_proceeds_ledger_when_sale_proceeds_exist(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": 0,
                "disposal_date": "2026-04-30",
                "sale_proceeds": "100.00",
                "narration": "Dispose asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("proceeds ledger is required", response.data["detail"].lower())
    def test_depreciation_run_calculate_blocks_locked_period_when_policy_is_hard(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            depreciation_lock_rule="hard",
        )
        self.entityfin.books_locked_until = date(2026, 4, 30)
        self.entityfin.save(update_fields=["books_locked_until", "updated_at"])

        run = DepreciationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            run_code="DEP-0001",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            posting_date=date(2026, 4, 30),
            created_by=self.owner,
            updated_by=self.owner,
        )

        response = self.client.post(reverse("assets_api:depreciation-run-calculate", args=[run.id]), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked books period", response.data["detail"].lower())

    def test_depreciation_run_create_blocks_overlapping_scope(self):
        DepreciationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            run_code="DEP-EXISTING",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            posting_date=date(2026, 4, 30),
            status=DepreciationRun.RunStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        response = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-OVERLAP",
                "period_from": "2026-04-15",
                "period_to": "2026-05-15",
                "posting_date": "2026-04-30",
                "depreciation_method": "SLM",
                "note": "Overlapping run",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overlapping depreciation run", str(response.data).lower())

    def test_depreciation_run_calculate_blocks_overlap_with_existing_posted_run(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-01",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        first_run = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-OV-001",
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "posting_date": "2026-04-30",
                "depreciation_method": "SLM",
                "note": "April depreciation",
            },
            format="json",
        )
        self.assertEqual(first_run.status_code, status.HTTP_201_CREATED)
        first_run_id = first_run.data["id"]
        self.assertEqual(
            self.client.post(reverse("assets_api:depreciation-run-calculate", args=[first_run_id]), {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(reverse("assets_api:depreciation-run-post", args=[first_run_id]), {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        overlapping_run = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-OV-002",
                "period_from": "2026-04-15",
                "period_to": "2026-05-15",
                "posting_date": "2026-05-15",
                "depreciation_method": "SLM",
                "note": "Overlap depreciation",
            },
            format="json",
        )
        self.assertEqual(overlapping_run.status_code, status.HTTP_201_CREATED)

        response = self.client.post(
            reverse("assets_api:depreciation-run-calculate", args=[overlapping_run.data["id"]]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overlaps with existing run", response.data["detail"].lower())

    def test_depreciation_run_calculate_for_multi_month_slm_uses_full_period_amount(self):
        self.asset.useful_life_months = 5
        self.asset.save(update_fields=["useful_life_months", "updated_at"])
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-01",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-MULTI-001",
                "period_from": "2026-04-01",
                "period_to": "2026-06-30",
                "posting_date": "2026-06-30",
                "depreciation_method": "SLM",
                "note": "Quarter depreciation",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(
            reverse("assets_api:depreciation-run-calculate", args=[create_response.data["id"]]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["total_amount"]), "3000.00")
        self.assertEqual(response.data["total_assets"], 1)

    def test_reverse_capitalization_restores_asset_to_draft_and_marks_entry_reversed(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        DepreciationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run_code="DEP-POSTED",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            posting_date=date(2026, 4, 30),
            status=DepreciationRun.RunStatus.POSTED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        pending_run = DepreciationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run_code="DEP-DRAFT",
            period_from=date(2026, 4, 10),
            period_to=date(2026, 4, 25),
            posting_date=date(2026, 4, 25),
            status=DepreciationRun.RunStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        response = self.client.post(
            reverse("assets_api:depreciation-run-calculate", args=[pending_run.id]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overlapping depreciation run", response.data["detail"].lower())

        response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-capitalization", args=[self.asset.id]),
            {"reason": "Wrong capitalization"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        entry = Entry.objects.get(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            txn_type="FAC",
            txn_id=self.asset.id,
        )
        self.assertEqual(self.asset.status, FixedAsset.AssetStatus.DRAFT)
        self.assertIsNone(self.asset.capitalization_date)
        self.assertIsNone(self.asset.capitalization_posting_batch_id)
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertIn("Wrong capitalization", self.asset.notes or "")

    def test_capitalization_precheck_reports_purchase_review_blocker(self):
        self.asset.purchase_document_no = "PI-1001"
        self.asset.location_name = ""
        self.asset.custodian_name = ""
        self.asset.save(update_fields=["purchase_document_no", "location_name", "custodian_name", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize-precheck", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
                "location_name": "",
                "custodian_name": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["allowed"])
        self.assertTrue(any("purchase intake asset review is incomplete" in item.lower() for item in response.data["blocking_reasons"]))

    def test_capitalization_precheck_warns_when_counter_ledger_matches_asset_ledger(self):
        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize-precheck", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["allowed"])
        self.assertTrue(any("counter ledger matches the asset ledger" in item.lower() for item in response.data["warnings"]))

    def test_capitalization_precheck_includes_effective_category_accounting_policy_profile(self):
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            require_asset_ledger_rule="warn",
            require_disposal_ledgers_rule="hard",
        )
        self.category.accounting_controls = {
            "asset_ledger_rule": "hard",
            "depreciation_ledgers_rule": "inherit",
            "impairment_ledgers_rule": "inherit",
            "disposal_ledgers_rule": "inherit",
            "cwip_ledger_rule": "off",
        }
        self.category.save(update_fields=["accounting_controls", "updated_at"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize-precheck", args=[self.asset.id]),
            {
                "counter_ledger_id": self.acc_dep_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("policy_profile", response.data)
        items = {item["code"]: item for item in response.data["policy_profile"]["items"]}
        self.assertEqual(items["asset_ledger_rule"]["effective_rule"], "hard")
        self.assertEqual(items["asset_ledger_rule"]["source"], "category")
        self.assertEqual(items["disposal_ledgers_rule"]["effective_rule"], "hard")
        self.assertEqual(items["disposal_ledgers_rule"]["source"], "scope")

    def test_reverse_capitalization_blocks_when_depreciation_exists(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-REV-001",
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "posting_date": "2026-04-30",
                "depreciation_method": "SLM",
                "note": "April depreciation",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        calculate_response = self.client.post(
            reverse("assets_api:depreciation-run-calculate", args=[create_response.data["id"]]),
            {},
            format="json",
        )
        self.assertEqual(calculate_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-capitalization", args=[self.asset.id]),
            {"reason": "Need correction"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("depreciation runs exist", response.data["detail"].lower())

    def test_reverse_capitalization_precheck_reports_depreciation_blocker(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-PRE-001",
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "posting_date": "2026-04-30",
                "depreciation_method": "SLM",
                "note": "April depreciation",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        calculate_response = self.client.post(
            reverse("assets_api:depreciation-run-calculate", args=[create_response.data["id"]]),
            {},
            format="json",
        )
        self.assertEqual(calculate_response.status_code, status.HTTP_200_OK)

        response = self.client.get(reverse("assets_api:fixed-asset-reverse-capitalization", args=[self.asset.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["allowed"])
        self.assertTrue(any("depreciation runs exist" in item.lower() for item in response.data["blocking_reasons"]))

    def test_reverse_capitalization_precheck_allows_clean_reversal(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        response = self.client.get(reverse("assets_api:fixed-asset-reverse-capitalization", args=[self.asset.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["allowed"])
        self.assertEqual(response.data["action"], "capitalization")
        self.assertEqual(response.data["snapshot"]["posting_batch_id"], capitalize_response.data["capitalization_posting_batch"])

    def test_reverse_impairment_clears_impairment_and_marks_entry_reversed(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        impair_response = self.client.post(
            reverse("assets_api:fixed-asset-impair", args=[self.asset.id]),
            {
                "impairment_amount": "250.00",
                "posting_date": "2026-05-01",
                "narration": "Impair asset",
            },
            format="json",
        )
        self.assertEqual(impair_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-impairment", args=[self.asset.id]),
            {"reason": "Impairment entered in error"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        entry = Entry.objects.get(posting_batch_id=impair_response.data["impairment_posting_batch"])
        self.assertEqual(str(self.asset.impairment_amount), "0.00")
        self.assertIsNone(self.asset.impairment_posting_batch_id)
        self.assertEqual(entry.status, EntryStatus.REVERSED)

    def test_reverse_impairment_truncates_accumulated_notes_to_field_limit(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        impair_response = self.client.post(
            reverse("assets_api:fixed-asset-impair", args=[self.asset.id]),
            {
                "impairment_amount": "250.00",
                "posting_date": "2026-05-01",
                "narration": "Impair asset",
            },
            format="json",
        )
        self.assertEqual(impair_response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.asset.notes = "x" * 495
        self.asset.save(update_fields=["notes"])

        response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-impairment", args=[self.asset.id]),
            {"reason": "Impairment entered in error"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertLessEqual(len(self.asset.notes or ""), 500)
        self.assertIn("Impairment reversed: Impairment entered in error", self.asset.notes or "")

    def test_impairment_precheck_blocks_amount_above_nbv(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-impair-precheck", args=[self.asset.id]),
            {
                "impairment_amount": "999999.00",
                "posting_date": "2026-05-01",
                "narration": "Impair asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["allowed"])
        self.assertTrue(any("cannot exceed current net book value" in item.lower() for item in response.data["blocking_reasons"]))

    def test_impairment_precheck_blocks_full_impairment_when_policy_is_hard(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.acc_dep_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        self._set_asset_policy(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            full_impairment_rule="hard",
        )

        response = self.client.post(
            reverse("assets_api:fixed-asset-impair-precheck", args=[self.asset.id]),
            {
                "impairment_amount": "5000.00",
                "posting_date": "2026-05-01",
                "narration": "Impair asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["allowed"])
        self.assertTrue(any("fully impair the asset" in item.lower() for item in response.data["blocking_reasons"]))

    def test_reverse_impairment_precheck_reports_disposal_blocker(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        impair_response = self.client.post(
            reverse("assets_api:fixed-asset-impair", args=[self.asset.id]),
            {
                "impairment_amount": "250.00",
                "posting_date": "2026-05-01",
                "narration": "Impair asset",
            },
            format="json",
        )
        self.assertEqual(impair_response.status_code, status.HTTP_200_OK)
        dispose_response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-05-10",
                "sale_proceeds": "100.00",
                "narration": "Dispose asset",
            },
            format="json",
        )
        self.assertEqual(dispose_response.status_code, status.HTTP_200_OK)

        response = self.client.get(reverse("assets_api:fixed-asset-reverse-impairment", args=[self.asset.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["allowed"])
        self.assertTrue(any("reverse disposal first" in item.lower() for item in response.data["blocking_reasons"]))

    def test_reverse_disposal_restores_active_status_and_marks_entry_reversed(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        dispose_response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-05-10",
                "sale_proceeds": "100.00",
                "narration": "Dispose asset",
            },
            format="json",
        )
        self.assertEqual(dispose_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-disposal", args=[self.asset.id]),
            {"reason": "Disposed wrong asset"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        entry = Entry.objects.get(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            txn_type="FADS",
            txn_id=self.asset.id,
        )
        self.assertEqual(self.asset.status, FixedAsset.AssetStatus.ACTIVE)
        self.assertIsNone(self.asset.disposal_date)
        self.assertIsNone(self.asset.disposal_posting_batch_id)
        self.assertEqual(str(self.asset.disposal_proceeds), "0.00")
        self.assertEqual(entry.status, EntryStatus.REVERSED)

    def test_disposal_precheck_reports_backdated_disposal_blocker(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-10",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assets_api:fixed-asset-dispose-precheck", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-04-05",
                "sale_proceeds": "100.00",
                "narration": "Dispose asset",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["allowed"])
        self.assertTrue(any("cannot be earlier than the asset capitalization date" in item.lower() for item in response.data["blocking_reasons"]))

    def test_reverse_disposal_precheck_allows_disposed_asset(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        dispose_response = self.client.post(
            reverse("assets_api:fixed-asset-dispose", args=[self.asset.id]),
            {
                "proceeds_ledger_id": self.asset_ledger.id,
                "disposal_date": "2026-05-10",
                "sale_proceeds": "100.00",
                "narration": "Dispose asset",
            },
            format="json",
        )
        self.assertEqual(dispose_response.status_code, status.HTTP_200_OK)

        response = self.client.get(reverse("assets_api:fixed-asset-reverse-disposal", args=[self.asset.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["allowed"])
        self.assertEqual(response.data["action"], "disposal")
        self.assertEqual(response.data["snapshot"]["posting_batch_id"], dispose_response.data["disposal_posting_batch"])

    def test_asset_history_shows_reversed_capitalization_status(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        reverse_response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-capitalization", args=[self.asset.id]),
            {"reason": "Wrong capitalization"},
            format="json",
        )
        self.assertEqual(reverse_response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            reverse("reports:fixed-asset-history"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "asset": self.asset.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        capitalization_events = [item for item in response.data["history"] if item["event_type"] == "capitalization"]
        self.assertTrue(capitalization_events)
        self.assertTrue(any(item.get("event_status") == "REVERSED" for item in capitalization_events))

    def test_asset_event_report_shows_reversed_capitalization_status(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        reverse_response = self.client.post(
            reverse("assets_api:fixed-asset-reverse-capitalization", args=[self.asset.id]),
            {"reason": "Wrong capitalization"},
            format="json",
        )
        self.assertEqual(reverse_response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            reverse("reports:fixed-asset-events"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "asset": self.asset.id,
                "event_type": "capitalization",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["rows"])
        self.assertEqual(response.data["rows"][0]["event_status"], "REVERSED")

    def test_cancel_posted_depreciation_run_preserves_audit_lines_and_marks_entry_reversed(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            reverse("assets_api:depreciation-run-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "run_code": "DEP-0002",
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "posting_date": "2026-04-30",
                "depreciation_method": "SLM",
                "note": "April depreciation",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        run_id = create_response.data["id"]

        calculate_response = self.client.post(
            reverse("assets_api:depreciation-run-calculate", args=[run_id]),
            {},
            format="json",
        )
        self.assertEqual(calculate_response.status_code, status.HTTP_200_OK)

        post_response = self.client.post(
            reverse("assets_api:depreciation-run-post", args=[run_id]),
            {},
            format="json",
        )
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)

        run = DepreciationRun.objects.get(pk=run_id)
        self.assertEqual(run.status, DepreciationRun.RunStatus.POSTED)
        self.assertIsNotNone(run.posting_batch_id)
        original_batch_id = run.posting_batch_id
        original_line_count = JournalLine.objects.filter(posting_batch_id=original_batch_id).count()
        self.assertGreater(original_line_count, 0)

        entry = Entry.objects.get(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            txn_type="FADP",
            txn_id=run_id,
        )
        self.assertEqual(entry.status, EntryStatus.POSTED)

        asset_before_cancel = FixedAsset.objects.get(pk=self.asset.id)
        self.assertGreater(float(asset_before_cancel.accumulated_depreciation), 0.0)

        cancel_response = self.client.post(
            reverse("assets_api:depreciation-run-cancel", args=[run_id]),
            {},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)

        run.refresh_from_db()
        entry.refresh_from_db()
        self.asset.refresh_from_db()

        self.assertEqual(run.status, DepreciationRun.RunStatus.CANCELLED)
        self.assertEqual(run.posting_batch_id, original_batch_id)
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(JournalLine.objects.filter(posting_batch_id=original_batch_id).count(), original_line_count)
        self.assertFalse(run.posting_batch.is_active)
        self.assertEqual(str(self.asset.accumulated_depreciation), "0.00")
        self.assertEqual(str(self.asset.net_book_value), "5000.00")

    def test_update_posted_asset_rejects_immutable_field_changes(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()

        response = self.client.patch(
            reverse("assets_api:fixed-asset-detail", args=[self.asset.id]),
            {
                "gross_block": "6000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("posted asset fields cannot be edited directly", response.data["detail"].lower())
        self.assertIn("gross_block", response.data["detail"])

    def test_cancelled_depreciation_run_is_excluded_from_asset_event_report(self):
        capitalize_response = self.client.post(
            reverse("assets_api:fixed-asset-capitalize", args=[self.asset.id]),
            {
                "counter_ledger_id": self.asset_ledger.id,
                "capitalization_date": "2026-04-02",
                "narration": "Capitalize asset",
            },
            format="json",
        )
        self.assertEqual(capitalize_response.status_code, status.HTTP_200_OK)

        run = DepreciationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run_code="DEP-0003",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            posting_date=date(2026, 4, 30),
            depreciation_method="SLM",
            created_by=self.owner,
            updated_by=self.owner,
        )

        calculate_response = self.client.post(reverse("assets_api:depreciation-run-calculate", args=[run.id]), {}, format="json")
        self.assertEqual(calculate_response.status_code, status.HTTP_200_OK)
        post_response = self.client.post(reverse("assets_api:depreciation-run-post", args=[run.id]), {}, format="json")
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)
        cancel_response = self.client.post(reverse("assets_api:depreciation-run-cancel", args=[run.id]), {}, format="json")
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            reverse("reports:fixed-asset-events"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "asset": self.asset.id,
                "event_type": "depreciation",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["rows"], [])

    def test_auto_numbered_assets_generate_unique_sequential_codes(self):
        AssetSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"auto_number_assets": True, "default_doc_code_asset": "FA"},
            user_id=self.owner.id,
        )

        asset_one = self.client.post(
            reverse("assets_api:fixed-asset-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "category": self.category.id,
                "ledger": self.asset_ledger.id,
                "asset_name": "Auto Asset One",
                "acquisition_date": "2026-04-10",
                "gross_block": "1000.00",
                "residual_value": "0.00",
                "depreciation_method": "SLM",
                "useful_life_months": 12,
            },
            format="json",
        )
        asset_two = self.client.post(
            reverse("assets_api:fixed-asset-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "category": self.category.id,
                "ledger": self.asset_ledger.id,
                "asset_name": "Auto Asset Two",
                "acquisition_date": "2026-04-11",
                "gross_block": "1200.00",
                "residual_value": "0.00",
                "depreciation_method": "SLM",
                "useful_life_months": 12,
            },
            format="json",
        )

        self.assertEqual(asset_one.status_code, status.HTTP_201_CREATED)
        self.assertEqual(asset_two.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(asset_one.data["asset_code"], asset_two.data["asset_code"])

    def test_auto_number_skips_legacy_non_numeric_codes_and_existing_gaps(self):
        for asset_code in [
            "FA-000002",
            "FA-000004",
            "FA-000005",
            "FA-000007",
            "FA-LEGACY",
        ]:
            FixedAsset.objects.create(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                category=self.category,
                ledger=self.asset_ledger,
                asset_code=asset_code,
                asset_name=f"Seed {asset_code}",
                acquisition_date=date(2026, 4, 1),
                gross_block=Decimal("1000.00"),
                residual_value=Decimal("0.00"),
                net_book_value=Decimal("1000.00"),
                useful_life_months=12,
                depreciation_method=FixedAsset.DepreciationMethod.SLM,
            )

        response = self.client.post(
            reverse("assets_api:fixed-asset-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "category": self.category.id,
                "ledger": self.asset_ledger.id,
                "asset_name": "Auto Asset After Legacy Codes",
                "acquisition_date": "2026-04-11",
                "gross_block": "1200.00",
                "residual_value": "0.00",
                "depreciation_method": "SLM",
                "useful_life_months": 12,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["asset_code"], "FA-000008")

    def test_auto_number_retries_when_generated_asset_code_hits_unique_collision(self):
        AssetSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"auto_number_assets": True, "default_doc_code_asset": "FA"},
            user_id=self.owner.id,
        )
        FixedAsset.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            category=self.category,
            ledger=self.asset_ledger,
            asset_code="FA-000007",
            asset_name="Existing collision asset",
            acquisition_date=date(2026, 4, 1),
            gross_block=Decimal("1000.00"),
            residual_value=Decimal("0.00"),
            net_book_value=Decimal("1000.00"),
            useful_life_months=12,
            depreciation_method=FixedAsset.DepreciationMethod.SLM,
        )

        with patch("assets.services.asset_service.AssetService.generate_asset_code", side_effect=["FA-000007", "FA-000008"]):
            response = self.client.post(
                reverse("assets_api:fixed-asset-list-create"),
                {
                    "entity": self.entity.id,
                    "entityfinid": self.entityfin.id,
                    "subentity": self.subentity.id,
                    "category": self.category.id,
                    "ledger": self.asset_ledger.id,
                    "asset_name": "Retry Auto Number Asset",
                    "acquisition_date": "2026-04-11",
                    "gross_block": "1200.00",
                    "residual_value": "0.00",
                    "depreciation_method": "SLM",
                    "useful_life_months": 12,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["asset_code"], "FA-000008")

    def test_bulk_commit_is_idempotent_for_validation_token(self):
        validate_response = self.client.post(
            reverse("assets_api:fixed-asset-bulk-import-validate"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "format": "xlsx",
                "file": self._build_fixed_asset_bulk_upload(
                    [
                        {
                            "asset_code": "FA-BULK-100",
                            "asset_name": "Bulk Asset 100",
                            "category": self.category.code,
                            "ledger": str(self.asset_ledger.ledger_code),
                            "entityfinid": str(self.entityfin.id),
                            "subentity": str(self.subentity.id),
                            "status": "DRAFT",
                            "acquisition_date": "2026-04-15",
                            "gross_block": "3500.00",
                            "residual_value": "0.00",
                            "useful_life_months": "24",
                            "depreciation_method": "SLM",
                        }
                    ]
                ),
            },
        )
        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        token = validate_response.data["validation_token"]

        first_commit = self.client.post(
            reverse("assets_api:fixed-asset-bulk-import-commit"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "validation_token": token,
            },
        )
        second_commit = self.client.post(
            reverse("assets_api:fixed-asset-bulk-import-commit"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "validation_token": token,
            },
        )

        self.assertEqual(first_commit.status_code, status.HTTP_200_OK)
        self.assertEqual(second_commit.status_code, status.HTTP_200_OK)
        self.assertEqual(FixedAsset.objects.filter(entity=self.entity, asset_code="FA-BULK-100").count(), 1)
        self.assertEqual(first_commit.data["job_id"], second_commit.data["job_id"])
        self.assertTrue(second_commit.data.get("idempotent_replay"))

        vjob = AssetBulkJob.objects.get(validation_token=token, job_type=AssetBulkJob.JobType.VALIDATE)
        self.assertIsNotNone(vjob.committed_at)
        self.assertIsNotNone(vjob.committed_import_job_id)

    def _build_fixed_asset_bulk_upload(self, rows):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import Workbook

        headers = [
            "asset_code",
            "asset_name",
            "category",
            "ledger",
            "entityfinid",
            "subentity",
            "asset_tag",
            "serial_number",
            "manufacturer",
            "model_number",
            "status",
            "acquisition_date",
            "capitalization_date",
            "put_to_use_date",
            "depreciation_start_date",
            "disposal_date",
            "quantity",
            "gross_block",
            "residual_value",
            "useful_life_months",
            "depreciation_method",
            "depreciation_rate",
            "location_name",
            "department_name",
            "custodian_name",
            "vendor_account",
            "purchase_document_no",
            "external_reference",
            "notes",
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = "fixed_assets"
        ws.append(headers)
        for row in rows:
            ws.append([row.get(header, "") for header in headers])

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            "fixed_assets_bulk.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class AssetSeedServiceTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="asset-seed-owner",
            email="asset-seed-owner@example.com",
            password="Password@123",
        )
        self.entity = Entity.objects.create(entityname="Seed Entity", createdby=self.owner)
        for code, name, drcr in (
            (2210, "Land", "Debit"),
            (2220, "Building", "Debit"),
            (2230, "Plant & Machinery", "Debit"),
            (2240, "Furniture & Fixtures", "Debit"),
            (2250, "Computers & Peripherals", "Debit"),
            (2260, "Office Equipment", "Debit"),
            (2270, "Vehicles", "Debit"),
            (2280, "Intangible Assets", "Debit"),
            (2290, "Capital Work In Progress", "Debit"),
            (8395, "Depreciation Expense", "Debit"),
            (7088, "Other Income", "Credit"),
            (8350, "Other Expenses", "Debit"),
        ):
            accountHead.objects.create(
                entity=self.entity,
                name=name,
                code=code,
                drcreffect=drcr,
                createdby=self.owner,
            )

    def _run_seed(self):
        with patch("assets.seeding.FinancialSeedService.seed_entity") as financial_seed:
            financial_seed.return_value = {
                "template_code": "indian_accounting_final",
                "financial_settings_id": None,
            }
            return AssetSeedService.seed_entity(entity=self.entity, actor=self.owner)

    def test_seed_rerun_preserves_existing_category_customizations(self):
        self._run_seed()

        custom_head = accountHead.objects.create(
            entity=self.entity,
            name="Custom Asset Head",
            code=9910,
            drcreffect="Debit",
            createdby=self.owner,
        )
        custom_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9911,
            name="Custom Computer Ledger",
            accounthead=custom_head,
            createdby=self.owner,
        )
        category = AssetCategory.objects.get(entity=self.entity, code="COMPUTER")
        category.name = "Customer Managed Computer Category"
        category.useful_life_months = 84
        category.asset_ledger = custom_ledger
        category.traceability_controls = {"serial_number_rule": "required"}
        category.accounting_controls = {"asset_ledger_rule": "strict"}
        category.save(
            update_fields=[
                "name",
                "useful_life_months",
                "asset_ledger",
                "traceability_controls",
                "accounting_controls",
            ]
        )

        self._run_seed()

        category.refresh_from_db()
        self.assertEqual(category.name, "Customer Managed Computer Category")
        self.assertEqual(category.useful_life_months, 84)
        self.assertEqual(category.asset_ledger_id, custom_ledger.id)
        self.assertEqual(category.traceability_controls, {"serial_number_rule": "required"})
        self.assertEqual(category.accounting_controls, {"asset_ledger_rule": "strict"})

    def test_seed_rerun_backfills_missing_category_ledger_without_overwriting_other_values(self):
        self._run_seed()

        category = AssetCategory.objects.get(entity=self.entity, code="PERIPHERAL")
        category.name = "Peripheral - Custom Name"
        category.accumulated_depreciation_ledger = None
        category.save(update_fields=["name", "accumulated_depreciation_ledger"])

        self._run_seed()

        category.refresh_from_db()
        self.assertEqual(category.name, "Peripheral - Custom Name")
        self.assertIsNotNone(category.accumulated_depreciation_ledger_id)

    def test_seed_rerun_preserves_existing_seeded_ledger_metadata(self):
        self._run_seed()

        ledger = Ledger.objects.get(entity=self.entity, ledger_code=2210)
        custom_head = accountHead.objects.create(
            entity=self.entity,
            name="Custom Ledger Head",
            code=9912,
            drcreffect="Debit",
            createdby=self.owner,
        )
        ledger.name = "Customer Computer Ledger"
        ledger.legal_name = "Customer Computer Ledger Pvt Ltd"
        ledger.accounthead = custom_head
        ledger.creditaccounthead = custom_head
        ledger.save(update_fields=["name", "legal_name", "accounthead", "creditaccounthead"])

        self._run_seed()

        ledger.refresh_from_db()
        self.assertEqual(ledger.name, "Customer Computer Ledger")
        self.assertEqual(ledger.legal_name, "Customer Computer Ledger Pvt Ltd")
        self.assertEqual(ledger.accounthead_id, custom_head.id)
        self.assertEqual(ledger.creditaccounthead_id, custom_head.id)

    def test_seed_rerun_backfills_missing_settings_without_overwriting_custom_defaults(self):
        self._run_seed()

        settings_obj = self.entity.asset_settings.get(subentity=None)
        settings_obj.default_doc_code_asset = ""
        settings_obj.default_doc_code_disposal = ""
        settings_obj.default_useful_life_months = 96
        settings_obj.default_residual_value_percent = Decimal("10.0000")
        settings_obj.policy_controls = {}
        settings_obj.save(
            update_fields=[
                "default_doc_code_asset",
                "default_doc_code_disposal",
                "default_useful_life_months",
                "default_residual_value_percent",
                "policy_controls",
            ]
        )

        self._run_seed()

        settings_obj.refresh_from_db()
        self.assertEqual(settings_obj.default_doc_code_asset, "FA")
        self.assertEqual(settings_obj.default_doc_code_disposal, "FAD")
        self.assertEqual(settings_obj.default_useful_life_months, 96)
        self.assertEqual(settings_obj.default_residual_value_percent, Decimal("10.0000"))
        self.assertTrue(settings_obj.policy_controls)

    def test_seed_creates_day_one_category_pack_with_expected_ledger_mappings(self):
        summary = self._run_seed()

        self.assertEqual(summary["category_count"], 20)
        self.assertEqual(AssetCategory.objects.filter(entity=self.entity).count(), 20)

        land = AssetCategory.objects.get(entity=self.entity, code="LAND")
        self.assertIsNone(land.accumulated_depreciation_ledger_id)
        self.assertIsNone(land.depreciation_expense_ledger_id)
        self.assertEqual(land.asset_ledger.ledger_code, 2201)

        vehicle = AssetCategory.objects.get(entity=self.entity, code="VEHICLE")
        self.assertEqual(vehicle.asset_ledger.accounthead.code, 2270)
        self.assertEqual(vehicle.accumulated_depreciation_ledger.ledger_code, 2313)
        self.assertEqual(vehicle.depreciation_expense_ledger.ledger_code, 8396)

        software = AssetCategory.objects.get(entity=self.entity, code="SOFTWARE")
        self.assertEqual(software.nature, AssetCategory.AssetNature.INTANGIBLE)
        self.assertEqual(software.asset_ledger.accounthead.code, 2280)
        self.assertEqual(software.accumulated_depreciation_ledger.ledger_code, 2314)
        self.assertEqual(software.depreciation_expense_ledger.ledger_code, 8397)

        rou_asset = AssetCategory.objects.get(entity=self.entity, code="ROU_ASSET")
        self.assertEqual(rou_asset.nature, AssetCategory.AssetNature.ROU)
        self.assertEqual(rou_asset.asset_ledger.accounthead.code, 2285)
        self.assertEqual(rou_asset.accumulated_depreciation_ledger.ledger_code, 2315)

        cwip = AssetCategory.objects.get(entity=self.entity, code="CWIP_GENERAL")
        self.assertEqual(cwip.nature, AssetCategory.AssetNature.CAPITAL_WIP)
        self.assertEqual(cwip.asset_ledger.ledger_code, 2209)
        self.assertEqual(cwip.cwip_ledger.ledger_code, 2209)
