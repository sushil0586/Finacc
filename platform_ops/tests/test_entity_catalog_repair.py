from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from catalog.models import HsnSac, ProductCategory, UnitOfMeasure
from catalog.seeding import CatalogSeedService
from entity.models import Entity
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityCatalogRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="catalog-maker", email="catalog-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="catalog-checker", email="catalog-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="catalog-executor", email="catalog-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="catalog-owner", email="catalog-owner@example.com", password="Pass123!")
        for user, code, permissions in (
            (cls.maker, "catalog-repair-maker", ("platform.repair.preview", "platform.repair.execute")),
            (cls.checker, "catalog-repair-checker", ("platform.operation.approve",)),
            (cls.executor, "catalog-repair-executor", ("platform.operation.execute",)),
        ):
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.owner, reason="Catalog repair tests")
        cls.customer = CustomerAccount.objects.create(name="Catalog Customer", slug="catalog-customer", owner=cls.owner)
        cls.entity = Entity.objects.create(entityname="Catalog Target", customer_account=cls.customer, createdby=cls.owner)
        cls.custom_category = ProductCategory.objects.create(
            entity=cls.entity, pcategoryname="Electronics", level=3, isactive=True,
        )
        cls.custom_uom = UnitOfMeasure.objects.create(
            entity=cls.entity, code="CUSTOM-NOS", description="Tenant custom", uqc="NOS", isactive=True,
        )
        cls.custom_hsn = HsnSac.objects.create(
            entity=cls.entity, code="85171200", description="Tenant phone classification",
            default_cgst=Decimal("2.50"), default_sgst=Decimal("2.50"), default_igst=Decimal("5.00"), isactive=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def request_repair(self, key="catalog-repair-1"):
        self.auth(self.maker)
        return self.client.post(f"/api/platform/entities/{self.entity.id}/catalog-repair-requests/", {
            "idempotency_key": key, "reason": "Restore missing catalog defaults after tenant audit",
            "ticket_reference": "OPS-CAT-1", "expected_target_version": self.entity.updated_at.isoformat(),
        }, format="json")

    def approve(self, operation_id):
        self.auth(self.checker)
        return self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Reviewed exact missing catalog creation payloads",
        }, format="json")

    def test_preview_preserves_claimed_uqc_and_existing_custom_rows(self):
        self.auth(self.maker)
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/catalog-repair-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        pcs = next(row for row in response.data["missing"]["uoms"] if row["code"] == "PCS")
        self.assertIsNone(pcs["uqc"])
        self.assertNotIn("Electronics", [row["name"] for row in response.data["missing"]["categories"]])
        self.assertNotIn("85171200", [row["code"] for row in response.data["missing"]["hsn_sac"]])

    def test_approved_repair_creates_only_missing_defaults_and_replays(self):
        requested = self.request_repair()
        operation_id = requested.data["operation"]["id"]
        expected_created = requested.data["operation"]["validation"]["preview"]["missing_count"]
        self.approve(operation_id)
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["operation"]["result"]["created_count"], expected_created)
        self.custom_category.refresh_from_db()
        self.custom_hsn.refresh_from_db()
        self.assertEqual(self.custom_category.level, 3)
        self.assertEqual(self.custom_hsn.default_igst, Decimal("5.00"))
        self.assertEqual(UnitOfMeasure.objects.get(entity=self.entity, code="PCS").uqc, None)
        self.assertEqual(ProductCategory.objects.get(entity=self.entity, pcategoryname="Mobile Phones").maincategory_id, self.custom_category.id)
        replay = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertTrue(replay.data["replayed"])

    def test_inactive_seed_code_blocks_entire_request(self):
        UnitOfMeasure.objects.create(entity=self.entity, code="BOX", description="Retired box", isactive=False)
        response = self.request_repair("catalog-repair-blocked")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["preview"]["blockers"][0]["code"], "inactive_catalog_conflict")
        self.assertFalse(UnitOfMeasure.objects.filter(entity=self.entity, code="PCS").exists())

    def test_stale_approval_does_not_create_catalog_rows(self):
        requested = self.request_repair("catalog-repair-stale")
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now())
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertFalse(UnitOfMeasure.objects.filter(entity=self.entity, code="PCS").exists())
