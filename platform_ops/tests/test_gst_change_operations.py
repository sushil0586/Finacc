import json

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityAddress, EntityGstRegistration
from geography.models import Country, State
from platform_ops.models import PlatformOperationRequest, PlatformPermission, PlatformRole, PlatformUserRole
from sales.models.mastergst_models import MasterGSTEnvironment, MasterGSTServiceScope, SalesMasterGSTCredential
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformGstChangeOperationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="gst-maker", email="gst-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="gst-checker", email="gst-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="gst-executor", email="gst-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="gst-owner", email="gst-owner@example.com", password="Pass123!")
        maker_role = PlatformRole.objects.create(code="gst-maker-role", name="GST Maker")
        maker_role.permissions.add(PlatformPermission.objects.get(code="platform.entity.update"))
        checker_role = PlatformRole.objects.create(code="gst-checker-role", name="GST Checker")
        checker_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.approve"))
        executor_role = PlatformRole.objects.create(code="gst-executor-role", name="GST Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        for user, role in ((cls.maker, maker_role), (cls.checker, checker_role), (cls.executor, executor_role)):
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="GST operation tests")

        cls.country = Country.objects.create(countryname="India GST Test", countrycode="IG")
        cls.state = State.objects.create(statename="Karnataka GST Test", statecode="29", country=cls.country)
        cls.customer = CustomerAccount.objects.create(name="GST Customer", slug="gst-customer", owner=cls.owner)

    def setUp(self):
        self.client = APIClient()
        self.entity = Entity.objects.create(
            entityname="GST Test Entity",
            entity_code=f"GST-{Entity.objects.count() + 1}",
            customer_account=self.customer,
            createdby=self.owner,
            gst_registration_status=Entity.GstStatus.UNREGISTERED,
        )
        EntityAddress.objects.create(
            entity=self.entity,
            address_type=EntityAddress.AddressType.PRINCIPAL,
            line1="1 GST Road",
            country=self.country,
            state=self.state,
            is_primary=True,
            createdby=self.owner,
        )

    def request_change(self, status="registered", gstin="29ABCDE1234F1Z5", key="gst-change-1"):
        self.client.force_authenticate(self.maker)
        self.entity.refresh_from_db()
        return self.client.post(
            f"/api/platform/entities/{self.entity.id}/gst-change-requests/",
            {
                "idempotency_key": key,
                "reason": "Correct GST registration after compliance review",
                "ticket_reference": "GST-2001",
                "expected_target_version": self.entity.updated_at.isoformat(),
                "gst_registration_status": status,
                "gstin": gstin,
                "effective_from": "2026-04-01",
            },
            format="json",
        )

    def approve_execute(self, operation_id):
        self.client.force_authenticate(self.checker)
        approval = self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": "approved", "comment": "GST evidence reviewed against registration"},
            format="json",
        )
        self.client.force_authenticate(self.executor)
        execution = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        return approval, execution

    def make_registered(self, gstin="29ABCDE1234F1Z5"):
        self.entity.gst_registration_status = Entity.GstStatus.REGISTERED
        self.entity.save(update_fields=["gst_registration_status", "updated_at"])
        return EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin=gstin,
            gst_status=Entity.GstStatus.REGISTERED,
            state=self.state,
            is_primary=True,
            createdby=self.owner,
        )

    def test_register_entity_requires_approval_and_creates_primary_registration(self):
        requested = self.request_change()

        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["status"], "pending_approval")
        approval, execution = self.approve_execute(requested.data["operation"]["id"])
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(execution.status_code, 200)
        self.entity.refresh_from_db()
        self.assertEqual(self.entity.gst_registration_status, Entity.GstStatus.REGISTERED)
        self.assertTrue(self.entity.gst_registrations.filter(gstin="29ABCDE1234F1Z5", is_primary=True, isactive=True).exists())

    def test_state_mismatch_and_duplicate_gstin_are_rejected_before_request(self):
        mismatch = self.request_change(gstin="27ABCDE1234F1Z5", key="state-mismatch")
        other = Entity.objects.create(entityname="Other GST Entity", entity_code="GST-OTHER", createdby=self.owner)
        EntityGstRegistration.objects.create(
            entity=other, gstin="29ABCDE1234F1Z5", is_primary=True, createdby=self.owner,
        )
        duplicate = self.request_change(key="duplicate-gstin")

        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("gstin", mismatch.data)
        self.assertIn("gstin", duplicate.data)

    def test_unregistration_preserves_history_and_disables_credentials(self):
        registration = self.make_registered()
        credential = SalesMasterGSTCredential.objects.create(
            entity=self.entity,
            environment=MasterGSTEnvironment.SANDBOX,
            service_scope=MasterGSTServiceScope.EINVOICE,
            gstin=registration.gstin,
            client_id="client-id",
            client_secret="client-secret",
            email="gst@example.com",
            gst_username="gst-user",
            gst_password="gst-password",
        )
        requested = self.request_change(status="unregistered", gstin="", key="unregister-gst")
        operation = PlatformOperationRequest.objects.get(pk=requested.data["operation"]["id"])

        self.assertNotIn("client-secret", json.dumps(operation.request_snapshot))
        self.assertNotIn("gst-password", json.dumps(operation.request_snapshot))
        _, execution = self.approve_execute(str(operation.id))
        self.assertEqual(execution.status_code, 200)
        registration.refresh_from_db()
        credential.refresh_from_db()
        self.assertFalse(registration.isactive)
        self.assertIsNotNone(registration.gst_cancelled_from)
        self.assertFalse(credential.is_active)

    def test_gstin_replacement_updates_existing_registration_and_credentials(self):
        registration = self.make_registered()
        credential = SalesMasterGSTCredential.objects.create(
            entity=self.entity,
            environment=MasterGSTEnvironment.SANDBOX,
            service_scope=MasterGSTServiceScope.EINVOICE,
            gstin=registration.gstin,
            client_id="client-id",
            client_secret="client-secret",
            email="gst@example.com",
            gst_username="gst-user",
            gst_password="gst-password",
        )
        requested = self.request_change(gstin="29ABCDE1234F2Z5", key="replace-gstin")

        _, execution = self.approve_execute(requested.data["operation"]["id"])

        self.assertEqual(execution.status_code, 200)
        registration.refresh_from_db()
        credential.refresh_from_db()
        self.assertEqual(registration.gstin, "29ABCDE1234F2Z5")
        self.assertEqual(credential.gstin, "29ABCDE1234F2Z5")
