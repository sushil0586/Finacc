from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import PlatformOperationRequest, PlatformPermission, PlatformRole, PlatformUserRole
from subscriptions.models import CustomerAccount, UserEntityAccess


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformOwnershipTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="owner-maker", email="owner-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="owner-checker", email="owner-checker@example.com", password="Pass123!")
        cls.second_checker = User.objects.create_user(username="owner-checker-2", email="owner-checker-2@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="owner-executor", email="owner-executor@example.com", password="Pass123!")
        cls.old_owner = User.objects.create_user(username="old-owner", email="old-owner@example.com", password="Pass123!", email_verified=True)
        cls.new_owner = User.objects.create_user(username="new-owner", email="new-owner@example.com", password="Pass123!", email_verified=True)
        maker_role = PlatformRole.objects.create(code="ownership-maker", name="Ownership Maker")
        maker_role.permissions.add(
            PlatformPermission.objects.get(code="platform.security.manage"),
            PlatformPermission.objects.get(code="platform.operation.approve"),
        )
        checker_role = PlatformRole.objects.create(code="ownership-checker", name="Ownership Checker")
        checker_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.approve"))
        executor_role = PlatformRole.objects.create(code="ownership-executor", name="Ownership Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        for user, role in ((cls.maker, maker_role), (cls.checker, checker_role), (cls.second_checker, checker_role), (cls.executor, executor_role)):
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="Ownership tests")

    def setUp(self):
        self.client = APIClient()
        self.customer = CustomerAccount.objects.create(
            name="Ownership Customer", slug=f"ownership-{CustomerAccount.objects.count()}",
            owner=self.old_owner, status=CustomerAccount.Status.ACTIVE,
        )
        self.old_membership = UserEntityAccess.objects.create(
            customer_account=self.customer, user=self.old_owner, role=UserEntityAccess.Role.OWNER,
        )
        self.target = UserEntityAccess.objects.create(
            customer_account=self.customer, user=self.new_owner, role=UserEntityAccess.Role.ADMIN,
        )

    def request_transfer(self, *, key="ownership-1", customer_version=None, member_version=None):
        self.client.force_authenticate(self.maker)
        self.customer.refresh_from_db()
        self.target.refresh_from_db()
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/ownership-transfer-requests/",
            {
                "idempotency_key": key,
                "reason": "Transfer ownership after verified executive authorization",
                "ticket_reference": "SEC-7001",
                "expected_target_version": (customer_version or self.customer.updated_at).isoformat(),
                "target_membership_id": self.target.id,
                "expected_membership_version": (member_version or self.target.updated_at).isoformat(),
            }, format="json",
        )

    def approve(self, operation_id, user=None):
        self.client.force_authenticate(user or self.checker)
        return self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": "approved", "comment": "Executive authorization and target identity verified"}, format="json",
        )

    def execute(self, operation_id):
        self.client.force_authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_approved_transfer_atomically_replaces_owner_and_replays(self):
        requested = self.request_transfer()
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["risk"], "critical")
        operation_id = requested.data["operation"]["id"]
        self.assertEqual(self.execute(operation_id).status_code, 400)
        first = self.approve(operation_id)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["status"], PlatformOperationRequest.Status.PENDING_APPROVAL)
        self.assertEqual(first.data["approvals_required"], 2)
        self.assertEqual(len(first.data["approvals"]), 1)
        self.assertEqual(self.execute(operation_id).status_code, 400)
        duplicate = self.approve(operation_id)
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("approver", duplicate.data)
        second = self.approve(operation_id, self.second_checker)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], PlatformOperationRequest.Status.APPROVED)
        self.assertEqual(len(second.data["approvals"]), 2)
        executed = self.execute(operation_id)
        replay = self.execute(operation_id)
        self.assertEqual(executed.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.customer.refresh_from_db()
        self.old_membership.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.customer.owner, self.new_owner)
        self.assertEqual(self.target.role, UserEntityAccess.Role.OWNER)
        self.assertIsNone(self.target.expires_at)
        self.assertEqual(self.old_membership.role, UserEntityAccess.Role.ADMIN)
        self.assertEqual(UserEntityAccess.objects.filter(customer_account=self.customer, role="owner", is_active=True).count(), 1)

    def test_requester_cannot_approve_critical_transfer(self):
        operation_id = self.request_transfer().data["operation"]["id"]
        response = self.approve(operation_id, self.maker)
        self.assertEqual(response.status_code, 400)
        self.assertIn("approver", response.data)

    def test_rejection_after_first_approval_terminates_critical_transfer(self):
        operation_id = self.request_transfer(key="critical-rejection").data["operation"]["id"]
        self.assertEqual(self.approve(operation_id).data["status"], PlatformOperationRequest.Status.PENDING_APPROVAL)
        self.client.force_authenticate(self.second_checker)
        rejected = self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": "rejected", "comment": "Executive authorization could not be verified"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["status"], PlatformOperationRequest.Status.REJECTED)
        self.assertEqual(self.execute(operation_id).status_code, 400)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.owner, self.old_owner)

    def test_unverified_or_inactive_target_is_rejected(self):
        self.new_owner.email_verified = False
        self.new_owner.save(update_fields=["email_verified", "updated_at"])
        self.assertEqual(self.request_transfer(key="unverified").status_code, 400)
        self.new_owner.email_verified = True
        self.new_owner.save(update_fields=["email_verified", "updated_at"])
        self.target.is_active = False
        self.target.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self.request_transfer(key="inactive").status_code, 400)

    def test_customer_or_membership_change_invalidates_transfer(self):
        operation_id = self.request_transfer(key="stale-customer").data["operation"]["id"]
        self.approve(operation_id)
        self.approve(operation_id, self.second_checker)
        CustomerAccount.objects.filter(pk=self.customer.id).update(updated_at=timezone.now() + timedelta(seconds=1))
        self.assertEqual(self.execute(operation_id).data["operation"]["failure"]["code"], "stale_approval")

        self.customer.refresh_from_db()
        operation_id = self.request_transfer(key="stale-member").data["operation"]["id"]
        self.approve(operation_id)
        self.approve(operation_id, self.second_checker)
        UserEntityAccess.objects.filter(pk=self.target.id).update(updated_at=timezone.now() + timedelta(seconds=2))
        self.assertEqual(self.execute(operation_id).data["operation"]["failure"]["code"], "stale_membership")

    def test_request_replays_idempotently(self):
        first = self.request_transfer()
        replay = self.request_transfer()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["replayed"])
        self.assertEqual(PlatformOperationRequest.objects.filter(
            operation_type=PlatformOperationRequest.OperationType.TRANSFER_CUSTOMER_OWNERSHIP,
        ).count(), 1)
