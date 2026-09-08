from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, SubEntity
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityChangeOperationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="entity-maker", email="entity-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="entity-checker", email="entity-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="entity-executor", email="entity-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="entity-owner", email="entity-owner@example.com", password="Pass123!")
        maker_role = PlatformRole.objects.create(code="entity-change-maker", name="Entity Change Maker")
        maker_role.permissions.add(PlatformPermission.objects.get(code="platform.entity.update"))
        checker_role = PlatformRole.objects.create(code="entity-change-checker", name="Entity Change Checker")
        checker_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.approve"))
        executor_role = PlatformRole.objects.create(code="entity-change-executor", name="Entity Change Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        for user, role in ((cls.maker, maker_role), (cls.checker, checker_role), (cls.executor, executor_role)):
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="Entity change tests")

        cls.customer = CustomerAccount.objects.create(name="Entity Change Customer", slug="entity-change", owner=cls.owner)
        cls.entity = Entity.objects.create(
            entityname="Entity Change Company",
            entity_code="CHANGE-ENTITY",
            customer_account=cls.customer,
            createdby=cls.owner,
        )
        SubEntity.objects.create(
            entity=cls.entity,
            subentityname="Head Office",
            subentity_code="HO",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )
        EntityFinancialYear.objects.create(
            entity=cls.entity,
            createdby=cls.owner,
            finstartyear=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            finendyear=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            year_code="FY2026-27",
            isactive=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def base(self, key):
        return {
            "idempotency_key": key,
            "reason": "Approved entity configuration request from operations",
            "ticket_reference": "OPS-ENTITY-1",
            "expected_target_version": self.entity.updated_at.isoformat(),
        }

    def execute(self, operation_id):
        self.auth(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def approve(self, operation_id):
        self.auth(self.checker)
        return self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": "approved", "comment": "Dates and posting scope reviewed"},
            format="json",
        )

    def test_add_branch_is_medium_risk_and_seeds_numbering_scopes(self):
        self.auth(self.maker)
        payload = {**self.base("add-branch-1"), "branch": {
            "subentityname": "Warehouse Bengaluru",
            "subentity_code": "WH-BLR",
            "branch_type": "warehouse",
            "sort_order": 20,
        }}
        requested = self.client.post(
            f"/api/platform/entities/{self.entity.id}/branch-change-requests/", payload, format="json",
        )

        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["risk"], "medium")
        self.assertEqual(requested.data["operation"]["status"], "validated")
        response = self.execute(requested.data["operation"]["id"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.entity.subentity.filter(subentity_code="WH-BLR", branch_type="warehouse").exists())

    def test_branch_rejects_duplicate_code_and_head_office(self):
        self.auth(self.maker)
        duplicate = {**self.base("duplicate-branch"), "branch": {
            "subentityname": "Duplicate", "subentity_code": "ho", "branch_type": "branch",
        }}
        head_office = {**self.base("head-office-branch"), "branch": {
            "subentityname": "Another HO", "subentity_code": "HO2", "branch_type": "head_office",
        }}

        duplicate_response = self.client.post(
            f"/api/platform/entities/{self.entity.id}/branch-change-requests/", duplicate, format="json",
        )
        head_office_response = self.client.post(
            f"/api/platform/entities/{self.entity.id}/branch-change-requests/", head_office, format="json",
        )
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertEqual(head_office_response.status_code, 400)

    def test_add_financial_year_requires_approval_then_executes(self):
        self.auth(self.maker)
        payload = {**self.base("add-fy-1"), "financial_year": {
            "finstartyear": "2027-04-01T00:00:00Z",
            "finendyear": "2028-03-31T00:00:00Z",
            "period_status": "open",
            "isactive": False,
        }}
        requested = self.client.post(
            f"/api/platform/entities/{self.entity.id}/financial-year-change-requests/", payload, format="json",
        )

        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["risk"], "high")
        operation_id = requested.data["operation"]["id"]
        self.assertEqual(self.execute(operation_id).status_code, 400)
        self.assertEqual(self.approve(operation_id).status_code, 200)
        response = self.execute(operation_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.entity.fy.filter(year_code="FY2027-28").exists())

    def test_financial_year_rejects_overlap(self):
        self.auth(self.maker)
        payload = {**self.base("overlap-fy"), "financial_year": {
            "finstartyear": "2027-01-01T00:00:00Z",
            "finendyear": "2027-12-31T00:00:00Z",
            "period_status": "open",
            "isactive": False,
        }}
        response = self.client.post(
            f"/api/platform/entities/{self.entity.id}/financial-year-change-requests/", payload, format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("financial_year", response.data)

    def test_financial_year_requires_an_ordered_date_range(self):
        self.auth(self.maker)
        payload = {**self.base("invalid-fy-range"), "financial_year": {
            "finstartyear": "2029-04-01T00:00:00Z",
            "finendyear": "2029-03-31T00:00:00Z",
            "period_status": "open",
            "isactive": False,
        }}

        response = self.client.post(
            f"/api/platform/entities/{self.entity.id}/financial-year-change-requests/", payload, format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("financial_year", response.data)

    def test_entity_change_after_approval_prevents_financial_year_creation(self):
        self.auth(self.maker)
        payload = {**self.base("stale-fy"), "financial_year": {
            "finstartyear": "2028-04-01T00:00:00Z",
            "finendyear": "2029-03-31T00:00:00Z",
            "period_status": "open",
            "isactive": False,
        }}
        requested = self.client.post(
            f"/api/platform/entities/{self.entity.id}/financial-year-change-requests/", payload, format="json",
        )
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now() + timedelta(seconds=1))

        response = self.execute(operation_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertFalse(self.entity.fy.filter(year_code="FY2028-29").exists())
