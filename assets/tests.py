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
        self.foreign_ledger = Ledger.objects.create(entity=self.foreign_entity, ledger_code=2001, name="Foreign Ledger", accounthead=self.foreign_head, createdby=self.foreign_owner)

        self.category = AssetCategory.objects.create(
            entity=self.entity,
            subentity=None,
            code="CAT-001",
            name="Office Equipment",
            asset_ledger=self.asset_ledger,
            accumulated_depreciation_ledger=self.acc_dep_ledger,
            depreciation_expense_ledger=self.dep_exp_ledger,
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

    def test_depreciation_run_calculate_blocks_overlap_created_outside_api(self):
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
