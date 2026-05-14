from __future__ import annotations

from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, GstRegistrationType
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class PayablesSettingsAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"payables-settings-{suffix}",
            email=f"payables-settings-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Settings Entity",
            legalname="Settings Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        role = Role.objects.create(
            entity=self.entity,
            name="Payables Settings Viewer",
            code=f"payables_settings_viewer_{suffix}",
            role_level=Role.LEVEL_ENTITY,
            is_system_role=False,
            is_assignable=True,
            priority=5,
            createdby=self.user,
        )
        for code in ("reports.payables.view", "reports.payables.settings.view"):
            permission, _ = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": code.replace(".", " ").title(),
                    "module": "reports",
                    "resource": "payables",
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

    def test_payables_settings_get_returns_defaults_and_payload(self):
        response = self.client.get(reverse("reports_api:payables-settings"), {"entity": self.entity.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "payables_settings")
        self.assertIn("global_defaults", payload["payload"])
        self.assertIn("display_preferences", payload["payload"])
        self.assertIn("filter_defaults", payload["payload"])
        self.assertIn("vendor_outstanding", payload["payload"]["report_overrides"])

    def test_payables_settings_patch_persists_normalized_values(self):
        response = self.client.patch(
            reverse("reports_api:payables-settings"),
            {
                "entity": self.entity.id,
                "payload": {
                    "global_defaults": {
                        "default_aging_basis": "bill_date",
                        "default_page_size": 9999,
                    },
                    "display_preferences": {
                        "amount_unit": "lakh",
                        "decimal_places": 9,
                        "date_format": "dd-mm-yyyy",
                    },
                    "thresholds": {
                        "overdue_days_warning": -5,
                    },
                    "export_defaults": {
                        "default_format": "csv",
                    },
                    "report_overrides": {
                        "vendor_outstanding": {
                            "columns": ["vendor_name", "bill_number", "outstanding", "vendor_name", ""],
                        }
                    },
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["payload"]
        self.assertEqual(payload["global_defaults"]["default_aging_basis"], "bill_date")
        self.assertEqual(payload["global_defaults"]["default_page_size"], 500)
        self.assertEqual(payload["display_preferences"]["amount_unit"], "lakh")
        self.assertEqual(payload["display_preferences"]["decimal_places"], 6)
        self.assertEqual(payload["thresholds"]["overdue_days_warning"], 0)
        self.assertEqual(payload["export_defaults"]["default_format"], "csv")
        self.assertEqual(
            payload["report_overrides"]["vendor_outstanding"]["columns"],
            ["vendor_name", "bill_number", "outstanding", "drilldown"],
        )

    def test_payables_settings_patch_normalizes_invalid_display_preferences(self):
        response = self.client.patch(
            reverse("reports_api:payables-settings"),
            {
                "entity": self.entity.id,
                "payload": {
                    "display_preferences": {
                        "amount_unit": "bad-unit",
                        "decimal_places": -2,
                        "rounding_mode": "bad",
                        "negative_number_style": "bad",
                        "date_format": "bad",
                    },
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        display = response.json()["payload"]["display_preferences"]
        self.assertEqual(display["amount_unit"], "actual")
        self.assertEqual(display["decimal_places"], 0)
        self.assertEqual(display["rounding_mode"], "half_up")
        self.assertEqual(display["negative_number_style"], "minus")
        self.assertEqual(display["date_format"], "dd-mm-yyyy")

    def test_payables_settings_requires_permission(self):
        other_suffix = uuid4().hex[:8]
        user = User.objects.create_user(
            username=f"payables-settings-denied-{other_suffix}",
            email=f"payables-settings-denied-{other_suffix}@example.com",
            password="pass123",
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(reverse("reports_api:payables-settings"), {"entity": self.entity.id})
        self.assertEqual(response.status_code, 403)

    def test_payables_settings_patch_restores_mandatory_columns_for_all_reports(self):
        response = self.client.patch(
            reverse("reports_api:payables-settings"),
            {
                "entity": self.entity.id,
                "payload": {
                    "report_overrides": {
                        "vendor_outstanding": {"columns": ["vendor_code"]},
                        "ap_aging": {"columns": ["bucket_1_30"]},
                        "vendor_ledger_statement": {"columns": ["document_number"]},
                        "upcoming_payments_calendar": {"columns": ["due_date"]},
                    }
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        overrides = response.json()["payload"]["report_overrides"]

        self.assertIn("vendor_name", overrides["vendor_outstanding"]["columns"])
        self.assertIn("outstanding", overrides["vendor_outstanding"]["columns"])
        self.assertIn("drilldown", overrides["vendor_outstanding"]["columns"])

        self.assertIn("vendor_name", overrides["ap_aging"]["columns"])
        self.assertIn("total_balance", overrides["ap_aging"]["columns"])
        self.assertIn("drilldown", overrides["ap_aging"]["columns"])

        self.assertIn("transaction_date", overrides["vendor_ledger_statement"]["columns"])
        self.assertIn("running_balance", overrides["vendor_ledger_statement"]["columns"])
        self.assertIn("drilldown", overrides["vendor_ledger_statement"]["columns"])

        self.assertIn("vendor_name", overrides["upcoming_payments_calendar"]["columns"])
        self.assertIn("balance", overrides["upcoming_payments_calendar"]["columns"])
        self.assertIn("drilldown", overrides["upcoming_payments_calendar"]["columns"])
