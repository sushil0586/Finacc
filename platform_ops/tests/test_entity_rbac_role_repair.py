from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity
from platform_ops.models import PlatformPermission, PlatformRole, PlatformUserRole
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment
from rbac.seeding import RBACSeedService
from subscriptions.models import CustomerAccount


@override_settings(PLATFORM_OPS_ENABLED=True, PLATFORM_OPS_MUTATIONS_ENABLED=True)
class PlatformEntityRbacRoleRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.maker = User.objects.create_user(username="rbac-maker", email="rbac-maker@example.com", password="Pass123!")
        cls.checker = User.objects.create_user(username="rbac-checker", email="rbac-checker@example.com", password="Pass123!")
        cls.executor = User.objects.create_user(username="rbac-executor", email="rbac-executor@example.com", password="Pass123!")
        cls.owner = User.objects.create_user(username="rbac-owner", email="rbac-owner@example.com", password="Pass123!")
        for user, code, permissions in (
            (cls.maker, "rbac-repair-maker", ("platform.repair.preview", "platform.repair.execute")),
            (cls.checker, "rbac-repair-checker", ("platform.operation.approve",)),
            (cls.executor, "rbac-repair-executor", ("platform.operation.execute",)),
        ):
            role = PlatformRole.objects.create(code=code, name=code)
            role.permissions.add(*PlatformPermission.objects.filter(code__in=permissions))
            PlatformUserRole.objects.create(user=user, role=role, granted_by=cls.owner, reason="RBAC repair tests")
        cls.customer = CustomerAccount.objects.create(name="RBAC Customer", slug="rbac-customer", owner=cls.owner)
        cls.entity = Entity.objects.create(entityname="RBAC Target", customer_account=cls.customer, createdby=cls.owner)
        for spec in RBACSeedService.DEFAULT_ROLE_SHELLS:
            if spec["code"] != "report_viewer":
                Role.objects.create(
                    entity=cls.entity, name=spec["name"], code=spec["code"], priority=spec["priority"],
                    createdby=cls.owner, isactive=True,
                )
        cls.custom_role = Role.objects.create(
            entity=cls.entity, name="Custom Auditor", code="custom_auditor", createdby=cls.owner, isactive=True,
        )
        cls.custom_permission = Permission.objects.create(
            code="custom.audit.special", name="Custom Audit", module="custom", resource="audit", action="special",
        )
        RolePermission.objects.create(role=cls.custom_role, permission=cls.custom_permission, effect=RolePermission.EFFECT_DENY)
        cls.custom_assignment = UserRoleAssignment.objects.create(
            user=cls.owner, entity=cls.entity, role=cls.custom_role, assigned_by=cls.owner,
        )

    def setUp(self):
        self.client = APIClient()
        self.entity.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def request_repair(self, key="rbac-role-repair-1"):
        self.auth(self.maker)
        return self.client.post(f"/api/platform/entities/{self.entity.id}/rbac-role-repair-requests/", {
            "idempotency_key": key, "reason": "Restore missing baseline role after access audit",
            "ticket_reference": "OPS-RBAC-1", "expected_target_version": self.entity.updated_at.isoformat(),
        }, format="json")

    def approve(self, operation_id):
        self.auth(self.checker)
        return self.client.post(f"/api/platform/operations/{operation_id}/decision/", {
            "decision": "approved", "comment": "Reviewed exact role and permission snapshot",
        }, format="json")

    def test_preview_reports_only_missing_baseline_role_without_writing(self):
        self.auth(self.maker)
        response = self.client.get(f"/api/platform/entities/{self.entity.id}/rbac-role-repair-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        self.assertEqual(response.data["missing_role_count"], 1)
        self.assertEqual(response.data["missing_roles"][0]["code"], "report_viewer")
        self.assertGreater(response.data["missing_roles"][0]["permission_count"], 0)

    def test_approved_repair_preserves_custom_roles_and_assignments(self):
        requested = self.request_repair()
        operation_id = requested.data["operation"]["id"]
        approved_permission_ids = set(requested.data["operation"]["validation"]["preview"]["missing_roles"][0]["permission_ids"])
        self.approve(operation_id)
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        role = Role.objects.get(entity=self.entity, code="report_viewer")
        self.assertEqual(set(role.role_permissions.values_list("permission_id", flat=True)), approved_permission_ids)
        self.assertTrue(Role.objects.filter(pk=self.custom_role.id).exists())
        self.assertTrue(RolePermission.objects.filter(role=self.custom_role, permission=self.custom_permission, effect="deny").exists())
        self.assertTrue(UserRoleAssignment.objects.filter(pk=self.custom_assignment.id).exists())
        self.assertFalse(UserRoleAssignment.objects.filter(role=role).exists())
        replay = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertTrue(replay.data["replayed"])

    def test_inactive_baseline_role_blocks_repair(self):
        Role.objects.create(entity=self.entity, name="Report Viewer", code="report_viewer", isactive=False)
        response = self.request_repair("rbac-role-repair-blocked")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["preview"]["blockers"][0]["code"], "inactive_role_conflict")

    def test_stale_approval_does_not_create_role(self):
        requested = self.request_repair("rbac-role-repair-stale")
        operation_id = requested.data["operation"]["id"]
        self.approve(operation_id)
        Entity.objects.filter(pk=self.entity.id).update(updated_at=timezone.now())
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "stale_approval")
        self.assertFalse(Role.objects.filter(entity=self.entity, code="report_viewer").exists())

    def test_deactivated_approved_permission_fails_atomically(self):
        requested = self.request_repair("rbac-role-repair-permission-change")
        operation_id = requested.data["operation"]["id"]
        permission_id = requested.data["operation"]["validation"]["preview"]["missing_roles"][0]["permission_ids"][0]
        self.approve(operation_id)
        Permission.objects.filter(pk=permission_id).update(isactive=False)
        self.auth(self.executor)
        response = self.client.post(f"/api/platform/operations/{operation_id}/execute/", {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["operation"]["failure"]["code"], "approved_permissions_changed")
        self.assertFalse(Role.objects.filter(entity=self.entity, code="report_viewer").exists())
