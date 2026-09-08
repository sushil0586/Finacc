from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, EntityGstRegistration, SubEntity
from platform_ops.models import PlatformAuditEvent, PlatformOperationRequest, PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount, CustomerSubscription, SubscriptionPlan, UserEntityAccess


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=False)
class PlatformDiscoveryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(
            username="discovery.operator",
            email="discovery.operator@example.com",
            password="StrongPass123!",
        )
        cls.owner = User.objects.create_user(
            username="customer.owner",
            email="owner.sensitive@example.com",
            password="StrongPass123!",
            first_name="Customer",
            last_name="Owner",
        )
        cls.plan = SubscriptionPlan.objects.create(
            name="Platform Discovery Plan",
            code="platform-discovery-plan",
            tier=SubscriptionPlan.PlanTier.BUSINESS,
            price_amount="4999.00",
        )
        cls.account = CustomerAccount.objects.create(
            name="Acme Operations",
            legal_name="Acme Operations Private Limited",
            trade_name="Acme",
            slug="acme-platform-discovery",
            status=CustomerAccount.Status.ACTIVE,
            owner=cls.owner,
            primary_contact_email="finance.sensitive@acme.example",
            primary_contact_phone="9876543210",
            billing_email="billing.sensitive@acme.example",
        )
        CustomerSubscription.objects.create(
            customer_account=cls.account,
            plan=cls.plan,
            status=CustomerSubscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        UserEntityAccess.objects.create(
            user=cls.owner,
            customer_account=cls.account,
            role=UserEntityAccess.Role.OWNER,
            granted_by=cls.owner,
        )
        cls.entity = Entity.objects.create(
            entityname="Acme Karnataka",
            legalname="Acme Operations Private Limited",
            entity_code="ACME-KA",
            customer_account=cls.account,
            createdby=cls.owner,
            gst_registration_status=Entity.GstStatus.REGISTERED,
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
            desc="FY 2026-27",
            year_code="FY2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now() + timedelta(days=364),
            createdby=cls.owner,
        )
        EntityGstRegistration.objects.create(
            entity=cls.entity,
            gstin="29ABCDE1234F1Z5",
            gst_status=Entity.GstStatus.REGISTERED,
            is_primary=True,
            createdby=cls.owner,
        )

        cls.customer_view = PlatformPermission.objects.get(code="platform.customer.view")
        cls.entity_view = PlatformPermission.objects.get(code="platform.entity.view")
        cls.sensitive_view = PlatformPermission.objects.get(code="platform.customer.sensitive.view")
        cls.role = PlatformRole.objects.create(code="discovery-test-role", name="Discovery Test Role")
        cls.role.permissions.add(cls.customer_view, cls.entity_view)
        PlatformUserRole.objects.create(
            user=cls.operator,
            role=cls.role,
            granted_by=cls.operator,
            reason="Discovery API tests",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.operator)

    def test_dashboard_returns_global_read_only_counts(self):
        response = self.client.get("/api/platform/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mode"], "read_only")
        self.assertGreaterEqual(response.data["customers"]["total"], 1)
        self.assertGreaterEqual(response.data["entities"]["active"], 1)
        self.assertGreaterEqual(response.data["memberships"]["active"], 1)

    def test_operator_directory_requires_security_permission_and_reports_effective_assignment(self):
        denied = self.client.get("/api/platform/operators/")
        self.assertEqual(denied.status_code, 403)

        self.role.permissions.add(PlatformPermission.objects.get(code="platform.security.manage"))
        response = self.client.get("/api/platform/operators/", {"q": self.operator.email, "state": "effective"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["meta"]["count"], 1)
        self.assertEqual(response.data["results"][0]["state"], "effective")
        self.assertEqual(response.data["results"][0]["user"]["email"], self.operator.email)

    def test_audit_explorer_filters_outcomes_and_exposes_correlation_trace(self):
        self.role.permissions.add(PlatformPermission.objects.get(code="platform.audit.view"))
        event = PlatformAuditEvent.objects.create(
            actor=self.operator,
            event_type="platform.test.failed",
            outcome=PlatformAuditEvent.Outcome.FAILED,
            permission_code="platform.entity.update",
            entity_id=self.entity.id,
            details={"code": "test_failure"},
        )

        response = self.client.get("/api/platform/audit-events/", {"q": str(event.correlation_id), "outcome": "failed"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["meta"]["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(event.id))
        self.assertEqual(response.data["results"][0]["details"], {"code": "test_failure"})

    def test_dashboard_excludes_expired_memberships(self):
        active_before = self.client.get("/api/platform/dashboard/").data["memberships"]["active"]
        UserEntityAccess.objects.create(
            user=self.operator,
            customer_account=self.account,
            role=UserEntityAccess.Role.VIEWER,
            granted_by=self.owner,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get("/api/platform/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["memberships"]["active"], active_before)

    def test_configuration_health_aggregates_findings_and_affected_entities(self):
        incomplete = Entity.objects.create(
            entityname="Health Attention Entity",
            entity_code="HEALTH-ATTN",
            customer_account=self.account,
            createdby=self.owner,
            gst_registration_status=Entity.GstStatus.UNREGISTERED,
        )

        response = self.client.get("/api/platform/configuration-health/")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["summary"]["attention_entities"], 1)
        self.assertGreaterEqual(response.data["summary"]["severity"]["high"], 2)
        codes = {row["code"] for row in response.data["issues"]}
        self.assertIn("branch_missing", codes)
        self.assertIn("financial_year_missing", codes)
        affected = {row["id"]: row for row in response.data["entities"]}
        self.assertIn(incomplete.id, affected)
        self.assertFalse(affected[incomplete.id]["repair_assessment_available"])

    def test_dashboard_reports_actionable_operation_counts(self):
        common = {
            "requested_by": self.operator,
            "reason": "Dashboard operation requiring operator attention",
            "ticket_reference": "OPS-DASHBOARD-1",
            "payload_hash": "d" * 64,
            "request_snapshot": {},
        }
        PlatformOperationRequest.objects.create(
            **common,
            operation_type=PlatformOperationRequest.OperationType.CUSTOMER_STATUS_UPDATE,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            idempotency_key="dashboard-pending",
        )
        PlatformOperationRequest.objects.create(
            **common,
            operation_type=PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=PlatformOperationRequest.Status.FAILED,
            failure_code="provisioning_failed",
            idempotency_key="dashboard-failed",
        )
        response = self.client.get("/api/platform/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["operations"]["pending_approval"], 1)
        self.assertGreaterEqual(response.data["operations"]["failed_onboarding"], 1)
        self.assertIn("approved_expiring_soon", response.data["operations"])
        self.assertIn("expired_approval", response.data["operations"])

    def test_customer_list_is_paginated_searchable_and_masked(self):
        response = self.client.get("/api/platform/customers/", {"q": "Acme", "page_size": 10})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["meta"]["count"], 1)
        self.assertEqual(response.data["meta"]["page"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["name"], "Acme Operations")
        self.assertEqual(row["entity_count"], 1)
        self.assertEqual(row["member_count"], 1)
        self.assertEqual(row["health"]["status"], "healthy")
        self.assertNotEqual(row["primary_contact_email"], "finance.sensitive@acme.example")
        self.assertTrue(row["primary_contact_phone"].endswith("3210"))

    def test_customer_detail_composes_entities_memberships_and_subscription(self):
        response = self.client.get(f"/api/platform/customers/{self.account.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subscription"]["plan"]["code"], "platform-discovery-plan")
        self.assertEqual(response.data["entities"][0]["id"], self.entity.id)
        self.assertEqual(response.data["memberships"][0]["role"], UserEntityAccess.Role.OWNER)
        self.assertNotEqual(response.data["memberships"][0]["email"], self.owner.email)

    def test_entity_list_supports_exact_gstin_search_without_revealing_gstin(self):
        response = self.client.get("/api/platform/entities/", {"q": "29ABCDE1234F1Z5"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["meta"]["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["id"], self.entity.id)
        self.assertEqual(row["health"]["status"], "healthy")
        self.assertNotEqual(row["primary_gstin"], "29ABCDE1234F1Z5")

    def test_entity_detail_returns_branches_and_financial_years(self):
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["branches"][0]["code"], "HO")
        self.assertEqual(response.data["financial_years"][0]["year_code"], "FY2026-27")

    def test_sensitive_permission_reveals_contacts_and_gstin(self):
        self.role.permissions.add(self.sensitive_view)

        customer = self.client.get(f"/api/platform/customers/{self.account.id}/")
        entity = self.client.get(f"/api/platform/entities/{self.entity.id}/")

        self.assertEqual(customer.data["primary_contact_email"], "finance.sensitive@acme.example")
        self.assertEqual(customer.data["memberships"][0]["email"], self.owner.email)
        self.assertEqual(entity.data["primary_gstin"], "29ABCDE1234F1Z5")

    def test_missing_resource_permission_is_denied_and_audited(self):
        self.role.permissions.remove(self.entity_view)

        response = self.client.get("/api/platform/entities/")

        self.assertEqual(response.status_code, 403)

    def test_entity_health_identifies_incomplete_non_gst_setup_without_false_gst_issue(self):
        incomplete = Entity.objects.create(
            entityname="Non GST Incomplete",
            entity_code="NON-GST-INCOMPLETE",
            customer_account=self.account,
            createdby=self.owner,
            gst_registration_status=Entity.GstStatus.UNREGISTERED,
        )

        response = self.client.get(f"/api/platform/entities/{incomplete.id}/")

        codes = {row["code"] for row in response.data["health"]["findings"]}
        self.assertIn("branch_missing", codes)
        self.assertIn("financial_year_missing", codes)
        self.assertNotIn("gst_registration_missing", codes)
