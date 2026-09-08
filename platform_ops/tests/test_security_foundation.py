from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from Authentication.models import User
from auditlogger.middleware import AuditMiddleware
from auditlogger.models import AuditLog
from subscriptions.models import CustomerAccount, UserEntityAccess

from platform_ops.models import PlatformAuditEvent, PlatformPermission, PlatformRole, PlatformUserRole
from platform_ops.permissions import HasPlatformPermissions, PlatformMutationsEnabled
from platform_ops.services import PlatformAccessService, PlatformAuditService


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=False)
class PlatformSecurityFoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="platform.operator",
            email="platform.operator@example.com",
            password="StrongPass123!",
        )
        self.permission = PlatformPermission.objects.create(
            code="platform.test.view",
            name="Test platform access",
        )
        self.role = PlatformRole.objects.create(code="phase1-test-viewer", name="Phase 1 Test Viewer")
        self.role.permissions.add(self.permission)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def assign_role(self, **overrides):
        values = {
            "user": self.user,
            "role": self.role,
            "granted_by": self.user,
            "reason": "Platform operations assignment",
        }
        values.update(overrides)
        return PlatformUserRole.objects.create(**values)

    def test_tenant_owner_membership_does_not_grant_platform_access(self):
        account = CustomerAccount.objects.create(
            name="Tenant only",
            slug="tenant-only-platform-test",
            owner=self.user,
            status=CustomerAccount.Status.ACTIVE,
        )
        UserEntityAccess.objects.create(
            user=self.user,
            customer_account=account,
            role=UserEntityAccess.Role.OWNER,
            granted_by=self.user,
        )

        response = self.client.get("/api/platform/me/")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PlatformAccessService.permission_codes(self.user))

    def test_staff_flag_alone_does_not_grant_platform_access(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.client.get("/api/platform/me/")

        self.assertEqual(response.status_code, 403)

    def test_effective_assignment_returns_capability_snapshot(self):
        self.assign_role()

        response = self.client.get("/api/platform/me/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_platform_operator"])
        self.assertFalse(response.data["mutations_enabled"])
        self.assertEqual(response.data["roles"], [{"code": "phase1-test-viewer", "name": "Phase 1 Test Viewer"}])
        self.assertEqual(response.data["permissions"], ["platform.test.view"])

    def test_expired_future_and_revoked_assignments_are_denied(self):
        now = timezone.now()
        cases = (
            {"expires_at": now - timedelta(seconds=1)},
            {"valid_from": now + timedelta(hours=1)},
            {"is_active": False, "revoked_at": now},
        )
        for index, values in enumerate(cases):
            with self.subTest(index=index):
                PlatformUserRole.objects.all().delete()
                self.assign_role(**values)
                response = self.client.get("/api/platform/me/")
                self.assertEqual(response.status_code, 403)

    @override_settings(PLATFORM_OPS_ENABLED=False)
    def test_feature_flag_denies_assigned_operator(self):
        self.assign_role()
        self.assertEqual(self.client.get("/api/platform/me/").status_code, 403)

    def test_mutation_kill_switch_preserves_reads_and_blocks_writes(self):
        permission = PlatformMutationsEnabled()
        factory = APIRequestFactory()

        self.assertTrue(permission.has_permission(factory.get("/api/platform/example/"), object()))
        self.assertFalse(permission.has_permission(factory.post("/api/platform/example/", {}), object()))

    def test_atomic_permission_check_requires_every_declared_permission(self):
        self.assign_role()
        request = APIRequestFactory().get("/api/platform/example/")
        request.user = self.user
        permission = HasPlatformPermissions()

        allowed_view = type("AllowedView", (), {"required_platform_permissions": ("platform.test.view",)})()
        denied_view = type(
            "DeniedView",
            (),
            {"required_platform_permissions": ("platform.test.view", "platform.security.manage")},
        )()

        self.assertTrue(permission.has_permission(request, allowed_view))
        self.assertFalse(permission.has_permission(request, denied_view))
        self.assertTrue(
            PlatformAuditEvent.objects.filter(
                actor=self.user,
                event_type="platform.permission.denied",
                outcome=PlatformAuditEvent.Outcome.DENIED,
            ).exists()
        )

    def test_audit_service_recursively_redacts_sensitive_fields(self):
        event = PlatformAuditService.log(
            actor=self.user,
            event_type="platform.security.test",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            details={
                "password": "do-not-store",
                "nested": {"access_token": "do-not-store", "allowed": "visible"},
                "rows": [{"bank_account_number": "123456789", "label": "Primary"}],
            },
        )

        self.assertEqual(event.details["password"], "[REDACTED]")
        self.assertEqual(event.details["nested"]["access_token"], "[REDACTED]")
        self.assertEqual(event.details["nested"]["allowed"], "visible")
        self.assertEqual(event.details["rows"][0]["bank_account_number"], "[REDACTED]")

    def test_audit_event_cannot_be_updated_or_deleted(self):
        event = PlatformAuditService.log(
            actor=self.user,
            event_type="platform.security.test",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
        )
        event.details = {"changed": True}

        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            PlatformAuditEvent.objects.filter(pk=event.pk).update(details={"changed": True})
        with self.assertRaises(ValidationError):
            PlatformAuditEvent.objects.filter(pk=event.pk).delete()

    def test_generic_audit_middleware_redacts_platform_request_body(self):
        request = RequestFactory().post(
            "/api/platform/example/",
            data={"password": "do-not-store", "name": "Example"},
            content_type="application/json",
        )
        request.user = self.user
        middleware = AuditMiddleware(lambda value: value)

        middleware.process_view(request, lambda value: value, (), {})

        audit = AuditLog.objects.get(path="/api/platform/example/")
        self.assertEqual(audit.new_data, {"redacted": True})
        self.assertNotIn("do-not-store", str(audit.new_data))
