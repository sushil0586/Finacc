from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from platform_ops.models import (
    PlatformOperationApproval,
    PlatformPermission,
    PlatformRole,
    PlatformUserRole,
)
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformApprovalWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="maker", email="maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="checker", email="checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="executor", email="executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="owner", email="owner@example.com", password="Pass123!")

        maker_role = PlatformRole.objects.create(code="status-maker", name="Status Maker")
        maker_role.permissions.add(
            PlatformPermission.objects.get(code="platform.customer.update"),
            PlatformPermission.objects.get(code="platform.operation.approve"),
        )
        checker_role = PlatformRole.objects.create(code="status-checker", name="Status Checker")
        checker_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.approve"))
        executor_role = PlatformRole.objects.create(code="status-executor", name="Status Executor")
        executor_role.permissions.add(PlatformPermission.objects.get(code="platform.operation.execute"))
        for user, role in ((cls.maker, maker_role), (cls.checker, checker_role), (cls.executor, executor_role)):
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="Approval tests")

        cls.customer = CustomerAccount.objects.create(
            name="Approval Customer",
            slug="approval-customer",
            owner=cls.owner,
            status=CustomerAccount.Status.ACTIVE,
        )

    def setUp(self):
        self.client = APIClient()
        self.customer.refresh_from_db()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def request_status(self, desired_status="suspended", key="status-request-1"):
        self.authenticate(self.maker)
        return self.client.post(
            f"/api/platform/customers/{self.customer.id}/status-change-requests/",
            {
                "idempotency_key": key,
                "reason": f"Change customer status to {desired_status} after operational review",
                "ticket_reference": "OPS-2001",
                "expected_target_version": self.customer.updated_at.isoformat(),
                "desired_status": desired_status,
            },
            format="json",
        )

    def decide(self, operation_id, decision="approved", user=None):
        self.authenticate(user or self.checker)
        return self.client.post(
            f"/api/platform/operations/{operation_id}/decision/",
            {"decision": decision, "comment": "Reviewed against the linked operations ticket"},
            format="json",
        )

    def execute(self, operation_id):
        self.authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_suspend_requires_independent_approval_and_executes_once(self):
        requested = self.request_status()
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["operation"]["status"], "pending_approval")
        operation_id = requested.data["operation"]["id"]

        premature = self.execute(operation_id)
        self.assertEqual(premature.status_code, 400)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, CustomerAccount.Status.ACTIVE)

        approved = self.decide(operation_id)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(approved.data["approval"]["decided_by"]["email"], self.checker.email)

        executed = self.execute(operation_id)
        replayed = self.execute(operation_id)
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.data["operation"]["status"], "succeeded")
        self.assertTrue(replayed.data["replayed"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, CustomerAccount.Status.SUSPENDED)

    def test_reactivation_round_trip(self):
        self.customer.status = CustomerAccount.Status.SUSPENDED
        self.customer.save(update_fields=["status", "updated_at"])

        requested = self.request_status(desired_status="active", key="reactivate-1")
        operation_id = requested.data["operation"]["id"]
        self.decide(operation_id)
        response = self.execute(operation_id)

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, CustomerAccount.Status.ACTIVE)

    def test_requester_cannot_approve_own_request_even_with_permission(self):
        operation_id = self.request_status().data["operation"]["id"]

        response = self.decide(operation_id, user=self.maker)

        self.assertEqual(response.status_code, 400)
        self.assertIn("approver", response.data)

    def test_rejection_is_terminal_and_cannot_execute(self):
        operation_id = self.request_status().data["operation"]["id"]

        rejected = self.decide(operation_id, decision="rejected")
        execution = self.execute(operation_id)

        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["status"], "rejected")
        self.assertEqual(execution.status_code, 400)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, CustomerAccount.Status.ACTIVE)

    def test_target_change_before_review_invalidates_request(self):
        operation_id = self.request_status().data["operation"]["id"]
        CustomerAccount.objects.filter(pk=self.customer.id).update(
            status_notes="Changed concurrently",
            updated_at=timezone.now() + timedelta(seconds=1),
        )

        response = self.decide(operation_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["failure"]["code"], "stale_target")
        self.assertIsNone(response.data["approval"])

    def test_target_change_after_approval_invalidates_approval(self):
        operation_id = self.request_status().data["operation"]["id"]
        self.decide(operation_id)
        CustomerAccount.objects.filter(pk=self.customer.id).update(
            status_notes="Changed after approval",
            updated_at=timezone.now() + timedelta(seconds=1),
        )

        response = self.execute(operation_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, CustomerAccount.Status.ACTIVE)

    def test_approval_decision_is_immutable(self):
        operation_id = self.request_status().data["operation"]["id"]
        self.decide(operation_id)
        approval = PlatformOperationApproval.objects.get(operation_id=operation_id)
        approval.comment = "Attempt to rewrite decision"

        with self.assertRaises(ValidationError):
            approval.save()
        with self.assertRaises(ValidationError):
            approval.delete()
        with self.assertRaises(ValidationError):
            PlatformOperationApproval.objects.filter(pk=approval.pk).update(comment="Rewritten")

    def test_only_valid_active_suspended_transitions_are_accepted(self):
        same = self.request_status(desired_status="active", key="same-status")
        self.customer.status = CustomerAccount.Status.CLOSED
        self.customer.save(update_fields=["status", "updated_at"])
        closed = self.request_status(desired_status="active", key="closed-status")

        self.assertEqual(same.status_code, 400)
        self.assertEqual(closed.status_code, 400)
        self.assertIn("desired_status", closed.data)
