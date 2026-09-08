from datetime import timedelta
import re
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import AuthOTP, User
from entity.models import Entity, EntityGstRegistration, SubEntity
from platform_ops.models import (
    PlatformAuditEvent,
    PlatformOperationRequest,
    PlatformPermission,
    PlatformProvisioningJob,
    PlatformRole,
    PlatformUserRole,
)
from subscriptions.models import CustomerAccount, PlanLimit, SubscriptionPlan
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=False)
class PlatformOnboardingValidationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(
            username="onboarding.operator",
            email="onboarding.operator@example.com",
            password="StrongPass123!",
        )
        cls.plan = SubscriptionPlan.objects.create(
            name="Platform Onboarding Plan",
            code="platform-onboarding-plan",
            tier=SubscriptionPlan.PlanTier.BUSINESS,
            price_amount="4999.00",
        )
        cls.role = PlatformRole.objects.create(code="onboarding-validator", name="Onboarding Validator")
        cls.role.permissions.add(
            PlatformPermission.objects.get(code="platform.customer.create"),
            PlatformPermission.objects.get(code="platform.entity.onboard"),
            PlatformPermission.objects.get(code="platform.operation.view"),
            PlatformPermission.objects.get(code="platform.operation.execute"),
            PlatformPermission.objects.get(code="platform.repair.execute"),
        )
        PlatformUserRole.objects.create(
            user=cls.operator,
            role=cls.role,
            granted_by=cls.operator,
            reason="Onboarding validation tests",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.operator)

    def payload(self):
        start = timezone.now().replace(month=4, day=1, hour=0, minute=0, second=0, microsecond=0)
        return {
            "owner": {
                "email": "new.owner@example.com",
                "first_name": "New",
                "last_name": "Owner",
            },
            "customer": {
                "name": "New Customer",
                "legal_name": "New Customer Private Limited",
                "primary_contact_email": "finance@new-customer.example",
                "primary_contact_phone": "9876500000",
                "external_customer_id": "EXT-NEW-001",
                "country": "IN",
                "timezone": "Asia/Kolkata",
            },
            "plan_code": self.plan.code,
            "intent": "standard",
            "onboarding": {
                "entity": {
                    "entityname": "New Customer Karnataka",
                    "legalname": "New Customer Private Limited",
                    "entity_code": "NEW-KA",
                    "gst_registration_status": Entity.GstStatus.UNREGISTERED,
                    "address": "1 Platform Road",
                    "country": None,
                    "state": None,
                    "district": None,
                    "city": None,
                    "phoneoffice": "9876500000",
                },
                "financial_years": [{
                    "finstartyear": start.isoformat(),
                    "finendyear": (start + timedelta(days=364)).isoformat(),
                    "period_status": "open",
                    "isactive": True,
                }],
                "seed_options": {"seed_default_subentity": True},
            },
        }

    def test_clean_validation_returns_masked_preview_without_writes(self):
        counts_before = (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count())

        response = self.client.post("/api/platform/onboarding/validate/", self.payload(), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["blocking_errors"], [])
        self.assertNotEqual(response.data["preview"]["owner"]["email"], "new.owner@example.com")
        self.assertEqual(response.data["preview"]["counts"]["branches"], 1)
        self.assertEqual(
            (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count()),
            counts_before,
        )
        self.assertTrue(PlatformAuditEvent.objects.filter(event_type="platform.onboarding.validation").exists())

    def test_preview_alias_uses_same_contract(self):
        response = self.client.post("/api/platform/onboarding/preview/", self.payload(), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])
        self.assertIn("subscription", response.data["preview"]["provisioning_stages"])

    def test_duplicate_owner_customer_entity_and_gstin_are_classified(self):
        payload = self.payload()
        owner = User.objects.create_user(
            username="new.owner@example.com",
            email="new.owner@example.com",
            password="StrongPass123!",
        )
        account = CustomerAccount.objects.create(
            name="Existing Customer",
            legal_name=payload["customer"]["legal_name"],
            slug="existing-platform-customer",
            owner=owner,
            primary_contact_phone=payload["customer"]["primary_contact_phone"],
            external_customer_id=payload["customer"]["external_customer_id"],
        )
        entity = Entity.objects.create(
            entityname=payload["onboarding"]["entity"]["entityname"],
            legalname=payload["onboarding"]["entity"]["legalname"],
            entity_code=payload["onboarding"]["entity"]["entity_code"],
            customer_account=account,
            createdby=owner,
        )
        payload["onboarding"]["entity"].update({
            "gst_registration_status": Entity.GstStatus.REGISTERED,
            "gstno": "29ABCDE1234F1Z5",
        })
        EntityGstRegistration.objects.create(
            entity=entity,
            gstin="29ABCDE1234F1Z5",
            is_primary=True,
            createdby=owner,
        )

        response = self.client.post("/api/platform/onboarding/validate/", payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["valid"])
        blocking_codes = {row["code"] for row in response.data["blocking_errors"]}
        warning_codes = {row["code"] for row in response.data["warnings"]}
        self.assertTrue({
            "owner_email_exists", "external_customer_id_exists", "customer_legal_name_exists",
            "entity_code_exists", "gstin_exists",
        }.issubset(blocking_codes))
        self.assertTrue({"customer_phone_exists", "entity_legal_name_exists"}.issubset(warning_codes))
        gst_finding = next(row for row in response.data["blocking_errors"] if row["code"] == "gstin_exists")
        self.assertNotEqual(gst_finding["matched_display"], "29ABCDE1234F1Z5")

    def test_invalid_nested_payload_returns_structured_error_and_failed_audit(self):
        payload = self.payload()
        payload["onboarding"]["financial_years"] = []

        response = self.client.post("/api/platform/onboarding/validate/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["valid"])
        self.assertEqual(response.data["code"], "invalid_onboarding_payload")
        self.assertIn("financial_years", response.data["errors"]["onboarding"])
        self.assertTrue(PlatformAuditEvent.objects.filter(
            event_type="platform.onboarding.validation",
            outcome=PlatformAuditEvent.Outcome.FAILED,
        ).exists())

    def test_both_permissions_are_required(self):
        self.role.permissions.remove(PlatformPermission.objects.get(code="platform.entity.onboard"))

        response = self.client.post("/api/platform/onboarding/validate/", self.payload(), format="json")

        self.assertEqual(response.status_code, 403)

    def test_inactive_plan_is_rejected(self):
        self.plan.is_active = False
        self.plan.save(update_fields=["is_active"])

        response = self.client.post("/api/platform/onboarding/validate/", self.payload(), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("plan_code", response.data["errors"])

    def request_payload(self):
        return {
            "idempotency_key": "onboard-new-customer-001",
            "reason": "Onboard customer from approved sales handoff",
            "ticket_reference": "OPS-1001",
            "payload": self.payload(),
        }

    def test_request_creation_is_blocked_when_platform_mutations_are_disabled(self):
        response = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(PlatformOperationRequest.objects.count(), 0)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_request_creates_durable_operation_and_pending_job(self):
        response = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["replayed"])
        operation = PlatformOperationRequest.objects.get()
        job = PlatformProvisioningJob.objects.get(operation=operation)
        self.assertEqual(operation.status, PlatformOperationRequest.Status.VALIDATED)
        self.assertEqual(job.status, PlatformProvisioningJob.Status.PENDING)
        self.assertEqual(len(job.stage_results), 9)
        self.assertNotIn("password", str(operation.request_snapshot).lower())

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_identical_idempotent_request_replays_original_operation(self):
        first = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")
        second = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["replayed"])
        self.assertEqual(first.data["operation"]["id"], second.data["operation"]["id"])
        self.assertEqual(PlatformOperationRequest.objects.count(), 1)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_reused_idempotency_key_with_changed_payload_is_rejected(self):
        original = self.request_payload()
        self.client.post("/api/platform/onboarding/requests/", original, format="json")
        changed = self.request_payload()
        changed["payload"]["customer"]["name"] = "Different Customer"

        response = self.client.post("/api/platform/onboarding/requests/", changed, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("idempotency_key", response.data)
        self.assertEqual(PlatformOperationRequest.objects.count(), 1)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_blocking_duplicate_does_not_create_operation(self):
        payload = self.request_payload()
        User.objects.create_user(
            username="new.owner@example.com",
            email="new.owner@example.com",
            password="StrongPass123!",
        )

        response = self.client.post("/api/platform/onboarding/requests/", payload, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "onboarding_blocked")
        self.assertEqual(PlatformOperationRequest.objects.count(), 0)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_operation_list_and_detail_return_job_progress_without_request_snapshot(self):
        created = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")
        operation_id = created.data["operation"]["id"]

        listing = self.client.get("/api/platform/operations/")
        detail = self.client.get(f"/api/platform/operations/{operation_id}/")

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["meta"]["count"], 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["job"]["status"], PlatformProvisioningJob.Status.PENDING)
        self.assertNotIn("request_snapshot", detail.data)

    def test_compliance_credentials_are_rejected_from_operation_snapshot(self):
        payload = self.payload()
        payload["onboarding"]["compliance_credentials"] = [{
            "environment": 1,
            "client_id": "client-id",
            "client_secret": "must-not-persist",
            "email": "gst@example.com",
            "gst_username": "gst-user",
            "gst_password": "must-not-persist",
        }]

        response = self.client.post("/api/platform/onboarding/validate/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("compliance_credentials", str(response.data))

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_execution_provisions_once_and_subsequent_call_replays(self):
        created = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")
        operation_id = created.data["operation"]["id"]
        counts_before = (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count())

        executed = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        replayed = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(executed.status_code, 200, executed.data)
        self.assertEqual(executed.data["operation"]["status"], PlatformOperationRequest.Status.SUCCEEDED)
        self.assertFalse(executed.data["replayed"])
        readiness = executed.data["operation"]["result"]["readiness"]
        self.assertEqual(readiness["status"], "ready", readiness)
        self.assertEqual(readiness["ready_count"], readiness["total_count"])
        self.assertEqual(
            {row["code"] for row in readiness["checks"]},
            {"owner", "branch", "financial_year", "financial", "posting", "numbering", "rbac", "subscription", "catalog", "assets", "trade", "choices"},
        )
        self.assertEqual(replayed.status_code, 200)
        self.assertTrue(replayed.data["replayed"])
        self.assertEqual(
            (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count()),
            tuple(value + 1 for value in counts_before),
        )
        operation = PlatformOperationRequest.objects.get(pk=operation_id)
        self.assertIsNotNone(operation.customer_account_id)
        self.assertIsNotNone(operation.entity_id)
        self.assertEqual(operation.provisioning_job.attempt_count, 1)
        self.assertEqual(len(operation.provisioning_job.completed_stages), 9)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_failed_entity_stage_rolls_back_tenant_data_and_records_retry_state(self):
        created = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")
        operation_id = created.data["operation"]["id"]
        counts_before = (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count())

        with patch("platform_ops.operations.EntityOnboardingService.create_entity", side_effect=RuntimeError("seed failure")):
            response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(
            (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count()),
            counts_before,
        )
        operation = PlatformOperationRequest.objects.get(pk=operation_id)
        self.assertEqual(operation.status, PlatformOperationRequest.Status.FAILED)
        self.assertEqual(operation.provisioning_job.status, PlatformProvisioningJob.Status.FAILED)
        self.assertEqual(operation.provisioning_job.current_stage, "entity")
        self.assertEqual(operation.provisioning_job.attempt_count, 1)

        retried = self.client.post(f"/api/platform/operations/{operation_id}/retry/", {}, format="json")

        self.assertEqual(retried.status_code, 200, retried.data)
        operation.refresh_from_db()
        self.assertEqual(operation.status, PlatformOperationRequest.Status.SUCCEEDED)
        self.assertEqual(operation.provisioning_job.attempt_count, 2)
        self.assertEqual(
            (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count()),
            tuple(value + 1 for value in counts_before),
        )

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_execution_requires_execute_permission(self):
        created = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")
        operation_id = created.data["operation"]["id"]
        self.role.permissions.remove(PlatformPermission.objects.get(code="platform.operation.execute"))

        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(PlatformOperationRequest.objects.get(pk=operation_id).status, PlatformOperationRequest.Status.VALIDATED)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_registered_gst_multibranch_execution_and_post_commit_verification(self):
        request_payload = self.request_payload()
        entity_payload = request_payload["payload"]["onboarding"]["entity"]
        entity_payload.update({
            "gst_registration_status": Entity.GstStatus.REGISTERED,
            "gstno": "29ABCDE1234F1Z5",
        })
        request_payload["payload"]["onboarding"]["subentities"] = [
            {
                "subentityname": "Head Office",
                "subentity_code": "HO",
                "branch_type": SubEntity.BranchType.HEAD_OFFICE,
                "is_head_office": True,
            },
            {
                "subentityname": "Warehouse",
                "subentity_code": "WH",
                "branch_type": SubEntity.BranchType.WAREHOUSE,
                "can_stock": True,
            },
        ]
        created = self.client.post("/api/platform/onboarding/requests/", request_payload, format="json")
        operation_id = created.data["operation"]["id"]

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        operation = PlatformOperationRequest.objects.get(pk=operation_id)
        entity = Entity.objects.get(pk=operation.entity_id)
        self.assertEqual(entity.gst_registrations.get(isactive=True).gstin, "29ABCDE1234F1Z5")
        self.assertEqual(entity.subentity.filter(isactive=True).count(), 2)
        self.assertTrue(entity.subentity.get(subentity_code="HO").is_head_office)
        self.assertTrue(AuthOTP.objects.filter(
            user_id=operation.result_snapshot["owner_id"],
            purpose="password_reset",
        ).exists())
        otp_match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        self.assertIsNotNone(otp_match)
        anonymous = APIClient()
        reset = anonymous.post("/api/auth/resetpassword", {
            "email": request_payload["payload"]["owner"]["email"],
            "otp": otp_match.group(1),
            "new_password": "OwnerChosenPass@123",
        }, format="json")
        login = anonymous.post("/api/auth/login", {
            "email": request_payload["payload"]["owner"]["email"],
            "password": "OwnerChosenPass@123",
        }, format="json")
        self.assertEqual(reset.status_code, 200, reset.data)
        self.assertEqual(login.status_code, 200, login.data)
        owner = User.objects.get(pk=operation.result_snapshot["owner_id"])
        self.assertTrue(owner.email_verified)

    @override_settings(PLATFORM_OPS_MUTATIONS_ENABLED=True)
    def test_plan_entity_limit_failure_rolls_back_entire_onboarding(self):
        SubscriptionService.ensure_plan_limit_catalog(plan=self.plan)
        limit = PlanLimit.objects.get(plan=self.plan, key=SubscriptionLimitCodes.MAX_ENTITIES)
        limit.is_unlimited = False
        limit.int_value = 0
        limit.save(update_fields=["is_unlimited", "int_value", "updated_at"])
        created = self.client.post("/api/platform/onboarding/requests/", self.request_payload(), format="json")
        operation_id = created.data["operation"]["id"]
        counts_before = (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count())

        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(
            (User.objects.count(), CustomerAccount.objects.count(), Entity.objects.count()),
            counts_before,
        )
        operation = PlatformOperationRequest.objects.get(pk=operation_id)
        self.assertEqual(operation.status, PlatformOperationRequest.Status.FAILED)
        self.assertEqual(operation.provisioning_job.current_stage, "entity")
