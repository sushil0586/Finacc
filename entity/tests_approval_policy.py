from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityApprovalPolicy, EntityOrgUnit, SubEntity
from subscriptions.services import SubscriptionService


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class EntityApprovalPolicyApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="policy-owner@example.com",
            username="policy-owner@example.com",
            password="secret123",
            email_verified=True,
        )
        self.other_user = User.objects.create_user(
            email="policy-other@example.com",
            username="policy-other@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Policy Entity", createdby=self.owner)
        SubscriptionService.register_entity_creation(entity=self.entity, owner=self.owner)
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Pune Branch",
            branch_type=SubEntity.BranchType.BRANCH,
        )
        self.department = EntityOrgUnit.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            unit_type=EntityOrgUnit.UnitType.DEPARTMENT,
            code="OPS-PUN",
            name="Operations Pune",
            createdby=self.owner,
        )
        EntityApprovalPolicy.objects.create(
            entity=self.entity,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
            code="PAY-RUN-BASE",
            name="Payroll Run Entity Policy",
            approval_mode=EntityApprovalPolicy.ApprovalMode.PERMISSION_BASED,
            approver_permissions=["payroll.run.approve"],
            createdby=self.owner,
        )
        EntityApprovalPolicy.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
            code="PAY-RUN-PUN",
            name="Payroll Run Pune Policy",
            approval_mode=EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN,
            manager_levels=2,
            createdby=self.owner,
        )
        EntityApprovalPolicy.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            org_unit=self.department,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
            code="PAY-RUN-PUN-OPS",
            name="Payroll Run Pune Ops Policy",
            approval_mode=EntityApprovalPolicy.ApprovalMode.MIXED,
            manager_levels=1,
            approver_roles=["payroll_reviewer"],
            createdby=self.owner,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_resolved_list_returns_entity_subentity_and_org_unit_policies(self):
        response = self.client.get(
            f"/api/entity/approval-policies/?entity={self.entity.id}&subentity={self.subentity.id}&org_unit={self.department.id}&policy_key=payroll_run&resolution_mode=resolved"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["code"] for row in response.data],
            ["PAY-RUN-PUN-OPS", "PAY-RUN-PUN", "PAY-RUN-BASE"],
        )

    def test_create_policy_persists_scoped_payload(self):
        response = self.client.post(
            "/api/entity/approval-policies/",
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "policy_key": "employment_change",
                "code": "EMP-CHG-PUN",
                "name": "Employment Change Pune",
                "approval_mode": "fixed_users",
                "min_approvers": 2,
                "approver_roles": ["hr_manager"],
                "approver_permissions": ["employee.change.approve"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["code"], "EMP-CHG-PUN")
        self.assertEqual(response.data["subentity_name"], "Pune Branch")
        self.assertTrue(
            EntityApprovalPolicy.objects.filter(
                entity=self.entity,
                code="EMP-CHG-PUN",
                policy_key=EntityApprovalPolicy.PolicyKey.EMPLOYMENT_CHANGE,
            ).exists()
        )

    def test_non_member_cannot_access_approval_policies(self):
        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)

        response = other_client.get(f"/api/entity/approval-policies/?entity={self.entity.id}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "tenant_membership_required")

    def test_create_policy_rejects_oversized_fields(self):
        response = self.client.post(
            "/api/entity/approval-policies/",
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "policy_key": "employment_change",
                "code": "C" * 51,
                "name": "N" * 151,
                "approval_mode": "fixed_users",
                "min_approvers": 2,
                "approver_roles": ["hr_manager"],
                "approver_permissions": ["employee.change.approve"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)
