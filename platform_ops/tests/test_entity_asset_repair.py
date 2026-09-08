from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from assets.models import AssetCategory, AssetSettings
from assets.seeding import AssetSeedService, CATEGORY_DEFINITIONS
from entity.models import Entity
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityAssetRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="asset-repair-maker", email="asset-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="asset-repair-checker", email="asset-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="asset-repair-executor", email="asset-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="asset-repair-owner", email="asset-owner@example.com", password="Pass123!")
        for user, code, permissions in (
            (cls.maker, "asset-repair-maker", ("platform.repair.preview", "platform.repair.execute")),
            (cls.checker, "asset-repair-checker", ("platform.operation.approve",)),
            (cls.executor, "asset-repair-executor", ("platform.operation.execute",)),
        ):
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.owner, reason="Asset repair tests")
        customer = CustomerAccount.objects.create(name="Asset Repair Customer", slug="asset-repair", owner=cls.owner)
        cls.entity = Entity.objects.create(entityname="Asset Repair Entity", customer_account=customer, createdby=cls.owner)
        AssetSeedService.seed_entity(entity=cls.entity, actor=cls.owner)
        cls.customized = AssetCategory.objects.get(entity=cls.entity, subentity=None, code="COMPUTER")
        cls.customized.name = "Tenant Managed Computers"
        cls.customized.useful_life_months = 48
        cls.customized.save()
        AssetCategory.objects.filter(entity=cls.entity, subentity=None, code="VEHICLE").delete()
        AssetSettings.objects.filter(entity=cls.entity, subentity=None).delete()

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def request_repair(self, key="asset-repair-1"):
        self.auth(self.maker)
        return self.client.post(f"/api/platform/entities/{self.entity.id}/asset-repair-requests/", {
            "idempotency_key": key, "reason": "Restore missing asset defaults after tenant audit",
            "ticket_reference": "OPS-ASSET-1", "expected_target_version": self.entity.updated_at.isoformat(),
        }, format="json")

    def approve(self, operation_id):
        self.auth(self.checker)
        return self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Verified exact missing asset configuration snapshot",
        }, format="json")

    def test_preview_is_missing_only_and_preserves_custom_category(self):
        self.auth(self.maker)
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/asset-repair-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        self.assertTrue(response.data["missing_settings"])
        self.assertEqual([row["code"] for row in response.data["missing_categories"]], ["VEHICLE"])
        self.customized.refresh_from_db()
        self.assertEqual(self.customized.useful_life_months, 48)

    def test_approved_repair_creates_only_snapshot_and_replays(self):
        requested = self.request_repair()
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["operation"]["result"]["settings_created"])
        self.assertEqual(response.data["operation"]["result"]["categories_created"], ["VEHICLE"])
        self.customized.refresh_from_db()
        self.assertEqual((self.customized.name, self.customized.useful_life_months), ("Tenant Managed Computers", 48))
        self.assertTrue(self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json").data["replayed"])

    def test_inactive_category_blocks_entire_request(self):
        vehicle = CATEGORY_DEFINITIONS[9]
        AssetCategory.objects.create(
            entity=self.entity, code=vehicle["code"], name=vehicle["name"],
            useful_life_months=vehicle["useful_life_months"], is_active=False,
        )
        response = self.request_repair("asset-repair-blocked")
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactive_asset_category", [row["code"] for row in response.data["preview"]["blockers"]])
        self.assertFalse(AssetSettings.objects.filter(entity=self.entity, subentity=None).exists())

    def test_stale_approval_or_deactivated_ledger_writes_nothing(self):
        requested = self.request_repair("asset-repair-stale")
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now())
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertFalse(AssetCategory.objects.filter(entity=self.entity, code="VEHICLE").exists())
        self.assertFalse(AssetSettings.objects.filter(entity=self.entity, subentity=None).exists())
