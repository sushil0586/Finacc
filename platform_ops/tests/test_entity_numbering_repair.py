from datetime import datetime, timezone as dt_timezone

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, SubEntity
from numbering.models import DocumentNumberSeries
from numbering.seeding import NumberingSeedService
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from platform_ops.operations import DEFAULT_NUMBERING_SPECS
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityNumberingRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="numbering-maker", email="numbering-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="numbering-checker", email="numbering-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="numbering-executor", email="numbering-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="numbering-owner", email="numbering-owner@example.com", password="Pass123!")
        for user, code, permissions in (
            (cls.maker, "numbering-maker", ("platform.repair.preview", "platform.repair.execute")),
            (cls.checker, "numbering-checker", ("platform.operation.approve",)),
            (cls.executor, "numbering-executor", ("platform.operation.execute",)),
        ):
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.owner, reason="Numbering repair tests")
        cls.customer = CustomerAccount.objects.create(name="Numbering Customer", slug="numbering-customer", owner=cls.owner)
        cls.entity = Entity.objects.create(entityname="Numbering Entity", customer_account=cls.customer, createdby=cls.owner)
        cls.year = EntityFinancialYear.objects.create(
            entity=cls.entity, createdby=cls.owner,
            finstartyear=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            finendyear=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            year_code="FY2026-27", isactive=True,
        )
        cls.branch = SubEntity.objects.create(entity=cls.entity, subentityname="Head Office", isactive=True)

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def request_repair(self, key="numbering-repair-1"):
        self.auth(self.maker)
        return self.client.post(f"/api/platform/entities/{self.entity.id}/numbering-repair-requests/", {
            "idempotency_key": key,
            "reason": "Restore missing document numbering configuration",
            "ticket_reference": "OPS-NUM-1",
            "expected_target_version": self.entity.updated_at.isoformat(),
        }, format="json")

    def test_preview_reports_exact_missing_series_without_writing(self):
        self.auth(self.maker)
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/numbering-repair-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        self.assertEqual(response.data["scope_count"], 2)
        self.assertEqual(response.data["missing_series_count"], 2 * len(DEFAULT_NUMBERING_SPECS))
        self.assertEqual(DocumentNumberSeries.objects.filter(entity=self.entity).count(), 0)

    def test_approved_repair_creates_only_missing_series_and_replay_is_idempotent(self):
        existing = NumberingSeedService.seed_document(
            entity_id=self.entity.id, entityfinid_id=self.year.id, subentity_id=None,
            module=DEFAULT_NUMBERING_SPECS[0].module, doc_key=DEFAULT_NUMBERING_SPECS[0].doc_key,
            name=DEFAULT_NUMBERING_SPECS[0].name, default_code=DEFAULT_NUMBERING_SPECS[0].default_code,
        )
        series = DocumentNumberSeries.objects.get(pk=existing["series_id"])
        series.current_number = 417
        series.save(update_fields=["current_number"])
        requested = self.request_repair()
        self.assertEqual(requested.status_code, 201)
        operation_id = requested.data["operation"]["id"]
        expected_created = 2 * len(DEFAULT_NUMBERING_SPECS) - 1

        self.auth(self.checker)
        approved = self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Reviewed exact missing numbering scopes",
        }, format="json")
        self.assertEqual(approved.status_code, 200)
        self.auth(self.executor)
        executed = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.data["operation"]["result"]["series_created"], expected_created)
        self.assertTrue(executed.data["operation"]["result"]["after"]["healthy"])
        series.refresh_from_db()
        self.assertEqual(series.current_number, 417)
        count = DocumentNumberSeries.objects.filter(entity=self.entity).count()
        replay = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(DocumentNumberSeries.objects.filter(entity=self.entity).count(), count)

    def test_stale_approval_does_not_repair(self):
        requested = self.request_repair("numbering-repair-stale")
        operation_id = requested.data["operation"]["id"]
        self.auth(self.checker)
        self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Reviewed repair request before entity changed",
        }, format="json")
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now())
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertEqual(DocumentNumberSeries.objects.filter(entity=self.entity).count(), 0)

    def test_healthy_entity_cannot_create_repair_request(self):
        for branch_id in (None, self.branch.id):
            NumberingSeedService.seed_documents(
                entity_id=self.entity.id, entityfinid_id=self.year.id,
                subentity_id=branch_id, specs=DEFAULT_NUMBERING_SPECS,
            )
        response = self.request_repair("numbering-repair-healthy")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DocumentNumberSeries.objects.filter(entity=self.entity).count(), 2 * len(DEFAULT_NUMBERING_SPECS))

    def test_execution_does_not_expand_beyond_approved_missing_snapshot(self):
        existing = NumberingSeedService.seed_document(
            entity_id=self.entity.id, entityfinid_id=self.year.id, subentity_id=None,
            module=DEFAULT_NUMBERING_SPECS[0].module, doc_key=DEFAULT_NUMBERING_SPECS[0].doc_key,
            name=DEFAULT_NUMBERING_SPECS[0].name, default_code=DEFAULT_NUMBERING_SPECS[0].default_code,
        )
        requested = self.request_repair("numbering-repair-snapshot")
        operation_id = requested.data["operation"]["id"]
        self.auth(self.checker)
        self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Approved the enumerated missing series only",
        }, format="json")
        DocumentNumberSeries.objects.filter(pk=existing["series_id"]).delete()

        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["operation"]["result"]["series_created"], 2 * len(DEFAULT_NUMBERING_SPECS) - 1)
        self.assertFalse(response.data["operation"]["result"]["after"]["healthy"])
        self.assertEqual(response.data["operation"]["result"]["after"]["missing_series_count"], 1)
