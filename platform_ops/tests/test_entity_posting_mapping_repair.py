from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity
from financial.models import Ledger, account
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from posting.models import EntityStaticAccountMap, StaticAccount, StaticAccountGroup
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityPostingMappingRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="mapping-maker", email="mapping-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="mapping-checker", email="mapping-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="mapping-executor", email="mapping-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="mapping-owner", email="mapping-owner@example.com", password="Pass123!")
        for user, code, permissions in (
            (cls.maker, "mapping-maker", ("platform.repair.preview", "platform.repair.execute")),
            (cls.checker, "mapping-checker", ("platform.operation.approve",)),
            (cls.executor, "mapping-executor", ("platform.operation.execute",)),
        ):
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.owner, reason="Posting mapping repair tests")
        StaticAccount.objects.update(is_required=False)
        cls.static_role = StaticAccount.objects.create(
            code="TEST_REQUIRED_POSTING", name="Required Posting Test", group=StaticAccountGroup.OTHER,
            is_required=True, is_active=True,
        )
        cls.customer = CustomerAccount.objects.create(name="Mapping Customer", slug="mapping-customer", owner=cls.owner)
        cls.template = Entity.objects.create(entityname="Mapping Template", customer_account=cls.customer, createdby=cls.owner)
        cls.entity = Entity.objects.create(entityname="Mapping Target", customer_account=cls.customer, createdby=cls.owner)
        template_ledger = Ledger.objects.create(entity=cls.template, ledger_code=8500, name="Template Expense")
        cls.target_ledger = Ledger.objects.create(entity=cls.entity, ledger_code=8500, name="Target Expense")
        template_account = account.objects.create(entity=cls.template, ledger=template_ledger, accountname="Template Expense")
        cls.target_account = account.objects.create(entity=cls.entity, ledger=cls.target_ledger, accountname="Target Expense")
        EntityStaticAccountMap.objects.create(
            entity=cls.template, static_account=cls.static_role, account=template_account, ledger=template_ledger,
        )

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()
        settings_override = override_settings(DEFAULT_STATIC_ACCOUNT_TEMPLATE_ENTITY_ID=self.template.id)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def auth(self, user):
        self.client.force_authenticate(user)

    def request_repair(self, key="mapping-repair-1"):
        self.auth(self.maker)
        return self.client.post(f"/api/platform/entities/{self.entity.id}/posting-mapping-repair-requests/", {
            "idempotency_key": key, "reason": "Restore mandatory posting role after configuration audit",
            "ticket_reference": "OPS-MAP-1", "expected_target_version": self.entity.updated_at.isoformat(),
        }, format="json")

    def approve(self, operation_id):
        self.auth(self.checker)
        return self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Verified target ledger and required posting role",
        }, format="json")

    def test_preview_resolves_required_role_without_writing(self):
        self.auth(self.maker)
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/posting-mapping-repair-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        self.assertEqual(response.data["missing_mapping_count"], 1)
        self.assertEqual(response.data["repairable_mappings"][0]["ledger_id"], self.target_ledger.id)
        self.assertFalse(EntityStaticAccountMap.objects.filter(entity=self.entity).exists())

    def test_approved_repair_creates_exact_mapping_and_replay_is_idempotent(self):
        requested = self.request_repair()
        self.assertEqual(requested.status_code, 201)
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        mapping = EntityStaticAccountMap.objects.get(entity=self.entity, static_account=self.static_role, is_active=True)
        self.assertEqual(mapping.account_id, self.target_account.id)
        self.assertEqual(mapping.ledger_id, self.target_ledger.id)
        replay = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(EntityStaticAccountMap.objects.filter(entity=self.entity, static_account=self.static_role).count(), 1)

    def test_unresolved_required_role_blocks_request(self):
        self.target_account.delete()
        self.target_ledger.delete()
        response = self.request_repair("mapping-repair-blocked")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["preview"]["blockers"][0]["code"], "required_mapping_unresolved")

    def test_stale_approval_does_not_create_mapping(self):
        requested = self.request_repair("mapping-repair-stale")
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now())
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertFalse(EntityStaticAccountMap.objects.filter(entity=self.entity).exists())
