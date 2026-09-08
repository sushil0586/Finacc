from datetime import datetime

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from purchase.models.purchase_config import PurchaseChoiceOverride, PurchaseSettings
from sales.models.sales_settings import SalesChoiceOverride, SalesSettings
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityTradeSettingsRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="trade-maker", email="trade-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="trade-checker", email="trade-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="trade-executor", email="trade-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="trade-owner", email="trade-owner@example.com", password="Pass123!")
        for user, code, permissions in (
            (cls.maker, "trade-maker", ("platform.repair.preview", "platform.repair.execute")),
            (cls.checker, "trade-checker", ("platform.operation.approve",)),
            (cls.executor, "trade-executor", ("platform.operation.execute",)),
        ):
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.owner, reason="Trade settings repair tests")
        customer = CustomerAccount.objects.create(name="Trade Settings Customer", slug="trade-settings", owner=cls.owner)
        cls.entity = Entity.objects.create(entityname="Trade Settings Entity", customer_account=customer, createdby=cls.owner)
        cls.year = EntityFinancialYear.objects.create(
            entity=cls.entity, year_code="FY2026-27", desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)), createdby=cls.owner,
        )

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def request_repair(self, key="trade-settings-1"):
        self.auth(self.maker)
        return self.client.post(f"/api/platform/entities/{self.entity.id}/trade-settings-repair-requests/", {
            "idempotency_key": key, "reason": "Restore missing purchase and sales settings after audit",
            "ticket_reference": "OPS-TRADE-1", "expected_target_version": self.entity.updated_at.isoformat(),
        }, format="json")

    def approve(self, operation_id):
        self.auth(self.checker)
        return self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Verified exact missing settings and financial year scope",
        }, format="json")

    def test_preview_and_approved_execution_create_only_missing_defaults(self):
        self.auth(self.maker)
        preview = self.client.get(f"/api/platform/entities/{self.entity.id}/trade-settings-repair-preview/")
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.data["eligible"])
        self.assertEqual(preview.data["sales_financial_year_id"], self.year.id)
        requested = self.request_repair()
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["operation"]["result"]["created"], ["purchase_settings", "sales_settings"])
        self.assertEqual(PurchaseSettings.objects.get(entity=self.entity, subentity=None).default_doc_code_invoice, "PINV")
        self.assertEqual(SalesSettings.objects.get(entity=self.entity, subentity=None).entityfinid_id, self.year.id)
        self.assertTrue(self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json").data["replayed"])

    def test_existing_custom_purchase_settings_are_preserved(self):
        custom = PurchaseSettings.objects.create(entity=self.entity, subentity=None, default_doc_code_invoice="CUSTOM")
        requested = self.request_repair("trade-settings-sales-only")
        self.assertEqual(requested.status_code, 201)
        self.assertFalse(requested.data["operation"]["validation"]["preview"]["missing_purchase_settings"])
        custom.refresh_from_db()
        self.assertEqual(custom.default_doc_code_invoice, "CUSTOM")

    def test_multiple_active_years_block_request(self):
        EntityFinancialYear.objects.create(
            entity=self.entity, year_code="FY2027-28", desc="FY 2027-28",
            finstartyear=timezone.make_aware(datetime(2027, 4, 1)),
            finendyear=timezone.make_aware(datetime(2028, 3, 31)), createdby=self.owner,
        )
        response = self.request_repair("trade-settings-ambiguous")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["preview"]["blockers"][0]["code"], "ambiguous_sales_financial_year")
        self.assertFalse(PurchaseSettings.objects.filter(entity=self.entity).exists())

    def test_stale_approval_writes_nothing(self):
        requested = self.request_repair("trade-settings-stale")
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now())
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(PurchaseSettings.objects.filter(entity=self.entity).exists())
        self.assertFalse(SalesSettings.objects.filter(entity=self.entity).exists())

    def test_choice_override_audit_is_read_only_and_classifies_policy(self):
        PurchaseChoiceOverride.objects.create(
            entity=self.entity, choice_group="Taxability", choice_key="TAXABLE",
            is_enabled=False, override_label="Taxable supply",
        )
        PurchaseChoiceOverride.objects.create(
            entity=self.entity, choice_group="LegacyGroup", choice_key="OLD", is_enabled=True,
        )
        SalesChoiceOverride.objects.create(
            entity=self.entity, choice_group="TaxRegime", choice_key="INTRA_STATE", is_enabled=True,
        )
        SalesChoiceOverride.objects.create(
            entity=self.entity, choice_group="TaxRegime", choice_key="INTRA_STATE", is_enabled=True,
        )
        before = PurchaseChoiceOverride.objects.filter(entity=self.entity).count() + SalesChoiceOverride.objects.filter(entity=self.entity).count()
        self.auth(self.maker)
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/choice-override-audit/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["read_only"])
        self.assertEqual(response.data["purchase"]["disabled_count"], 1)
        self.assertEqual(response.data["purchase"]["relabeled_count"], 1)
        self.assertEqual(response.data["purchase"]["unknown_count"], 1)
        self.assertEqual(response.data["sales"]["duplicate_count"], 1)
        after = PurchaseChoiceOverride.objects.filter(entity=self.entity).count() + SalesChoiceOverride.objects.filter(entity=self.entity).count()
        self.assertEqual(after, before)
