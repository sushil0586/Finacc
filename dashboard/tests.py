from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=False)
class DashboardHomeMetaAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"dashboard-user-{suffix}",
            email=f"dashboard-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Dashboard Entity",
            legalname="Dashboard Entity Pvt Ltd",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.fin_year = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
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
            name="Dashboard Viewer",
            code="dashboard_viewer",
            role_level=Role.LEVEL_ENTITY,
            is_assignable=True,
            priority=10,
            createdby=self.user,
        )
        self.page_permission, _ = Permission.objects.get_or_create(
            code="dashboard.home.view",
            defaults={
                "name": "View Dashboard Home",
                "module": "dashboard",
                "resource": "dashboard",
                "action": "view",
            },
        )
        self.payables_permission, _ = Permission.objects.get_or_create(
            code="reports.vendoroutstanding.view",
            defaults={
                "name": "View Vendor Outstanding",
                "module": "reports",
                "resource": "payables",
                "action": "view",
            },
        )
        self.ap_aging_permission, _ = Permission.objects.get_or_create(
            code="reports.accountspayableaging.view",
            defaults={
                "name": "View AP Aging",
                "module": "reports",
                "resource": "payables",
                "action": "view",
            },
        )
        for permission in (self.page_permission, self.payables_permission, self.ap_aging_permission):
            RolePermission.objects.create(role=self.role, permission=permission)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity, role=self.role, is_primary=True)

    def test_dashboard_meta_returns_scope_filters_and_phase_zero_shell_widgets(self):
        response = self.client.get(
            "/api/dashboard/home/meta/",
            {"entity": self.entity.id, "entityfinid": self.fin_year.id, "subentity": self.subentity.id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["dashboard_code"], "home")
        self.assertEqual(payload["dashboard_name"], "Command Center")
        self.assertEqual(payload["dashboard_type"], "workspace")
        self.assertEqual(payload["phase"], 0)
        self.assertTrue(payload["permissions"]["page"]["granted"])
        self.assertEqual(payload["scope"]["entity"]["id"], self.entity.id)
        self.assertEqual(payload["scope"]["financial_year"]["id"], self.fin_year.id)
        self.assertEqual(payload["scope"]["subentity"]["id"], self.subentity.id)
        self.assertIn("entity", [item["code"] for item in payload["filters"]["catalog"]])
        self.assertEqual([item["code"] for item in payload["dashboard_types"]], ["workspace", "analytics"])
        self.assertIn("attention_strip", payload["available_widget_codes"])
        self.assertIn("summary_shell", payload["available_widget_codes"])
        self.assertIn("payables_risk", [item["code"] for item in payload["widget_catalog"]])
        payables_widget = next(item for item in payload["widget_catalog"] if item["code"] == "payables_risk")
        self.assertFalse(payables_widget["available"])
        self.assertEqual(payables_widget["availability_reason"], "planned_for_phase_2")
        self.assertIn("payables_risk", payload["permissions"]["locked_widget_codes"])
        self.assertEqual(payload["layout"]["zone_widget_codes"]["summary_grid"], ["summary_shell"])

    def test_dashboard_meta_defaults_scope_values_when_optional_filters_are_missing(self):
        response = self.client.get("/api/dashboard/home/meta/", {"entity": self.entity.id})

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["default_scope"]["entity"], self.entity.id)
        self.assertEqual(payload["default_scope"]["entityfinid"], self.fin_year.id)
        self.assertEqual(payload["default_scope"]["subentity"], self.subentity.id)
        self.assertEqual(payload["scope"]["financial_year"]["id"], self.fin_year.id)
        self.assertEqual(payload["scope"]["subentity"]["id"], self.subentity.id)

    def test_dashboard_meta_denies_access_without_page_permission(self):
        self.role.role_permissions.filter(permission=self.page_permission).delete()

        response = self.client.get("/api/dashboard/home/meta/", {"entity": self.entity.id})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "You do not have permission to access dashboard.home.view.")
