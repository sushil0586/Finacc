from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from cfo.models import CashFlowForecastAdjustment, CfoEvidenceItem
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


CFO_VIEW_PERMISSIONS = (
    "cfo.control_tower.view",
    "cfo.receivables.view",
    "cfo.payables.view",
    "cfo.cash_flow.view",
    "cfo.month_close.view",
    "cfo.budget.view",
    "cfo.risk_queue.view",
    "cfo.management_pack.view",
    "cfo.evidence_center.view",
    "cfo.insights.view",
    "cfo.scenario_planner.view",
)


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=False)
class CfoWritePermissionAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"cfo-viewer-{suffix}",
            email=f"cfo-viewer-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.gst_type = GstRegistrationType.objects.create(Name=f"Regular {suffix}", Description="Regular")
        self.entity = Entity.objects.create(
            entityname=f"CFO Permission Entity {suffix}",
            legalname=f"CFO Permission Entity {suffix} Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.fin_year = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            is_head_office=True,
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
        )
        self.role = Role.objects.create(
            entity=self.entity,
            name="CFO Viewer",
            code=f"cfo_viewer_{suffix}",
            role_level=Role.LEVEL_ENTITY,
            is_assignable=True,
            priority=10,
            createdby=self.user,
        )
        for code in CFO_VIEW_PERMISSIONS:
            RolePermission.objects.create(role=self.role, permission=self._permission(code))
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity, role=self.role, is_primary=True)

        self.adjustment = CashFlowForecastAdjustment.objects.create(
            entity=self.entity,
            entityfinid=self.fin_year,
            subentity=self.subentity,
            scenario=CashFlowForecastAdjustment.Scenario.BASE,
            adjustment_date="2026-09-30",
            direction=CashFlowForecastAdjustment.Direction.INFLOW,
            category="opening",
            description="Seeded adjustment",
            amount="1000.00",
            createdby=self.user,
        )
        self.evidence = CfoEvidenceItem.objects.create(
            entity=self.entity,
            entityfinid=self.fin_year,
            subentity=self.subentity,
            period_start="2026-09-01",
            period_end="2026-09-30",
            evidence_type=CfoEvidenceItem.EvidenceType.OTHER,
            title="Seeded evidence",
            status=CfoEvidenceItem.Status.OPEN,
            createdby=self.user,
        )

    def _permission(self, code: str):
        module, resource, action = code.split(".", 2)
        permission, _ = Permission.objects.get_or_create(
            code=code,
            defaults={
                "name": code,
                "module": module,
                "resource": resource,
                "action": action,
                "description": code,
                "scope_type": Permission.SCOPE_ENTITY,
                "is_system_defined": True,
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=["isactive", "updated_at"])
        return permission

    def _scope_payload(self):
        return {
            "entity": self.entity.id,
            "entityfinid": self.fin_year.id,
            "subentity": self.subentity.id,
        }

    def _period_payload(self):
        return {
            **self._scope_payload(),
            "from_date": "2026-09-01",
            "to_date": "2026-09-30",
        }

    def _assert_forbidden(self, response):
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertIn("permission", str(response.data).lower())

    def test_cash_flow_adjustment_writes_require_adjust_permission(self):
        create_response = self.client.post(
            "/api/cfo/cash-flow/adjustments/",
            {
                **self._scope_payload(),
                "scenario": "base",
                "adjustment_date": "2026-10-02",
                "direction": "inflow",
                "category": "manual",
                "description": "Unauthorized create",
                "amount": "250.00",
            },
            format="json",
        )
        self._assert_forbidden(create_response)

        patch_response = self.client.patch(
            f"/api/cfo/cash-flow/adjustments/{self.adjustment.id}/",
            {
                **self._scope_payload(),
                "scenario": "base",
                "adjustment_date": "2026-10-03",
                "direction": "outflow",
                "category": "manual",
                "description": "Unauthorized update",
                "amount": "300.00",
            },
            format="json",
        )
        self._assert_forbidden(patch_response)

        delete_response = self.client.delete(f"/api/cfo/cash-flow/adjustments/{self.adjustment.id}/")
        self._assert_forbidden(delete_response)

        self.adjustment.refresh_from_db()
        self.assertTrue(self.adjustment.isactive)
        self.assertEqual(str(self.adjustment.amount), "1000.00")
        self.assertFalse(CashFlowForecastAdjustment.objects.filter(description="Unauthorized create").exists())

    def test_month_close_actions_require_manage_or_lock_permission(self):
        actions = (
            "/api/cfo/month-close/tasks/bank_reconciliation/mark-complete/",
            "/api/cfo/month-close/tasks/bank_reconciliation/reopen/",
            "/api/cfo/month-close/lock-period/",
            "/api/cfo/month-close/unlock-period/",
        )
        payload = {**self._period_payload(), "reason": "Direct API attempt", "notes": "Direct API attempt"}

        for url in actions:
            with self.subTest(url=url):
                self._assert_forbidden(self.client.post(url, payload, format="json"))

    def test_budget_writes_require_manage_or_review_permission(self):
        upsert_response = self.client.post(
            "/api/cfo/budget-vs-actual/budgets/",
            {
                **self._period_payload(),
                "category": "revenue",
                "budget_amount": "50000.00",
                "notes": "Unauthorized budget",
            },
            format="json",
        )
        self._assert_forbidden(upsert_response)

        review_response = self.client.post(
            "/api/cfo/budget-vs-actual/variances/revenue/review/",
            {
                **self._period_payload(),
                "status": "explained",
                "explanation": "Unauthorized review",
                "action_owner": "Finance",
            },
            format="json",
        )
        self._assert_forbidden(review_response)

    def test_risk_review_requires_review_permission(self):
        response = self.client.post(
            "/api/cfo/risk-queue/reviews/",
            {
                **self._scope_payload(),
                "item_key": "phase12g-risk",
                "risk_type": "cash",
                "source_type": "test",
                "source_id": "RISK-1",
                "status": "acknowledged",
                "note": "Unauthorized risk acknowledgement",
            },
            format="json",
        )
        self._assert_forbidden(response)

    def test_management_pack_snapshot_requires_publish_permission(self):
        response = self.client.post(
            "/api/cfo/management-pack/snapshots/",
            {
                **self._period_payload(),
                "title": "Unauthorized CFO pack draft",
                "status": "draft",
                "notes": "This draft should not be created directly.",
            },
            format="json",
        )
        self._assert_forbidden(response)

    def test_evidence_writes_require_manage_permission(self):
        create_response = self.client.post(
            "/api/cfo/evidence-center/items/",
            {
                **self._period_payload(),
                "evidence_type": "other",
                "title": "Unauthorized evidence",
                "description": "Direct API attempt",
                "status": "open",
            },
            format="json",
        )
        self._assert_forbidden(create_response)

        review_response = self.client.post(
            f"/api/cfo/evidence-center/items/{self.evidence.id}/review/",
            {
                **self._scope_payload(),
                "status": "reviewed",
                "description": "Unauthorized review",
            },
            format="json",
        )
        self._assert_forbidden(review_response)

        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.status, CfoEvidenceItem.Status.OPEN)
        self.assertFalse(CfoEvidenceItem.objects.filter(title="Unauthorized evidence").exists())

    def test_insight_review_requires_review_permission(self):
        response = self.client.post(
            "/api/cfo/insights/reviews/",
            {
                **self._period_payload(),
                "signal_key": "phase12g-insight",
                "signal_type": "margin",
                "severity": "medium",
                "status": "acknowledged",
                "note": "Unauthorized insight acknowledgement",
            },
            format="json",
        )
        self._assert_forbidden(response)

    def test_scenario_plan_requires_manage_permission(self):
        response = self.client.post(
            "/api/cfo/scenario-planner/plans/",
            {
                **self._period_payload(),
                "title": "Unauthorized scenario",
                "status": "approved",
                "notes": "Direct API attempt",
                "revenue_change_percent": "5.00",
                "purchase_change_percent": "2.00",
                "collection_delay_days": 3,
                "vendor_delay_days": 2,
                "expense_increase_amount": "1000.00",
                "one_time_cash_inflow": "500.00",
                "one_time_cash_outflow": "100.00",
            },
            format="json",
        )
        self._assert_forbidden(response)
