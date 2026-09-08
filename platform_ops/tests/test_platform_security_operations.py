from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from Authentication.services import AuthTokenService
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformSecurityOperationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="security-maker", email="security-maker@example.com", password="Pass123!")
        cls.checker_one = User.objects.create_user(username="security-checker-1", email="security-checker-1@example.com", password="Pass123!")
        cls.checker_two = User.objects.create_user(username="security-checker-2", email="security-checker-2@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="security-executor", email="security-executor@example.com", password="Pass123!")
        cls.target = User.objects.create_user(username="security-target", email="security-target@example.com", password="Pass123!")

        assignments = (
            (cls.maker, "security-maker-role", ("platform.security.manage", "platform.operation.view")),
            (cls.checker_one, "security-checker-role-1", ("platform.operation.approve",)),
            (cls.checker_two, "security-checker-role-2", ("platform.operation.approve",)),
            (cls.executor, "security-executor-role", ("platform.operation.execute",)),
        )
        for user, code, permissions in assignments:
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.maker, reason="Security workflow tests")
        cls.granted_role = PlatformRole.objects.get(code="platform-viewer")

    def setUp(self):
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def request_role(self, action="grant", assignment=None, key="security-role-1"):
        self.authenticate(self.maker)
        payload = {
            "idempotency_key": key,
            "reason": "Approved platform access change for support coverage",
            "ticket_reference": "SEC-1001",
            "action": action,
        }
        if action == "grant":
            payload.update(user_id=self.target.id, role_code=self.granted_role.code)
        else:
            payload["assignment_id"] = assignment.id
        return self.client.post("/api/platform/operators/role-change-requests/", payload, format="json")

    def approve_twice(self, operation_id):
        responses = []
        for user in (self.checker_one, self.checker_two):
            self.authenticate(user)
            responses.append(self.client.post(
                f"/api/platform/operations/{operation_id}/decision/",
                {"decision": "approved", "comment": "Verified against security ticket"}, format="json",
            ))
        return responses

    def execute(self, operation_id):
        self.authenticate(self.executor)
        return self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")

    def test_role_grant_requires_two_approvals_and_execution_is_replay_safe(self):
        requested = self.request_role()
        self.assertEqual(requested.status_code, 201)
        operation_id = requested.data["operation"]["id"]

        first, second = self.approve_twice(operation_id)
        self.assertEqual(first.data["status"], "pending_approval")
        self.assertEqual(second.data["status"], "approved")
        executed = self.execute(operation_id)
        replayed = self.execute(operation_id)

        self.assertEqual(executed.status_code, 200)
        self.assertTrue(replayed.data["replayed"])
        self.assertTrue(PlatformUserRole.objects.filter(user=self.target, role=self.granted_role, is_active=True).exists())

    def test_role_revoke_is_atomic_and_cannot_be_requested_for_self(self):
        assignment = PlatformUserRole.objects.create(
            user=self.target, role=self.granted_role, granted_by=self.maker, reason="Temporary support access",
        )
        requested = self.request_role(action="revoke", assignment=assignment, key="security-revoke-1")
        operation_id = requested.data["operation"]["id"]
        self.approve_twice(operation_id)
        self.execute(operation_id)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(assignment.revoked_at)

        own_assignment = PlatformUserRole.objects.filter(user=self.maker, is_active=True).first()
        denied = self.request_role(action="revoke", assignment=own_assignment, key="security-self-revoke")
        self.assertEqual(denied.status_code, 400)

    def test_session_revocation_invalidates_sessions_and_bumps_token_version(self):
        session, _ = AuthTokenService.create_session(self.target)
        original_version = self.target.token_version
        self.authenticate(self.maker)
        requested = self.client.post("/api/platform/operators/session-revocation-requests/", {
            "idempotency_key": "security-sessions-1",
            "reason": "Terminate sessions after confirmed credential exposure",
            "ticket_reference": "SEC-1002",
            "user_id": self.target.id,
        }, format="json")
        operation_id = requested.data["operation"]["id"]
        self.approve_twice(operation_id)
        self.execute(operation_id)

        session.refresh_from_db()
        self.target.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.revoked_reason, "platform_security")
        self.assertEqual(self.target.token_version, original_version + 1)

    def test_emergency_access_requires_support_role_and_eight_hour_maximum(self):
        self.authenticate(self.maker)
        base = {
            "idempotency_key": "emergency-access-1",
            "reason": "Emergency production investigation under incident command",
            "ticket_reference": "INC-9001",
            "action": "grant",
            "user_id": self.target.id,
            "role_code": "support-operator",
            "emergency_access": True,
        }
        missing_expiry = self.client.post("/api/platform/operators/role-change-requests/", base, format="json")
        excessive = self.client.post("/api/platform/operators/role-change-requests/", {
            **base, "idempotency_key": "emergency-access-2",
            "expires_at": (timezone.now() + timedelta(hours=9)).isoformat(),
        }, format="json")
        valid = self.client.post("/api/platform/operators/role-change-requests/", {
            **base, "idempotency_key": "emergency-access-3",
            "expires_at": (timezone.now() + timedelta(hours=4)).isoformat(),
        }, format="json")

        self.assertEqual(missing_expiry.status_code, 400)
        self.assertEqual(excessive.status_code, 400)
        self.assertEqual(valid.status_code, 201)
        self.assertEqual(valid.data["operation"]["risk"], "critical")
        self.assertEqual(valid.data["operation"]["approvals_required"], 2)
