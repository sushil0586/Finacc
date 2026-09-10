from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from reports.tests_support.compliance_golden_dataset import build_compliance_golden_scope


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class ControlsApiPermissionTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="controls-rbac-user",
            email="controls-rbac@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=[
                "reports.financial_hub.controls_phase_one.view",
                "reports.financial_hub.posting_setup.view",
                "reports.financial_hub.year_end_close.view",
            ],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        golden = build_compliance_golden_scope(user=self.user, entity_name="Controls Entity")
        self.entity = golden.entity
        self.subentity = golden.subentity
        self.entityfin = golden.entityfin
        self.scope_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_phase_one_hub_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-meta"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_posting_setup_preview_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-posting-setup-preview"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_close_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_year_end_close_meta_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-year-end-close-meta"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_policy_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-opening-policy"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_preview_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-opening-preview"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_generate_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.post(reverse("reports_api:controls-phase-one-opening-generate"), self.scope_params, format="json")
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_rollback_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.post(reverse("reports_api:controls-phase-one-opening-rollback"), self.scope_params, format="json")
        self.assertEqual(response.status_code, 403)

    def test_view_only_permissions_deny_every_control_mutation(self):
        mutation_requests = (
            ("patch", "reports_api:controls-phase-one-opening-policy", {"entity": self.entity.id, "opening_mode": "hybrid"}),
            ("post", "reports_api:controls-phase-one-opening-generate", self.scope_params),
            ("post", "reports_api:controls-phase-one-opening-rollback", self.scope_params),
            ("post", "reports_api:controls-posting-setup-apply", self.scope_params),
            ("post", "reports_api:controls-year-end-close-execute", self.scope_params),
            ("post", "reports_api:controls-year-end-close-rollback", self.scope_params),
        )

        for method, route_name, payload in mutation_requests:
            with self.subTest(route=route_name):
                response = getattr(self.client, method)(reverse(route_name), payload, format="json")
                self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.update_opening_policy")
    def test_opening_policy_patch_uses_action_permission_and_updates_policy(self, mock_update):
        mock_update.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "hybrid",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "carry_forward": {},
            "reset": {},
            "grouped_sections": [],
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-opening-policy"),
                {"entity": self.entity.id, "opening_mode": "hybrid"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            updates={"opening_mode": "hybrid"},
            created_by=self.user,
        )

    @patch("reports.api.controls_views.build_phase_one_controls_hub")
    def test_phase_one_hub_exposes_compliance_readiness_actions(self, mock_build_hub):
        mock_build_hub.return_value = {
            "report_code": "phase_one_controls_hub",
            "report_name": "Financial Controls Phase 1",
            "summary_cards": [],
            "sections": [],
            "compliance_readiness": {
                "status": "blocked",
                "status_label": "Blocked",
                "summary_cards": [],
                "actions": [
                    {
                        "label": "Open GST Blockers",
                        "route": "/reports/compliance/gst-exception-dashboard",
                        "params": {
                            "entityfinid": self.entityfin.id,
                            "subentity": self.subentity.id,
                            "tab": 1,
                            "focus": "blockers",
                        },
                    },
                    {
                        "label": "Open TCS Pending Collection",
                        "route": "/tcsstatutory",
                        "params": {
                            "entityfinid": self.entityfin.id,
                            "subentity": self.subentity.id,
                            "workspace_status": "COMPUTED_PENDING_COLLECTION",
                        },
                    },
                ],
            },
        }

        response = self.client.get(reverse("reports_api:controls-phase-one-meta"), self.scope_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("compliance_readiness", payload)
        self.assertIn("actions", payload["compliance_readiness"])
        actions = payload["compliance_readiness"]["actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["route"], "/reports/compliance/gst-exception-dashboard")
        self.assertEqual(actions[0]["params"]["focus"], "blockers")
        self.assertEqual(actions[1]["route"], "/tcsstatutory")
        self.assertEqual(actions[1]["params"]["workspace_status"], "COMPUTED_PENDING_COLLECTION")
