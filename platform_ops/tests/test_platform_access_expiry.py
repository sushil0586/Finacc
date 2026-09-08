import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from Authentication.models import User
from Authentication.services import AuthTokenService
from platform_ops.models import PlatformAuditEvent, PlatformRole, PlatformUserRole
from platform_ops.services import PlatformAccessService


@override_settings(PLATFORM_OPS_ENABLED=True)
class PlatformAccessExpiryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.granter = User.objects.create_user(username="expiry-owner", email="expiry-owner@example.com", password="Pass123!")
        cls.operator = User.objects.create_user(username="expiring-user", email="expiring-user@example.com", password="Pass123!")
        cls.role = PlatformRole.objects.get(code="support-operator")

    def assignment(self, *, expired=True, role=None):
        return PlatformUserRole.objects.create(
            user=self.operator, role=role or self.role, granted_by=self.granter,
            reason="Time-bound platform access",
            expires_at=timezone.now() - timedelta(minutes=1) if expired else timezone.now() + timedelta(hours=2),
        )

    def test_final_expired_assignment_revokes_sessions_and_is_idempotent(self):
        assignment = self.assignment()
        session, _ = AuthTokenService.create_session(self.operator)
        original_version = self.operator.token_version

        first = PlatformAccessService.expire_assignments()
        second = PlatformAccessService.expire_assignments()

        assignment.refresh_from_db(); session.refresh_from_db(); self.operator.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertEqual(first["expired"], 1)
        self.assertEqual(first["sessions_revoked"], 1)
        self.assertEqual(second["expired"], 0)
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(self.operator.token_version, original_version + 1)
        self.assertEqual(PlatformAuditEvent.objects.filter(event_type="platform.security.assignment.expired").count(), 1)

    def test_remaining_effective_role_preserves_sessions(self):
        self.assignment()
        second_role = PlatformRole.objects.get(code="platform-viewer")
        self.assignment(expired=False, role=second_role)
        session, _ = AuthTokenService.create_session(self.operator)

        result = PlatformAccessService.expire_assignments()

        session.refresh_from_db()
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["sessions_revoked"], 0)
        self.assertIsNone(session.revoked_at)

    def test_command_and_deployment_timer_contract(self):
        assignment = self.assignment()
        output = StringIO()
        call_command("expire_platform_access", "--dry-run", "--json", stdout=output)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["matched"], 1)
        self.assertEqual(payload["expired"], 0)
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)

        root = Path(__file__).resolve().parents[2]
        service = (root / "deploy/ec2/finacc-platform-access-expiry.service").read_text()
        timer = (root / "deploy/ec2/finacc-platform-access-expiry.timer").read_text()
        refresh = (root / "deploy/ec2/staging_refresh_backend.sh").read_text()
        self.assertIn("expire_platform_access --json", service)
        self.assertIn("OnCalendar=*:0/15", timer)
        self.assertIn("enable --now finacc-platform-access-expiry.timer", refresh)
