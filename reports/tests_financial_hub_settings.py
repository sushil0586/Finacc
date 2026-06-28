from __future__ import annotations

from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, GstRegistrationType
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class FinancialHubSettingsAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"financial-hub-settings-{suffix}",
            email=f"financial-hub-settings-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Hub Settings Entity",
            legalname="Hub Settings Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        role = Role.objects.create(
            entity=self.entity,
            name="Financial Hub Settings Viewer",
            code=f"financial_hub_settings_viewer_{suffix}",
            role_level=Role.LEVEL_ENTITY,
            is_system_role=False,
            is_assignable=True,
            priority=5,
            createdby=self.user,
        )
        permission, _ = Permission.objects.get_or_create(
            code="reports.gst.view",
            defaults={
                "name": "Reports Gst View",
                "module": "reports",
                "resource": "financial_hub_settings",
                "action": "view",
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=["isactive"])
        RolePermission.objects.get_or_create(
            role=role,
            permission=permission,
            defaults={"effect": RolePermission.EFFECT_ALLOW},
        )
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=role,
            assigned_by=self.user,
            is_primary=True,
        )
        self.url = reverse("reports_api:financial-hub-settings")

    def test_get_returns_defaults_and_effective_payload(self):
        response = self.client.get(self.url, {"entity": self.entity.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "financial_hub_settings")
        self.assertIn("defaults", payload)
        self.assertIn("payload", payload)
        self.assertIn("effective", payload)
        expected_reports = {
            "trial_balance",
            "ledger_book",
            "ledger_summary",
            "profit_loss",
            "balance_sheet",
            "trading_account",
            "daybook",
            "cashbook",
        }
        self.assertTrue(expected_reports.issubset(payload["effective"].keys()))
        self.assertTrue(expected_reports.issubset(payload["payload"]["report_overrides"].keys()))
        self.assertTrue(payload["effective"]["trial_balance"]["columns"]["name"]["mandatory"])
        self.assertTrue(payload["effective"]["ledger_book"]["columns"]["date"]["mandatory"])
        self.assertTrue(payload["effective"]["daybook"]["columns"]["transaction_date"]["mandatory"])
        self.assertTrue(payload["effective"]["cashbook"]["columns"]["date"]["mandatory"])

    def test_patch_persists_normalized_report_settings(self):
        response = self.client.patch(
            self.url,
            {
                "entity": self.entity.id,
                "payload": {
                    "general_display": {
                        "amount_display_unit": "lakhs",
                        "decimal_places": 9,
                        "negative_number_style": "brackets",
                        "zero_value_display": "dash",
                    },
                    "export_layout": {
                        "default_export_format": "excel",
                        "show_pdf_export": False,
                        "show_excel_export": True,
                    },
                    "report_defaults": {
                        "default_group_by": "accounttype",
                        "default_view_type": "detailed",
                        "default_sort_order": "desc",
                    },
                    "report_overrides": {
                        "trial_balance": {
                            "enabled": True,
                            "columns": {
                                "name": {"mandatory": True},
                                "opening": {"mandatory": True},
                            },
                        }
                    },
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["payload"]["general_display"]["amount_display_unit"], "lakhs")
        self.assertEqual(payload["payload"]["general_display"]["decimal_places"], 4)
        self.assertEqual(payload["payload"]["general_display"]["negative_number_style"], "brackets")
        self.assertEqual(payload["payload"]["general_display"]["zero_value_display"], "dash")
        self.assertEqual(payload["payload"]["export_layout"]["default_export_format"], "excel")
        self.assertFalse(payload["payload"]["export_layout"]["show_pdf_export"])
        self.assertTrue(payload["payload"]["export_layout"]["show_excel_export"])
        self.assertEqual(payload["payload"]["report_defaults"]["default_group_by"], "accounttype")
        self.assertEqual(payload["payload"]["report_defaults"]["default_view_type"], "detailed")
        self.assertEqual(payload["payload"]["report_defaults"]["default_sort_order"], "desc")
        self.assertTrue(payload["payload"]["report_overrides"]["trial_balance"]["enabled"])
        self.assertTrue(payload["effective"]["trial_balance"]["columns"]["name"]["mandatory"])
        self.assertTrue(payload["effective"]["trial_balance"]["columns"]["opening"]["mandatory"])
        self.assertIn("ledger_summary", payload["effective"])
        self.assertIn("profit_loss", payload["effective"])
        self.assertIn("daybook", payload["effective"])
        self.assertIn("cashbook", payload["effective"])

    def test_patch_requires_entity_access(self):
        other = User.objects.create_user(
            username=f"financial-hub-settings-denied-{uuid4().hex[:8]}",
            email=f"financial-hub-settings-denied-{uuid4().hex[:8]}@example.com",
            password="pass123",
        )
        client = APIClient()
        client.force_authenticate(user=other)
        response = client.get(self.url, {"entity": self.entity.id})
        self.assertEqual(response.status_code, 403)
