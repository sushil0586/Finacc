from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone

from Authentication.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import Ledger, accountHead
from subscriptions.models import PlanLimit
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from .models import AssetCategory, DepreciationRun, FixedAsset
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
